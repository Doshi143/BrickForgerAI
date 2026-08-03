import pytest

from brickforge.lattice import (
    BRICK_HEIGHT_LDU,
    PLATE_HEIGHT_LDU,
    STUD_LDU,
    GridPos,
    Rotation,
    placement_to_ldraw,
)


def test_constants_match_ldraw_spec():
    # https://www.ldraw.org/article/218.html
    assert STUD_LDU == 20
    assert PLATE_HEIGHT_LDU == 8
    assert BRICK_HEIGHT_LDU == 24
    assert BRICK_HEIGHT_LDU == PLATE_HEIGHT_LDU * 3


def test_yaw_0_places_1x1_plate_centered_over_its_cell():
    # height_plates=1: origin (=top, verified against 3024.dat) sits 8 LDU
    # ("up" = -Y) above the cell's bottom.
    x, y, z = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0)
    assert (x, y, z) == (10, -PLATE_HEIGHT_LDU, 10)


def test_yaw_0_places_2x4_brick_centered_over_footprint():
    # A 2x4 brick (width=2 studs in x, depth=4 studs in z, height=3 plates)
    # anchored at origin: footprint centers at (20, -, 40); origin sits at
    # the part's top, i.e. 24 LDU ("up") above the cell's bottom.
    x, y, z = placement_to_ldraw(GridPos(0, 0, 0), 2, 4, 3, Rotation.YAW_0)
    assert (x, y, z) == (20, -BRICK_HEIGHT_LDU, 40)


def test_rotation_swaps_footprint_for_90_and_270():
    assert Rotation.YAW_0.rotate_footprint(2, 4) == (2, 4)
    assert Rotation.YAW_90.rotate_footprint(2, 4) == (4, 2)
    assert Rotation.YAW_180.rotate_footprint(2, 4) == (2, 4)
    assert Rotation.YAW_270.rotate_footprint(2, 4) == (4, 2)


def test_yaw_90_repositions_origin_to_rotated_footprint_center():
    x, y, z = placement_to_ldraw(GridPos(0, 0, 0), 2, 4, 3, Rotation.YAW_90)
    # rotated footprint is (4, 2) studs -> centered at (80/2, -, 40/2)
    assert (x, y, z) == (40, -BRICK_HEIGHT_LDU, 20)


def test_origin_is_top_anchored_not_bottom_anchored():
    # Verified against official part files (parts/3005.dat, parts/3024.dat):
    # local Y=0 is the part's TOP, not its bottom. A part's origin Y must
    # therefore depend on its height, not just its grid y.
    _, y_plate, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0)
    _, y_brick, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 3, Rotation.YAW_0)
    assert y_plate == -PLATE_HEIGHT_LDU
    assert y_brick == -BRICK_HEIGHT_LDU
    assert y_plate != y_brick  # would be equal (both 0) under the old, wrong formula


def test_bottom_anchored_part_places_origin_at_grid_y_directly():
    # Verified against official part files for the 2-plate slope family
    # (54200, 5404, 85984, 7825, 7835): local Y=0 is the part's BOTTOM,
    # the mirror image of the top-anchored case above. The origin must
    # therefore sit at grid y directly, independent of height.
    _, y_plate_height, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0, y_anchor="bottom")
    _, y_two_plate_height, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 2, Rotation.YAW_0, y_anchor="bottom")
    assert y_plate_height == 0
    assert y_two_plate_height == 0  # unlike top-anchored, height doesn't shift a bottom-anchored origin


def test_bottom_anchored_slope_sits_flush_on_top_of_a_plate_below():
    # A 1-plate plate at grid y=0 topped by a 2-plate bottom-anchored slope
    # at grid y=1 must meet with zero gap: the plate's TOP (its top-anchored
    # origin) must equal the slope's BOTTOM (its bottom-anchored origin,
    # since for a bottom-anchored part the origin IS the bottom).
    _, y_plate, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0, y_anchor="top")
    _, y_slope, _ = placement_to_ldraw(GridPos(0, 1, 0), 1, 1, 2, Rotation.YAW_0, y_anchor="bottom")
    plate_top = y_plate
    slope_bottom = y_slope
    assert plate_top == slope_bottom


def test_unknown_y_anchor_raises():
    with pytest.raises(ValueError):
        placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0, y_anchor="sideways")


def test_stacked_same_height_parts_are_contiguous():
    # Two 1-plate parts stacked at grid y=0 and y=1 must meet with zero gap
    # at their shared boundary: the lower part's TOP (= its origin, since
    # origin is top-anchored) must equal the upper part's BOTTOM (= its
    # origin plus its own height, since raw Y grows downward).
    _, y0, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0)
    _, y1, _ = placement_to_ldraw(GridPos(0, 1, 0), 1, 1, 1, Rotation.YAW_0)
    lower_top = y0
    upper_bottom = y1 + PLATE_HEIGHT_LDU
    assert lower_top == upper_bottom


def test_stacked_different_height_parts_are_contiguous():
    # A 1-plate part at grid y=0..1 topped by a 3-plate brick at grid y=1..4
    # must meet with zero gap at their shared boundary despite the height
    # difference -- this is exactly the case (roof plate under taller
    # merlons) that the old, wrong (height-independent) formula got wrong.
    _, y_plate, _ = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0)
    _, y_brick, _ = placement_to_ldraw(GridPos(0, 1, 0), 1, 1, 3, Rotation.YAW_0)
    plate_top = y_plate
    brick_bottom = y_brick + BRICK_HEIGHT_LDU
    assert plate_top == brick_bottom


def test_grid_offset_translates_linearly_in_x_and_z():
    x0, _, z0 = placement_to_ldraw(GridPos(0, 0, 0), 1, 1, 1, Rotation.YAW_0)
    x1, _, z1 = placement_to_ldraw(GridPos(3, 0, 5), 1, 1, 1, Rotation.YAW_0)
    assert x1 - x0 == 3 * STUD_LDU
    assert z1 - z0 == 5 * STUD_LDU


def test_all_yaw_matrices_are_orthogonal_rotation_matrices():
    import numpy as np

    for rot in Rotation:
        m = np.array(rot.matrix).reshape(3, 3)
        # orthogonal: M * M^T == identity
        assert np.allclose(m @ m.T, np.eye(3))
        # proper rotation (no reflection): det == 1
        assert round(np.linalg.det(m)) == 1
