import pytest

from brickforge import Model, PartCatalog
from brickforge.lattice import GridPos, Rotation, placement_to_ldraw
from brickforge.pipeline.symmetry import (
    MirrorPlane,
    _mirror_placement,
    detect_mirror_plane,
    enforce_symmetry,
)
from brickforge.structure import analyze, bridge_unstable, refill_enclosed_holes

RED = 4
BLUE = 1


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


# --- Mirror-rotation correctness -------------------------------------
# The crux of this module: verifies the algebraically-derived rotation
# table (see symmetry.py's own module docstring) against an INDEPENDENT
# computation -- the real LDU coordinate placement_to_ldraw produces for
# the computed mirror placement must equal `20*k - original_ldu`, the
# direct reflection formula in LDU space (derived separately in the
# docstring: the grid-mirror plane sits at grid-coordinate k/2, i.e.
# LDU coordinate 10*k, so a point at ldu_x reflects to 20*k - ldu_x).
# Uses "3040" (Slope Brick 45 2 x 1), a genuinely asymmetric part
# (local_offset [0, 10]) precisely because a bug here would be invisible
# on a symmetric part (footprint/local_offset (0,0)) -- the same
# "don't test only the easy case" discipline this catalog's own history
# already learned the hard way (see catalog/parts_v1.yaml's local_offset
# commentary).


@pytest.mark.parametrize("rotation", [Rotation.YAW_0, Rotation.YAW_90, Rotation.YAW_180, Rotation.YAW_270])
@pytest.mark.parametrize("axis,k", [("x", 7), ("z", 7), ("x", 8), ("z", 8)])
def test_mirror_rotation_matches_true_ldu_reflection(catalog, rotation, axis, k):
    part = catalog.get("3040")
    pos = GridPos(2, 0, 3)
    brick = Model(catalog=catalog).place(part.id, RED, pos.x, pos.y, pos.z, rotation=rotation)

    orig_ldu = placement_to_ldraw(
        brick.pos, *part.footprint, part.height_plates, brick.rotation,
        local_offset=part.local_offset, y_anchor=part.y_anchor,
    )

    mirror_part_id, mirror_color, mirror_pos, mirror_rotation = _mirror_placement(brick, axis, k)
    assert mirror_part_id == part.id
    assert mirror_color == RED

    mirror_ldu = placement_to_ldraw(
        GridPos(*mirror_pos), *part.footprint, part.height_plates, mirror_rotation,
        local_offset=part.local_offset, y_anchor=part.y_anchor,
    )

    if axis == "x":
        assert mirror_ldu[0] == 20 * k - orig_ldu[0]
        assert mirror_ldu[2] == orig_ldu[2]
    else:
        assert mirror_ldu[2] == 20 * k - orig_ldu[2]
        assert mirror_ldu[0] == orig_ldu[0]
    assert mirror_ldu[1] == orig_ldu[1]  # height is never touched by a horizontal mirror


# --- detect_mirror_plane ---------------------------------------------


def test_detects_a_genuinely_symmetric_model(catalog):
    model = Model(catalog=catalog)
    # Symmetric about grid-x = 2 (k = 2*2 = 4: cell x mirrors to 4-x-1=3-x).
    model.place("3024", RED, x=0, y=0, z=0)
    model.place("3024", RED, x=3, y=0, z=0)
    model.place("3024", BLUE, x=1, y=0, z=0)
    model.place("3024", BLUE, x=2, y=0, z=0)

    plane = detect_mirror_plane(model)

    assert plane is not None
    assert plane.axis == "x"
    assert plane.score == 1.0


def test_does_not_detect_a_plane_for_a_genuinely_asymmetric_model(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, x=0, y=0, z=0)
    model.place("3024", BLUE, x=5, y=0, z=0)
    model.place("3024", RED, x=9, y=0, z=2)

    plane = detect_mirror_plane(model)

    assert plane is None


def test_empty_model_has_no_mirror_plane(catalog):
    model = Model(catalog=catalog)
    assert detect_mirror_plane(model) is None


# --- enforce_symmetry --------------------------------------------------


def test_enforce_symmetry_replaces_the_asymmetric_half(catalog):
    # Left half (x=0,1) is the "good" side; right half has one cell
    # wrong (BLUE instead of RED) and one cell simply missing. After
    # enforcement, every occupied cell's mirror must match exactly.
    model = Model(catalog=catalog)
    model.place("3024", RED, x=0, y=0, z=0)  # mirrors to x=3
    model.place("3024", RED, x=1, y=0, z=0)  # mirrors to x=2
    model.place("3024", BLUE, x=3, y=0, z=0)  # wrong colour -- should be replaced
    # x=2 deliberately left empty -- should be filled in by the mirror pass

    plane = MirrorPlane(axis="x", k=4, score=0.5)
    refined = enforce_symmetry(model, plane)

    cells = {}
    for brick in refined:
        for cell in brick.occupied_cells():
            cells[cell] = brick.color

    for (x, y, z), color in cells.items():
        mirror_cell = (plane.k - x - 1, y, z)
        assert cells.get(mirror_cell) == color, f"cell {(x, y, z)} has no matching mirror"


def test_symmetrized_model_can_be_repaired_to_full_connectivity(catalog):
    # A real end-to-end shape: a torso spanning two leg columns, a
    # complete (grounded, torso-connected) left leg, and an asymmetric
    # right leg missing its own y=1 plate (as if the legalizer/mesh had
    # introduced small noise) -- so the right leg independently touches
    # the ground but does NOT reach up to the torso, a real disconnection
    # (not just an asymmetry) before symmetrization. Mirrors exactly how
    # this is meant to be used in the real pipeline (see
    # brickforge_bridge.py's own wiring: detect+enforce, then re-analyze
    # and repair, never trusted to be structurally sound on its own) --
    # note two SEPARATE legs that never connect to each other or anything
    # above them would legitimately stay "not one piece" no matter how
    # symmetric they are (see structure/weakpoints.py's own docstring on
    # why an independently-grounded component is correctly left alone,
    # not merged into "main" just for existing) -- the torso here is what
    # makes "one piece" the correct, achievable outcome.
    model = Model(catalog=catalog)
    model.place("3024", RED, x=0, y=0, z=0)  # left leg, full height
    model.place("3024", RED, x=0, y=1, z=0)
    model.place("3024", RED, x=3, y=0, z=0)  # right leg, missing the y=1 plate (asymmetric)
    model.place("3710", RED, x=0, y=2, z=0)  # torso: Plate 1x4, spans both leg columns

    # Explicit plane, not detect_mirror_plane: every placement here sits
    # at z=0 with zero Z-depth, so a Z-mirror is trivially "perfectly
    # symmetric" (nothing varies along Z at all) and scores 1.0 -- higher
    # than the genuinely-intended X-axis leg symmetry, which is real but
    # imperfect (the right leg is missing a plate). detect_mirror_plane's
    # own axis-selection is separately and thoroughly covered by
    # test_detects_a_genuinely_symmetric_model and
    # test_does_not_detect_a_plane_for_a_genuinely_asymmetric_model above;
    # this test's own focus is the symmetrize-then-repair pipeline, so it
    # targets the X plane directly rather than fighting that ambiguity.
    plane = MirrorPlane(axis="x", k=4, score=1.0)  # x=0 <-> x=3
    symmetrized = enforce_symmetry(model, plane)

    report = analyze(symmetrized)
    if not report.is_single_piece or report.critical_bricks:
        bridged = bridge_unstable(symmetrized)
        refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
        symmetrized = refilled.model
        report = analyze(symmetrized)

    assert report.is_single_piece
    assert report.critical_bricks == set()
