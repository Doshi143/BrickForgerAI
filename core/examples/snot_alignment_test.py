"""Phase A milestone: hand-build a minimal SNOT (Studs Not On Top) test
scene through the real Model.place / save_ldr API (not hand-written LDU)
and confirm in Studio that the sideways-mounted plates sit flush against
the core, with no gap or overlap.

This is deliberately the smallest possible real case, not a demo of the
eventual algorithm: a 2x2 core of ordinary bricks, with one corner
replaced by 87087 (Brick 1 x 1 with Stud on 1 Side) facing outward on its
verified "-z" face, and two plates stacked onto that side stud.

The core brick's own placement uses nothing new -- normal Model.place,
same as every other example in this directory. Only the two outward
plates use the new snot.py machinery (snot_frame_for_brick,
place_in_frame), and since they don't live on Model's shared grid, they
can't be added via Model.place -- they're passed to save_ldr as
RawPlacements instead (see ldr_writer.py's own docstring for why that's
a deliberate, temporary seam: these two plates aren't yet tracked by
collision detection or the structural graph, Phase A only proves their
*position* is correct).

Run:
    python examples/snot_alignment_test.py
"""

from pathlib import Path

from brickforge import GridPos, Model, PartCatalog, RawPlacement, Rotation, save_ldr
from brickforge.snot import place_in_frame, snot_frame_for_brick

CORE_COLOR = 71  # Light_Bluish_Gray
SNOT_BRICK_COLOR = 4  # Red -- makes the part under test easy to spot
PLATE_COLOR = 14  # Yellow -- makes the sideways-mounted plates easy to spot


def build() -> tuple[Model, list[RawPlacement]]:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)

    # A 2x2 stud footprint, one brick-course tall. Three ordinary corners,
    # one corner is 87087 instead of a plain 1x1 brick -- same footprint
    # and height, so it drops into the same grid position with no other
    # change needed. Placed at YAW_0, so its side stud (verified "-z" in
    # the part's own unrotated frame -- see catalog/parts_v1.yaml) points
    # toward world -Z, away from the other three corners: an unobstructed
    # outward face, not one that would collide with the rest of the core.
    model.place("3005", CORE_COLOR, x=0, y=0, z=1, rotation=Rotation.YAW_0)  # back-left
    model.place("3005", CORE_COLOR, x=1, y=0, z=1, rotation=Rotation.YAW_0)  # back-right
    model.place("3005", CORE_COLOR, x=1, y=0, z=0, rotation=Rotation.YAW_0)  # front-right
    snot_brick = model.place("87087", SNOT_BRICK_COLOR, x=0, y=0, z=0, rotation=Rotation.YAW_0)  # front-left

    # The part's own verified real geometry (side_stud_face="-z",
    # side_stud_offset=(0, 10) -- 10 LDU from its own top, not the naive
    # 12 LDU half-height default) is passed through explicitly, not left
    # to the frame's own default approximation.
    frame = snot_frame_for_brick(
        snot_brick,
        snot_brick.part.side_stud_face,
        face_offset=snot_brick.part.side_stud_offset,
    )
    plate_part = catalog.get("3024")  # Plate 1 x 1

    raw_placements: list[RawPlacement] = []
    for local_y in (0, 1):  # two plates, stacked further outward
        pos, matrix = place_in_frame(frame, plate_part, GridPos(0, local_y, 0), Rotation.YAW_0)
        raw_placements.append(RawPlacement(part_id="3024", color=PLATE_COLOR, pos_ldu=pos, matrix=matrix))

    return model, raw_placements


def main() -> None:
    model, raw_placements = build()
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    path = save_ldr(
        model,
        out_dir / "snot_alignment_test.ldr",
        name="BrickForgerAI SNOT Alignment Test",
        raw_placements=raw_placements,
    )
    print(f"Wrote {path} -- {len(model)} grid-placed bricks + {len(raw_placements)} SNOT plate(s).")
    print("Open in Studio and confirm the two yellow plates sit flush against the red")
    print("brick's side face, extending straight outward with no gap or overlap.")


if __name__ == "__main__":
    main()
