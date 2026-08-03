"""
Runs the fully-free portion of the pipeline (everything after the mesh
already exists) on a synthetic test mesh, and prints a report.

This stands in for what happens after TRELLIS hands back a .glb file --
swap sample_hull.glb for a real TRELLIS response and nothing else in this
script changes. Needs core/brickforge installed editable (see README.md).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.pipeline.brickforge_bridge import mesh_to_ldr

MESH_PATH = os.path.join(os.path.dirname(__file__), "sample_hull.glb")
OUT_PATH = os.path.join(os.path.dirname(__file__), "sample_hull_output.ldr")


def main():
    print(f"Running mesh -> repaired, refined, colored LDraw model on {MESH_PATH}...")
    stats = mesh_to_ldr(MESH_PATH, OUT_PATH, target_studs=24, model_name="Test Hull")
    print(f"  {stats}")
    print(f"Wrote {OUT_PATH}")

    if stats["still_critical_count"] > 0:
        print(
            f"  NOTE: {stats['still_critical_count']} part(s) are still critical after "
            "repair (e.g. overloaded connections) -- this is a real, informational "
            "finding, not a bug in this test."
        )

    print("\nDone. Open the .ldr file in BrickLink Studio to see the "
          "actual model, run its stability checker, and generate "
          "instructions.")


if __name__ == "__main__":
    main()
