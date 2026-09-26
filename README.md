# BrickForgerAI

Turn a text prompt into a physically buildable brick model, exported as a
`.ldr` file with a parts list and a step-by-step PDF build guide - built
from real, purchasable brick/plate/tile/slope parts, with every
connection checked so the model holds together.

Two generation modes:

- **Voxel** (1 credit) - the prompt becomes a picture, the picture becomes
  a 3D mesh, and the mesh is voxelized onto a real stud/plate lattice,
  repaired so it won't fall apart, and refined with slopes and tiles. Best
  on organic shapes.
- **Detailed (beta)** (2 credits) - Claude designs the model piece by piece
  in a compact spec language, and a deterministic engine builds and checks
  it, sending problems back for fixing. Uses real building techniques
  (curved slopes, round bricks, windows, doors, wheels, plants, sideways
  building). Best on buildings, vehicles and animals.

Live at [brickforgerai.com](https://brickforgerai.com).

Not affiliated with, endorsed, or sponsored by the LEGO Group. Part
geometry comes from the [LDraw](https://www.ldraw.org/) parts library,
licensed under CCAL 2.0.

## Contents

- [Repo layout](#repo-layout)
- [Quickstart: the Voxel pipeline](#quickstart-the-voxel-pipeline)
- [Quickstart: the Detailed designer](#quickstart-the-detailed-designer)
- [Quickstart: the web app](#quickstart-the-web-app)
- [Status](#status)
- [License](#license)

## Repo layout

| Path | What's there |
|---|---|
| `core/` | `brickforge` - the Voxel pipeline (voxelize -> shell -> color-quantize -> legalize -> structural repair -> surface refinement -> LDR), a standalone, tested Python library + CLI. |
| `core/brickforge/` | The library: lattice + part catalog, pipeline stages, structural analysis/repair, SNOT (sideways-building) placement. |
| `core/examples/` | Runnable scripts that produce the example models and stability reports. |
| `designer/` | `brickforge_designer` - Detailed mode: the `.bfd` spec language, the engine that builds and checks it, the prompt Claude designs with (`PROMPT.md`), and the evaluation tools. `TECHNIQUES.md` lists the building techniques and their status. |
| `web/` | The live Next.js frontend + FastAPI backend behind brickforgerai.com - accounts, credits, Stripe billing, a Redis/RQ job queue, the Discover gallery, wired to image/mesh generation, `core` and `designer`. See [`web/README.md`](web/README.md). |
| `viewer/` | A standalone three.js LDR viewer (drag-and-drop any `.ldr`/`.mpd` file). |

## Quickstart: the Voxel pipeline

```bash
cd core
pip install -e ".[dev]"
pytest -q                                       # full test suite

python examples/structural_report.py            # stability report + repair
                                                # on the bundled example models

brickforge-cli mesh.glb --studs 24 -o out.ldr   # run the pipeline directly
                                                # on any mesh file
```

## Quickstart: the Detailed designer

Building a spec is free and offline; only designing a new one from a
prompt calls the Claude API (needs `ANTHROPIC_API_KEY`).

```bash
cd designer
pip install -e ".[dev]"
python -m pytest -q                                          # full test suite

python -m brickforge_designer.pipeline specs/house.bfd       # build + check a spec
python -m brickforge_designer.pipeline --api --prompt "a red fire truck" --size 24
```

Output (`.ldr`, plus a report of anything loose or unsupported) goes to
`designer/out/`.

## Quickstart: the web app

See [`web/README.md`](web/README.md) for running the frontend, backend and
worker locally (parts of it predate Detailed mode). The backend reads its
settings from `web/backend/.env` - start from `.env.example`:

- **Voxel:** `IMAGE_GEN_PROVIDER=openai` with an OpenAI key (prompt ->
  picture) and `MESH_GEN_PROVIDER=fal_trellis2` with `FAL_KEY` (picture ->
  mesh, hosted TRELLIS 2). A locally run TRELLIS/ComfyUI is optional.
- **Detailed:** `ANTHROPIC_API_KEY` and `DETAILED_MODE_ENABLED=true` on the
  API and the worker; `DETAILED_MODE_ALLOWLIST` (comma-separated emails)
  limits it to those accounts, and leaving it empty opens it to everyone.
- Never run the backend locally with the production `DATABASE_URL` /
  `REDIS_URL` - blank them first.

## Status

- The Voxel pipeline (lattice, catalog, legalizer, structural repair,
  tiles and slopes, SNOT side panels) is done and tested.
- Detailed mode has been live for everyone since 2026-09-26, as a beta.
- The web app is in production at brickforgerai.com with real Stripe
  payments (subscriptions, top-ups, and buying builds from Discover). Failed
  generations refund their credits automatically, and if an AI provider
  runs out of credit, users are told generation is paused.
- The project is in maintenance mode: the site stays live, but no new
  features are planned for now.

## License

Source-available, not open-source: no license is granted, all rights
reserved. This code is public for visibility, not for reuse, modification,
or redistribution. (LDraw part geometry remains separately licensed under
CCAL 2.0 - see above.)
