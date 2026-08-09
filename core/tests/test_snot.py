import pytest

from brickforge.lattice import GridPos, PLATE_HEIGHT_LDU, Rotation
from brickforge.model import Brick
from brickforge.parts import PartCatalog
from brickforge.snot import (
    _FACES,
    _LOCAL_TILT_MATRIX,
    _matmul,
    _matvec,
    place_in_frame,
    snot_frame_for_brick,
)

_CATALOG = PartCatalog.load_default()


def _raw_geometry_bbox(pos_ldraw, matrix, half_x=10, half_z=10, height=PLATE_HEIGHT_LDU):
    """Faithfully replicates what an LDR renderer actually does: every
    raw vertex V in a part's .dat file (native LDraw coordinates) maps to
    world_V = matrix @ V + pos. Using a part's real raw-geometry corners
    here, not just its placement_to_ldraw origin point, is what this
    module's own test suite relies on to catch two real bugs an
    origin-only check missed -- see snot.py's own module/function
    docstrings for both."""
    a, b, c, d, e, f, g, h, i = matrix
    corners = [(dx, dy, dz) for dx in (-half_x, half_x) for dz in (-half_z, half_z) for dy in (0, height)]
    world_corners = [
        (a * lx + b * ly + c * lz + pos_ldraw[0], d * lx + e * ly + f * lz + pos_ldraw[1], g * lx + h * ly + i * lz + pos_ldraw[2])
        for (lx, ly, lz) in corners
    ]
    xs = [p[0] for p in world_corners]
    ys = [p[1] for p in world_corners]
    zs = [p[2] for p in world_corners]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def test_all_tilt_matrices_are_proper_rotations():
    import numpy as np

    for face in _FACES:
        m = np.array(_LOCAL_TILT_MATRIX[face]).reshape(3, 3)
        assert np.allclose(m @ m.T, np.eye(3))  # orthogonal
        assert round(np.linalg.det(m)) == 1  # proper rotation, no mirroring


def test_each_tilt_matrix_sends_the_real_native_top_stud_direction_to_its_named_face():
    # Local -Y, NOT +Y -- this project's own established, verified
    # convention (lattice.py's own module docstring) is that a
    # top-anchored part's origin sits at local Y=0 (the top / stud side)
    # and the raw geometry extends in *increasing* local Y toward the
    # bottom, meaning the real direction pointing away from a stud, in
    # the part's own native .dat coordinates, is -Y. An earlier version
    # of this table was derived and verified against +Y instead, which
    # is a real, previously-shipped bug this test pins against recurring.
    expected = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
    for face in _FACES:
        assert _matvec(_LOCAL_TILT_MATRIX[face], (0, -1, 0)) == expected[face]


def test_unknown_face_raises():
    brick = _CATALOG.get("3005")
    parent = Brick(part=brick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)
    with pytest.raises(ValueError):
        snot_frame_for_brick(parent, "+y")


def test_yawed_parent_carries_the_snot_frame_with_it():
    # A part's local +X face, after the parent itself is yawed 90 degrees,
    # must end up pointing world -Z -- not still world +X. Verified two
    # ways: the resulting matrix matches an independently hand-computed
    # composition, AND it actually sends the part's real native stud
    # direction (-Y) to the expected world direction. This is the exact
    # case that first exposed a real bug: an earlier version looked the
    # tilt matrix up by resolved *world* direction alone, which is
    # provably NOT equivalent to composing the parent's yaw with the
    # LOCAL face's tilt matrix whenever the parent has a non-identity yaw
    # (confirmed by direct computation, not just argued) -- this test
    # pins the correct composition so that mistake can't silently return.
    plate = _CATALOG.get("3024")
    parent = Brick(part=plate, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_90)
    frame = snot_frame_for_brick(parent, "+x")
    assert frame.matrix == _matmul(Rotation.YAW_90.matrix, _LOCAL_TILT_MATRIX["+x"])
    assert _matvec(frame.matrix, (0, -1, 0)) == (0, 0, -1)


@pytest.mark.parametrize(
    "face,outward_axis_index,expected_outward,expected_in_plane",
    [
        ("+x", 0, (20, 28), (0, 20)),
        ("-x", 0, (-8, 0), (0, 20)),
        ("+z", 2, (20, 28), (0, 20)),
        ("-z", 2, (-8, 0), (0, 20)),
    ],
)
def test_child_full_geometry_sits_flush_outward_and_centered_in_plane(
    face, outward_axis_index, expected_outward, expected_in_plane
):
    # The two real bugs this pins down, each found only by checking the
    # CHILD'S FULL RAW GEOMETRY (all 8 corners of its actual .dat-file
    # bounding box, exactly what Studio would render), not just its
    # placement_to_ldraw origin point -- an origin-only check passed
    # while both of these were still present:
    #
    # 1. Convention-mixing: an earlier place_in_frame undid
    #    placement_to_ldraw's native LDraw Y-flip before rotating, then
    #    reapplied it after -- correct as a *concept*, but it was only
    #    ever applied to the origin POINT, not to the fact that
    #    _LOCAL_TILT_MATRIX itself needed to be derived against native
    #    -Y (see the test above). A plate meant to sit flush *outward*
    #    against a parent's face instead landed *inside* the parent's
    #    own body.
    # 2. Double-centering: snot_frame_for_brick's in-plane origin used
    #    to add half the parent's own face width as a "center the face"
    #    term, on top of placement_to_ldraw's own already-centering the
    #    child within its footprint cell on that same axis -- a 1x1
    #    plate meant to center on a 1x1 parent's face (both spanning
    #    world X [0, 20]) instead landed at world X [10, 30].
    brick = _CATALOG.get("3005")  # 1x1x3 brick, world footprint [0,20]x[0,20]
    plate = _CATALOG.get("3024")  # 1x1x1 plate
    core = Brick(part=brick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)

    frame = snot_frame_for_brick(core, face)
    pos, matrix = place_in_frame(frame, plate, GridPos(0, 0, 0), Rotation.YAW_0)
    x_range, _, z_range = _raw_geometry_bbox(pos, matrix)

    outward = x_range if outward_axis_index == 0 else z_range
    in_plane = z_range if outward_axis_index == 0 else x_range
    assert outward == expected_outward, f"{face}: outward span {outward}, expected {expected_outward}"
    assert in_plane == expected_in_plane, f"{face}: in-plane span {in_plane}, expected {expected_in_plane}"


def test_stacked_children_extend_further_outward_without_overlapping_each_other():
    brick = _CATALOG.get("3005")
    plate = _CATALOG.get("3024")
    core = Brick(part=brick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)
    frame = snot_frame_for_brick(core, "+x")

    pos0, mat0 = place_in_frame(frame, plate, GridPos(0, 0, 0), Rotation.YAW_0)
    pos1, mat1 = place_in_frame(frame, plate, GridPos(0, 1, 0), Rotation.YAW_0)
    x_range0, _, _ = _raw_geometry_bbox(pos0, mat0)
    x_range1, _, _ = _raw_geometry_bbox(pos1, mat1)

    assert x_range0 == (20, 28)
    assert x_range1 == (28, 36)  # picks up exactly where the first plate ends


def test_face_offset_overrides_the_centered_half_height_default():
    # Confirmed wrong for a real measured part, not just theoretically
    # possible: 87087's real side stud sits 10 LDU from its own top, not
    # the 12 LDU half-height a "centered" default assumes (see the
    # catalog entry's own comment for the raw-.dat verification).
    brick = _CATALOG.get("3005")
    core = Brick(part=brick, color=4, pos=GridPos(5, 0, 5), rotation=Rotation.YAW_0)

    default_frame = snot_frame_for_brick(core, "-z")
    # Native LDraw convention (-Y up): the brick's own top-anchored origin
    # at this grid position is -24; half of its 24-LDU height down from
    # there is -24 + 12 = -12.
    assert default_frame.origin_ldu[1] == -12

    measured_frame = snot_frame_for_brick(core, "-z", face_offset=(0, 10))
    assert measured_frame.origin_ldu[1] == -24 + 10 == -14
    assert measured_frame.origin_ldu[1] != default_frame.origin_ldu[1]


def test_87087_catalog_entry_matches_its_verified_raw_geometry():
    # Pins the exact measured values from 87087.dat's own subfile
    # placement line (`1 16 0 10 -10 ... stud2a.dat`) so a future catalog
    # edit can't silently drift from the real part.
    part = _CATALOG.get("87087")
    assert part.category == "snot"
    assert part.footprint == (1, 1)
    assert part.height_plates == 3
    assert part.top == "none"  # no top stud on this part -- only the side one
    assert part.side_stud_face == "-z"
    assert part.side_stud_offset == (0, 10)
