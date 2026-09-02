"""Builds examples/output/slope11477_orientation_test.ldr for manual Studio
verification of the new curved slope (11477) -- the one open item flagged
when 11477 was added to the catalog: every other slope family in this
catalog only got trusted for automatic staircase substitution after a
synthetic orientation test like this one was visually confirmed in Studio.
That confirmation hasn't happened yet for 11477 -- this file is what needs
opening and checking, the same way slope3040_test.py/slope33_test.py were.

11477's footprint is [1, 2] (perp width 1, run 2 studs) -- the same run
length as the 3-plate 3040 family, not the 1-stud run of the 2-plate
54200/85984 family it's otherwise closest to in height. So the candidate
here is a 2-tall PAIR of "Plate 1 x 2" (3023), rotated YAW_90 so the run
direction lands along Z, exactly mirroring how slope3040_test.py rotated
its own 1x2 brick candidate -- not the un-rotated 3023 the 54200-family
test (test_2plate_step_down_edge_is_merged_into_matching_slope) uses,
since that family's run direction is the opposite axis.

Scene, built through substitute_staircase_slopes on a real step-down (not
hand-placed slope + hand-guessed rotation): a Brick 1x1 (3005, 3 plates
tall -- taller than the riser=2 this tier needs) sits uphill at z=-1; the
2-tall Plate 1x2 pair sits at z=0..1; open air past z=1 is the genuine
step down. Correct geometry to check in Studio: the slope's TALL/rounded
face should sit flush against the uphill brick with no gap or overlap,
and its THIN/tapered edge should meet the ground with no overhang past
where the candidate plates used to sit. If it's backwards (thin edge
against the uphill brick instead), "11477" needs adding to
_FLIPPED_PART_IDS in slopes.py, the same fix 54200/85984/7825/7835 needed
when their own tier shipped backwards the first time.
"""
from __future__ import annotations

from brickforge import Model, PartCatalog, Rotation, save_ldr
from brickforge.pipeline.slopes import substitute_staircase_slopes

RED = 4


def main() -> None:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # uphill support, 3 plates tall (>= riser=2)
    model.place("3023", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)  # candidate, lower plate
    model.place("3023", RED, x=0, y=1, z=0, rotation=Rotation.YAW_90)  # candidate, upper plate

    refined = substitute_staircase_slopes(model)
    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    print(f"substituted part: {candidate.part.id}, rotation: {candidate.rotation}")
    assert candidate.part.id == "11477"
    assert len(refined) == len(model) - 1  # two plates merged into one slope

    save_ldr(refined, "examples/output/slope11477_orientation_test.ldr")
    print("wrote examples/output/slope11477_orientation_test.ldr")


if __name__ == "__main__":
    main()
