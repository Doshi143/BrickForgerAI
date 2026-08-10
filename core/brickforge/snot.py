"""SNOT (Studs Not On Top) coordinate-frame math -- Phase A.

Deliberately a new, separate, composable module rather than an extension
of the existing yaw-only `Rotation` enum in lattice.py: `Model`, `Brick`,
collision detection, and the structural connectivity graph all assume
every placed part lives on one shared Y-up grid, and none of that is
touched here. This module adds the ability to place a SNOT sub-assembly
in its OWN locally-rotated grid, anchored to a specific face of an
already-placed, ordinary parent `Brick` -- with zero regression risk to
anything that already works, since nothing existing is modified.

Phase A scope, precisely: prove this coordinate math is correct (verified
in Studio, see examples/snot_alignment_test.py), for a single SNOT brick
centered on one face of an ordinary parent brick. NOT in scope yet:
folding SNOT children into `Model`'s collision grid or the structural
connectivity graph (structure/graph.py still only understands top/bottom
stud edges) -- that is Phase B, and must not be assumed to work until
built and verified on its own terms.

The core idea: a SNOT child's own local placement is computed with the
EXACT SAME, already-proven `lattice.placement_to_ldraw` used for every
other part in this codebase -- nothing about that function changes. The
only new work is (1) determining the world position and rotation of the
child's local origin (a `SnotFrame`, anchored at a parent brick's face),
and (2) transforming the child's already-computed local LDU placement by
that frame to get its final world LDU position and rotation matrix.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lattice import GridPos, PLATE_HEIGHT_LDU, Rotation, STUD_LDU, placement_to_ldraw
from .model import Brick
from .parts import Part

Face = str  # "+x" | "-x" | "+z" | "-z"

_FACES: tuple[Face, ...] = ("+x", "-x", "+z", "-z")

# Which of a SNOT child's own LOCAL axes runs IN-PLANE (parallel to the
# parent's face, i.e. along a multi-stud side row) rather than outward
# (always GridPos.y, the frame's own stacking axis) or vertical (whichever
# axis the tilt matrix redirects into world Y -- see place_in_frame's own
# docstring). Same distinction snot_frame_for_brick's `in_face_local`
# already encodes ad hoc; exposed as a named function so callers outside
# this module (structure/graph.py, for SNOT edge weights) don't have to
# re-derive it from the tilt matrices.
_IN_PLANE_AXIS: dict[Face, str] = {"+x": "z", "-x": "z", "+z": "x", "-z": "x"}


def in_plane_axis(face: Face) -> str:
    """'x' or 'z' -- which of a child's own local GridPos axes indexes
    position along `face`'s in-plane, multi-stud direction."""
    if face not in _FACES:
        raise ValueError(f"Unknown face {face!r}, expected one of {_FACES}")
    return _IN_PLANE_AXIS[face]

# A face is a fixed property of a SNOT part's own geometry (like top/bottom
# coverage) -- expressed in the part's own UNROTATED local frame, as a unit
# (dx, dz) direction. Reused directly as input to Rotation.rotate_offset,
# the exact same function local_offset already uses to correctly rotate a
# local-frame direction into world space under a parent's yaw -- a face
# direction transforms exactly the same way a position offset does.
_FACE_UNIT_OFFSET: dict[Face, tuple[int, int]] = {
    "+x": (1, 0),
    "-x": (-1, 0),
    "+z": (0, 1),
    "-z": (0, -1),
}

# Tilts a part so its local -Y -- the part's REAL native top-stud
# direction -- points toward the stated LOCAL face direction, i.e. this
# is the matrix for a part whose parent is at YAW_0 (identity yaw).
# Row-major "world = M @ local" convention, matching Rotation's own
# documented a-b-c/d-e-f/g-h-i layout (see lattice.py). Each derived as
# an elementary rotation about a HORIZONTAL axis (X or Z -- yaw only ever
# rotates about the vertical Y axis and cannot produce this).
#
# Real bug caught here, not just a hypothetical: an earlier version of
# this table was derived and verified against local **+Y**, reasoning
# about it as a generic "up" direction -- but this project's own
# established, verified convention (see lattice.py's own module
# docstring) is that a part's origin is TOP-anchored with local Y=0 at
# the top, and the raw .dat geometry extends in *increasing* local Y
# toward the BOTTOM. That means the real native direction pointing away
# from a top stud -- the direction that actually needs to end up facing
# outward on a SNOT face -- is local **-Y**, not +Y. Confirmed
# concretely, not just reasoned about on paper: with the old matrices, a
# 1x1 plate meant to sit flush against a 1x1 parent's face instead landed
# 8 LDU further out with an 8 LDU gap in between (full raw-geometry
# corners transformed and compared against the parent's own known
# bounding box, not just the origin point -- the origin-only check in an
# earlier pass wasn't rigorous enough to catch this). Fixed by using each
# matrix's derivation for the *opposite* labeled face -- since negating
# the target direction is equivalent to using the supplementary rotation
# angle, which turns out to be exactly the matrix originally derived for
# the other face.
#
# Independently verified computationally (not just by hand) in
# tests/test_snot.py: each is a proper rotation (orthonormal, determinant
# +1 -- i.e. no mirroring), each actually sends local -Y to the stated
# direction, and a full raw-geometry bounding box (not just the origin
# point) lands flush against a real parent brick with zero gap or overlap.
#
# Known open question, deliberately not resolved here: each face's matrix
# is individually a *correct* rotation, but the remaining one-degree-of-
# freedom "spin" around the tilt axis was picked independently per face,
# with nothing yet forcing the four to agree with each other on how a
# NON-symmetric part's other two axes get distributed. There's no single
# "obviously correct" spin to fix that with, without a real bracket
# part's own geometry to anchor against -- a real SNOT bracket has actual
# molded asymmetry that decides this for real, the same way local_offset
# already does for slopes. Phase A verifies all four faces are
# geometrically correct for a symmetric 1x1 part; reconciling spin choice
# for asymmetric parts against real per-part geometry is Phase B/C work.
_LOCAL_TILT_MATRIX: dict[Face, tuple[int, ...]] = {
    "+x": (0, -1, 0, 1, 0, 0, 0, 0, 1),
    "-x": (0, 1, 0, -1, 0, 0, 0, 0, 1),
    "+z": (1, 0, 0, 0, 0, 1, 0, -1, 0),
    "-z": (1, 0, 0, 0, 0, -1, 0, 1, 0),
}


def _matmul(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """3x3 * 3x3 product, both given as row-major 9-tuples."""
    result = []
    for i in range(3):
        for j in range(3):
            result.append(sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3)))
    return tuple(result)


def _matvec(m: tuple[int, ...], v: tuple[int, int, int]) -> tuple[int, int, int]:
    a, b, c, d, e, f, g, h, i = m
    x, y, z = v
    return (a * x + b * y + c * z, d * x + e * y + f * z, g * x + h * y + i * z)


@dataclass(frozen=True)
class SnotFrame:
    """A local-to-world transform for a SNOT sub-assembly, anchored at a
    specific point on a specific already-placed parent `Brick`'s face.

    Both fields are in NATIVE LDraw convention throughout (-Y up, the
    exact space `placement_to_ldraw` already returns, and the space the
    raw .dat geometry itself is defined in) -- deliberately, not an
    "internal Y-up" convention requiring a flip/unflip dance at the
    boundary. An earlier version of this module tried the flip/unflip
    approach and it was a real, caught source of bugs (see
    _LOCAL_TILT_MATRIX's own docstring and place_in_frame's git history):
    every one of `frame.matrix`, `local_rotation.matrix`, and the raw
    .dat file's own vertex data needs to agree on ONE convention to
    compose correctly, and native LDraw convention is the one they can
    all already agree on for free, since that's what the .dat files and
    placement_to_ldraw's *output* already are.

    `origin_ldu`: world LDU position of the frame's own local origin.
    `matrix`: world rotation matrix (row-major 9-tuple) mapping the SNOT
    sub-assembly's own local axes into world axes -- local -Y (a child
    part's own real top-stud direction, native convention) maps to
    whichever world direction this frame's face actually points,
    accounting for the parent's own yaw.
    """

    origin_ldu: tuple[int, int, int]
    matrix: tuple[int, ...]


def snot_frame_for_brick(
    parent: Brick,
    local_face: Face,
    face_offset: tuple[int, int | None] = (0, None),
) -> SnotFrame:
    """Compute the world frame for a SNOT sub-assembly attached at
    `parent`'s `local_face` -- a fixed property of the PART's own
    geometry (e.g. "the side its molded stud is actually on"), expressed
    in the part's own unrotated local frame, not world space. Rotated
    into world space by the parent's own yaw.

    `face_offset` = (offset along the face's in-plane horizontal axis,
    offset down from the parent's own top), in LDU, both measured in the
    part's own unrotated local frame -- same convention as
    Part.side_stud_offset, which should be passed here directly once
    known for a real part. Defaults to (0, None): a plain corner on the
    in-plane axis (see below for why that's the right default, not a
    center), and the parent's exact half-height on the vertical axis.
    `from_top`'s half-height default is only an approximation -- confirmed
    wrong for a real measured part, not just suspected: part 87087's real
    side stud sits at 10 LDU from its own top, not the 12 LDU half-height
    of its 24-LDU-tall body, verified from 87087.dat's own raw geometry
    (`1 16 0 10 -10 ... stud2a.dat`). Pass the part's real
    Part.side_stud_offset whenever it's known, rather than trusting this
    default.

    Real bug caught by the full-corner-based bounding-box check in this
    module's own test suite, not just the origin-point check that missed
    it: the in-plane axis's origin used to add HALF the parent's own
    face width as a "center the face" term -- but placement_to_ldraw
    (called later, inside place_in_frame, for the CHILD's own local
    placement) already centers the child within its own footprint cell
    on that exact axis. Adding both meant a child was pushed a full
    child-footprint-width past where it should sit, not centered on the
    parent's face at all -- confirmed concretely: a 1x1 plate meant to
    center on a 1x1 parent's face (both spanning world X [0, 20]) instead
    landed at world X [10, 30]. The origin's in-plane component is now a
    plain CORNER reference (matching how GridPos(0, 0, 0) is already a
    corner, not a center, everywhere else in this codebase) -- letting
    placement_to_ldraw's own single, already-correct centering do that
    job, with `face_offset`'s `along` layered on top only as an
    intentional additional shift from that corner, not a second centering.

    `origin_ldu` is in NATIVE LDraw convention (-Y up), matching
    place_in_frame's own docstring on why that's the one convention every
    piece of this composition (the raw .dat geometry, placement_to_ldraw's
    output, and _LOCAL_TILT_MATRIX) can already agree on without an
    internal flip/unflip step."""
    if local_face not in _FACES:
        raise ValueError(f"Unknown face {local_face!r}, expected one of {_FACES}")
    along, from_top = face_offset

    # Composed in this order, not looked up by world-facing direction
    # alone -- confirmed by direct computation (not just argued) that the
    # two are NOT equivalent whenever the parent has a non-identity yaw:
    # the parent's own rotation must carry the SNOT child's whole local
    # frame along with it, same as it would for a real physical brick.
    matrix = _matmul(parent.rotation.matrix, _LOCAL_TILT_MATRIX[local_face])

    # rotate_offset resolves which WORLD-axis-aligned face this actually
    # is, post-yaw -- reused directly rather than re-deriving, since this
    # is exactly what it's already proven to do correctly for local_offset.
    world_fx, world_fz = parent.rotation.rotate_offset(*_FACE_UNIT_OFFSET[local_face])
    # `along` is measured along the face's own in-plane horizontal axis
    # (Z for a +x/-x face, X for a +z/-z face) -- rotated into world by
    # the same parent yaw, exactly like local_offset's own components are.
    in_face_local = (0, along) if local_face in ("+x", "-x") else (along, 0)
    world_along_x, world_along_z = parent.rotation.rotate_offset(*in_face_local)

    ew, ed = parent.footprint  # already post-rotation (Brick.footprint property)
    x0 = parent.pos.x * STUD_LDU
    z0 = parent.pos.z * STUD_LDU
    # Native LDraw convention throughout: the parent's own TOP, in the
    # same -Y-up terms placement_to_ldraw itself would give a top-anchored
    # part at this grid position -- then `from_top` (a positive LDU count
    # going DOWN from that top, same direction native Y already increases
    # in) is added directly, no extra sign juggling needed.
    parent_top_native = -((parent.pos.y + parent.part.height_plates) * PLATE_HEIGHT_LDU)
    y_center = parent_top_native + (
        (parent.part.height_plates * PLATE_HEIGHT_LDU) // 2 if from_top is None else from_top
    )

    # Real bug, found only by testing an ASYMMETRIC child (30414's own
    # full-width plate) across all 4 parent yaws, not just the native
    # YAW_0 case every earlier test used -- a symmetric 1x1 child (Phase
    # A's only child so far) can't expose this, since a mirrored span
    # looks identical either way. Confirmed by direct computation on the
    # real turret model, not hypothetical: 2 of 6 SNOT panels landed
    # mirrored to completely the wrong side of their parent, which is
    # exactly the "pieces are off" the founder flagged in Studio.
    #
    # The in-plane origin below used to be an UNCONDITIONAL corner (x0 or
    # z0, whichever axis is in-plane for this face) -- correct only when
    # the child's local X axis maps to that world axis with coefficient
    # +1. For a `local_face` of "-z" (the only value ever used in this
    # codebase -- every SNOT part's `side_stud_face`) composed with a
    # parent at YAW_90 or YAW_180, that coefficient is actually -1 (the
    # composition puts local X on the "wrong end" of the axis), and an
    # unconditional MIN corner then puts a wide child's span entirely on
    # the opposite side of where it should be. `matrix[0]`/`matrix[6]`
    # (the ALREADY-COMPOSED frame matrix's own coefficients for "local X's
    # contribution to world X / world Z") tell us this directly and
    # generally -- reusing the exact same real transform already computed
    # above, not a re-derived proxy that could disagree with it. When
    # local X is actually the VERTICAL axis for this face instead (the
    # direct-face-parameter Phase A test cases, e.g. face="+x" at YAW_0),
    # both coefficients are 0, and `>= 0` safely falls back to the
    # original MIN-corner behavior those cases were already verified
    # against -- confirmed by direct computation across all 4 native
    # tilts, not just argued. See tests/test_snot.py for the parametrized
    # regression pinning all 4 parent yaws for an asymmetric child.
    if (world_fx, world_fz) == (1, 0):
        origin_z = z0 if matrix[6] >= 0 else z0 + ed * STUD_LDU
        origin = (x0 + ew * STUD_LDU, y_center, origin_z)
    elif (world_fx, world_fz) == (-1, 0):
        origin_z = z0 if matrix[6] >= 0 else z0 + ed * STUD_LDU
        origin = (x0, y_center, origin_z)
    elif (world_fx, world_fz) == (0, 1):
        origin_x = x0 if matrix[0] >= 0 else x0 + ew * STUD_LDU
        origin = (origin_x, y_center, z0 + ed * STUD_LDU)
    else:  # (0, -1)
        origin_x = x0 if matrix[0] >= 0 else x0 + ew * STUD_LDU
        origin = (origin_x, y_center, z0)

    origin = (origin[0] + world_along_x, origin[1], origin[2] + world_along_z)
    return SnotFrame(origin_ldu=origin, matrix=matrix)


def place_in_frame(
    frame: SnotFrame,
    part: Part,
    local_pos: GridPos,
    local_rotation: Rotation = Rotation.YAW_0,
) -> tuple[tuple[int, int, int], tuple[int, ...]]:
    """Final world (x, y, z) LDU position (LDraw convention) and world
    3x3 rotation matrix for a part placed at `local_pos` within `frame`'s
    own local sub-lattice. `local_pos.y = 0` is flush against the frame's
    origin (i.e. directly against the parent's stud), exactly the same as
    GridPos.y = 0 means "resting on the ground" in the normal grid.

    A single, direct composition: placement_to_ldraw's own output is
    already in native LDraw convention, and so is frame.matrix (see
    _LOCAL_TILT_MATRIX's own docstring) -- so the child's local placement
    can be rotated and translated by the frame in one step, with no
    intermediate convention conversion at all.

    An earlier version of this function DID insert an "undo the LDraw
    flip, transform, then reapply it" step here, reasoning (correctly, as
    far as it went) that placement_to_ldraw's Y output and a rotation
    matrix derived assuming un-flipped Y-up couldn't be composed directly.
    That was real and the fix (verified: a plate that had been landing
    *inside* the parent's own body instead sat flush and outward) is
    still real, but it was only a partial fix -- _LOCAL_TILT_MATRIX
    itself was later found to have been derived against the WRONG
    reference vector for this project's actual top-anchored convention
    (see that table's own docstring), and once the matrices were
    corrected to operate on genuinely native coordinates, the "undo the
    flip" step here became unnecessary AND wrong -- it would have
    silently re-introduced a mismatched convention in the opposite
    direction. Both fixes were required together, each verified with a
    full raw-geometry bounding box, not just an origin point, before
    being trusted (see this module's own test suite).

    A THIRD bug, caught only by the user's own Studio screenshot after
    Phase A shipped -- the horizontal/outward tests all passed while this
    one was still broken, because none of them checked the vertical span
    at all. `placement_to_ldraw` centers a part within its own local grid
    cell on BOTH horizontal axes (`pos*STUD_LDU + footprint*STUD_LDU//2`)
    -- correct for the two axes this frame actually uses (local Y, the
    outward-stacking axis; and whichever of local X/Z the tilt keeps
    in-plane, matching the parent's face width -- both independently
    verified flush/centered by this module's own test suite). But the
    THIRD axis -- whichever of local X/Z the tilt matrix redirects into
    WORLD Y (vertical) -- isn't a footprint-covering axis at all: a
    single stud is a POINT on the parent's face, not a cell to center
    within. Leaving that axis's automatic half-footprint centering in
    place put every SNOT child a half-footprint-width (10 LDU for a
    1-stud part) away from the real attachment point -- confirmed by hand
    computation against the real 87087 example: the child landed centered
    at world Y -2 instead of the frame's own measured -12/-14 origin,
    exactly the "10 LDU too high" the screenshot showed. Fixed by
    detecting which local axis feeds world Y directly from frame.matrix's
    own world-Y row (index 3:6) -- exactly one of its local-X or local-Z
    coefficient is nonzero for every _LOCAL_TILT_MATRIX entry, since
    tilting about a horizontal axis always swaps one horizontal axis with
    vertical -- and subtracting that axis's own automatic centering back
    out, so it lands exactly on the frame's origin instead of a
    half-footprint-width away from it."""
    local_ldraw = placement_to_ldraw(
        local_pos,
        *part.footprint,
        part.height_plates,
        local_rotation,
        local_offset=part.local_offset,
        y_anchor=part.y_anchor,
    )

    eff_width, eff_depth = local_rotation.rotate_footprint(*part.footprint)
    _, _, _, world_y_from_x, _, world_y_from_z, _, _, _ = frame.matrix
    lx, ly, lz = local_ldraw
    if world_y_from_x != 0:
        lx -= (eff_width * STUD_LDU) // 2
    elif world_y_from_z != 0:
        lz -= (eff_depth * STUD_LDU) // 2
    local_ldraw = (lx, ly, lz)

    world_ldraw = _matvec(frame.matrix, local_ldraw)
    world_ldraw = tuple(o + w for o, w in zip(world_ldraw, frame.origin_ldu))
    world_matrix = _matmul(frame.matrix, local_rotation.matrix)
    return world_ldraw, world_matrix


@dataclass(frozen=True)
class SnotChild:
    """One SNOT sub-assembly part attached in a parent brick's local
    `SnotFrame` -- Phase B's own unit of work, and the thing
    `structure/graph.py::build_connectivity_graph` treats as a graph node
    once wired in. Deliberately NOT stored on `Model` (see this module's
    own top-of-file docstring for why SNOT children stay outside Model's
    shared grid/collision system) -- this is a parallel, explicitly-indexed
    list a caller keeps alongside a `Model` and hands to both
    `place_in_frame` (for LDR serialization, via `snot_frame_for_brick`)
    and `build_connectivity_graph` (for structural analysis).

    `parent_index` is the index into `model.bricks` of the already-placed
    SNOT-category brick this child is anchored to -- its own
    `part.side_stud_face` supplies which face, so there is currently no
    support for a parent with more than one side-stud face active at once.
    `local_pos`/`local_rotation` are passed straight through to
    `place_in_frame`: `local_pos.y == 0` means flush against the parent's
    own molded stud(s) (the sideways equivalent of `GridPos.y == 0` meaning
    "resting on the ground"), and the in-plane axis (`local_pos.x` for a
    +/-z face, `local_pos.z` for a +/-x face -- see `in_plane_axis`)
    indexes along the parent's side-stud ROW the same corner-based way
    `GridPos.x` already indexes the ordinary grid: a child placed with its
    in-plane coordinate equal to `k` lands on stud index `k` (0-indexed
    from the frame's own corner), for a parent whose SnotFrame was built at
    the default `face_offset=(0, ...)`. Verified computationally against
    30414's own real, independently-fetched stud positions in
    tests/test_snot.py -- not just asserted to generalize from the
    single-stud 87087 case Phase A shipped with.

    `parent_overlaps` (Phase C.1's region-growing): `parent_index` is
    always the frame used for this child's OWN geometry (`place_in_frame`
    needs exactly one frame, so this can't change), but a region-grown
    panel spanning several merged parents can rest on studs belonging to
    OTHER parents too, not just the one whose frame anchors it -- a plain
    `_in_plane_span`-vs-`side_stud_count` check against `parent_index`
    alone would miss those entirely (confirmed as a real bug, not
    hypothetical: a merged panel's trailing tile landed with ZERO graph
    edge at all, not even an undercounted one, since it didn't overlap the
    anchor's own single stud). When set (a tuple of `(parent_index,
    overlap_stud_count)` pairs, pre-computed by whichever pipeline stage
    built this child -- see `pipeline/snot_placement.py::_tile_run`),
    `structure/graph.py` trusts it directly instead of recomputing overlap
    against `parent_index` alone, the same "measured once at the emitting
    stage, trusted by the graph" pattern already used for ordinary
    top/bottom stud edges. `None` (default) preserves the exact
    single-parent behavior every pre-region-growing caller already relies
    on."""

    parent_index: int
    part: Part
    local_pos: GridPos
    local_rotation: Rotation = Rotation.YAW_0
    parent_overlaps: tuple[tuple[int, int], ...] | None = None


def rotation_for_outward_face(part: Part, target_face: Face, world_footprint: tuple[int, int]) -> Rotation | None:
    """Phase C: which `Rotation`, if any, makes `part` -- placed at this
    rotation -- occupy exactly `world_footprint` (so it collides with
    nothing else the original brick it's replacing didn't already touch)
    AND point `part`'s own native `side_stud_face` toward `target_face` in
    world space. Returns `None` if no rotation satisfies both, which is a
    real, correct outcome for some (part, face) pairs, not a bug: exactly 2
    of the 4 rotations preserve a given ASYMMETRIC footprint (e.g. 30414's
    `[4, 1]`), and those 2 map its native face to the two faces
    PERPENDICULAR to the long axis -- so a 4-long part's short ends
    correctly never resolve, with no special-casing needed, because the
    footprint-preservation filter alone already rules them out. Verified
    computationally, not just argued, in tests/test_snot.py.

    Raises if `part` has no `side_stud_face` at all -- a caller bug (only a
    SNOT-category part can be pointed at a face), not a case to silently
    skip."""
    if part.side_stud_face is None:
        raise ValueError(f"Part {part.id!r} has no side_stud_face")
    for rotation in Rotation:
        if rotation.rotate_footprint(*part.footprint) != world_footprint:
            continue
        world_face = rotation.rotate_offset(*_FACE_UNIT_OFFSET[part.side_stud_face])
        if world_face == _FACE_UNIT_OFFSET[target_face]:
            return rotation
    return None
