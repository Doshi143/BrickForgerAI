# BrickForge trial web app

Prompt → image → 3D mesh → structurally-repaired, surface-refined, colored
brick model you can view in the browser and download as `.ldr`.

```
web/
  backend/    FastAPI job API; calls core/brickforge for the mesh->bricks work
  frontend/   Next.js 16 app (landing page + live job page with a 3D viewer)
```

## Running it

Three pieces, all local. Start them in this order.

**1. ComfyUI + TRELLIS (you run this yourself)**

The image→mesh stage posts to a local ComfyUI server, by default
`http://127.0.0.1:8188`, running the workflow bundled at
`backend/app/clients/trellis_workflow_api.json`. This repo does not install
or start it. Check it's up:

```bash
curl http://127.0.0.1:8188/system_stats
```

**2. Backend** (port 8000)

```bash
cd web/backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pip install -e ../../core
cp .env.example .env    # then fill in your real OpenAI key
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

**3. Frontend** (port 3000)

```bash
cd web/frontend
npm install
npm run dev
```

Then open http://localhost:3000, type a prompt, and hit Generate.

Both servers are also defined in `.claude/launch.json` as `backend` and
`frontend`.

## Verifying without API keys or a GPU

The brickforge stage runs standalone on a bundled test mesh — no OpenAI
key, no ComfyUI needed:

```bash
cd web/backend
.venv/Scripts/python app/tests/test_pipeline_end_to_end.py
```

## A known limitation you should know about

The bundled TRELLIS workflow is **shape-only** — it has no
texture/appearance stage, so the meshes it returns carry no color at all
(verified: every vertex identical gray). Colors in the final model are
therefore projected from the reference image by
`backend/app/pipeline/reference_color.py`, which is an orthographic
approximation of a three-quarter-view photo: broadly right (a red car comes
out red), but front and back faces get mirrored colors and the mapping is
skewed rather than exact.

The real fix is adding TRELLIS's texture stage to the ComfyUI workflow. That
module detects a genuinely-textured mesh and stops firing on its own, with
no code change needed.

## What isn't built

No auth, no payments, no persistent storage, no real task queue — the job
store is an in-memory dict, which is fine for local trial use and not for
concurrent users. See `DESIGN.md` §9 for the intended shape of the rest.
