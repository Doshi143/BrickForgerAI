"""Shared job model, on-disk/object-storage persistence, and pipeline
execution -- imported by both the API process (main.py, which enqueues
work) and the worker process (worker.py, which executes it).

Splitting this out of main.py is what makes a separate worker possible at
all: RQ needs a plain importable function it can enqueue a reference to,
and the worker runs in a genuinely different OS process with no shared
memory -- meta.json (and STORAGE) is the *only* channel back to the API,
not a Python object either process could mutate in place.
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import redis
from rq import Queue

from . import auth
from .clients.image_gen import build_image_prompt, get_image_client
from .clients.mesh_gen import get_mesh_client
from .pipeline.brickforge_bridge import mesh_to_ldr
from .storage import R2Storage, get_storage

JOBS_DIR = os.path.join(os.path.dirname(__file__), "..", "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

STORAGE = get_storage()


def _init_job_index() -> None:
    """A durable (Postgres/SQLite, not local-disk) record of which job IDs
    exist and who owns them -- fixes a real production bug: main.py's
    list_jobs used to discover jobs by listing JOBS_DIR, which only ever
    contains whatever this *specific* container has locally written.
    backend redeploys on every push (several times a day some days), each
    one wiping that listing clean -- a user's actual jobs were always
    safe in R2, just no longer *discoverable*, so "My Builds" would
    silently go back to empty after every deploy. This table is the fix:
    populated from save_job_meta below (every process, every write), so
    it survives exactly the redeploys local-disk listing couldn't."""
    with auth._connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_index (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Denormalized from meta.json specifically so the gallery's search
        # box can query Postgres/SQLite directly (LIKE over this column)
        # rather than pulling every published job's full meta.json out of
        # R2 just to filter by prompt text.
        auth._add_column_if_missing(conn, "ALTER TABLE job_index ADD COLUMN prompt TEXT", "prompt")
        # is_published/published_at, not a separate table -- a job's
        # gallery status is 1:1 with the job itself, same relationship as
        # status/created_at already have here. Uses the shared
        # _add_column_if_missing helper (see auth.py) specifically because
        # a repeat of the earlier signup_source incident -- a migration
        # that silently fails and leaves this column missing -- would
        # break the publish endpoint for everyone, not just crash quietly.
        auth._add_column_if_missing(
            conn, "ALTER TABLE job_index ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT FALSE", "is_published"
        )
        auth._add_column_if_missing(conn, "ALTER TABLE job_index ADD COLUMN published_at TEXT", "published_at")
        # Who has paid to download which gallery job -- deliberately NOT
        # the same instructions_unlocked flag a job already carries for
        # its own creator. That flag is a single value on the job itself;
        # once true, the existing (pre-gallery) download endpoint let
        # *anyone* with the URL download for free. Reusing it for gallery
        # purchases would mean the very first buyer's payment silently
        # unlocks free downloads for every other visitor too -- a real
        # revenue hole, not a hypothetical one, the moment a job is both
        # published and already-unlocked for its creator (any Builder/Pro
        # creator's published job, immediately). One row per (job, buyer)
        # keeps each purchase scoped to the person who actually paid.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gallery_purchases (
                job_id TEXT NOT NULL,
                buyer_user_id TEXT NOT NULL,
                purchased_at TEXT NOT NULL,
                PRIMARY KEY (job_id, buyer_user_id)
            )
            """
        )


_init_job_index()

# Short, not the pool's own 30s default -- see _record_job_index's own
# docstring for why a write this module already treats as safe to drop
# should fail fast rather than block a job on the pool's full patience.
_INDEX_WRITE_TIMEOUT = 5.0


def _record_job_index(job_id: str, user_id: str, status: str, created_at: str, prompt: str | None = None) -> None:
    """Upsert, not insert -- called on every save_job_meta, so a job's
    entry here tracks its latest status exactly as reliably as meta.json
    itself does (same call site, always in lockstep).

    Never raises -- confirmed as a real production failure, not a
    hypothetical: a psycopg_pool.PoolTimeout here (the connection pool
    momentarily exhausted, e.g. by a redeploy landing mid-job and the old
    container's connections not yet reclaimed by Postgres) propagated all
    the way up through save_job_meta -> _set_status and killed an entire
    multi-minute, real-API-cost generation over what is fundamentally a
    non-essential side write: the job's actual result is already durably
    saved via STORAGE.put/meta.json regardless of whether this specific
    index update succeeds, and job_index only powers "My Builds"
    discoverability (see its own docstring above), not the job itself.
    One retry after a short pause rides out a genuinely transient blip;
    if it still fails, this logs and moves on rather than taking the job
    down with it -- same fail-open-for-a-non-critical-path reasoning as
    rate_limit.py's Redis handling.

    `_INDEX_WRITE_TIMEOUT` (not the pool's own 30s default) on both
    attempts -- confirmed in production logs that this path was eating
    up to ~63s per job (two 30s waits plus the retry sleep) whenever the
    pool was under real, sustained pressure, not just the brief redeploy
    blip this retry loop was originally written for. A write this module
    already treats as safe to simply drop should fail fast, not hold up
    a job's actual, real-API-cost work for a minute over a "My Builds"
    visibility update."""
    for attempt in range(2):
        try:
            with auth._connect(timeout=_INDEX_WRITE_TIMEOUT) as conn:
                conn.execute(
                    auth._ph(
                        """
                        INSERT INTO job_index (job_id, user_id, status, created_at, prompt) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (job_id) DO UPDATE SET status = excluded.status, prompt = excluded.prompt
                        """
                    ),
                    (job_id, user_id, status, created_at, prompt),
                )
            return
        except Exception:
            if attempt == 0:
                time.sleep(3)
                continue
            logger.warning(
                "job_index write failed for job %s (status=%s) -- job itself is unaffected, "
                "only this update's visibility in 'My Builds' until the next status write succeeds",
                job_id,
                status,
                exc_info=True,
            )


def list_job_ids_for_user(user_id: str) -> list[str]:
    """Every job ID this user has ever created, in no particular order --
    main.py's list_jobs still does its own status/month filtering after
    calling load_job_meta on each, this only replaces *discovery*."""
    with auth._connect() as conn:
        rows = conn.execute(
            auth._ph("SELECT job_id FROM job_index WHERE user_id = ?"), (user_id,)
        ).fetchall()
    return [row["job_id"] for row in rows]


def delete_jobs_for_user(user_id: str) -> None:
    """Used by account deletion (main.py's DELETE /auth/me). Only removes
    job_index rows that were never published to the Discover gallery --
    a published job's own gallery_purchases rows (recorded against
    job_id, not the original creator) stay valid for whoever bought it,
    so deleting the creator's account must not pull the build out from
    under a paying buyer. This intentionally leaves a published job's
    row (and its R2 files) behind with no live owner, the same tradeoff
    "delete my account" makes everywhere the deleted account's content
    has already been shared with other people."""
    with auth._connect() as conn:
        conn.execute(
            auth._ph("DELETE FROM job_index WHERE user_id = ? AND (is_published IS NULL OR is_published = FALSE)"),
            (user_id,),
        )


def set_job_published(job_id: str, user_id: str, published: bool, prompt: str | None = None) -> bool:
    """Returns False if job_id doesn't exist in the index or doesn't
    belong to user_id -- the caller (main.py) turns that into a 403/404.

    `prompt`, when publishing, is backfilled into job_index alongside
    is_published/published_at -- a real bug found by tracing why gallery
    search was silently missing builds whose title displayed correctly
    everywhere else: a job created before the `prompt` column existed (or
    whose job_index row otherwise never got a prompt written to it, e.g.
    a partial index write) keeps prompt=NULL forever, since the ordinary
    save_job_meta -> _record_job_index path only ever runs on the job's
    OWN status changes, not on a later publish action. `LOWER(prompt)
    LIKE LOWER(?)` against a NULL column matches nothing in either SQLite
    or Postgres, so the build silently never appears in search, even
    though `meta.json` (and thus its title everywhere else) has the
    correct prompt the whole time. Publishing is the one moment a job's
    prompt is guaranteed to be freshly available (the caller already
    loaded it from meta.json to check the job is DONE), so backfilling
    here fixes both old and any-other-reason-missing rows without a
    separate migration. Passing `prompt=None` here is a no-op on the
    `is_published=False` (unpublish) path, and simply skips the backfill
    if omitted -- existing callers that don't pass it keep today's
    behavior."""
    with auth._connect() as conn:
        row = conn.execute(auth._ph("SELECT user_id FROM job_index WHERE job_id = ?"), (job_id,)).fetchone()
        if row is None or row["user_id"] != user_id:
            return False
        if published:
            if prompt is not None:
                conn.execute(
                    auth._ph(
                        "UPDATE job_index SET is_published = TRUE, published_at = ?, prompt = ? WHERE job_id = ?"
                    ),
                    (datetime.now(timezone.utc).isoformat(), prompt, job_id),
                )
            else:
                conn.execute(
                    auth._ph("UPDATE job_index SET is_published = TRUE, published_at = ? WHERE job_id = ?"),
                    (datetime.now(timezone.utc).isoformat(), job_id),
                )
        else:
            conn.execute(auth._ph("UPDATE job_index SET is_published = FALSE WHERE job_id = ?"), (job_id,))
    return True


def is_job_published(job_id: str) -> bool:
    with auth._connect() as conn:
        row = conn.execute(
            auth._ph("SELECT is_published FROM job_index WHERE job_id = ?"), (job_id,)
        ).fetchone()
    return bool(row and row["is_published"])


def list_gallery_jobs(search: str | None, limit: int, offset: int) -> list[tuple[str, str | None, str | None]]:
    """Returns (job_id, prompt, published_at) tuples for published jobs,
    newest first. Case-insensitive substring match on prompt when search
    is given, via LOWER()-wrapped LIKE rather than Postgres-only ILIKE --
    SQLite has no ILIKE, and this way the exact same query string works
    against both backends."""
    with auth._connect() as conn:
        if search:
            rows = conn.execute(
                auth._ph(
                    "SELECT job_id, prompt, published_at FROM job_index "
                    "WHERE is_published = TRUE AND LOWER(prompt) LIKE LOWER(?) "
                    "ORDER BY published_at DESC LIMIT ? OFFSET ?"
                ),
                (f"%{search}%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                auth._ph(
                    "SELECT job_id, prompt, published_at FROM job_index "
                    "WHERE is_published = TRUE "
                    "ORDER BY published_at DESC LIMIT ? OFFSET ?"
                ),
                (limit, offset),
            ).fetchall()
    return [(r["job_id"], r["prompt"], r["published_at"]) for r in rows]


def has_gallery_access(job_id: str, user_id: str) -> bool:
    """True if user_id has specifically paid for this gallery job -- see
    gallery_purchases's own docstring in _init_job_index for why this is
    a separate per-buyer record rather than reusing the job's own
    instructions_unlocked flag."""
    with auth._connect() as conn:
        row = conn.execute(
            auth._ph("SELECT 1 FROM gallery_purchases WHERE job_id = ? AND buyer_user_id = ?"),
            (job_id, user_id),
        ).fetchone()
    return row is not None


def record_gallery_purchase(job_id: str, buyer_user_id: str) -> None:
    """Called from the Stripe webhook once a gallery purchase is
    confirmed -- see billing.handle_webhook_event. ON CONFLICT DO NOTHING
    since a retried webhook delivery for the same event must not error --
    idempotency is already enforced earlier by main.py's
    auth.mark_stripe_event_processed check, this is just a harmless
    second line of defense for the same scenario."""
    with auth._connect() as conn:
        conn.execute(
            auth._ph(
                """
                INSERT INTO gallery_purchases (job_id, buyer_user_id, purchased_at) VALUES (?, ?, ?)
                ON CONFLICT (job_id, buyer_user_id) DO NOTHING
                """
            ),
            (job_id, buyer_user_id, datetime.now(timezone.utc).isoformat()),
        )

REDIS_URL = os.environ.get("REDIS_URL")
REDIS_CONN = redis.from_url(REDIS_URL) if REDIS_URL else None
QUEUE = Queue("brickforge", connection=REDIS_CONN) if REDIS_CONN else None
# Generous enough for image-gen + mesh-gen + brickify combined -- each
# stage alone can take minutes (TRELLIS_TIMEOUT_S alone defaults to 1800s)
# -- RQ's own default job_timeout (180s) would kill a real job partway
# through.
JOB_TIMEOUT_S = 3600


class JobStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_IMAGE = "generating_image"
    GENERATING_MESH = "generating_mesh"
    BUILDING_BRICKS = "building_bricks"  # voxelize -> shell -> quantize -> legalize -> repair -> refine
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    prompt: str
    target_size_studs: int
    created_at: str
    user_id: str
    instructions_unlocked: bool  # true for pro-plan users; free users see a paywall stub
    # Which of consume_credit()'s three pools (monthly/dev/topup) paid for
    # this job -- internal-only, same as user_id, persisted purely so
    # _recover_orphaned_jobs can refund into the correct pool if this job
    # never finishes. None for jobs created before this field existed.
    credit_source: str | None = None
    status: JobStatus = JobStatus.QUEUED
    error: str | None = None
    image_path: str | None = None
    mesh_path: str | None = None
    ldr_path: str | None = None
    pdf_path: str | None = None  # instructions.pdf -- see brickforge_bridge.mesh_to_ldr's pdf_out_path
    part_count: int | None = None
    slope_count: int | None = None
    tile_count: int | None = None
    color_count: int | None = None
    color_source: str | None = None
    was_repaired: bool | None = None
    still_critical_count: int | None = None
    is_single_piece: bool | None = None
    symmetrized: bool | None = None


def _job_dir(job_id: str) -> str:
    path = os.path.join(JOBS_DIR, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def _estimate_instructions_price_gbp(part_count: int | None) -> int:
    """Placeholder pricing formula for the free plan's pay-per-instructions
    option (GBP 5-15, per the pricing page): scales gently with part count
    so a bigger build costs a bit more, clamped to the stated range. Not
    connected to any real payment processor yet -- see auth.py's module
    docstring."""
    if not part_count:
        return 5
    return max(5, min(15, 5 + part_count // 400))


def _job_to_dict(job: Job) -> dict:
    return {
        "job_id": job.id,
        "prompt": job.prompt,
        "target_size_studs": job.target_size_studs,
        "created_at": job.created_at,
        # Internal-only: needed so unlock_instructions can verify ownership
        # from persisted meta alone (the worker updates this job from a
        # separate process, so there is no live in-memory object to check
        # against) -- public-facing endpoints (get_job, list_jobs in
        # main.py) must strip this before returning it to a client.
        "user_id": job.user_id,
        "credit_source": job.credit_source,
        "instructions_unlocked": job.instructions_unlocked,
        "instructions_price_gbp": _estimate_instructions_price_gbp(job.part_count),
        "status": job.status.value if isinstance(job.status, JobStatus) else job.status,
        "error": job.error,
        "part_count": job.part_count,
        "slope_count": job.slope_count,
        "tile_count": job.tile_count,
        "color_count": job.color_count,
        "color_source": job.color_source,
        "was_repaired": job.was_repaired,
        "still_critical_count": job.still_critical_count,
        "is_single_piece": job.is_single_piece,
        "symmetrized": job.symmetrized,
        "ldr_download_url": f"/generate/{job.id}/download" if job.ldr_path else None,
        # None (not just missing/false) when generation succeeded but the
        # PDF render itself failed -- see mesh_to_ldr's own docstring for
        # why that's best-effort rather than job-fatal. The frontend just
        # hides the instructions-PDF button in that case, same as before
        # this feature existed.
        "instructions_pdf_url": f"/generate/{job.id}/instructions.pdf" if job.pdf_path else None,
        "thumbnail_url": f"/generate/{job.id}/thumbnail" if job.image_path else None,
        "has_render": STORAGE.exists(job.id, "render.png"),
    }


def _write_job_meta_dict(job_id: str, data: dict) -> None:
    path = os.path.join(_job_dir(job_id), "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    STORAGE.put(job_id, "meta.json", path)
    # Hooked here rather than only in save_job_meta below: main.py's
    # _unlock_instructions_for_job calls this directly with a plain dict
    # (from the webhook, no live Job object to hand save_job_meta), so
    # this is the one choke point every write -- from either process --
    # actually goes through.
    if data.get("user_id") and data.get("status") and data.get("created_at"):
        _record_job_index(job_id, data["user_id"], data["status"], data["created_at"], data.get("prompt"))


def save_job_meta(job: Job) -> None:
    _write_job_meta_dict(job.id, _job_to_dict(job))


def load_job_meta(job_id: str) -> dict | None:
    # R2 first when R2 is the active backend -- it's the only channel a
    # separate worker process's status updates can actually reach this
    # process through (see module docstring). Local disk is only ever
    # accurate in a single-process, no-queue local dev run (LocalStorage,
    # no R2 configured); in the real split backend/worker deployment it's
    # a fossil of whatever *this* process itself last wrote -- generate()
    # writes an initial "queued" snapshot to its own local disk before the
    # job is ever enqueued, and preferring that local copy unconditionally
    # meant this process could never see any status the worker wrote
    # afterward, for the rest of this process's lifetime (a redeploy that
    # happened to wipe this process's local disk was the only thing that
    # ever "fixed" it, by forcing a genuine R2 read). Confirmed on a real
    # job RQ logged as completed in 0:01:03 while this API kept reporting
    # "queued" indefinitely.
    path = os.path.join(JOBS_DIR, job_id, "meta.json")
    data = None
    if isinstance(STORAGE, R2Storage):
        raw = STORAGE.get_bytes(job_id, "meta.json")
        if raw is not None:
            data = json.loads(raw)
    if data is None and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    if data is None:
        raw = STORAGE.get_bytes(job_id, "meta.json")
        if raw is None:
            return None
        data = json.loads(raw)
    # has_render can't be baked into the saved snapshot: render.png is
    # captured asynchronously by whichever browser first opens this job's
    # model, which can happen long after the job (and its meta.json) was
    # written -- including by the gallery's own backfill render. Recompute
    # it fresh on every read instead of trusting the stored value, or a
    # freshly-backfilled render would never be reflected here and the
    # gallery would keep re-rendering a job that already has a thumbnail.
    data["has_render"] = STORAGE.exists(job_id, "render.png")
    return data


def _backfill_missing_prompts() -> None:
    """One-time, idempotent data fix, same self-healing spirit as the
    schema migrations in _init_job_index -- run once per process start
    (both API and worker import this module), so any published job
    stuck with prompt=NULL from before set_job_published started
    backfilling it on publish (see that function's own docstring) gets
    fixed automatically the first time this code is deployed, with no
    separate manual migration step. Scoped to published rows only (the
    only ones that actually need to be searchable) and re-reads real
    data from meta.json rather than guessing -- a job this can't find
    data for is skipped, not retried forever, so this doesn't get slower
    as unrelated bad rows accumulate."""
    with auth._connect() as conn:
        rows = conn.execute(
            auth._ph("SELECT job_id FROM job_index WHERE is_published = TRUE AND prompt IS NULL")
        ).fetchall()
    fixed = 0
    for row in rows:
        job_id = row["job_id"]
        try:
            meta = load_job_meta(job_id)
        except Exception:
            logger.warning("prompt backfill: could not load meta for %s", job_id, exc_info=True)
            continue
        prompt = meta.get("prompt") if meta else None
        if not prompt:
            continue
        with auth._connect() as conn:
            conn.execute(auth._ph("UPDATE job_index SET prompt = ? WHERE job_id = ?"), (prompt, job_id))
        fixed += 1
    if rows:
        logger.info("prompt backfill: fixed %d/%d published job(s) with a missing prompt", fixed, len(rows))


_backfill_missing_prompts()


def _backfill_stale_statuses() -> None:
    """One-time, idempotent reconciliation, same self-healing spirit as
    _backfill_missing_prompts above -- run once per process start (both API
    and worker import this module).

    Root cause this fixes: _record_job_index (called from every
    save_job_meta) can transiently fail to reach Postgres (confirmed in
    production logs: psycopg_pool.PoolTimeout during a redeploy overlapping
    a running job) and, unlike most of this job's status writes, a job's
    *final* transition (done/failed) never gets a natural retry -- nothing
    calls save_job_meta again after the job finishes, so a dropped write for
    that specific transition leaves job_index permanently stuck on
    whatever status the job was in before. Confirmed directly on real
    production data: a worker log showed a job completing successfully
    end-to-end ("Successfully completed ... job in 0:06:30") while every one
    of its status writes -- including the final "done" -- failed with
    PoolTimeout, leaving job_index reporting "queued" for a job that was
    actually done. 39 of 83 real jobs were affected this way as of the
    session that added this fix; separately confirmed that job_index.status
    itself isn't read by any user-facing code path today (list_jobs and
    get_job both go straight to the authoritative meta.json), so this was
    silently misleading anyone querying job_index directly -- e.g. for
    production health checks -- not actual users.

    Scoped to non-terminal rows only (done/failed jobs already have their
    correct final status, whether or not the write that got them there
    originally succeeded) and re-reads real data from meta.json rather than
    guessing, matching _backfill_missing_prompts's own approach -- a job
    this can't find data for is skipped, not retried forever."""
    with auth._connect() as conn:
        rows = conn.execute(
            auth._ph("SELECT job_id, status FROM job_index WHERE status NOT IN (?, ?)"),
            (JobStatus.DONE.value, JobStatus.FAILED.value),
        ).fetchall()
    fixed = 0
    for row in rows:
        job_id = row["job_id"]
        try:
            meta = load_job_meta(job_id)
        except Exception:
            logger.warning("status backfill: could not load meta for %s", job_id, exc_info=True)
            continue
        real_status = meta.get("status") if meta else None
        if not real_status or real_status == row["status"]:
            continue
        with auth._connect() as conn:
            conn.execute(auth._ph("UPDATE job_index SET status = ? WHERE job_id = ?"), (real_status, job_id))
        fixed += 1
    if rows:
        logger.info("status backfill: reconciled %d/%d non-terminal job_index row(s) against meta.json", fixed, len(rows))


_backfill_stale_statuses()


# How long a job can sit in a non-terminal status before it's treated as
# abandoned rather than still legitimately running. Generous relative to
# process_job's own "easily minutes" runtime and railway.worker.json's
# drainingSeconds grace period (see that file's own comment) combined --
# wide enough margin that no genuinely-still-running job should ever be
# caught by this, only ones truly orphaned by a dead worker.
_ORPHAN_THRESHOLD_SECONDS = 30 * 60


def _recover_orphaned_jobs() -> None:
    """One-time, idempotent self-healing, same pattern as
    _backfill_missing_prompts/_backfill_stale_statuses above -- run once
    per process start (both API and worker import this module), after
    _backfill_stale_statuses has already reconciled job_index against
    meta.json, so whatever's left non-terminal here really is stuck (or
    unreadable), not just stale bookkeeping that already resolved.

    Root cause this fixes: a worker process that dies mid-job (a crash, an
    OOM kill, or a deploy's SIGKILL arriving before RQ's own warm shutdown
    -- see worker.py -- can finish it) leaves that job frozen forever in
    whatever non-terminal status it was last in, with no error and no
    retry -- confirmed on real production data: two real users' first-ever
    generations died mid-pipeline when a deploy restarted the worker while
    their job was running, and neither the app nor the user ever saw
    anything but an indefinitely spinning "generating...". Increasing
    railway.worker.json's drainingSeconds gives RQ's existing warm
    shutdown (which already waits for an in-flight job to finish before
    exiting -- see rq.worker.Worker._shutdown) a real chance to succeed,
    but nothing can save a job from a genuine crash or OOM kill (SIGKILL
    bypasses graceful shutdown entirely, by definition) -- this is the
    safety net for that case, and for any other reason a worker might
    disappear mid-job.

    Scoped to jobs whose own meta.json (the actual source of truth for
    status -- see load_job_meta's own docstring on why job_index isn't)
    is still non-terminal well past any legitimate runtime for this
    pipeline -- a job this can't find meta.json for at all is left alone
    (no evidence either way, same conservative behaviour as the other two
    backfills above), not marked failed by assumption."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=_ORPHAN_THRESHOLD_SECONDS)).isoformat()
    with auth._connect() as conn:
        rows = conn.execute(
            auth._ph("SELECT job_id FROM job_index WHERE status NOT IN (?, ?) AND created_at <= ?"),
            (JobStatus.DONE.value, JobStatus.FAILED.value, cutoff),
        ).fetchall()
    recovered = 0
    for row in rows:
        job_id = row["job_id"]
        try:
            meta = load_job_meta(job_id)
        except Exception:
            logger.warning("orphan recovery: could not load meta for %s", job_id, exc_info=True)
            continue
        if meta is None or meta.get("status") in (JobStatus.DONE.value, JobStatus.FAILED.value):
            continue
        meta["status"] = JobStatus.FAILED.value
        meta["error"] = (
            "This job was interrupted before it could finish (its worker process stopped "
            "unexpectedly, e.g. during a deploy) and could not be automatically resumed. "
            "Please try generating again. Your credit for this generation has been refunded."
        )
        _write_job_meta_dict(job_id, meta)
        # The same real bug as /generate's enqueue-failure case (see
        # main.py): a credit was already spent for a job that never
        # produced anything usable. credit_source is only present on jobs
        # created after that field was added -- an older orphaned job
        # (nothing to refund correctly into, source unknown) is logged and
        # skipped rather than guessed at, same conservative "no evidence,
        # no action" stance the rest of this function already takes.
        user_id = meta.get("user_id")
        credit_source = meta.get("credit_source")
        if user_id and credit_source:
            try:
                auth.refund_credit(user_id, credit_source)
            except Exception:
                logger.warning("orphan recovery: failed to refund credit for %s", job_id, exc_info=True)
        elif user_id:
            logger.warning("orphan recovery: %s has no credit_source on record, cannot auto-refund", job_id)
        recovered += 1
    if rows:
        logger.info("orphan recovery: marked %d/%d abandoned non-terminal job(s) as failed", recovered, len(rows))


_recover_orphaned_jobs()


def _set_status(job: Job, status: JobStatus) -> None:
    job.status = status
    save_job_meta(job)


def process_job(
    job_id: str,
    prompt: str,
    target_size_studs: int,
    user_id: str,
    instructions_unlocked: bool,
    created_at: str,
) -> None:
    """The actual pipeline: prompt -> image -> mesh -> LEGO parts ->
    LDraw. Runs in the worker process when REDIS_URL is set (enqueued via
    QUEUE.enqueue in main.py) or in-process via BackgroundTasks otherwise
    (see main.py's generate() -- local dev without Redis running still
    works, matching every other phase's local-fallback pattern). Takes
    plain primitives rather than a Job object deliberately: RQ pickles
    whatever it enqueues, and passing a mutable object across the process
    boundary would invite the mistake of assuming mutations are visible to
    the caller, which they never are once this runs in a separate process."""
    job = Job(
        id=job_id,
        prompt=prompt,
        target_size_studs=target_size_studs,
        created_at=created_at,
        user_id=user_id,
        instructions_unlocked=instructions_unlocked,
    )
    jdir = _job_dir(job.id)
    try:
        _set_status(job, JobStatus.GENERATING_IMAGE)
        image_client = get_image_client()
        image_prompt = build_image_prompt(job.prompt)
        image_path = os.path.join(jdir, "reference.png")
        image_client.generate(image_prompt, image_path)
        job.image_path = image_path
        STORAGE.put(job.id, "reference.png", image_path)

        _set_status(job, JobStatus.GENERATING_MESH)
        mesh_client = get_mesh_client()
        mesh_path = os.path.join(jdir, "model.glb")
        mesh_client.generate(image_path, mesh_path)
        job.mesh_path = mesh_path
        STORAGE.put(job.id, "model.glb", mesh_path)

        _set_status(job, JobStatus.BUILDING_BRICKS)
        ldr_path = os.path.join(jdir, "model.ldr")
        pdf_path = os.path.join(jdir, "instructions.pdf")
        stats = mesh_to_ldr(
            mesh_path,
            ldr_path,
            target_studs=target_size_studs,
            model_name=job.prompt[:40],
            reference_image_path=image_path,
            pdf_out_path=pdf_path,
            prompt=job.prompt,
        )
        job.ldr_path = ldr_path
        STORAGE.put(job.id, "model.ldr", ldr_path)
        if stats.get("pdf_generated"):
            job.pdf_path = pdf_path
            STORAGE.put(job.id, "instructions.pdf", pdf_path)
        job.part_count = stats["part_count"]
        job.slope_count = stats["slope_count"]
        job.tile_count = stats["tile_count"]
        job.color_count = stats["color_count"]
        job.color_source = stats["color_source"]
        job.was_repaired = stats["was_repaired"]
        job.still_critical_count = stats["still_critical_count"]
        job.is_single_piece = stats["is_single_piece"]
        job.symmetrized = stats.get("symmetrized", False)
        _set_status(job, JobStatus.DONE)

    except Exception as exc:  # noqa: BLE001
        job.error = f"{exc}\n{traceback.format_exc()}"
        _set_status(job, JobStatus.FAILED)
