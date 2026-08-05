"""FastAPI backend for the prompt -> LEGO-instructions pipeline."""
from __future__ import annotations

import base64
import json
import os
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from dotenv import load_dotenv

# Explicitly anchored to this package's own directory rather than the bare
# load_dotenv() default, which resolves .env relative to the *current working
# directory* -- so running uvicorn from the repo root (or anywhere but
# web/backend) silently loaded no config at all and every job failed with
# "No image generation provider configured".
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth
from .clients.image_gen import build_image_prompt, get_image_client
from .clients.mesh_gen import get_mesh_client
from .pipeline.brickforge_bridge import mesh_to_ldr

auth.init_db()

app = FastAPI(title="Prompt-to-LEGO Backend")
app.include_router(auth.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR = os.path.join(os.path.dirname(__file__), "..", "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)


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


# In-memory for jobs created since this process started; meta.json on disk
# (see _save_job_meta) is what survives a backend restart -- both the
# Gallery listing and single-job lookups below fall back to it, so an old
# link doesn't just 404 the moment `--reload` fires during development.
JOBS: dict[str, Job] = {}


class GenerateRequest(BaseModel):
    prompt: str
    target_size_studs: int = 32


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    credits_remaining: int


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
        # Distinct from thumbnail_url (which is truthy the moment there's
        # any fallback image at all -- see get_thumbnail): lets the gallery
        # tell "already has a real 3D render" apart from "still serving the
        # AI reference photo because nobody's browser has ever rendered
        # this job's model yet" -- there's no server-side LDraw renderer in
        # this trial app, so that's the only way a render.png gets made.
        "has_render": os.path.isfile(os.path.join(JOBS_DIR, job.id, "render.png")),
    }


def _save_job_meta(job: Job) -> None:
    path = os.path.join(_job_dir(job.id), "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_job_to_dict(job), f)


def _load_job_meta(job_id: str) -> dict | None:
    path = os.path.join(JOBS_DIR, job_id, "meta.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # has_render can't be baked into the saved snapshot: render.png is
    # captured asynchronously by whichever browser first opens this job's
    # model, which can happen long after the job (and its meta.json) was
    # written -- including by the gallery's own backfill render. Recompute
    # it fresh on every read instead of trusting the stored value, or a
    # freshly-backfilled render would never be reflected here and the
    # gallery would keep re-rendering a job that already has a thumbnail.
    data["has_render"] = os.path.isfile(os.path.join(JOBS_DIR, job_id, "render.png"))
    return data


def _set_status(job: Job, status: JobStatus) -> None:
    job.status = status
    _save_job_meta(job)


def run_pipeline(job: Job, target_size_studs: int) -> None:
    """Run prompt -> image -> mesh -> LEGO parts -> LDraw."""
    jdir = _job_dir(job.id)
    try:
        _set_status(job, JobStatus.GENERATING_IMAGE)
        image_client = get_image_client()
        image_prompt = build_image_prompt(job.prompt)
        image_path = os.path.join(jdir, "reference.png")
        image_client.generate(image_prompt, image_path)
        job.image_path = image_path

        _set_status(job, JobStatus.GENERATING_MESH)
        mesh_client = get_mesh_client()
        mesh_path = os.path.join(jdir, "model.glb")
        mesh_client.generate(image_path, mesh_path)
        job.mesh_path = mesh_path

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


@app.post("/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(auth.get_current_user),
) -> GenerateResponse:
    if not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")

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
    JOBS[job_id] = job
    _save_job_meta(job)

    # Runs after this request returns, so /generate responds immediately
    # with status=queued and the frontend can poll GET /generate/{id} to
    # watch it move through the real JobStatus phases -- without this, the
    # request itself would block until the whole pipeline (image gen +
    # TRELLIS + brickforge) finished, making that enum pointless.
    background_tasks.add_task(run_pipeline, job, req.target_size_studs)

    return GenerateResponse(job_id=job_id, status=job.status, credits_remaining=user.credits_remaining)


@app.get("/generate")
def list_jobs(month_only: bool = True) -> list[dict]:
    """Gallery data: every *completed* job, newest first. Reads meta.json
    files directly off disk (not the in-memory JOBS dict) so this survives
    a backend restart, same reasoning as get_job's fallback below."""
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    for entry in os.listdir(JOBS_DIR):
        if not os.path.isdir(os.path.join(JOBS_DIR, entry)):
            continue
        data = _load_job_meta(entry)
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
    return results


def _get_job_dict_or_404(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is not None:
        return _job_to_dict(job)

    data = _load_job_meta(job_id)
    if data is not None:
        return data

    raise HTTPException(404, "job not found")


@app.get("/generate/{job_id}")
def get_job(job_id: str) -> dict:
    return _get_job_dict_or_404(job_id)


@app.get("/generate/{job_id}/preview")
def preview_ldr(job_id: str) -> FileResponse:
    """Unrestricted -- this is what the in-browser 3D viewer fetches to
    render the free preview (per the pricing page, the preview itself is
    free on every plan). Deliberately separate from /download below, which
    is the actual "save this file to your computer" action and IS gated."""
    ldr_path = os.path.join(JOBS_DIR, job_id, "model.ldr")
    if not os.path.isfile(ldr_path):
        raise HTTPException(404, "file not ready")
    # no-store: without an explicit Cache-Control, browsers are free to
    # reuse a cached copy of this exact URL indefinitely on heuristics
    # alone -- harmless for a normal job (model.ldr never changes after
    # completion) but a real, confirmed bug the moment a job's file is
    # ever regenerated in place (as happened when re-running existing jobs
    # through an updated brickforge pipeline): the stats panel (a fresh
    # JSON fetch) showed the new part count while the 3D viewer kept
    # rendering the stale cached geometry.
    return FileResponse(ldr_path, media_type="text/plain", headers={"Cache-Control": "no-store"})


@app.get("/generate/{job_id}/download")
def download_ldr(job_id: str) -> FileResponse:
    """Gated behind instructions_unlocked (free-plan pay-per-model, or
    included automatically for pro-plan jobs -- see generate()). The 3D
    preview (GET .../preview, above) is intentionally not behind this
    gate; only actually saving the file is."""
    data = _get_job_dict_or_404(job_id)
    if not data.get("instructions_unlocked"):
        raise HTTPException(402, "Unlock instructions to download this model's .ldr file")

    ldr_path = os.path.join(JOBS_DIR, job_id, "model.ldr")
    if not os.path.isfile(ldr_path):
        raise HTTPException(404, "file not ready")
    return FileResponse(ldr_path, filename=f"{job_id}.ldr")


@app.post("/generate/{job_id}/unlock-instructions")
def unlock_instructions(job_id: str, user: auth.User = Depends(auth.get_current_user)) -> dict:
    """Mock purchase: marks a free-plan job's instructions as unlocked with
    no real payment behind it (Stripe is explicitly deferred -- see the
    pricing page and auth.py's module docstring). Exists so the pricing
    model has a real, working data flow end to end; wiring an actual
    charge here is the next step, not a rewrite of this endpoint."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.user_id != user.id:
        raise HTTPException(403, "not your job")

    job.instructions_unlocked = True
    _save_job_meta(job)
    return _job_to_dict(job)


@app.get("/generate/{job_id}/thumbnail")
def get_thumbnail(job_id: str) -> FileResponse:
    """Prefers an actual render of the finished brick model (render.png,
    captured client-side by the 3D viewer -- see RenderCapture below) over
    the AI-generated reference photo (reference.png), since the gallery
    should show what got built, not the prompt image that inspired it.
    Falls back to the reference photo only if a render was never
    captured (e.g. nobody has opened that job's results page yet)."""
    jdir = os.path.join(JOBS_DIR, job_id)
    render_path = os.path.join(jdir, "render.png")
    if os.path.isfile(render_path):
        # no-store: same reasoning as preview_ldr above -- render.png gets
        # overwritten in place (a new capture from the 3D viewer, or a
        # regenerated job), and this URL never changes, so a browser must
        # not be allowed to keep serving a stale cached image for it.
        return FileResponse(render_path, media_type="image/png", headers={"Cache-Control": "no-store"})

    reference_path = os.path.join(jdir, "reference.png")
    if os.path.isfile(reference_path):
        return FileResponse(reference_path, media_type="image/png", headers={"Cache-Control": "no-store"})

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
    with open(os.path.join(jdir, "render.png"), "wb") as f:
        f.write(png_bytes)
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
