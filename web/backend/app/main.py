"""FastAPI backend for the prompt -> LEGO-instructions pipeline."""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

# Explicitly anchored to this package's own directory rather than the bare
# load_dotenv() default, which resolves .env relative to the *current working
# directory* -- so running uvicorn from the repo root (or anywhere but
# web/backend) silently loaded no config at all and every job failed with
# "No image generation provider configured".
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import uuid

import sentry_sdk
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import auth, billing, content_filter, rate_limit, waitlist
from .storage import R2Storage
from .jobs import (
    JOB_TIMEOUT_S,
    JOBS_DIR,
    QUEUE,
    REDIS_CONN,
    STORAGE,
    Job,
    JobStatus,
    _job_dir,
    _write_job_meta_dict,
    delete_jobs_for_user,
    has_gallery_access,
    is_job_published,
    list_gallery_jobs,
    list_job_ids_for_user,
    load_job_meta,
    process_job,
    record_gallery_purchase,
    save_job_meta,
    set_job_published,
)

logger = logging.getLogger(__name__)

# No-op when SENTRY_DSN is unset -- sentry_sdk.init(dsn=None) disables
# capture entirely rather than erroring, so no separate guard is needed
# beyond not calling it with a bad value.
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1)

auth.init_db()

# Empty by default -- every signed-up user can generate and pay, the
# normal behavior. Set to a comma-separated list of emails
# (case-insensitive) to temporarily restrict every cost-incurring or
# money-moving action -- generating, subscribing, buying a top-up, or
# unlocking instructions -- to just those accounts, e.g. while doing
# further testing/maintenance and real strangers shouldn't be able to
# either run up API costs or complete real charges. Signup/login stay
# open either way -- only these specific endpoints are gated -- so
# lifting this later is just clearing the env var in Railway, no code
# change or redeploy needed. Does NOT gate the Stripe webhook itself: a
# payment that already completed must still be honored regardless, this
# only stops new purchase attempts from starting.
GENERATION_ALLOWLIST = {
    e.strip().lower() for e in os.environ.get("GENERATION_ALLOWLIST", "").split(",") if e.strip()
}

# Off by default -- a plain code constant, not a Railway env var, so this
# can be flipped with a normal commit + push (Railway auto-redeploys on
# push) rather than needing dashboard access. Blocks EVERYONE, no
# exceptions, including the founder's own account -- unlike
# GENERATION_ALLOWLIST above (a controlled-beta allowlist), the whole
# point here is stopping real API spend outright while the budget is low,
# and testing still spends it. Meant to be flipped together with the
# frontend's own MAINTENANCE_MODE (lib/api.ts) in the same commit -- that
# half swaps the homepage UI to a waitlist form, this half is what
# actually stops the spend, and either can be toggled independently if
# only one effect is wanted.
MAINTENANCE_MODE = False


def _check_generation_allowlist(user: "auth.User") -> None:
    """Raises 503 if MAINTENANCE_MODE is on (see its own docstring above --
    blocks everyone, no exceptions), or 403 if GENERATION_ALLOWLIST is set
    and this user isn't on it -- shared by every endpoint that either costs
    real API money (generate) or moves real money (checkout/top-up/unlock).
    See GENERATION_ALLOWLIST's own docstring above for why webhook handling
    itself is deliberately excluded from this check."""
    if MAINTENANCE_MODE:
        raise HTTPException(503, "Generation is temporarily paused while we restock our AI budget -- check back soon!")
    if GENERATION_ALLOWLIST and user.email.lower() not in GENERATION_ALLOWLIST:
        raise HTTPException(
            403, "This action is temporarily restricted while we finish setting up payments -- check back soon!"
        )

# Off by default: public interactive docs (/docs, /redoc, /openapi.json)
# hand anyone your complete route/parameter surface for free reconnaissance,
# and nothing in this app actually needs them exposed publicly (the
# frontend is the real client, not third-party API consumers). Opt in with
# ENABLE_API_DOCS=true for local dev or ad-hoc debugging against a
# deployed environment -- same unset-is-the-safe-default convention as
# every other flag in .env.example.
_DOCS_ENABLED = os.environ.get("ENABLE_API_DOCS", "false").lower() == "true"
app = FastAPI(
    title="Prompt-to-LEGO Backend",
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)
app.include_router(auth.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Baseline headers with no real downside for a JSON API -- this app
    serves no HTML of its own (the frontend is a separate Next.js
    deployment), so a strict CSP here can't break anything self-hosted.
    Skipped for /docs, /redoc, /openapi.json (only reachable at all when
    ENABLE_API_DOCS=true) since Swagger/ReDoc's UI loads CDN JS/CSS that
    default-src 'none' would otherwise block.

    Also skipped on redirect responses (3xx) -- confirmed as the actual
    cause of the 3D preview silently failing in every browser while
    working fine from curl and from a direct fetch of the redirect
    target: _serve_job_file's 307 to a presigned R2 URL carried this same
    CSP header, and Chrome refuses to auto-follow a cross-origin redirect
    whose response sets a restrictive CSP, even though the redirect
    itself has no body/content for a CSP to meaningfully restrict in the
    first place. Skipping it for every redirect (not just these three
    endpoints) means this can't quietly break again if another
    redirect-returning endpoint is added later."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    is_redirect = 300 <= response.status_code < 400
    if not is_redirect and request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


class GenerateRequest(BaseModel):
    prompt: str
    target_size_studs: int = 32


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    credits_remaining: int


class WaitlistRequest(BaseModel):
    email: str


@app.post("/waitlist")
def join_waitlist(req: WaitlistRequest, request: Request) -> dict:
    """No auth -- this exists specifically for MAINTENANCE_MODE, when the
    frontend shows a waitlist form instead of the real generate flow to a
    logged-out visitor. Same IP-based throttle shape as the auth endpoints
    (see auth.py's own _client_ip/check_auth_rate_limit) since this is
    otherwise a fully open, unauthenticated write."""
    if not rate_limit.check_auth_rate_limit(auth._client_ip(request), "waitlist", limit=5, window_s=3600):
        raise HTTPException(429, "Too many requests -- try again later.")
    try:
        waitlist.add_to_waitlist(req.email)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


def _strip_internal_fields(data: dict) -> dict:
    """user_id is persisted in meta.json (see jobs.py::_job_to_dict) so
    unlock_instructions can verify ownership from disk/storage alone --
    the worker updates a job from a separate process, so there's no live
    in-memory object left in this process to check against. credit_source
    is persisted the same way, purely so _recover_orphaned_jobs can refund
    into the right pool if this job never finishes -- neither belongs in a
    client-facing response. Every endpoint that returns job data to a
    client must strip both here first."""
    return {k: v for k, v in data.items() if k not in ("user_id", "credit_source")}


@app.post("/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(auth.get_current_user),
) -> GenerateResponse:
    if not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")

    # Checked first, before anything else costs a request cycle -- see
    # GENERATION_ALLOWLIST's own docstring above.
    _check_generation_allowlist(user)

    # Runs before rate limiting/credits too -- rejecting a copyrighted-
    # character prompt should never cost the user a credit or count
    # against their hourly cap, and definitely must happen before this
    # job ever reaches gpt-image-1.
    is_allowed, rejection_message = content_filter.check_prompt(req.prompt)
    if not is_allowed:
        raise HTTPException(400, rejection_message)

    # Both checks run before consume_credit -- a rejected request must not
    # cost the user a credit -- and in this order: a single abusive user
    # hitting their own hourly cap shouldn't also count against (and
    # potentially exhaust) the shared global ceiling first.
    if not rate_limit.check_per_user_rate_limit(user.id, user.plan):
        raise HTTPException(429, "Too many generations this hour -- try again later.")
    if not rate_limit.check_global_daily_ceiling():
        raise HTTPException(503, "Daily generation limit reached -- try again tomorrow.")

    try:
        user, credit_source = auth.consume_credit(user.id)
    except ValueError as exc:
        raise HTTPException(402, str(exc)) from exc

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        prompt=req.prompt,
        target_size_studs=req.target_size_studs,
        created_at=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        credit_source=credit_source,
        # Builder was missing here before -- only "pro" (Master Builder)
        # ever got free instructions at job-creation time, contradicting
        # what the account info/pricing page/Terms all actually promise
        # Builder subscribers. A "dev" credit always unlocks (it was never
        # sold to anyone); a "topup" credit never auto-unlocks, even on a
        # paid plan (it IS real, tracked revenue) -- see consume_credit's
        # own docstring for the full reasoning behind all three sources.
        instructions_unlocked=credit_source == "dev"
        or (credit_source == "monthly" and user.plan in ("starter", "builder", "pro")),
    )
    save_job_meta(job)

    # Enqueued to the RQ worker (separate process, see worker.py) when
    # REDIS_URL is configured; falls back to the original in-process
    # BackgroundTasks execution otherwise, so local dev without Redis
    # running still works -- matching every other phase's local-fallback
    # pattern (Postgres/SQLite, R2/local storage). Either way this call
    # returns immediately with status=queued; the frontend polls
    # GET /generate/{id} to watch it move through the real JobStatus
    # phases, which is the actual point of not blocking here.
    if QUEUE is not None:
        # Positional, deliberately -- RQ's own enqueue() reserves "job_id"
        # as a keyword argument (it means "assign this ID to the RQ job
        # itself"), which silently swallowed process_job's job_id kwarg
        # instead of passing it through: a real bug, caught by actually
        # running two jobs through the worker, not by reading the code.
        # job_timeout is RQ's own distinctly-named reserved kwarg (renamed
        # by RQ upstream from a plain "timeout" for exactly this collision
        # reason) and is safe to pass as a keyword.
        try:
            QUEUE.enqueue(
                process_job,
                job.id,
                job.prompt,
                job.target_size_studs,
                job.user_id,
                job.instructions_unlocked,
                job.created_at,
                job_timeout=JOB_TIMEOUT_S,
            )
        except Exception as exc:
            # consume_credit() above already spent a real credit for a job
            # that never actually made it onto the queue -- confirmed as a
            # real production failure, not hypothetical: Redis restarting
            # (e.g. Railway's own image upgrades) at exactly this moment
            # raises here uncaught, and this endpoint had no guard for it
            # while rate_limit.py's own Redis calls already did (see that
            # module's own fail-open handling of the identical error
            # class). Refund before surfacing the error, and still report
            # it to Sentry explicitly -- catching it here would otherwise
            # make this failure mode invisible to monitoring.
            auth.refund_credit(user.id, credit_source)
            logger.error("Failed to enqueue job %s, refunded credit: %s", job.id, exc)
            sentry_sdk.capture_exception(exc)
            raise HTTPException(
                503, "Couldn't start your generation right now -- please try again. You have not been charged a credit."
            ) from exc
    else:
        background_tasks.add_task(
            process_job,
            job_id=job.id,
            prompt=job.prompt,
            target_size_studs=job.target_size_studs,
            user_id=job.user_id,
            instructions_unlocked=job.instructions_unlocked,
            created_at=job.created_at,
        )

    return GenerateResponse(job_id=job_id, status=job.status, credits_remaining=user.credits_remaining)


@app.get("/generate")
def list_jobs(month_only: bool = True, user: auth.User = Depends(auth.get_current_user)) -> list[dict]:
    """This user's own completed jobs, newest first. Discovers which job
    IDs exist via jobs.py's Postgres/SQLite-backed job_index, not a local
    directory listing -- the previous approach only ever saw whatever
    *this specific container* happened to have written locally, which a
    redeploy (backend redeploys on every push) wipes clean, silently
    emptying "My Builds" for jobs that are still completely safe in R2,
    just no longer discoverable. Confirmed as a real, repeatedly-hit
    production issue, not a hypothetical.

    Requires auth and filters to the caller's own user_id -- previously
    this was public and returned *every* user's completed jobs (prompts and
    stats included), which also made every job_id trivially enumerable
    since job_id is used unauthenticated elsewhere (preview, thumbnail).
    Scoping to the caller closes both issues at once."""
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    for entry in list_job_ids_for_user(user.id):
        data = load_job_meta(entry)
        if data is None or data.get("status") != JobStatus.DONE.value:
            continue
        if month_only:
            created = data.get("created_at")
            if not created:
                continue
            created_dt = datetime.fromisoformat(created)
            if (created_dt.year, created_dt.month) != (now.year, now.month):
                continue
        # Lives in job_index (Postgres/SQLite), not meta.json (R2/local) --
        # gallery publish state was never part of the pipeline's own
        # output, so it has to be joined in here rather than already
        # being on `data`.
        data["is_published"] = is_job_published(entry)
        results.append(data)

    results.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return [_strip_internal_fields(r) for r in results]


def _validate_job_id_or_404(job_id: str) -> None:
    """Every job_id this app ever creates is a uuid4 (see generate() above)
    -- anything that doesn't parse as one is never a real job, so rejecting
    it here closes off path traversal in LocalStorage mode (job_id flows
    straight into os.path.join, see storage.py::LocalStorage._path) before
    it ever reaches a filesystem call. 404, not 400: a malformed job_id and
    a well-formed-but-missing one should look identical to a caller probing
    for valid IDs."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(404, "job not found")


def _get_job_dict_or_404(job_id: str) -> dict:
    _validate_job_id_or_404(job_id)
    data = load_job_meta(job_id)
    if data is not None:
        return data
    raise HTTPException(404, "job not found")


@app.get("/generate/{job_id}")
def get_job(job_id: str) -> dict:
    return _strip_internal_fields(_get_job_dict_or_404(job_id))


def _serve_job_file(
    job_id: str,
    filename: str,
    media_type: str,
    download_filename: str | None = None,
) -> Response:
    """Shared by preview/download/thumbnail below. Raises 404 itself so
    callers can just return its result.

    Always streams the bytes through this backend when running on R2,
    rather than redirecting to a presigned URL, regardless of whether
    download_filename is set. A 307 redirect there is a confirmed dead
    end: R2's own CORS response is independently correct (verified
    directly with curl -- both the preflight and the final GET, from
    multiple angles, with the right Access-Control-Allow-Origin every
    time), yet real browsers still fail the *redirected* fetch with "No
    Access-Control-Allow-Origin header is present" -- cross-origin
    redirect + CORS-mode fetch is a known-fragile combination across
    browser implementations, not something fixable by correcting either
    origin's headers further. Streaming through this backend sidesteps
    it entirely: the browser only ever talks to api.brickforgerai.com,
    already proven to work correctly for every other endpoint.

    This used to only apply when download_filename was unset (the
    preview/thumbnail case), on the theory that an actual "save this
    file" download was always a plain <a download> click -- a top-level
    navigation, which handles a redirect with no CORS involved at all,
    letting R2 serve it directly instead of costing this backend the
    bandwidth. That stopped being true the moment download_ldr started
    requiring auth (see its own docstring): a bare link can't carry an
    Authorization header, so the frontend's downloadLdr() does a real
    authenticated `fetch()` instead and saves the result via a blob URL
    it constructs itself. A JS fetch() is exactly the "CORS-mode fetch"
    case above, not a top-level navigation -- so the redirect path was
    silently broken for every real download (reported as a generic
    "download failed" with no HTTP status, since a redirect-following
    fetch that fails CORS throws before a response ever exists to read a
    status from) from the moment auth was added, until this fix. The
    frontend already sets its own `download` filename on the blob it
    builds, so R2's Content-Disposition header -- still passed through
    signed_url below for the local-storage/no-R2 fallback path -- is set
    explicitly here too, but only cosmetic for the browsers that reach
    this branch."""
    _validate_job_id_or_404(job_id)
    if not STORAGE.exists(job_id, filename):
        raise HTTPException(404, "file not ready")

    if isinstance(STORAGE, R2Storage):
        data = STORAGE.get_bytes(job_id, filename)
        if data is not None:
            headers = {"Cache-Control": "no-store"}
            if download_filename:
                headers["Content-Disposition"] = f'attachment; filename="{download_filename}"'
            return Response(content=data, media_type=media_type, headers=headers)

    url = STORAGE.signed_url(job_id, filename, download_filename=download_filename)
    if url:
        return RedirectResponse(url)

    local_path = os.path.join(JOBS_DIR, job_id, filename)
    if download_filename:
        return FileResponse(local_path, filename=download_filename)
    # no-store: without an explicit Cache-Control, browsers are free to
    # reuse a cached copy of this exact URL indefinitely on heuristics
    # alone -- harmless for a normal job (these files never change after
    # completion) but a real, confirmed bug the moment a job's file is
    # ever regenerated in place (as happened when re-running existing jobs
    # through an updated brickforge pipeline): the stats panel (a fresh
    # JSON fetch) showed the new part count while the 3D viewer kept
    # rendering the stale cached geometry.
    return FileResponse(local_path, media_type=media_type, headers={"Cache-Control": "no-store"})


@app.get("/generate/{job_id}/preview")
def preview_ldr(job_id: str) -> Response:
    """Unrestricted -- this is what the in-browser 3D viewer fetches to
    render the free preview (per the pricing page, the preview itself is
    free on every plan). Deliberately separate from /download below, which
    is the actual "save this file to your computer" action and IS gated."""
    return _serve_job_file(job_id, "model.ldr", media_type="text/plain")


@app.get("/generate/{job_id}/download")
def download_ldr(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> Response:
    """Gated on TWO different rules depending on who's asking, not one:
    the job's own creator uses instructions_unlocked exactly as before
    (free-plan pay-per-model, or included automatically for Builder/Pro);
    anyone else can only download if they've specifically paid for this
    job through the gallery (see has_gallery_access/gallery_purchases).

    Now requires auth -- it didn't before. That's a deliberate, necessary
    tightening, not scope creep: previously this endpoint only checked
    the job's own instructions_unlocked flag with no notion of who was
    asking, so *anyone* who knew or guessed a job_id could download it
    for free the moment its creator had unlocked it. That was low-risk
    while job_ids were only ever shared privately by their own creator,
    but the gallery makes published job_ids genuinely public and
    searchable -- without this change, the very first Builder/Pro
    creator to publish a job would have handed out free downloads to
    every visitor, bypassing the gallery's own pricing entirely. The 3D
    preview (GET .../preview, above) stays unauthenticated on purpose --
    only the actual "save this file" action needs to know who's asking."""
    data = _get_job_dict_or_404(job_id)
    is_owner = data.get("user_id") == user.id
    if is_owner:
        if not data.get("instructions_unlocked"):
            raise HTTPException(402, "Unlock instructions to download this model's .ldr file")
    elif not has_gallery_access(job_id, user.id):
        raise HTTPException(402, "Purchase this gallery build to download its .ldr file")

    return _serve_job_file(job_id, "model.ldr", media_type="text/plain", download_filename=f"{job_id}.ldr")


@app.get("/generate/{job_id}/instructions.pdf")
def download_instructions_pdf(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> Response:
    """Same gating as download_ldr above -- bundled with the .ldr at the
    exact same price, not a separate paid tier: whoever is entitled to
    download the model gets its build-instruction PDF too. 404s (rather
    than a silent empty response) if generation succeeded but the PDF
    render itself failed -- see brickforge_bridge.mesh_to_ldr's own
    docstring for why that's a best-effort step that doesn't fail the
    whole job."""
    data = _get_job_dict_or_404(job_id)
    is_owner = data.get("user_id") == user.id
    if is_owner:
        if not data.get("instructions_unlocked"):
            raise HTTPException(402, "Unlock instructions to download this model's build guide")
    elif not has_gallery_access(job_id, user.id):
        raise HTTPException(402, "Purchase this gallery build to download its build guide")
    if not data.get("instructions_pdf_url"):
        raise HTTPException(404, "instructions PDF not available for this build")

    return _serve_job_file(
        job_id, "instructions.pdf", media_type="application/pdf", download_filename=f"{job_id}-instructions.pdf"
    )


@app.post("/generate/{job_id}/unlock-instructions")
def unlock_instructions(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Real charge, via Stripe Checkout -- returns a checkout_url to
    redirect the browser to rather than unlocking immediately. The actual
    unlock happens from the webhook (see _unlock_instructions_for_job
    below and billing.handle_webhook_event), once Stripe confirms the
    payment actually went through, not before.

    Dynamic price (£5-15, scaled by part count -- see
    jobs.py::_estimate_instructions_price_gbp), so this can't use one of
    billing.PRICE_IDS the way plan checkout does; billing.py builds an
    inline price_data line item instead."""
    _check_generation_allowlist(user)
    data = _get_job_dict_or_404(job_id)
    if data.get("user_id") != user.id:
        raise HTTPException(403, "not your job")
    if data.get("instructions_unlocked"):
        raise HTTPException(400, "already unlocked")

    checkout_url = billing.create_unlock_instructions_checkout(
        user, job_id, data.get("instructions_price_gbp", 5)
    )
    return {"checkout_url": checkout_url}


def _unlock_instructions_for_job(job_id: str) -> None:
    """Called from the Stripe webhook once a job's instructions-unlock
    payment is confirmed. Separate from the endpoint above (which creates
    the checkout, not the unlock itself) -- injected into
    billing.handle_webhook_event to avoid a circular import between
    main.py and billing.py."""
    data = load_job_meta(job_id)
    if data is None:
        return
    data["instructions_unlocked"] = True
    _write_job_meta_dict(job_id, data)


@app.post("/gallery/{job_id}/publish")
def publish_to_gallery(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Only the job's own creator can publish it, and only once it's
    actually finished -- a queued/failed job has no thumbnail, parts
    list, or price to show in the gallery yet."""
    data = _get_job_dict_or_404(job_id)
    if data.get("user_id") != user.id:
        raise HTTPException(403, "not your job")
    if data.get("status") != JobStatus.DONE.value:
        raise HTTPException(400, "only a completed build can be published")
    # Backfills job_index.prompt from the meta we already loaded above --
    # fixes gallery search silently missing builds whose prompt was never
    # written to the index (jobs created before that column existed, or
    # any other reason it went missing) -- see set_job_published's own
    # docstring.
    if not set_job_published(job_id, user.id, True, prompt=data.get("prompt")):
        raise HTTPException(404, "job not found")
    return {"published": True}


@app.post("/gallery/{job_id}/unpublish")
def unpublish_from_gallery(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    if not set_job_published(job_id, user.id, False):
        raise HTTPException(403, "not your job")
    return {"published": False}


def _gallery_card(job_id: str, prompt: str | None, published_at: str | None) -> dict | None:
    """Public-safe summary for one gallery listing row -- an explicit
    whitelist of fields, not a reuse of _strip_internal_fields: this
    endpoint has no auth at all (the gallery is browsable logged out), so
    nothing beyond what's listed here should ever be reachable from it,
    unlike the single-owner-authenticated /generate/{id} response
    _strip_internal_fields was designed for."""
    meta = load_job_meta(job_id)
    if meta is None:
        return None
    return {
        "job_id": job_id,
        "prompt": prompt,
        "published_at": published_at,
        "part_count": meta.get("part_count"),
        "color_count": meta.get("color_count"),
        "thumbnail_url": meta.get("thumbnail_url"),
        "instructions_price_gbp": meta.get("instructions_price_gbp", 5),
    }


@app.get("/gallery")
def gallery_list(q: str | None = None, limit: int = 24, offset: int = 0) -> list[dict]:
    """Public -- no auth required, since the gallery is meant to be
    browsable while logged out. q searches prompt text, case-insensitive
    substring match (see jobs.list_gallery_jobs)."""
    limit = min(max(limit, 1), 60)
    offset = max(offset, 0)
    rows = list_gallery_jobs(search=q.strip() if q else None, limit=limit, offset=offset)
    cards = [_gallery_card(job_id, prompt, published_at) for job_id, prompt, published_at in rows]
    return [c for c in cards if c is not None]


@app.get("/gallery/{job_id}")
def gallery_detail(job_id: str) -> dict:
    """Public detail view for one published gallery job. 404s for an
    unpublished job the same as a nonexistent one -- this must not be
    usable to probe whether a private job_id exists at all."""
    _validate_job_id_or_404(job_id)
    if not is_job_published(job_id):
        raise HTTPException(404, "gallery item not found")
    meta = load_job_meta(job_id)
    if meta is None:
        raise HTTPException(404, "gallery item not found")
    return {
        "job_id": job_id,
        "prompt": meta.get("prompt"),
        "part_count": meta.get("part_count"),
        "slope_count": meta.get("slope_count"),
        "tile_count": meta.get("tile_count"),
        "color_count": meta.get("color_count"),
        "thumbnail_url": meta.get("thumbnail_url"),
        "instructions_price_gbp": meta.get("instructions_price_gbp", 5),
        "instructions_pdf_url": meta.get("instructions_pdf_url"),
        "symmetrized": meta.get("symmetrized"),
    }


@app.get("/gallery/{job_id}/access")
def gallery_access(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Lets the frontend show "Download" vs "Buy — £X" correctly on a
    return visit, not just right after a checkout redirect -- without
    this, a signed-in user who already bought a gallery build yesterday
    would see a "Buy" button again today (harmless if clicked, since
    purchase-checkout itself still rejects an already-owned job, but a
    confusing button to show)."""
    data = _get_job_dict_or_404(job_id)
    is_owner = data.get("user_id") == user.id
    has_access = bool(data.get("instructions_unlocked")) if is_owner else has_gallery_access(job_id, user.id)
    return {"is_owner": is_owner, "has_access": has_access}


@app.post("/gallery/{job_id}/purchase-checkout")
def gallery_purchase_checkout(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """A non-creator buying download access to a published gallery
    build. The creator viewing/downloading their own published job never
    hits this -- they already have (or can buy) access through the
    normal unlock-instructions flow, gated on their own plan, not this
    always-pay gallery price."""
    _check_generation_allowlist(user)
    if not is_job_published(job_id):
        raise HTTPException(404, "gallery item not found")
    data = _get_job_dict_or_404(job_id)
    if data.get("user_id") == user.id:
        raise HTTPException(400, "this is your own build -- use the normal unlock flow, not a gallery purchase")
    if has_gallery_access(job_id, user.id):
        raise HTTPException(400, "already purchased")

    checkout_url = billing.create_gallery_purchase_checkout(user, job_id, data.get("instructions_price_gbp", 5))
    return {"checkout_url": checkout_url}


class PlanCheckoutRequest(BaseModel):
    plan: str  # "starter", "builder", or "pro"


@app.post("/billing/checkout")
def billing_checkout(req: PlanCheckoutRequest, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Free -> Builder/Master Builder, or a plan change between the two --
    returns a checkout_url to redirect the browser to. The actual plan
    change happens from the webhook once Stripe confirms the
    subscription, not here."""
    _check_generation_allowlist(user)
    if req.plan not in billing.PRICE_IDS:
        raise HTTPException(400, f"Unknown plan: {req.plan!r}")
    try:
        return {"checkout_url": billing.create_subscription_checkout(user, req.plan)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/billing/topup-checkout")
def billing_topup_checkout(user: auth.User = Depends(auth.get_current_user)) -> dict:
    """+5 credits for £6, available to any signed-in user on any plan."""
    _check_generation_allowlist(user)
    return {"checkout_url": billing.create_topup_checkout(user)}


@app.post("/billing/portal")
def billing_portal(user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Returns a URL to Stripe's hosted Billing Portal -- next billing
    date, card updates, invoices, and cancellation, all handled by Stripe
    itself. Not gated by _check_generation_allowlist: managing an
    already-existing subscription doesn't start a new charge or cost this
    app anything, unlike checkout/topup/unlock, which is what that gate
    exists to restrict (see its own docstring)."""
    try:
        return {"portal_url": billing.create_billing_portal_session(user)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/auth/me")
def delete_account(user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Permanently deletes the signed-in account: cancels any active
    Stripe subscription first (so deleting the account doesn't leave
    someone billed with no way to log back in and stop it), then removes
    the user's own non-published job history and the account row itself.
    A published job stays live for anyone who already bought or is
    viewing it in Discover -- see jobs.delete_jobs_for_user's own
    docstring. Irreversible; the frontend is responsible for confirming
    with the user before calling this."""
    billing.cancel_all_subscriptions(user)
    delete_jobs_for_user(user.id)
    auth.delete_user(user.id)
    return {"deleted": True}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Verifies the signature, dedupes by event ID (Stripe retries
    delivery on anything short of a 200 -- see
    auth.mark_stripe_event_processed's own docstring for why this matters
    for the top-up flow specifically), then dispatches. Returns 200 for a
    duplicate delivery too -- acknowledging it (rather than erroring) is
    what stops Stripe from retrying forever."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = billing.verify_and_parse_webhook(payload, signature)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not auth.mark_stripe_event_processed(event["id"]):
        return {"received": True}

    billing.handle_webhook_event(event, _unlock_instructions_for_job, record_gallery_purchase)
    return {"received": True}


@app.get("/generate/{job_id}/thumbnail")
def get_thumbnail(job_id: str) -> Response:
    """Prefers an actual render of the finished brick model (render.png,
    captured client-side by the 3D viewer -- see RenderCapture below) over
    the AI-generated reference photo (reference.png), since the gallery
    should show what got built, not the prompt image that inspired it.
    Falls back to the reference photo only if a render was never
    captured (e.g. nobody has opened that job's results page yet)."""
    # Validated up front, not left to _serve_job_file below -- the two
    # STORAGE.exists() calls above it run first and, in LocalStorage mode,
    # reach LocalStorage._path()'s os.makedirs() before either call site
    # would otherwise catch a malformed job_id.
    _validate_job_id_or_404(job_id)
    if STORAGE.exists(job_id, "render.png"):
        return _serve_job_file(job_id, "render.png", media_type="image/png")
    if STORAGE.exists(job_id, "reference.png"):
        return _serve_job_file(job_id, "reference.png", media_type="image/png")
    raise HTTPException(404, "thumbnail not ready")


class RenderCapture(BaseModel):
    image_data_url: str  # "data:image/png;base64,...."


@app.post("/generate/{job_id}/render")
def save_render(job_id: str, body: RenderCapture) -> dict:
    """Receives a screenshot of the actual rendered brick model from the
    3D viewer (client-side canvas capture -- there's no server-side
    LDraw renderer in this trial app) and saves it as this job's
    thumbnail. Low-stakes cosmetic data, so deliberately not behind auth
    here -- worst case someone overwrites a gallery thumbnail with a
    wrong image, not a real security concern for a trial app."""
    _validate_job_id_or_404(job_id)
    # load_job_meta, not a bare os.path.isdir(JOBS_DIR/job_id) -- the same
    # bug as the "stuck at queued" fix above, just in a different
    # function: this container's own local disk only has a directory for
    # a job if THIS container happened to be the one that created or
    # processed it. Any redeploy since then (this endpoint is on
    # `backend`, which redeploys on every push, same as `worker`) wipes
    # that clean, and a real, already-completed job then gets a false
    # "job not found" the moment its render is captured on a fresh
    # container -- confirmed on a real job, not assumed.
    if load_job_meta(job_id) is None:
        raise HTTPException(404, "job not found")
    jdir = _job_dir(job_id)

    prefix = "data:image/png;base64,"
    if not body.image_data_url.startswith(prefix):
        raise HTTPException(400, "expected a data:image/png;base64 URL")

    png_bytes = base64.b64decode(body.image_data_url[len(prefix):])
    render_path = os.path.join(jdir, "render.png")
    with open(render_path, "wb") as f:
        f.write(png_bytes)
    STORAGE.put(job_id, "render.png", render_path)
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    """Actually checks the database and queue rather than just returning
    200 unconditionally -- a health check that can't fail isn't checking
    anything. Redis absent (REDIS_CONN is None, e.g. local dev without it
    configured) is reported distinctly from Redis present-but-unreachable
    -- the former is expected and not a failure, the latter is."""
    try:
        with auth._connect() as conn:
            conn.execute(auth._ph("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if REDIS_CONN is None:
        redis_status = "not configured"
        redis_ok = True
    else:
        try:
            REDIS_CONN.ping()
            redis_status = "ok"
            redis_ok = True
        except Exception:
            redis_status = "unreachable"
            redis_ok = False

    healthy = db_ok and redis_ok
    return {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "redis": redis_status,
    }
