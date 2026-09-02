import pytest

from brickforge import Model, PartCatalog, Rotation
from brickforge.pipeline.slopes import substitute_staircase_slopes
from brickforge.structure import analyze

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_step_down_edge_is_substituted_with_matching_upright_slope(catalog):
    # Tall block (2 bricks) at z=[-2,0), a 1-brick-tall block at z=[0,2)
    # (the candidate), open air at z=[2,4) -- a genuine step down in +Z.
    # Verified orientation: downhill +Z -> YAW_0 (see slopes.py docstring).
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)  # 2x2 brick, uphill
    model.place("3003", RED, x=0, y=3, z=-2)  # second brick on top, 2 bricks tall
    model.place("3003", RED, x=0, y=0, z=0)  # 2x2 brick, the candidate

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos.z == 0)
    assert candidate.part.id == "3039"  # Slope Brick 45 2 x 2
    assert candidate.rotation == Rotation.YAW_0
    assert candidate.pos == model.bricks[2].pos


def test_flat_roof_is_not_substituted(catalog):
    # Same height on every side -- no real step, must be left as a brick.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)
    model.place("3003", RED, x=0, y=0, z=2)

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos.z == 0)
    assert candidate.part.id == "3003"


def test_brick_with_something_resting_on_top_is_not_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)  # would otherwise qualify
    model.place("3024", RED, x=0, y=3, z=0)  # something resting on top of it

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert candidate.part.id == "3003"


def test_plates_and_tiles_are_never_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3020", RED, x=0, y=0, z=0)  # Plate 2x4, not brick height

    refined = substitute_staircase_slopes(model).model

    assert refined.bricks[0].part.id == "3020"


def test_isolated_peak_with_no_matching_direction_is_left_alone(catalog):
    # Candidate is taller than all 4 neighbours -- nothing is "uphill" of
    # it in any direction, so no substitution should fire.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=0)  # the peak, top exposed
    model.place("3003", RED, x=0, y=0, z=-2)  # shorter on every side
    model.place("3003", RED, x=0, y=0, z=2)
    model.place("3003", RED, x=-2, y=0, z=0)
    model.place("3003", RED, x=2, y=0, z=0)

    refined = substitute_staircase_slopes(model).model

    peak = next(b for b in refined if b.pos == model.bricks[0].pos)
    assert peak.part.id == "3003"


def test_slope_substitution_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model).model
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece
    assert len(refined) == len(model)


# --- 2-plate ("2/3 brick") merge tier ---
# Unlike the 3-plate tier (a 1-to-1 swap of an already-placed brick), this
# tier merges two vertically-stacked plates into one slope -- see
# slopes.py's module docstring. Same step-edge geometry, mirrored at
# y-height 2 instead of 3, with height_plates=1 "plate" pieces instead of
# a single height_plates=3 "brick".


def test_2plate_step_down_edge_is_merged_into_matching_slope(catalog):
    # The 2-plate tier's real parts (54200/85984/7825/7835) all have a
    # 1-stud run, so the candidate pair must be 1-stud deep along the
    # incline direction, unlike the 3-plate tier's 2-stud-deep 2x2 bricks
    # -- Plate 1 x 2 (footprint 2x1), not Plate 2 x 2, is the matching
    # candidate shape here. Brick 1x2 (also footprint 2x1) at z=-1 is
    # tall enough (3 plates >= the 2-plate riser) to be "uphill"; open air
    # at z=1 is the genuine step down.
    model = Model(catalog=catalog)
    model.place("3004", RED, x=0, y=0, z=-1)  # Brick 1x2, uphill
    model.place("3023", RED, x=0, y=0, z=0)  # Plate 1x2, lower of the pair
    model.place("3023", RED, x=0, y=1, z=0)  # Plate 1x2, upper of the pair

    refined = substitute_staircase_slopes(model).model

    assert len(refined) == len(model) - 1  # two plates merged into one slope
    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert candidate.part.id == "85984"  # Slope Brick 31 1 x 2 (perp width 2, run 1)
    # YAW_180, not YAW_0: this family's tall/uphill face sits at +Z at rest,
    # the mirror image of the 3-plate family -- see slopes.py's module
    # docstring (a real bug the first version shipped with).
    assert candidate.rotation == Rotation.YAW_180
    assert candidate.pos == model.bricks[1].pos  # anchored at the LOWER plate's position


def test_2plate_flat_roof_is_not_merged(catalog):
    # Same shape as the 3-plate test_flat_roof_is_not_substituted: only the
    # middle pair's fate is asserted -- the edge pairs border open air past
    # the modeled region, which is indistinguishable from a genuine step
    # down (an accepted, pre-existing limitation, not new to this tier).
    model = Model(catalog=catalog)
    model.place("3023", RED, x=0, y=0, z=-1)
    model.place("3023", RED, x=0, y=1, z=-1)
    model.place("3023", RED, x=0, y=0, z=0)
    model.place("3023", RED, x=0, y=1, z=0)
    model.place("3023", RED, x=0, y=0, z=1)
    model.place("3023", RED, x=0, y=1, z=1)

    refined = substitute_staircase_slopes(model).model

    middle_lower = next(b for b in refined if b.pos == model.bricks[2].pos)
    middle_upper = next(b for b in refined if b.pos == model.bricks[3].pos)
    assert middle_lower.part.id == "3023"
    assert middle_upper.part.id == "3023"


def test_2plate_pair_with_something_on_top_is_not_merged(catalog):
    model = Model(catalog=catalog)
    model.place("3004", RED, x=0, y=0, z=-1)  # uphill
    model.place("3023", RED, x=0, y=0, z=0)  # would otherwise qualify
    model.place("3023", RED, x=0, y=1, z=0)
    # A tile (not a plate) resting on top -- blocks top_exposed for this
    # pair without itself being a second, independently-valid plate-pair
    # candidate one level up.
    model.place("3069b", RED, x=0, y=2, z=0)

    refined = substitute_staircase_slopes(model).model

    assert len(refined) == len(model)  # nothing merged
    lower = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert lower.part.id == "3023"


def test_2plate_mismatched_footprint_above_is_not_merged(catalog):
    # The layer directly above the candidate is tiled with two smaller
    # plates instead of one matching the full footprint -- there is no
    # single part to merge with, so the pair must be left alone.
    model = Model(catalog=catalog)
    model.place("3004", RED, x=0, y=0, z=-1)  # uphill
    model.place("3023", RED, x=0, y=0, z=0)  # Plate 1x2, lower
    model.place("3024", RED, x=0, y=1, z=0)  # Plate 1x1 -- only covers half
    model.place("3024", RED, x=1, y=1, z=0)  # the other half

    refined = substitute_staircase_slopes(model).model

    assert len(refined) == len(model)  # nothing merged
    lower = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert lower.part.id == "3023"


def test_2plate_merge_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3004", RED, x=0, y=0, z=-1)
    model.place("3023", RED, x=0, y=0, z=0)
    model.place("3023", RED, x=0, y=1, z=0)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model).model
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece
    assert len(refined) == len(model) - 1


def test_both_tiers_fire_independently_in_the_same_model(catalog):
    # A genuine 3-plate step (uses the swap tier) and a genuine 2-plate
    # step (uses the merge tier) far apart in the same model -- neither
    # should starve the other.
    model = Model(catalog=catalog)
    # 3-plate step at x=0 (2x2 bricks, 2-stud run -- matches the 3-plate tier).
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)
    # 2-plate step at x=10 (1x2 plates, 1-stud run -- matches the 2-plate
    # tier), far enough away to not interact.
    model.place("3004", RED, x=10, y=0, z=-1)  # uphill
    model.place("3023", RED, x=10, y=0, z=0)  # lower plate
    model.place("3023", RED, x=10, y=1, z=0)  # upper plate

    refined = substitute_staircase_slopes(model).model

    three_plate_result = next(b for b in refined if b.pos == model.bricks[2].pos)
    two_plate_result = next(b for b in refined if b.pos == model.bricks[4].pos)
    assert three_plate_result.part.id == "3039"  # Slope Brick 45 2 x 2
    assert two_plate_result.part.id == "85984"  # Slope Brick 31 1 x 2
    assert len(refined) == len(model) - 1  # only the 2-plate pair merges away a part
    # Regression pin for a real bug: for the identical downhill direction
    # (+Z), the two families need opposite rotations, because the 2-plate
    # family's rest orientation is the mirror image of the 3-plate one's
    # (verified from raw geometry -- see slopes.py's module docstring).
    assert three_plate_result.rotation == Rotation.YAW_0
    assert two_plate_result.rotation == Rotation.YAW_180


# --- 3-plate STACK tier (unconsolidated plates, not yet a brick) ---
# Same riser (3) and the same _find_step_edge_rotation geometry as the
# swap tier above, but the candidate arrives as three separate identically-
# footprinted PLATES stacked at the same position -- exactly the material
# legalize.py's Stage B now deliberately leaves behind for a genuinely
# top-exposed run (see that module's own Stage B comment). Added so a
# real step-down edge can become a slope even when the legalizer's own
# tiling never independently decided to consolidate that run into a brick.


def test_3plate_stack_step_down_edge_is_merged_into_matching_slope(catalog):
    # Identical geometry to test_step_down_edge_is_substituted_with_
    # matching_upright_slope, except the candidate is three unconsolidated
    # 2x2 plates (3022) instead of one pre-formed 2x2 brick (3003) -- must
    # resolve to the exact same slope part and rotation.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)  # 2x2 brick, uphill
    model.place("3003", RED, x=0, y=3, z=-2)  # second brick on top, tall enough
    model.place("3022", RED, x=0, y=0, z=0)  # Plate 2x2, lowest of the stack
    model.place("3022", RED, x=0, y=1, z=0)  # Plate 2x2, middle
    model.place("3022", RED, x=0, y=2, z=0)  # Plate 2x2, uppermost

    refined = substitute_staircase_slopes(model).model

    assert len(refined) == len(model) - 2  # three plates merged into one slope
    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert candidate.part.id == "3039"  # Slope Brick 45 2 x 2 -- same part the swap tier uses
    assert candidate.rotation == Rotation.YAW_0


def test_3plate_stack_with_something_on_top_is_not_merged(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3022", RED, x=0, y=0, z=0)  # would otherwise qualify
    model.place("3022", RED, x=0, y=1, z=0)
    model.place("3022", RED, x=0, y=2, z=0)
    model.place("3069b", RED, x=0, y=3, z=0)  # tile resting on top -- blocks top_exposed

    refined = substitute_staircase_slopes(model).model

    assert len(refined) == len(model)  # nothing merged
    lowest = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert lowest.part.id == "3022"


def test_3plate_stack_mismatched_footprint_above_is_not_merged(catalog):
    # The layer directly above the two-plate candidate is tiled with two
    # smaller plates instead of one matching the full footprint -- there
    # is no single third part to stack with, so the pair must be left for
    # a different tier (here, correctly, the 2-plate merge tier) rather
    # than forcing a 3-stack that doesn't exist.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3022", RED, x=0, y=0, z=0)  # Plate 2x2, lowest
    model.place("3022", RED, x=0, y=1, z=0)  # Plate 2x2, middle
    model.place("3024", RED, x=0, y=2, z=0)  # Plate 1x1 -- only covers a quarter
    model.place("3024", RED, x=1, y=2, z=0)
    model.place("3024", RED, x=0, y=2, z=1)
    model.place("3024", RED, x=1, y=2, z=1)

    refined = substitute_staircase_slopes(model).model

    # No 3-stack (mismatched top layer), and no 2-plate merge either --
    # this family's real parts are all a 1-stud run, and this candidate's
    # 2-stud run doesn't match any 2-plate catalog entry. Left as plates.
    lowest = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert lowest.part.id == "3022"


def test_3plate_stack_substitution_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3022", RED, x=0, y=0, z=0)
    model.place("3022", RED, x=0, y=1, z=0)
    model.place("3022", RED, x=0, y=2, z=0)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model).model
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece
    assert len(refined) == len(model) - 2


# --- 33-degree family (run=3 studs) ---
# Shares height_plates=3 and perpendicular widths 1-4 studs with the
# 45-degree family (run=2 studs) above -- exactly the scenario the
# generalized (height, perp, run) lookup key in slopes.py exists to
# disambiguate. These tests would fail with a silent wrong-part
# substitution (or a KeyError) if the two families were ever able to
# shadow each other again.


def test_33_degree_slope_fires_for_a_3_stud_run_step_down(catalog):
    # Brick 1x3 (3622), rotated so its 3-stud-long axis runs along Z --
    # a run length only the 33-degree family (not the 2-stud 45-degree
    # family) matches for perp width 1.
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # uphill support, brick 1
    model.place("3005", RED, x=0, y=3, z=-1)  # uphill support, brick 2 (2 bricks tall)
    model.place("3622", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)  # candidate, 1x3 along Z

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert candidate.part.id == "4286"  # Slope Brick 33 3 x 1 (perp=1, run=3)
    # YAW_180, not the base table's YAW_0 for a +Z downhill: this family is
    # in _FLIPPED_PART_IDS, the mirror image of the 45-degree family's own
    # rest orientation (see slopes.py's module docstring and
    # catalog/parts_v1.yaml's header on this family for the raw-geometry
    # evidence).
    assert candidate.rotation == Rotation.YAW_180


def test_33_degree_and_45_degree_families_do_not_shadow_each_other(catalog):
    # Two step-down candidates, same perpendicular width (1 stud) and same
    # height tier (brick height), but different run lengths -- one must
    # resolve to the 45-degree family (run=2) and the other to the
    # 33-degree family (run=3). A 2-key (height, perp) lookup would let
    # whichever family's dict entry was inserted last silently win both;
    # this pins that it doesn't.
    model = Model(catalog=catalog)
    # 45-degree candidate at x=0: Brick 1x2 (3004), run=2 along Z.
    model.place("3005", RED, x=0, y=0, z=-1)
    model.place("3005", RED, x=0, y=3, z=-1)
    model.place("3004", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)
    # 33-degree candidate at x=5, far enough away not to interact: Brick
    # 1x3 (3622), run=3 along Z.
    model.place("3005", RED, x=5, y=0, z=-1)
    model.place("3005", RED, x=5, y=3, z=-1)
    model.place("3622", RED, x=5, y=0, z=0, rotation=Rotation.YAW_90)

    refined = substitute_staircase_slopes(model).model

    slope_45 = next(b for b in refined if b.pos == model.bricks[2].pos)
    slope_33 = next(b for b in refined if b.pos == model.bricks[5].pos)
    assert slope_45.part.id == "3040"  # Slope Brick 45 2 x 1 (run=2)
    assert slope_33.part.id == "4286"  # Slope Brick 33 3 x 1 (run=3)


def test_33_degree_slope_substitution_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)
    model.place("3005", RED, x=0, y=3, z=-1)
    model.place("3622", RED, x=0, y=0, z=0, rotation=Rotation.YAW_90)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model).model
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece


# --- Inverted (underside/overhang) tier ---
# Mirror of the 3-plate upright swap tier: a brick-category candidate
# whose own BOTTOM is exposed, with a genuine step-up edge underneath it
# (support on one side reaching at least as deep, open air on the
# other), gets swapped for the matching inverted slope.


def test_overhang_step_up_edge_is_substituted_with_matching_inverted_slope(catalog):
    # A single ground-level brick at z=-2 (top at y=3), and a candidate
    # floating one floor up at z=0 (y=[3,6)) with nothing at all below
    # it -- open air at z=[2,4), genuine support reaching down to the
    # ground at z=[-2,0). The tower is deliberately only 1 brick tall
    # (not 2): a taller tower would ALSO satisfy the *upright* swap
    # tier's own top-exposure test (a real thing this test caught on its
    # first version -- the candidate's own top was exposed too, and the
    # upright tier's match won the tie-break before this was fixed),
    # since the tower's own top would then be flush with the candidate's
    # top. A 1-brick tower's top (y=3) sits well below the candidate's
    # own top (y=6), which fails the upright tier's "uphill must be at
    # least as tall" test on its own, isolating this to the inverted
    # tier only.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)  # 2x2 brick, the support -- reaches the ground
    model.place("3003", RED, x=0, y=3, z=0)  # floating candidate, bottom exposed

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert candidate.part.id == "3660"  # Slope Inverted 45 2 x 2
    # 3660 is a FLIPPED part (see _FLIPPED_PART_IDS) -- downhill +Z maps
    # to the opposite of the upright family's own YAW_0.
    assert candidate.rotation == Rotation.YAW_180


def test_ground_level_brick_with_exposed_bottom_is_not_substituted(catalog):
    # Flat roof at ground level: same height on both sides, no genuine
    # step in either direction, so neither tier should fire -- but every
    # one of these ground-level bricks has "nothing below" in the sense
    # the inverted tier's bottom-exposure check looks for, since y0 == 0
    # is the model's own floor, not an overhang. Real bug this shape
    # pins: before the y0 <= 0 guard existed, an equivalent ground-level
    # shape (see test_brick_with_something_resting_on_top_is_not_substituted
    # above) was wrongly swapped for an inverted slope.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)
    model.place("3003", RED, x=0, y=0, z=2)

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert candidate.part.id == "3003"


def test_overhang_with_something_below_is_not_substituted(catalog):
    # Same shape as the genuine-overhang test above, but with a plate
    # directly beneath the candidate -- its bottom is no longer exposed,
    # so it must be left alone regardless of the step pattern around it.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3024", RED, x=0, y=2, z=0)  # 1x1 plate directly beneath the candidate
    model.place("3003", RED, x=0, y=3, z=0)

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert candidate.part.id == "3003"


def test_decorative_inverted_variants_do_not_shadow_the_plain_part(catalog):
    # 2310 and 3676 share an exact (height, perp, run) key with 3665 and
    # 3660 respectively (see _build_inverted_slope_map's own docstring).
    # An automatic substitution must always resolve to the plain part,
    # never the cutout/double-convex variant, regardless of catalog
    # iteration order.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=0)

    refined = substitute_staircase_slopes(model).model

    candidate = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert candidate.part.id == "3660"


def test_inverted_slope_substitution_does_not_introduce_new_structural_issues(catalog):
    # A real overhang candidate can never rest directly on anything (its
    # own bottom must be exposed, by definition), so unlike every other
    # tier's safety test above (which all put their candidate at y=0 and
    # let the GROUND node carry it for free), this one needs an actual
    # connected topology: a 2-brick tower reaching the ground, a floating
    # candidate one column over at the same height, and a single wide
    # plate (rotated so its footprint spans both columns) resting on top
    # of both -- candidate -> plate -> tower -> GROUND. The plate on top
    # also happens to be what keeps the *upright* swap tier from matching
    # this same candidate (its top is no longer exposed either), so only
    # the inverted tier is actually exercised here.
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)  # tower, lower brick -- reaches ground
    model.place("3003", RED, x=0, y=3, z=-2)  # tower, upper brick
    model.place("3003", RED, x=0, y=3, z=0)  # floating candidate, bottom exposed
    model.place("3020", RED, x=0, y=6, z=-2, rotation=Rotation.YAW_90)  # spans both columns

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model).model
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece
    assert len(refined) == len(model)  # 1-to-1 swap, not a merge
    assert len(refined) == len(model)  # 1-to-1 swap, not a merge


def test_11477_backing_plate_lands_inside_the_slopes_own_notch(catalog):
    # 11477's real geometry has a genuine notch under its own anchor cell
    # (see slopes.py's own _NEEDS_ANCHOR_BACKING_PLATE docstring) -- a
    # full plate-height void INSIDE the part's own declared 2-plate range,
    # not below it. A first (wrong) version of this fix placed a plate
    # one layer below the slope instead, which left the box's own already-
    # flush boundary untouched and never reached the real gap -- pinned
    # here by asserting the plate's own real LDU position, not just that
    # a raw_placement exists at all.
    model = Model(catalog=catalog)
    model.place("3005", RED, x=0, y=0, z=-1)  # ground support
    model.place("3005", RED, x=0, y=3, z=-1)  # uphill support
    model.place("3023", RED, x=0, y=1, z=0, rotation=Rotation.YAW_90)  # candidate, lower
    model.place("3023", RED, x=0, y=2, z=0, rotation=Rotation.YAW_90)  # candidate, upper

    result = substitute_staircase_slopes(model)
    refined = result.model

    slope = next(b for b in refined if b.part.id == "11477")
    assert slope.pos == model.bricks[2].pos  # anchored at the lower plate's own position

    assert len(result.raw_placements) == 1
    backing = result.raw_placements[0]
    assert backing.part_id == "3024"
    # The slope's own declared origin (bottom-anchored) computes to LDU
    # Y=-8 at pos.y=1 -- confirmed flush with a normal top-anchored plate
    # placed at pos.y=0 (also LDU Y=-8), which is exactly why a plate
    # placed there (the first, wrong fix) can never reach the real notch:
    # the boxes were already touching. The real notch, measured directly
    # from 11477's own raw geometry, is one full plate INSIDE that box,
    # landing at LDU Y=-16 -- not -8.
    assert backing.pos_ldu == (10, -16, 10)
