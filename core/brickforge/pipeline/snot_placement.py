"""SNOT Phase C.1: automatic anchor detection + region-grown panel
attachment (DESIGN.md's Phase 6 "region-growing on near-vertical
surfaces", scoped down to its first verified slice -- see the approved
plan for the full reasoning on why this is deliberately NOT the whole of
Phase C).

`place_snot_panels` scans an already-repaired `Model` for ordinary bricks
with a fully-exposed outward side face, swaps each candidate in place for
the matching real SNOT part (87087 or 30414, at whichever rotation points
that part's own molded stud toward the exposed face -- see
`snot.rotation_for_outward_face`), gated by the mesh's original solid
silhouette (`solid_grid`, same source `structure/bridge.py` already uses
for its own "stay inside the real shape" check) so nothing pokes into open
air.

**Region-growing** (added after the founder's direct feedback that a
single narrow panel per brick -- matching only that one brick's own
footprint -- doesn't read as real coverage): swapped-in parents that share
the exact same part id and rotation (guaranteeing an IDENTICAL frame
matrix -- see `snot.rotation_for_outward_face`'s own docstring on why
different parts/rotations can have a different "spin") and whose computed
`SnotFrame` origins are contiguous along the in-plane axis (differ by
exactly `side_stud_count * STUD_LDU`, with the vertical and outward
coordinates identical) are merged into one RUN, tiled with the widest
available plates rather than one plate per brick. The merge only ever uses
ONE anchor parent's frame (the run's first member) -- a wide plate placed
within it via `local_pos` legitimately spans neighboring parents' physical
positions too, since a `SnotFrame` is just a rigid linear coordinate
system, but the structural graph (`structure/graph.py`) still only ever
adds an edge to the declared anchor, not to every parent the panel
physically rests on. That's a real, accepted under-count, not a
soundness bug -- the same "never overclaim connectivity" direction this
project already takes elsewhere (see e.g. `Part.top: none`'s own
docstring) -- documented here rather than silently assumed away.

Deliberately NOT attempted here (see the plan): a closing slope/wedge to
actually smooth the silhouette, or multi-plate depth beyond a single
outward step. This is the foundation those build on, not a replacement.

Safety argument for the brick swap, same shape as tile/slope substitution
in this package: every candidate SNOT part has `bottom: full`, matching
every ordinary brick's own `bottom: full`, so downward connectivity is
never affected. 30414 also has `top: full`, so swapping it in never loses
anything. 87087 has `top: none`, so it's only ever swapped in where the
candidate brick's own top is already fully exposed (nothing resting on
it) -- the identical "only where already exposed" rule
`surface_refine.py`'s tile substitution already relies on. Verified with
before/after `analyze()` checks in tests/test_pipeline_snot_placement.py
and in examples/structural_report.py, not just argued.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..lattice import STUD_LDU, GridPos, Rotation
from ..model import Brick, Model
from ..parts import Part, PartCatalog
from ..snot import SnotChild, in_plane_axis, rotation_for_outward_face, snot_frame_for_brick
from .grid import VoxelGrid

_FACE_STEP: dict[str, tuple[int, int]] = {"+x": (1, 0), "-x": (-1, 0), "+z": (0, 1), "-z": (0, -1)}
_FACE_ORDER = ("+x", "-x", "+z", "-z")
_OPPOSITE_FACE: dict[str, str] = {"+x": "-x", "-x": "+x", "+z": "-z", "-z": "+z"}


@dataclass
class SnotPlacementResult:
    model: Model
    snot_children: list[SnotChild] = field(default_factory=list)
    swapped: int = 0  # bricks replaced by their SNOT-category equivalent
    attached: int = 0  # panel parts attached (can be fewer than `swapped` once several anchors merge into one run)


def _snot_candidates(catalog: PartCatalog) -> list[Part]:
    return [p for p in catalog if p.category == "snot" and p.side_stud_face is not None]


def _widening_plates(catalog: PartCatalog) -> list[Part]:
    """Every `plate`-category part exactly 1 stud deep (footprint depth ==
    1), widest first -- the set of parts usable to tile a run's own
    in-plane span. Depth must stay 1: for a SNOT child at `local_rotation=
    YAW_0`, the plate's own DEPTH axis becomes the VERTICAL extent once
    tilted (see place_in_frame's own docstring), which must stay pinned to
    the single row of real side studs being covered, not spread across
    multiple plate-heights."""
    plates = [p for p in catalog if p.category == "plate" and min(p.footprint) == 1]
    return sorted(plates, key=lambda p: -max(p.footprint))


@dataclass(frozen=True)
class _SwappedCandidate:
    index: int  # brick index in the post-swap `working` Model
    part: Part
    rotation: Rotation
    face: str


def _outward_cells(brick: Brick, face: str) -> list[tuple[int, int, int]]:
    """The cells immediately outward of `brick`'s own footprint, across its
    whole extent in `face`'s direction -- one stud step beyond the brick,
    at every plate layer of its height. Used both to test whether a face is
    exposed (against the model's own occupied cells) and to test whether a
    flush panel there would stay inside the original solid silhouette
    (against `solid_grid`) -- the same cells, two different questions."""
    dx, dz = _FACE_STEP[face]
    w, d = brick.footprint
    if dx != 0:
        x = brick.pos.x + (w if dx > 0 else -1)
        return [(x, brick.pos.y + dy, brick.pos.z + dz2) for dy in range(brick.part.height_plates) for dz2 in range(d)]
    z = brick.pos.z + (d if dz > 0 else -1)
    return [(brick.pos.x + dx2, brick.pos.y + dy, z) for dy in range(brick.part.height_plates) for dx2 in range(w)]


def _something_on_top(brick: Brick, occupied: set[tuple[int, int, int]]) -> bool:
    w, d = brick.footprint
    top_y = brick.pos.y + brick.part.height_plates
    return any((brick.pos.x + dx, top_y, brick.pos.z + dz) in occupied for dx in range(w) for dz in range(d))


def _is_solid(solid_grid: VoxelGrid, x: int, y: int, z: int) -> bool:
    nx, ny, nz = solid_grid.shape
    if not (0 <= x < nx and 0 <= y < ny and 0 <= z < nz):
        return False
    return bool(solid_grid.occupied[x, y, z])


def _find_panel(
    brick: Brick,
    candidates: list[Part],
    occupied: set[tuple[int, int, int]],
    solid_grid: VoxelGrid | None,
):
    """The (part, rotation, face, outward_cells) to use for `brick`, or
    `None` if no exposed face has an eligible SNOT part -- checked in a
    fixed face order (+x, -x, +z, -z), falling through to the next
    candidate face rather than giving up if the first exposed face fails
    every other check (footprint/rotation, top-connectivity, solid_grid).

    A face only qualifies if its OPPOSITE face is NOT also exposed -- i.e.
    this brick has real material backing it in that axis, confirming it
    reads as part of an actual wall/shell, not a free-floating single
    stud (a spike, an isolated crenellation tip) with no principled
    "outward" direction at all. Without this, a brick with all 4 side
    faces open (nothing beside it in ANY direction) would always resolve
    to the first face in `_FACE_ORDER` regardless of where it actually
    sits on the model -- confirmed as a real bug, not hypothetical, on the
    turret example: every isolated single-stud merlon tip picked the same
    fixed +x direction, producing several panels pointing sideways at each
    other/into gaps between merlons instead of a coherent outward
    direction. A brick like this is now correctly left un-swapped rather
    than given an arbitrary panel."""
    for face in _FACE_ORDER:
        outward = _outward_cells(brick, face)
        if any(c in occupied for c in outward):
            continue  # not exposed on this face at all
        opposite = _outward_cells(brick, _OPPOSITE_FACE[face])
        if not any(c in occupied for c in opposite):
            continue  # no backing material -- an isolated spike, not a wall
        if solid_grid is not None and not all(_is_solid(solid_grid, *c) for c in outward):
            continue  # would poke into open air past the mesh's own silhouette

        for part in candidates:
            if part.height_plates != brick.part.height_plates:
                continue
            rotation = rotation_for_outward_face(part, face, brick.footprint)
            if rotation is None:
                continue
            if part.top == "none" and _something_on_top(brick, occupied):
                continue  # would sever a real top-stud connection
            return part, rotation, face, outward
    return None


def _group_into_runs(candidates: list[_SwappedCandidate], model: Model) -> list[list[_SwappedCandidate]]:
    """Group swapped parents into runs eligible to share ONE wide,
    region-grown panel: same part id + rotation (identical frame matrix --
    see module docstring), contiguous along the in-plane axis (the next
    member's frame origin starts exactly where the previous one's own
    side-stud row ends), with the vertical and outward coordinates
    unchanged. Computed from each candidate's REAL `SnotFrame` origin, not
    a re-derived world position, so it can't disagree with what
    `place_in_frame` will actually place.

    Real bug caught by testing an actual multi-brick merge, not just
    individual placements: within a group, members are sorted by
    increasing WORLD in-plane coordinate for the contiguity check --
    correct for grouping, but `_tile_run` always treats a run's first
    member as the anchor (`local_pos=0`) and walks FORWARD through the
    rest with increasing `local_pos`. Whether increasing `local_pos`
    actually moves toward increasing or decreasing world coordinate
    depends on the sign of the frame matrix's own in-plane coefficient
    (`matrix[0]` for the X axis, `matrix[6]` for Z -- see
    `snot_frame_for_brick`'s own origin-fix docstring for why this isn't
    always +1). When it's -1, walking a run in world-ascending order and
    handing `_tile_run` that same order placed the second tile's world
    span on the wrong side of the anchor entirely -- confirmed on a real
    5-brick test wall, not hypothetical. Each run is now stored in
    whichever order actually matches increasing `local_pos` (reversed
    when the coefficient is negative), so `_tile_run` never has to know
    about this itself."""
    by_part_rotation: dict[tuple[str, Rotation], list[_SwappedCandidate]] = {}
    for c in candidates:
        by_part_rotation.setdefault((c.part.id, c.rotation), []).append(c)

    runs: list[list[_SwappedCandidate]] = []
    for (_part_id, _rotation), members in by_part_rotation.items():
        axis_index = 0 if in_plane_axis(members[0].face) == "x" else 2
        with_origin = []
        for c in members:
            brick = model.bricks[c.index]
            frame = snot_frame_for_brick(brick, c.part.side_stud_face, face_offset=c.part.side_stud_offset)
            with_origin.append((frame.origin_ldu, frame.matrix, c))
        with_origin.sort(key=lambda t: t[0][axis_index])

        current_run: list[tuple[tuple[int, int, int], _SwappedCandidate]] = []
        for origin, _matrix, c in with_origin:
            if current_run:
                prev_origin = current_run[-1][0]
                expected = prev_origin[axis_index] + current_run[-1][1].part.side_stud_count * STUD_LDU
                same_plane = all(origin[i] == prev_origin[i] for i in (0, 1, 2) if i != axis_index)
                if same_plane and origin[axis_index] == expected:
                    current_run.append((origin, c))
                    continue
                runs.append(current_run)
            current_run = [(origin, c)]
        if current_run:
            runs.append(current_run)

    # Each run is currently in world-ascending in-plane order; that only
    # matches increasing local_pos when the group's own coefficient is
    # positive -- reverse it otherwise so _tile_run's anchor (run[0]) is
    # genuinely the local_pos=0 end.
    oriented_runs: list[list[_SwappedCandidate]] = []
    for run in runs:
        origin_a, cand_a = run[0]
        brick_a = model.bricks[cand_a.index]
        frame_a = snot_frame_for_brick(brick_a, cand_a.part.side_stud_face, face_offset=cand_a.part.side_stud_offset)
        axis_index = 0 if in_plane_axis(cand_a.face) == "x" else 2
        coefficient = frame_a.matrix[axis_index * 3]
        ordered = [c for _o, c in run]
        if coefficient < 0:
            ordered = list(reversed(ordered))
        oriented_runs.append(ordered)

    return oriented_runs


def _tile_run(
    run: list[_SwappedCandidate], widening_plates: list[Part], model: Model
) -> list[SnotChild]:
    """Cover a run's combined in-plane span with the widest available
    plates (greedy, largest-fits-first -- same simple tiling shape Stage
    A's own legalizer uses), all placed within the FIRST member's own
    frame -- valid because every member shares an identical frame matrix,
    and a `SnotFrame`'s local coordinate system is a rigid linear
    transform that extends correctly across the whole run, not just the
    anchor's own footprint (see module docstring).

    Each tile's `parent_overlaps` records EVERY run member it actually
    covers and by how many studs, not just the anchor -- a tile spanning
    several merged bricks (the common case once tiles are wider than any
    single member's own `side_stud_count`) genuinely rests on all of
    them, and the structural graph needs that full list to add a real
    edge to each rather than only ever crediting the anchor (see
    SnotChild's own docstring for the bug this fixes: a merged run's
    trailing tile used to get NO graph edge at all when it didn't happen
    to overlap the anchor's own single stud)."""
    axis = in_plane_axis(run[0].face)
    if not widening_plates:
        return []

    # Each member's own [start, end) stud range within the run's local
    # coordinate system (0-indexed from run[0], matching local_pos units).
    member_ranges: list[tuple[int, int, int]] = []
    cursor = 0
    for c in run:
        member_ranges.append((cursor, cursor + c.part.side_stud_count, c.index))
        cursor += c.part.side_stud_count
    total_width = cursor

    anchor_index = run[0].index
    children: list[SnotChild] = []
    offset = 0
    remaining = total_width
    while remaining > 0:
        tile = next((p for p in widening_plates if max(p.footprint) <= remaining), widening_plates[-1])
        width = max(tile.footprint)
        tile_start, tile_end = offset, offset + width
        overlaps = tuple(
            (idx, min(end, tile_end) - max(start, tile_start))
            for start, end, idx in member_ranges
            if min(end, tile_end) - max(start, tile_start) > 0
        )
        local_pos = GridPos(offset, 0, 0) if axis == "x" else GridPos(0, 0, offset)
        children.append(SnotChild(parent_index=anchor_index, part=tile, local_pos=local_pos, parent_overlaps=overlaps))
        offset += width
        remaining -= width
    return children


def place_snot_panels(model: Model, solid_grid: VoxelGrid | None = None) -> SnotPlacementResult:
    catalog = model.catalog
    candidates = _snot_candidates(catalog)
    widening_plates = _widening_plates(catalog)
    if not candidates or not widening_plates:
        return SnotPlacementResult(model=model)

    occupied: set[tuple[int, int, int]] = set()
    for brick in model.bricks:
        occupied.update(brick.occupied_cells())

    working = Model(catalog=catalog)
    swapped_candidates: list[_SwappedCandidate] = []

    for brick in model.bricks:
        found = None
        if brick.part.category == "brick" and brick.part.top == "full":
            found = _find_panel(brick, candidates, occupied, solid_grid)

        if found is None:
            working.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
            continue

        part, rotation, face, outward_cells = found
        parent_index = len(working.bricks)
        working.place(part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=rotation)
        swapped_candidates.append(_SwappedCandidate(index=parent_index, part=part, rotation=rotation, face=face))
        # Registering the panel's own cells here means a LATER candidate's
        # exposed-face check correctly sees this space as occupied -- a
        # real, sequential (not fully symmetric) mitigation against two
        # independently-attached panels colliding at a concave corner, not
        # a complete collision-detection system.
        occupied.update(outward_cells)

    runs = _group_into_runs(swapped_candidates, working)
    snot_children: list[SnotChild] = []
    for run in runs:
        snot_children.extend(_tile_run(run, widening_plates, working))

    return SnotPlacementResult(
        model=working,
        snot_children=snot_children,
        swapped=len(swapped_candidates),
        attached=len(snot_children),
    )
