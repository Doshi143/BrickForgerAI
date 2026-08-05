"""Builds examples/output/slope33_orientation_test.ldr for manual Studio
verification of the new 33-degree slope family (4286/3298/4161/3297, see
catalog/parts_v1.yaml's header and pipeline/slopes.py's module docstring).

Mirrors the same discipline as slope_orientation_test.ldr /
slope_alignment_test.ldr for the 45-degree and 2-plate families: build
through the real Model.place / save_ldr API (not hand-written LDU), then
have a human open it in Studio and confirm visually flush geometry with no
gap or overlap -- pattern-matching the rotation convention against an
already-verified family is a reasonable prior, not proof.

Scene, built directly through substitute_staircase_slopes on a real
step-down (not hand-placed slope + hand-guessed rotation): a Brick 1x3
(3622, rotated so its 3-stud run runs along Z) sits at a genuine step-down
edge, with a 2-brick-tall Brick 1x1 (3005) column uphill of it and open air
downhill. The swap should replace the candidate with "4286" (Slope Brick 33
3 x 1) at YAW_180. Correct geometry looks like: the slope's TALL face sits
flush against the uphill column with no gap or overlap, and its THIN edge
touches the ground plane with no overhang past where the candidate brick
used to sit.
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
    model.place("3622", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)  # candidate, 1x3 along Z

    refined = substitute_staircase_slopes(model)
    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    print(f"substituted part: {candidate.part.id}, rotation: {candidate.rotation}")
    assert candidate.part.id == "4286"

    save_ldr(refined, "examples/output/slope33_orientation_test.ldr")
    print("wrote examples/output/slope33_orientation_test.ldr")


if __name__ == "__main__":
    main()
