"""Builds examples/output/slope3665_orientation_test.ldr for manual Studio
verification of the INVERTED 45-degree family's non-square 1x2 member
(3665) -- the existing inverted-tier regression test only ever exercises
3660 (the square 2x2 member), which can't expose an axis-swap bug the
same way a non-square candidate can (see slope3040_test.py's own
docstring for the identical reasoning on the upright side).

Scene, built through substitute_staircase_slopes on a real overhang (not
hand-placed slope + hand-guessed rotation): a 1-brick-tall Brick 1x1
(3005) column reaching the ground, with a floating Brick 1x2 (3004),
rotated so it runs along Z, resting just 1 plate above the ground with
nothing at all beneath it -- open air past its far end, genuine support
reaching the ground on the near end.

y0=1 (not a full brick up, unlike this module's own reference inverted
test in tests/test_pipeline_slopes.py, which uses y0=3 specifically to
keep that scene's geometry as close as possible to a different, already-
existing test it was copied from) -- chosen here so the candidate's own
height range overlaps the support column's, which renders as a visually
flush corbel/overhang in Studio instead of two disconnected-looking
blocks floating near each other with an empty diagonal gap between them.
Still correctly isolates the inverted tier from the upright one: the
support's own top (y=3) is less than the candidate's own top (y=1+3=4),
so the upright tier's "uphill must be at least as tall as the candidate"
check still fails on its own, the same isolation the y0=3 version relies
on, just with less unnecessary vertical spacing.

Correct geometry: the slope's TALL face sits flush against the uphill
column with no gap or overlap, its THIN edge sits flush over the open
side, and its flat (top: full) face rests level with the block that
would have been above it -- open this file in Studio and check exactly
that, the same way every other slope family in this catalog was
confirmed.
"""
from __future__ import annotations

from brickforge import Model, PartCatalog, Rotation, save_ldr
from brickforge.pipeline.slopes import substitute_staircase_slopes

RED = 4


def main() -> None:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # ground-reaching support, 1 brick tall
    model.place("3004", RED, x=0, y=1, z=0, rotation=Rotation.YAW_90)  # candidate, floating just 1 plate up, 1x2 along Z

    refined = substitute_staircase_slopes(model).model
    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    print(f"substituted part: {candidate.part.id}, rotation: {candidate.rotation}")
    assert candidate.part.id == "3665"

    save_ldr(refined, "examples/output/slope3665_orientation_test.ldr")
    print("wrote examples/output/slope3665_orientation_test.ldr")


if __name__ == "__main__":
    main()
