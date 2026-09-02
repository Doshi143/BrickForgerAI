"""One-off empirical sweep for recalibrating the web app's Small/Medium/
Large stud-size presets (see CLAUDE.md and the user's request: Small
200-1000 parts, Medium 1000-2000, Large 2000+). Part count depends on the
NEW pipeline behavior (Stage B seam-penalty loosening + the 33-degree slope
family), so this runs after both land, against real meshes rather than
picked blind.

Measures FINAL part count (after bridge -> refill -> prune -> slope
substitution -> tile substitution, i.e. everything a real job actually
produces) at a range of stud sizes, for every real mesh available locally:
duck.glb (glTF sample asset), the Stanford bunny, and two real generated-job
meshes already on disk (a rocket and a cactus, from earlier trial-app
testing).

Run:
    python examples/size_sweep.py
"""
from __future__ import annotations

import time
from pathlib import Path

from brickforge.pipeline.mesh_to_model import mesh_to_model_full
from brickforge.pipeline.slopes import substitute_staircase_slopes
from brickforge.pipeline.surface_refine import substitute_tiles
from brickforge.structure import bridge_unstable, refill_enclosed_holes

CORE_DIR = Path(__file__).parent
MESHES = {
    "duck": CORE_DIR / "meshes" / "duck.glb",
    "bunny": CORE_DIR / "meshes" / "stanford-bunny.obj",
    "rocket": CORE_DIR.parent.parent / "web" / "backend" / "jobs" / "6299409c-d419-423d-8917-b1cdc29075e2" / "model.glb",
    "cactus": CORE_DIR.parent.parent / "web" / "backend" / "jobs" / "75cf3d6d-41b0-4da4-9716-7bd28b50ed0a" / "model.glb",
}

STUD_SIZES = [8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40]


def final_part_count(mesh_path: Path, studs: int) -> int:
    result = mesh_to_model_full(mesh_path, studs)
    bridged = bridge_unstable(result.model, solid_grid=result.solid_grid)
    refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
    sloped = substitute_staircase_slopes(refilled.model)
    refined = substitute_tiles(sloped.model)
    return len(refined)


def main() -> None:
    for name, path in MESHES.items():
        if not path.exists():
            print(f"skipping {name}: {path} not found")
            continue
        print(f"\n=== {name} ===")
        for studs in STUD_SIZES:
            start = time.time()
            try:
                count = final_part_count(path, studs)
            except Exception as exc:  # noqa: BLE001 -- report and keep sweeping
                print(f"  studs={studs:3d}: FAILED ({exc})")
                continue
            elapsed = time.time() - start
            print(f"  studs={studs:3d}: {count:5d} parts  ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
