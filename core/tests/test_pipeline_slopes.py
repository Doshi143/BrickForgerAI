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

    refined = substitute_staircase_slopes(model)

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

    refined = substitute_staircase_slopes(model)

    candidate = next(b for b in refined if b.pos.z == 0)
    assert candidate.part.id == "3003"


def test_brick_with_something_resting_on_top_is_not_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)  # would otherwise qualify
    model.place("3024", RED, x=0, y=3, z=0)  # something resting on top of it

    refined = substitute_staircase_slopes(model)

    candidate = next(b for b in refined if b.pos == model.bricks[2].pos)
    assert candidate.part.id == "3003"


def test_plates_and_tiles_are_never_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3020", RED, x=0, y=0, z=0)  # Plate 2x4, not brick height

    refined = substitute_staircase_slopes(model)

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

    refined = substitute_staircase_slopes(model)

    peak = next(b for b in refined if b.pos == model.bricks[0].pos)
    assert peak.part.id == "3003"


def test_slope_substitution_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, x=0, y=0, z=-2)
    model.place("3003", RED, x=0, y=3, z=-2)
    model.place("3003", RED, x=0, y=0, z=0)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model)
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

    refined = substitute_staircase_slopes(model)

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

    refined = substitute_staircase_slopes(model)

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

    refined = substitute_staircase_slopes(model)

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

    refined = substitute_staircase_slopes(model)

    assert len(refined) == len(model)  # nothing merged
    lower = next(b for b in refined if b.pos == model.bricks[1].pos)
    assert lower.part.id == "3023"


def test_2plate_merge_does_not_introduce_new_structural_issues(catalog):
    model = Model(catalog=catalog)
    model.place("3004", RED, x=0, y=0, z=-1)
    model.place("3023", RED, x=0, y=0, z=0)
    model.place("3023", RED, x=0, y=1, z=0)

    report_before = analyze(model)
    refined = substitute_staircase_slopes(model)
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

    refined = substitute_staircase_slopes(model)

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
