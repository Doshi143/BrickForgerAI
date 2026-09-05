# BrickForgerAI

Turn a text prompt into a physically buildable brick sculpture: a full
pipeline that voxelizes a 3D shape onto a real stud/plate lattice, checks
it won't fall apart, refines the surface with slopes and tiles, and
exports a `.ldr` file plus a parts list — built from real, purchasable
brick/plate/tile/slope parts, not an abstraction.

Live at [brickforgerai.com](https://brickforgerai.com).

Not affiliated with, endorsed, or sponsored by the LEGO Group. Part
geometry comes from the [LDraw](https://www.ldraw.org/) parts library,
licensed under CCAL 2.0.

## Contents

- [Repo layout](#repo-layout)
- [Quickstart: the core pipeline](#quickstart-the-core-pipeline)
- [Quickstart: the trial web app](#quickstart-the-trial-web-app)
- [Status](#status)
- [License](#license)

## Repo layout

| Path | What's there |
|---|---|
| `core/` | `brickforge` — the actual pipeline (voxelize → shell → color-quantize → legalize → structural repair → surface refinement → LDR), a standalone, tested Python library + CLI. |
| `core/brickforge/` | The library: lattice + part catalog, pipeline stages, structural analysis/repair, SNOT (sideways-building) placement. |
| `core/examples/` | Runnable scripts that produce the example models/reports referenced above. |
| `core/tests/` | Full pytest suite. |
| `web/` | The live Next.js frontend + FastAPI backend behind brickforgerai.com — accounts, credits, Stripe billing, a Redis/RQ job queue, wired to image/mesh generation and the `core` pipeline. See [`web/README.md`](web/README.md). |
| `viewer/` | A standalone three.js LDR viewer (drag-and-drop any `.ldr`/`.mpd` file). |

## Quickstart: the core pipeline

```bash
cd core
pip install -e ".[dev]"
pytest -q                                       # full test suite

python examples/structural_report.py            # stability report + repair
                                                 # on the bundled example models

brickforge-cli mesh.glb --studs 24 -o out.ldr    # run the pipeline directly
                                                 # on any mesh file
```

## Quickstart: the trial web app

See [`web/README.md`](web/README.md) — it needs a local TRELLIS/ComfyUI
server (image → mesh) and an OpenAI API key (prompt → image); the
brickforge stage itself runs with neither, against a bundled test mesh.

## Status

Phases 0–3 (lattice/catalog/LDR export, the legalizer, structural analysis
+ repair, and surface refinement — tiles plus two slope tiers) are done and
tested. SNOT (sideways/side-stud building) is in active development. The
web app in `web/` is live in production at brickforgerai.com — real Stripe
payments, a persistent Redis/RQ job queue, and real users, not a local-only
trial.

## License

Source-available, not open-source: no license is granted, all rights
reserved. This code is public for visibility, not for reuse, modification,
or redistribution. (LDraw part geometry remains separately licensed under
CCAL 2.0 — see above.)
