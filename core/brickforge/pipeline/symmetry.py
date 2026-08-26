"""Mirror-symmetry detection and enforcement for "ordered" builds
(vehicles, buildings, furniture -- anything a person would expect to be
built flush and symmetric) as opposed to "organic" builds (animals, food,
landscapes), where a legalized model's own natural asymmetry -- a real
mesh is never perfectly symmetric, and this pipeline's own tiling/seam-
staggering can introduce more -- is left alone rather than "corrected"
into something that looks wrong for the subject.

Two pieces:

1. `detect_mirror_plane` scores candidate vertical mirror planes (a
   world-X or world-Z grid line) by what fraction of the model's own
   occupied cells have a matching-colour cell at their mirror position,
   and returns the best one if it clears a real symmetry threshold.
   Deliberately conservative: a model that isn't already close to
   symmetric returns None, and the caller (web/backend's prompt
   classifier decides "ordered" vs "organic"; this module only ever
   decides "is there actually a plane worth enforcing" -- two different
   questions, kept separate) should simply leave the model untouched
   rather than force a bad mirror onto something that was never meant
   to be symmetric.

2. `enforce_symmetry` rebuilds one half of the model as an EXACT mirror
   image of the other half -- not a nudge or an average, a real
   replacement, since "close to symmetric but not exactly" (a real
   complaint from actual generated output) is exactly what this
   replaces. The weaker/asymmetric half is discarded entirely, not
   patched.

**The geometry problem this had to solve, worked out algebraically, not
guessed:** this catalog's `Rotation` enum only has the 4 proper yaw
rotations (0/90/180/270 about the vertical axis) -- no reflections.
Mirroring a placed part across a world-X or world-Z plane is, in
general, an IMPROPER transform (determinant -1) that none of those 4
rotations can represent on its own. What makes it representable here
anyway: every part in this catalog (verified per-part via
`local_offset`, see catalog/parts_v1.yaml) has a footprint that is
symmetric in its own LOCAL X axis -- only local Z ever carries an
asymmetric offset (the slope families) or a directional "tall face".
Given local U (=local X) is footprint-symmetric, negating U in a
placement is *invisible* -- it renders identically either way -- so a
true reflection can always be re-expressed as one of the 4 existing
rotations, as long as the terms that multiply local W (=local Z, the
one axis that DOES matter) come out exactly right.

Worked the algebra directly from each Rotation's own (a, c, g, i) matrix
entries (the same ones `rotate_offset`/`rotate_footprint` already use):
for a rotation with world_x = a*u + c*w and world_z = g*u + i*w, a
world-X mirror needs a replacement rotation whose (c, i) exactly matches
(-c, i) -- the u-terms (a, g) are free to differ in sign, since u is
symmetric. Working through all 4 rotations against all 4 candidates
gives a clean, closed table with no exceptions:

    mirror across world X:  YAW_0->YAW_0, YAW_90->YAW_270,
                             YAW_180->YAW_180, YAW_270->YAW_90
    mirror across world Z:  YAW_0->YAW_180, YAW_90->YAW_90,
                             YAW_180->YAW_0, YAW_270->YAW_270

(Mirror-X swaps the two rotations whose footprint swap applies to the
X/Z axes -- 90 and 270 -- and leaves 0/180 fixed; mirror-Z is the exact
mirror image, swapping 0/180 and leaving 90/270 fixed.) This holds for
every part in the catalog, slopes included, precisely because every
slope's own asymmetry lives entirely in local Z, never local X --
confirmed catalog-wide, not assumed. Pinned computationally (not just
argued) in tests/test_pipeline_symmetry.py, which mirrors an actual
asymmetric slope through all 4 rotations and checks the real resulting
world-space footprint/position against the independently-computed
expected mirror image.

Safety: `enforce_symmetry` never asserts the result is structurally
sound on its own -- discarding an entire half of the model and rebuilding
it from a mirror can absolutely disconnect something that depended on
the discarded geometry (a wall built asymmetrically thicker on one side
for exactly the height something needed, say). This module makes no
connectivity claim; the caller MUST re-run `structure.analyze` (and
repair if needed) on the result before treating it as final, exactly the
same discipline every other mutating pass in this pipeline
(slopes.py, surface_refine.py, snot_placement.py) already follows -- see
brickforge_bridge.py's own wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..lattice import Rotation
from ..model import Brick, Model, PlacementError

# See module docstring for the derivation. Mirroring across world X only
# ever swaps YAW_90<->YAW_270 (the two rotations whose local Z axis maps
# into world X); YAW_0/YAW_180 are unaffected since their local Z stays
# mapped to world Z, untouched by an X mirror.
_MIRROR_X_ROTATION: dict[Rotation, Rotation] = {
    Rotation.YAW_0: Rotation.YAW_0,
    Rotation.YAW_90: Rotation.YAW_270,
    Rotation.YAW_180: Rotation.YAW_180,
    Rotation.YAW_270: Rotation.YAW_90,
}

# Mirror image of the table above: mirroring across world Z swaps
# YAW_0<->YAW_180 (their local Z maps into world Z) and leaves
# YAW_90/YAW_270 (whose local Z maps into world X) unaffected.
_MIRROR_Z_ROTATION: dict[Rotation, Rotation] = {
    Rotation.YAW_0: Rotation.YAW_180,
    Rotation.YAW_90: Rotation.YAW_90,
    Rotation.YAW_180: Rotation.YAW_0,
    Rotation.YAW_270: Rotation.YAW_270,
}

_MIN_SYMMETRY_SCORE = 0.85


@dataclass(frozen=True)
class MirrorPlane:
    axis: str  # "x" | "z"
    k: int  # a cell at index i mirrors to index (k - i - 1) along `axis`
    score: float  # fraction of occupied cells whose mirror cell matches (same colour)


def _occupied_cells_by_color(model: Model) -> dict[tuple[int, int, int], int]:
    cells: dict[tuple[int, int, int], int] = {}
    for brick in model.bricks:
        for cell in brick.occupied_cells():
            cells[cell] = brick.color
    return cells


def _symmetry_score(cells: dict[tuple[int, int, int], int], axis: str, k: int) -> float:
    if not cells:
        return 0.0
    matched = 0
    for (x, y, z), color in cells.items():
        mirror_cell = (k - x - 1, y, z) if axis == "x" else (x, y, k - z - 1)
        if cells.get(mirror_cell) == color:
            matched += 1
    return matched / len(cells)


def detect_mirror_plane(model: Model, min_score: float = _MIN_SYMMETRY_SCORE) -> MirrorPlane | None:
    """Scores every plausible mirror plane (both axes, a small window of
    candidate positions around each axis' own bounding-box center) and
    returns the best one, or None if nothing clears `min_score` -- a
    model that isn't already close to symmetric should never be forced
    into one, see module docstring."""
    cells = _occupied_cells_by_color(model)
    if not cells:
        return None

    xs = [c[0] for c in cells]
    zs = [c[2] for c in cells]

    best: MirrorPlane | None = None
    for axis, coords in (("x", xs), ("z", zs)):
        lo, hi = min(coords), max(coords)
        # A perfectly-centered symmetric range mirrors at k = lo+hi+1
        # (derived from "cell i mirrors to k-i-1"; setting lo<->hi gives
        # k = lo+hi+1 exactly). Scanning a small window around that
        # accounts for a model that's close to, but not exactly,
        # centered on its own bounding box.
        center_k = lo + hi + 1
        for k in range(center_k - 3, center_k + 4):
            score = _symmetry_score(cells, axis, k)
            if best is None or score > best.score:
                best = MirrorPlane(axis=axis, k=k, score=score)

    if best is not None and best.score >= min_score:
        return best
    return None


def _mirror_placement(brick: Brick, axis: str, k: int) -> tuple[str, int, tuple[int, int, int], Rotation]:
    """The mirror image of `brick`'s placement across `axis` at `k` --
    part and colour unchanged, position and rotation transformed per
    the module docstring's derivation."""
    w, d = brick.footprint
    new_rotation = (_MIRROR_X_ROTATION if axis == "x" else _MIRROR_Z_ROTATION)[brick.rotation]
    if axis == "x":
        new_pos = (k - brick.pos.x - w, brick.pos.y, brick.pos.z)
    else:
        new_pos = (brick.pos.x, brick.pos.y, k - brick.pos.z - d)
    return brick.part.id, brick.color, new_pos, new_rotation


def enforce_symmetry(model: Model, plane: MirrorPlane) -> Model:
    """Rebuilds `model` so that one half is an exact mirror image of the
    other, discarding the weaker/asymmetric half entirely rather than
    patching it. Deliberately tolerant of individual placement failures
    (try/except around every `place` call): mirroring an entire half
    in one pass can produce a handful of colliding or overlapping
    placements from residual asymmetry the detection score didn't catch
    down to the last cell, and the right response is to skip that one
    piece -- the caller's mandatory post-pass repair (see module
    docstring) is what actually guarantees the final result is sound,
    not this function."""
    result = Model(catalog=model.catalog)

    keep_bricks = []
    for brick in model.bricks:
        coord = brick.pos.x if plane.axis == "x" else brick.pos.z
        width = brick.footprint[0] if plane.axis == "x" else brick.footprint[1]
        if 2 * coord + width <= plane.k:
            keep_bricks.append(brick)

    for brick in keep_bricks:
        try:
            result.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
        except PlacementError:
            continue

        part_id, color, new_pos, new_rotation = _mirror_placement(brick, plane.axis, plane.k)
        if (new_pos, new_rotation) == ((brick.pos.x, brick.pos.y, brick.pos.z), brick.rotation):
            continue  # self-symmetric placement, already placed once above
        try:
            result.place(part_id, color, new_pos[0], new_pos[1], new_pos[2], rotation=new_rotation)
        except PlacementError:
            continue

    return result


def symmetrize_if_detected(model: Model, min_score: float = _MIN_SYMMETRY_SCORE) -> Model:
    """Convenience entry point: detect a mirror plane and enforce it if
    found, otherwise return `model` unchanged. Callers that want the
    detected plane itself (e.g. for logging/stats) should call
    `detect_mirror_plane` and `enforce_symmetry` directly instead --
    this wrapper is for the common case, not the only way to use this
    module. Does NOT re-run structural analysis/repair -- see module
    docstring, that's the caller's responsibility."""
    plane = detect_mirror_plane(model, min_score=min_score)
    if plane is None:
        return model
    return enforce_symmetry(model, plane)
