"""Builds examples/output/slope3040_orientation_test.ldr for manual Studio
verification of the 45-degree family's *non-square* 1x2 member (3040),
specifically -- the family's original orientation verification
(slope_orientation_test.ldr) only ever used the square 2x2 member (3039).
3040's own raw part geometry was independently checked against 3039's and
found to follow the identical Z/Y ramp pattern (no per-part mirroring, the
way the 2-plate "cheese" family turned out to be genuinely mirrored from
the 3-plate family) -- but that only rules out the part's own geometry
being backwards, not a rotation/footprint-handling bug specific to
substituting a *non-square* candidate (the square 3039 case can't expose an
axis-swap bug the way a 1x2 candidate can, since swapping X/Z on a square
footprint changes nothing).

Scene, built through substitute_staircase_slopes on a real step-down (not
hand-placed slope + hand-guessed rotation): a Brick 1x2 (3004), rotated so
its long axis runs along Z, sits at a genuine step-down edge, with a
2-brick-tall Brick 1x1 (3005) column uphill of it and open air downhill.
Correct geometry: the slope's TALL face sits flush against the uphill
column with no gap or overlap, and its THIN edge touches the ground with
no overhang past where the candidate brick used to sit -- open this file in
Studio and check exactly that, the same way every other slope family in
this catalog was confirmed.
"""
from __future__ import annotations

from brickforge import Model, PartCatalog, Rotation, save_ldr
from brickforge.pipeline.slopes import substitute_staircase_slopes

RED = 4


def main() -> None:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # uphill support, brick 1
    model.place("3005", RED, x=0, y=3, z=-1)  # uphill support, brick 2 (2 bricks tall)
    model.place("3004", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)  # candidate, 1x2 along Z

    refined = substitute_staircase_slopes(model)
    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    print(f"substituted part: {candidate.part.id}, rotation: {candidate.rotation}")
    assert candidate.part.id == "3040"

    save_ldr(refined, "examples/output/slope3040_orientation_test.ldr")
    print("wrote examples/output/slope3040_orientation_test.ldr")


if __name__ == "__main__":
    main()
