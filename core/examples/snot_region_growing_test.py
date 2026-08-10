"""Phase C.1 region-growing demonstration: a real 5-brick wall, backed
and bounded so all 5 side faces qualify for SNOT and face the same
direction, run through the real `place_snot_panels` -- confirms the
merged run is tiled with 2 plates (4-wide + 1-wide) spanning all 5
bricks, not 5 separate 1x1 plates.

This scene exists because the CURRENT example models (turret/mushroom/
bunny) don't happen to have any physically-adjacent SNOT candidates to
merge -- their real candidates are documented (CLAUDE.md) to already be
isolated, on different walls/height-tiers. Region-growing is correct and
tested (tests/test_pipeline_snot_placement.py), but showing it off
visually on a real model needs different geometry than what exists today.

Run:
    python examples/snot_region_growing_test.py
"""

from pathlib import Path

from brickforge import Model, PartCatalog, RawPlacement, save_ldr
from brickforge.pipeline.snot_placement import place_snot_panels
from brickforge.snot import place_in_frame, snot_frame_for_brick

WALL_COLOR = 71  # Light_Bluish_Gray
PANEL_COLOR = 14  # Yellow -- makes the region-grown panel easy to spot


def build() -> tuple[Model, list, "object"]:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)

    model.place("3460", WALL_COLOR, 0, 0, 0)  # Plate 1x8 backing wall
    for x in (1, 2, 3, 4, 5):
        model.place("3005", WALL_COLOR, x, 0, 1)  # 5 candidate bricks in a row
    model.place("3024", WALL_COLOR, 0, 0, 1)  # blocker so -x never competes with +z
    model.place("3024", WALL_COLOR, 6, 0, 1)  # blocker so +x never competes with +z

    result = place_snot_panels(model)

    raw_placements: list[RawPlacement] = []
    for child in result.snot_children:
        parent = result.model.bricks[child.parent_index]
        frame = snot_frame_for_brick(parent, parent.part.side_stud_face, face_offset=parent.part.side_stud_offset)
        pos, matrix = place_in_frame(frame, child.part, child.local_pos, child.local_rotation)
        raw_placements.append(RawPlacement(part_id=child.part.id, color=PANEL_COLOR, pos_ldu=pos, matrix=matrix))

    return result.model, raw_placements, result


def main() -> None:
    model, raw_placements, result = build()
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    path = save_ldr(
        model,
        out_dir / "snot_region_growing_test.ldr",
        name="BrickForgerAI SNOT Region-Growing Test",
        raw_placements=raw_placements,
    )
    print(f"Wrote {path} -- {result.swapped} bricks swapped, {result.attached} panel(s) attached.")
    print("Open in Studio and confirm: ONE 4-wide yellow plate + ONE 1-wide yellow plate,")
    print("together spanning all 5 gray SNOT bricks with no gap or overlap -- not 5 separate tiles.")


if __name__ == "__main__":
    main()
