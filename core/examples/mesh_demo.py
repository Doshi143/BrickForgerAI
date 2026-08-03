"""Phase 1 milestone: run a synthetic two-color mesh through the full
brickify pipeline (voxelize -> shell -> quantize -> legalize -> LDR).

No image-gen/mesh-gen API is wired up yet (DESIGN.md scopes that as bought-in
infrastructure, separate from the brickify algorithm this phase is about),
so the input here is generated programmatically with trimesh primitives: a
tan cylinder "stem" with a red sphere "cap", loosely mushroom-shaped. This
exercises every pipeline stage -- multi-region occupancy, two colors,
shelling, tiling, brick consolidation -- without depending on a download or
an API key.

Run:
    python examples/mesh_demo.py
"""

from pathlib import Path

import numpy as np
import trimesh

from brickforge import save_ldr
from brickforge.pipeline.mesh_to_model import mesh_to_model

STEM_RGBA = [180, 140, 90, 255]
CAP_RGBA = [196, 40, 27, 255]


def build_mesh() -> trimesh.Trimesh:
    stem = trimesh.creation.cylinder(radius=6, height=20, sections=24)
    # trimesh.creation.cylinder's "height" runs along local Z by default,
    # not Y -- verified by checking .extents ([12, 12, 20], i.e. round in
    # X-Y, tall in Z) before assuming it. Rotate the Z axis onto Y so the
    # stem actually stands upright instead of lying on its side as a
    # squashed disk (which is what silently produced a rectangular slab
    # instead of a cylinder in the first version of this script).
    stem.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    stem.apply_translation([0, 10, 0])  # sits on Y=0, top at Y=20
    stem.visual.vertex_colors = np.tile(STEM_RGBA, (len(stem.vertices), 1))

    cap = trimesh.creation.icosphere(subdivisions=3, radius=11)
    cap.apply_translation([0, 20, 0])  # centered at the stem's top
    cap.visual.vertex_colors = np.tile(CAP_RGBA, (len(cap.vertices), 1))

    return trimesh.util.concatenate([stem, cap])


def main() -> None:
    mesh = build_mesh()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    mesh_path = out_dir / "mushroom_source.glb"
    mesh.export(mesh_path)

    model = mesh_to_model(mesh_path, target_width_studs=24)
    print(f"Legalized model: {len(model)} parts")

    out_path = out_dir / "mushroom.ldr"
    save_ldr(model, out_path, name="BrickForgerAI Phase 1 Mushroom")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
