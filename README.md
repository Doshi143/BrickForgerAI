# BrickForgerAI

Turn a text prompt into a physically buildable brick sculpture: a full
pipeline that voxelizes a 3D shape onto a real stud/plate lattice, checks
it won't fall apart, refines the surface with slopes and tiles, and
exports a `.ldr` file plus a parts list — built from real, purchasable
brick/plate/tile/slope parts, not an abstraction.

Not affiliated with, endorsed, or sponsored by the LEGO Group. Part
geometry comes from the [LDraw](https://www.ldraw.org/) parts library,
licensed under CCAL 2.0.

## Layout

```
core/     brickforge — the actual pipeline (voxelize → shell → color-quantize
          → legalize → structural repair → surface refinement → LDR), as a
          standalone, tested Python library + CLI.
web/      A trial Next.js frontend + FastAPI backend wiring that pipeline to
          image generation and mesh reconstruction, with accounts, credits,
          and a pricing model. See web/README.md to run it.
viewer/   A standalone three.js LDR viewer (drag-and-drop any .ldr/.mpd file).
```

`DESIGN.md` has the full architecture, algorithm references, and roadmap.
`CLAUDE.md` has the detailed build history — what's been tried, measured,
and fixed, and why — kept current as work progresses.

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

Phases 0–2 (lattice/catalog/LDR export, the legalizer, and structural
analysis + repair) are done and tested. Phase 3 (surface refinement —
tiles, two slope tiers) is in progress. The trial web app in `web/` is an
early Phase 4/5 slice (no payments, no persistent job queue yet). See
`CLAUDE.md` for exactly what's been measured and what's still open.

## License

Source-available, not open-source: no license is granted, all rights
reserved. This code is public for visibility, not for reuse, modification,
or redistribution. (LDraw part geometry remains separately licensed under
CCAL 2.0 — see above.)
