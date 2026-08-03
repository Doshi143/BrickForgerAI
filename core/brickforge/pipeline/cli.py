"""CLI: brickforge-cli mesh.glb --studs 24 -o out.ldr

See DESIGN.md sec. 9 (Phase 1 milestone): "a recognizable, hollow,
buildable model from a downloaded mesh."
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..ldr_writer import save_ldr
from .mesh_to_model import mesh_to_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a 3D mesh into an LDR brick model.")
    parser.add_argument("mesh", help="Path to the input mesh (any format trimesh can load: .glb, .obj, .stl, ...)")
    parser.add_argument("--studs", type=int, default=24, help="Target width, in studs, of the model's largest horizontal extent")
    parser.add_argument("-o", "--output", required=True, help="Output .ldr path")
    parser.add_argument("--shell-thickness", type=int, default=2, help="Shell thickness in grid cells")
    parser.add_argument("--support-pitch", type=int, default=5, help="Internal support wall spacing in studs")
    parser.add_argument("--seed", type=int, default=0, help="Legalizer randomized-restart seed (reproducibility)")
    parser.add_argument("--restarts", type=int, default=5, help="Legalizer tiling attempts per layer (1 = deterministic only)")
    args = parser.parse_args()

    model = mesh_to_model(
        args.mesh,
        args.studs,
        shell_thickness=args.shell_thickness,
        support_pitch=args.support_pitch,
        seed=args.seed,
        restarts=args.restarts,
    )

    out_path = Path(args.output)
    save_ldr(model, out_path, name=out_path.stem)
    print(f"{len(model)} parts -> {out_path}")


if __name__ == "__main__":
    main()
