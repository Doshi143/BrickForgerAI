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
import os
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import redis
from rq import Queue

from .clients.image_gen import build_image_prompt, get_image_client
from .clients.mesh_gen import get_mesh_client
from .pipeline.brickforge_bridge import mesh_to_ldr
from .storage import R2Storage, get_storage

JOBS_DIR = os.path.join(os.path.dirname(__file__), "..", "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

STORAGE = get_storage()

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
    status: JobStatus = JobStatus.QUEUED
    error: str | None = None
    image_path: str | None = None
    mesh_path: str | None = None
    ldr_path: str | None = None
    part_count: int | None = None
    slope_count: int | None = None
    tile_count: int | None = None
    color_count: int | None = None
    color_source: str | None = None
    was_repaired: bool | None = None
    still_critical_count: int | None = None
    is_single_piece: bool | None = None


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
        "ldr_download_url": f"/generate/{job.id}/download" if job.ldr_path else None,
        "thumbnail_url": f"/generate/{job.id}/thumbnail" if job.image_path else None,
        "has_render": STORAGE.exists(job.id, "render.png"),
    }


def _write_job_meta_dict(job_id: str, data: dict) -> None:
    path = os.path.join(_job_dir(job_id), "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    STORAGE.put(job_id, "meta.json", path)


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
        stats = mesh_to_ldr(
            mesh_path,
            ldr_path,
            target_studs=target_size_studs,
            model_name=job.prompt[:40],
            reference_image_path=image_path,
        )
        job.ldr_path = ldr_path
        STORAGE.put(job.id, "model.ldr", ldr_path)
        job.part_count = stats["part_count"]
        job.slope_count = stats["slope_count"]
        job.tile_count = stats["tile_count"]
        job.color_count = stats["color_count"]
        job.color_source = stats["color_source"]
        job.was_repaired = stats["was_repaired"]
        job.still_critical_count = stats["still_critical_count"]
        job.is_single_piece = stats["is_single_piece"]
        _set_status(job, JobStatus.DONE)

    except Exception as exc:  # noqa: BLE001
        job.error = f"{exc}\n{traceback.format_exc()}"
        _set_status(job, JobStatus.FAILED)
