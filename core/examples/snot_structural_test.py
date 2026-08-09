"""Phase B milestone: a real SNOT branch, run through the actual
structural analyzer (structure/report.py::analyze), not just placed and
eyeballed. Two things are being proven here, together:

1. Geometry: 30414 (Brick 1 x 4 with 4 Studs on Side) -- the first
   "longer" SNOT part in this catalog, verified against its own raw .dat
   geometry, see catalog/parts_v1.yaml -- correctly carries a WIDE plate
   across its entire 4-stud side row, plus a second plate stacked further
   outward on top of that. Run this and open the .ldr in Studio to confirm
   both sit flush with no gap or overlap, the same "fix, then re-verify
   visually" checkpoint every prior lattice change in this project has
   gone through (see tests/test_snot.py for the computed version of this
   same claim).
2. Structure: this is the part Phase A explicitly could NOT do --
   `analyze()` is called with the branch's `SnotChild` records, and the
   printed report is the actual, current output of
   structure/graph.py::build_connectivity_graph's new SNOT edges, not a
   hand-argued claim that they'd work. A model with a floating SNOT branch
   your own eyes can't easily judge from a render should now show up as
   `critical_bricks`, exactly the same as any other real structural gap
   this project's repair tooling already catches.

Run:
    python examples/snot_structural_test.py
"""

from pathlib import Path

from brickforge import GridPos, Model, PartCatalog, RawPlacement, Rotation, SnotChild, save_ldr
from brickforge.snot import place_in_frame, snot_frame_for_brick
from brickforge.structure.report import analyze, summarize

CORE_COLOR = 71  # Light_Bluish_Gray
SNOT_BRICK_COLOR = 4  # Red -- makes the part under test easy to spot
PLATE_COLOR = 14  # Yellow -- the wide, full-row plate
TAB_COLOR = 27  # Bright_Green -- the single-stud plate at one specific stud index


def build() -> tuple[Model, list[SnotChild], list[RawPlacement]]:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)

    # A single grounded 30414, sitting alone on the baseplate -- deliberately
    # the smallest real case, not a demo of the eventual placement algorithm.
    snot_brick = model.place("30414", SNOT_BRICK_COLOR, x=0, y=0, z=0, rotation=Rotation.YAW_0)
    parent_index = 0

    wide_plate = catalog.get("3710")  # Plate 1 x 4 -- spans all 4 side studs at once
    narrow_plate = catalog.get("3024")  # Plate 1 x 1 -- placed at one specific stud index

    children = [
        SnotChild(parent_index=parent_index, part=wide_plate, local_pos=GridPos(0, 0, 0)),
        SnotChild(parent_index=parent_index, part=wide_plate, local_pos=GridPos(0, 1, 0)),
        SnotChild(parent_index=parent_index, part=narrow_plate, local_pos=GridPos(2, 2, 0)),
    ]

    # The children above are the analyzable, indexed record Phase B's graph
    # consumes. For the .ldr file itself, still go through the same
    # snot_frame_for_brick/place_in_frame calls as Phase A's example --
    # SNOT children still aren't tracked by Model's own grid (see snot.py's
    # module docstring), so they're still written out as RawPlacements.
    frame = snot_frame_for_brick(
        snot_brick,
        snot_brick.part.side_stud_face,
        face_offset=snot_brick.part.side_stud_offset,
    )
    raw_placements: list[RawPlacement] = []
    for child in children:
        pos, matrix = place_in_frame(frame, child.part, child.local_pos, child.local_rotation)
        color = TAB_COLOR if child.part.id == "3024" else PLATE_COLOR
        raw_placements.append(RawPlacement(part_id=child.part.id, color=color, pos_ldu=pos, matrix=matrix))

    return model, children, raw_placements


def main() -> None:
    model, children, raw_placements = build()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    path = save_ldr(
        model,
        out_dir / "snot_structural_test.ldr",
        name="BrickForgerAI SNOT Structural Test",
        raw_placements=raw_placements,
    )
    print(f"Wrote {path} -- {len(model)} grid-placed brick(s) + {len(raw_placements)} SNOT part(s).")
    print(
        "Open in Studio and confirm: the two wide yellow plates sit flush across the\n"
        "red brick's whole side face (stacked outward, no gap/overlap), and the small\n"
        "green plate sits flush at stud index 2 of that same row, one layer further out."
    )

    report = analyze(model, children)
    print()
    print(summarize(report))
    print(f"is_single_piece={report.is_single_piece}  critical_bricks={report.critical_bricks}")


if __name__ == "__main__":
    main()
