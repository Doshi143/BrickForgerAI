"""Builds examples/output/slope11477_backing_plate_demo.ldr -- a minimal
file to confirm the backing-plate fix (see _NEEDS_ANCHOR_BACKING_PLATE in
slopes.py) actually closes the gap: 11477's own real geometry has a genuine
notch under its own anchor cell (the thick/tall end), one full plate deep,
sitting INSIDE the slope's own declared 2-plate range -- not below it. A
normal Model.place() can never reach that cell (it always collides with
the slope's own occupied_cells()), so the fix is a RawPlacement, computed
directly from the slope's own position rather than placed through the
model's collision grid.

Works the same regardless of how high off the ground the pair sits --
unlike an earlier (wrong) version of this fix, which needed the pair
elevated to have room to place a plate *below* it. Kept elevated here
anyway, purely so the uphill support and the gap both read clearly in a
render.
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
    model.place("3023", RED, x=0, y=1, z=0, rotation=Rotation.YAW_90)  # candidate, lower plate
    model.place("3023", RED, x=0, y=2, z=0, rotation=Rotation.YAW_90)  # candidate, upper plate

    result = substitute_staircase_slopes(model)
    refined = result.model
    print(f"{len(refined)} bricks:")
    for b in refined.bricks:
        print(f"  {b.part.id} at {b.pos} rotation={b.rotation}")
    print(f"{len(result.raw_placements)} raw placement(s) (backing plate, rendered inside the slope's own footprint):")
    for rp in result.raw_placements:
        print(f"  {rp.part_id} at LDU {rp.pos_ldu}")

    save_ldr(
        refined,
        "examples/output/slope11477_backing_plate_demo.ldr",
        raw_placements=result.raw_placements,
    )
    print("wrote examples/output/slope11477_backing_plate_demo.ldr")


if __name__ == "__main__":
    main()
