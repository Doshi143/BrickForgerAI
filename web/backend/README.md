# Prompt-to-LEGO backend

Pipeline: **text prompt → AI image → 3D mesh → real LEGO bricks → LDraw
file**, served over a small FastAPI job API for the Next.js frontend in
`../frontend`.

## Status

| Stage | File | Status |
|---|---|---|
| Prompt → image | `app/clients/image_gen.py` | **Working** — `OpenAIImageClient` calls OpenAI's `gpt-image-1` image endpoint. Needs `IMAGE_GEN_PROVIDER=openai` + `IMAGE_GEN_API_KEY` (or `OPENAI_API_KEY`) in `.env`. |
| Image → mesh | `app/clients/mesh_gen.py` | **Working.** Default provider is `fal_trellis2` (`FalTrellis2Client`) — hosted `fal-ai/trellis-2` over fal.ai's queue API, needs only `FAL_KEY`, no local GPU. `trellis_local` (`TrellisComfyUIClient`) remains available as an opt-in for offline dev — it calls a **locally-run** ComfyUI server (default `http://127.0.0.1:8188`) running a TRELLIS 2 workflow that you run yourself; this backend does not install or start it. Never point either at the original (non-"2") TRELLIS/`fal-ai/trellis` — that model is shape-only (see CLAUDE.md). |
| Mesh → repaired, refined, colored LDraw model | `app/pipeline/brickforge_bridge.py` | **Working, tested.** Thin adapter over `core/brickforge` (this repo's own pipeline — see the repo root `CLAUDE.md`/`DESIGN.md`): voxelize → shell → color-quantize → legalize → structural repair (bridge/refill/prune) → slope/tile surface refinement → LDR. Replaces this project's original naive greedy voxel coverer. |
| Stability check + instructions | *(external)* | Not built — open the exported `.ldr` in **BrickLink Studio** (free) for a second opinion, its Stability tool, and Instruction Maker. |

## Setup

`core/brickforge` (this repo's own package, one level up from `web/`) must
be installed editable so `import brickforge` works from this backend:

```bash
pip install -r requirements.txt
pip install -e ../../core
```

Test the brickforge-backed pipeline stage directly, no API keys or ComfyUI
needed (uses the bundled `app/tests/sample_hull.glb`):

```bash
python3 app/tests/test_pipeline_end_to_end.py
```

Run the API server (the frontend expects this on port 8000):

```bash
uvicorn app.main:app --reload --port 8000
```

Copy `.env.example` to `.env` and fill in real values (`.env` itself is
gitignored — never commit real keys).

Without a working image/mesh provider, `POST /generate` will run, hit the
image generation stage, and fail cleanly with a clear error surfaced via
`GET /generate/{id}` — this is expected and confirms the orchestration
works correctly even without live credentials.

## Known limitations / where to improve next

1. **In-memory job store in `main.py`** — fine for local trial use, not for
   concurrent production users. `/generate` now runs the pipeline via
   FastAPI `BackgroundTasks` (not fully synchronous anymore, so polling
   `GET /generate/{id}` shows real incremental progress) — still not a
   real task queue; swap for one (Celery/RQ + Redis, or similar) plus
   object storage before going live. None of the pipeline code needs to
   change for that.
2. ~~**`brickforge_bridge.py`'s texture→vertex-color fallback is defensive,
   not the expected path**~~ — superseded. The `TextureVisuals` branch is
   now the expected path for the default provider: `fal-ai/trellis-2`
   returns `TextureVisuals` meshes (verified on a real generation — 18,310
   unique baked vertex colors on ~367k vertices, `color_source: "texture"`
   through the real `_prepare_colored_mesh`), while local ComfyUI TRELLIS 2
   returns `ColorVisuals` directly. Both paths are now real, exercised
   paths, not one live and one defensive.
3. Whatever `core/brickforge`'s own `CLAUDE.md` documents as open
   (curved slopes, 33°/65°/75° slope families, CIELAB color quantization,
   inventory/purchasability checks) is open here too, unchanged — this
   backend doesn't duplicate that pipeline, it calls it.

## Legal reminders baked into this design

- No LEGO branding anywhere in this codebase's naming — keep your
  product name and marketing "brick-compatible," not "LEGO."
- Nothing here trains on or scrapes Rebrickable — their ToS explicitly
  prohibits using their content for AI training.
- The generation pipeline produces **original** models from prompts, not
  reproductions of existing copyrighted sets/characters — keep it that
  way in how you prompt-engineer and market this.
