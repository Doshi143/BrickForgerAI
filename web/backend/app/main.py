"""FastAPI backend for the prompt -> LEGO-instructions pipeline."""
from __future__ import annotations

import base64
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
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import auth, content_filter, rate_limit
from .jobs import (
    JOB_TIMEOUT_S,
    JOBS_DIR,
    QUEUE,
    REDIS_CONN,
    STORAGE,
    Job,
    JobStatus,
    _write_job_meta_dict,
    load_job_meta,
    process_job,
    save_job_meta,
)

# No-op when SENTRY_DSN is unset -- sentry_sdk.init(dsn=None) disables
# capture entirely rather than erroring, so no separate guard is needed
# beyond not calling it with a bad value.
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1)

auth.init_db()

app = FastAPI(title="Prompt-to-LEGO Backend")
app.include_router(auth.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str
    target_size_studs: int = 32


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    credits_remaining: int


def _strip_internal_fields(data: dict) -> dict:
    """user_id is persisted in meta.json (see jobs.py::_job_to_dict) so
    unlock_instructions can verify ownership from disk/storage alone --
    the worker updates a job from a separate process, so there's no live
    in-memory object left in this process to check against. Every
    endpoint that returns job data to a client must strip it here first."""
    return {k: v for k, v in data.items() if k != "user_id"}


@app.post("/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(auth.get_current_user),
) -> GenerateResponse:
    if not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")

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
        user = auth.consume_credit(user.id)
    except ValueError as exc:
        raise HTTPException(402, str(exc)) from exc

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        prompt=req.prompt,
        target_size_studs=req.target_size_studs,
        created_at=datetime.now(timezone.utc).isoformat(),
        user_id=user.id,
        instructions_unlocked=(user.plan == "pro"),
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
def list_jobs(month_only: bool = True) -> list[dict]:
    """Gallery data: every *completed* job, newest first. Reads meta.json
    files directly off disk -- see jobs.py::load_job_meta's own docstring
    for why this is still a local-directory enumeration, not something
    that can see jobs whose local copy is gone after a redeploy."""
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    for entry in os.listdir(JOBS_DIR):
        if not os.path.isdir(os.path.join(JOBS_DIR, entry)):
            continue
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
        results.append(data)

    results.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return [_strip_internal_fields(r) for r in results]


def _get_job_dict_or_404(job_id: str) -> dict:
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
    """Shared by preview/download/thumbnail below: redirect to a short-lived
    signed URL when the storage backend can produce one (R2), otherwise
    fall back to serving straight from local disk (LocalStorage -- signed
    urls don't mean anything for a file on this same machine). Raises 404
    itself so callers can just return its result."""
    if not STORAGE.exists(job_id, filename):
        raise HTTPException(404, "file not ready")

    url = STORAGE.signed_url(job_id, filename)
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
def download_ldr(job_id: str) -> Response:
    """Gated behind instructions_unlocked (free-plan pay-per-model, or
    included automatically for pro-plan jobs -- see generate()). The 3D
    preview (GET .../preview, above) is intentionally not behind this
    gate; only actually saving the file is."""
    data = _get_job_dict_or_404(job_id)
    if not data.get("instructions_unlocked"):
        raise HTTPException(402, "Unlock instructions to download this model's .ldr file")

    return _serve_job_file(job_id, "model.ldr", media_type="text/plain", download_filename=f"{job_id}.ldr")


@app.post("/generate/{job_id}/unlock-instructions")
def unlock_instructions(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Mock purchase: marks a free-plan job's instructions as unlocked with
    no real payment behind it (Stripe is explicitly deferred -- see the
    pricing page and auth.py's module docstring). Exists so the pricing
    model has a real, working data flow end to end; wiring an actual
    charge here is the next step, not a rewrite of this endpoint.

    Reads/writes meta.json directly (via load_job_meta / _write_job_meta_dict)
    rather than an in-memory JOBS dict -- once the pipeline runs in a
    separate worker process, there is no live Job object left in this
    process to mutate; persisted meta is the only thing both processes
    actually share."""
    data = load_job_meta(job_id)
    if data is None:
        raise HTTPException(404, "job not found")
    if data.get("user_id") != user.id:
        raise HTTPException(403, "not your job")

    data["instructions_unlocked"] = True
    _write_job_meta_dict(job_id, data)
    return _strip_internal_fields(data)


@app.get("/generate/{job_id}/thumbnail")
def get_thumbnail(job_id: str) -> Response:
    """Prefers an actual render of the finished brick model (render.png,
    captured client-side by the 3D viewer -- see RenderCapture below) over
    the AI-generated reference photo (reference.png), since the gallery
    should show what got built, not the prompt image that inspired it.
    Falls back to the reference photo only if a render was never
    captured (e.g. nobody has opened that job's results page yet)."""
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
    jdir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(jdir):
        raise HTTPException(404, "job not found")

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
