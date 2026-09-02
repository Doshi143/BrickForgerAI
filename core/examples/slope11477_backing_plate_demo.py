"""Builds examples/output/slope11477_backing_plate_demo.ldr -- a minimal
file to confirm the backing-plate fix (see _NEEDS_ANCHOR_BACKING_PLATE in
slopes.py) actually fires: 11477's own real geometry has no material under
its own anchor cell (the thick/tall end), so the substitution now places a
real 1x1 plate (3024) there to close that gap.

Elevated one plate off the ground (y0=1, not y0=0) specifically so there's
room below the anchor cell for that backing plate to land -- the same
scenario as slope11477_test.py would just place the pair at y=0, where the
y >= 1 guard correctly skips adding one (nothing to place below the
baseplate itself).
"""
from __future__ import annotations

from brickforge import Model, PartCatalog, Rotation, save_ldr
from brickforge.pipeline.slopes import substitute_staircase_slopes

RED = 4


def main() -> None:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # ground support under the uphill column
    model.place("3005", RED, x=0, y=3, z=-1)  # uphill support, elevated to match the pair
    # Deliberately nothing at (0, 0, 0) -- the pair's own column is empty
    # below y=1, so the new backing plate is the ONLY thing this demo adds
    # between the slope and open space, making it easy to see in isolation.
    model.place("3023", RED, x=0, y=1, z=0, rotation=Rotation.YAW_90)  # candidate, lower plate
    model.place("3023", RED, x=0, y=2, z=0, rotation=Rotation.YAW_90)  # candidate, upper plate

    refined = substitute_staircase_slopes(model)
    print(f"{len(refined)} parts:")
    for b in refined.bricks:
        print(f"  {b.part.id} at {b.pos} rotation={b.rotation}")

    save_ldr(refined, "examples/output/slope11477_backing_plate_demo.ldr")
    print("wrote examples/output/slope11477_backing_plate_demo.ldr")


if __name__ == "__main__":
    main()
