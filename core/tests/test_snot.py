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
    rotation_for_outward_face,
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


@pytest.mark.parametrize("face", ["+x", "-x", "+z", "-z"])
def test_child_full_geometry_is_vertically_centered_on_the_frame_origin(face):
    # Real bug, caught only by the user's own Studio screenshot after
    # Phase A shipped, not by this test suite -- the horizontal tests
    # above all passed while this was still broken, because none of them
    # checked the vertical span at all. placement_to_ldraw centers a part
    # within its own local grid cell on both horizontal axes, which is
    # correct for the outward and in-plane axes (tested above), but WRONG
    # for the third axis -- whichever of local X/Z the tilt redirects
    # into world Y (vertical) -- since a single stud is a point on the
    # parent's face, not a cell to center within. This left every SNOT
    # child's vertical midpoint 10 LDU (half a 1-stud footprint) away
    # from the frame's own measured origin. Pins that the child's raw
    # geometry is now centered exactly on frame.origin_ldu[1], for all 4
    # faces, not just the one face the user happened to screenshot.
    brick = _CATALOG.get("3005")
    plate = _CATALOG.get("3024")
    core = Brick(part=brick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)

    frame = snot_frame_for_brick(core, face)
    pos, matrix = place_in_frame(frame, plate, GridPos(0, 0, 0), Rotation.YAW_0)
    _, y_range, _ = _raw_geometry_bbox(pos, matrix)

    midpoint = (y_range[0] + y_range[1]) / 2
    assert midpoint == frame.origin_ldu[1], f"{face}: vertical midpoint {midpoint}, expected {frame.origin_ldu[1]}"


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
    assert part.side_stud_count == 1


def test_30414_catalog_entry_matches_its_verified_raw_geometry():
    # Pins the exact measured values fetched from 30414.dat: four
    # `stud2a.dat` placements at local X = -30, -10, 10, 30, Y=10, Z=-10 --
    # same face/from_top convention as 87087, but 4 studs in a row instead
    # of 1. Also has real top studs (`stud.dat` at Y=0), unlike 87087.
    part = _CATALOG.get("30414")
    assert part.category == "snot"
    assert part.footprint == (4, 1)
    assert part.height_plates == 3
    assert part.top == "full"
    assert part.side_stud_face == "-z"
    assert part.side_stud_offset == (0, 10)
    assert part.side_stud_count == 4
    assert part.side_stud_local_positions() == [(-30, 10), (-10, 10), (10, 10), (30, 10)]


def test_single_stud_children_land_exactly_on_30414s_real_measured_stud_positions():
    # The real claim this test pins: SnotChild.local_pos's in-plane axis
    # (local_pos.x, for a -z face) indexes a parent's side-stud ROW the
    # same corner-based way GridPos.x indexes the ordinary grid -- a child
    # at local_pos.x=k lands on stud index k. Verified against 30414's own
    # independently-fetched real stud positions (-30, -10, 10, 30, relative
    # to the PART's own center), not just checked for internal
    # self-consistency: converts each real local stud X to its expected
    # WORLD X (parent's own footprint center + the real local offset) and
    # compares against place_in_frame's actual computed geometry for a
    # 1-wide plate placed at local_pos.x=k, k=0..3.
    longbrick = _CATALOG.get("30414")
    plate = _CATALOG.get("3024")
    parent = Brick(part=longbrick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)
    frame = snot_frame_for_brick(parent, "-z")

    real_local_stud_x = [-30, -10, 10, 30]
    parent_center_x = 0 * 20 + (4 * 20) // 2  # pos.x*STUD_LDU + ew*STUD_LDU//2 = 40

    for k, expected_local_x in enumerate(real_local_stud_x):
        pos, matrix = place_in_frame(frame, plate, GridPos(k, 0, 0), Rotation.YAW_0)
        x_range, _, _ = _raw_geometry_bbox(pos, matrix)
        center = (x_range[0] + x_range[1]) / 2
        assert center == parent_center_x + expected_local_x, f"stud {k}: got {center}"


def test_wide_child_spans_the_entire_side_stud_row_flush_and_centered():
    # The other real claim this test pins: a SINGLE child whose own
    # footprint matches the parent's full side-stud row width (here, a
    # "Plate 1 x 4" against 30414's 4-stud row) needs NO extra
    # face_offset math at all -- along=0 (the default) already spans the
    # parent's entire face exactly, because placement_to_ldraw's own
    # per-child centering and the frame's corner-based origin combine
    # correctly regardless of child width, not just for the child-width
    # == parent-width == 1 case Phase A shipped with. Checked against the
    # FULL raw geometry (all 8 corners), not just the origin point --
    # this module's own established discipline (see place_in_frame's
    # docstring for why an origin-only check has already let two real
    # bugs through).
    longbrick = _CATALOG.get("30414")
    wide_plate = _CATALOG.get("3710")  # Plate 1 x 4, footprint [4, 1]
    parent = Brick(part=longbrick, color=4, pos=GridPos(0, 0, 0), rotation=Rotation.YAW_0)
    frame = snot_frame_for_brick(parent, "-z")

    pos, matrix = place_in_frame(frame, wide_plate, GridPos(0, 0, 0), Rotation.YAW_0)
    x_range, _, z_range = _raw_geometry_bbox(pos, matrix, half_x=40, half_z=10)

    # Parent's own face spans world X [0, 80] (4 studs); the wide plate
    # should land flush across the whole thing, outward face at Z<0
    # (matching the -z direction), no gap or overlap.
    assert x_range == (0, 80)
    assert z_range == (-8, 0)


@pytest.mark.parametrize(
    "rotation,expected_in_plane_axis",
    [
        (Rotation.YAW_0, "x"),
        (Rotation.YAW_90, "z"),
        (Rotation.YAW_180, "x"),
        (Rotation.YAW_270, "z"),
    ],
)
def test_wide_child_stays_flush_across_all_four_parent_rotations(rotation, expected_in_plane_axis):
    # Real bug, found on the real turret model, not hypothetical: a wide
    # (asymmetric) child spanning a parent's full row landed correctly for
    # YAW_0 and YAW_270 but MIRRORED to the wrong side entirely for YAW_90
    # and YAW_180 -- 2 of the turret's 6 real SNOT panels were affected.
    # No earlier test could have caught this: Phase A's own tests only
    # ever used a symmetric 1x1 child (a mirrored span is identical either
    # way), and Phase B's wide-child test
    # (test_wide_child_spans_the_entire_side_stud_row_flush_and_centered,
    # above) only ever used a YAW_0 parent. This test is the first to
    # cross an ASYMMETRIC child with ALL FOUR parent yaws -- exactly the
    # combination that exposed the bug -- and pins the fix (snot_frame_for_brick
    # now derives the in-plane origin's corner from the actual composed
    # frame matrix's own sign, not an unconditional assumption).
    longbrick = _CATALOG.get("30414")
    wide_plate = _CATALOG.get("3710")  # Plate 1 x 4, footprint [4, 1]
    parent = Brick(part=longbrick, color=4, pos=GridPos(0, 0, 0), rotation=rotation)
    w, d = parent.footprint

    frame = snot_frame_for_brick(parent, longbrick.side_stud_face, face_offset=longbrick.side_stud_offset)
    pos, matrix = place_in_frame(frame, wide_plate, GridPos(0, 0, 0), Rotation.YAW_0)
    x_range, _, z_range = _raw_geometry_bbox(pos, matrix, half_x=40, half_z=10)

    in_plane_range = x_range if expected_in_plane_axis == "x" else z_range
    expected = (0, max(w, d) * 20)
    assert in_plane_range == expected, f"{rotation.name}: in-plane range {in_plane_range}, expected {expected}"


def test_rotation_for_outward_face_raises_for_a_non_snot_part():
    with pytest.raises(ValueError):
        rotation_for_outward_face(_CATALOG.get("3005"), "+x", (1, 1))


def test_rotation_for_outward_face_87087_resolves_for_every_face():
    # 87087's footprint (1,1) is symmetric -- every rotation preserves it --
    # so all 4 world faces should resolve to some rotation.
    part = _CATALOG.get("87087")
    for face in ("+x", "-x", "+z", "-z"):
        assert rotation_for_outward_face(part, face, (1, 1)) is not None


@pytest.mark.parametrize(
    "target_face,world_footprint,expected_rotation",
    [
        ("-z", (4, 1), Rotation.YAW_0),
        ("+z", (4, 1), Rotation.YAW_180),
        ("-x", (1, 4), Rotation.YAW_90),
        ("+x", (1, 4), Rotation.YAW_270),
    ],
)
def test_rotation_for_outward_face_30414_resolves_only_for_its_long_faces(
    target_face, world_footprint, expected_rotation
):
    part = _CATALOG.get("30414")
    assert rotation_for_outward_face(part, target_face, world_footprint) == expected_rotation


def test_rotation_for_outward_face_30414_never_resolves_for_its_short_ends():
    # The real, provable claim: exactly 2 of the 4 rotations preserve an
    # asymmetric footprint like [4, 1], and those 2 map the native face to
    # the two faces PERPENDICULAR to the long axis -- so the short ends
    # correctly never resolve, for either world orientation of the brick.
    part = _CATALOG.get("30414")
    assert rotation_for_outward_face(part, "+x", (4, 1)) is None
    assert rotation_for_outward_face(part, "-x", (4, 1)) is None
    assert rotation_for_outward_face(part, "+z", (1, 4)) is None
    assert rotation_for_outward_face(part, "-z", (1, 4)) is None
