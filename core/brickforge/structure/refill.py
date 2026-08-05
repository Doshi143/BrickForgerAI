"""Hole refill: after bridge.py::bridge_unstable prunes whatever it
couldn't connect invisibly, put back any of that pruned material that can
be re-attached with a *genuine* stud connection to already-grounded
material -- not proximity, not being boxed in by neighbors, an actual
edge in the same graph structure.py uses everywhere else.

v1 and v2 of this function tried weaker rules (a single cell boxed in on
4 sides; later, a connected pocket with a high enough "fraction of
boundary faces touching present material") and both were rejected once
their actual implication was worked through: exterior shell material is
roughly half-exposed *by definition* (that's what being on the surface
means), so no proximity-based threshold can tell a small dimple apart
from a large floating chunk, and more importantly, neither rule requires
the refilled cell to have anything holding it up against gravity -- a
piece wedged between neighbors on its sides with nothing underneath is
still, physically, not attached the way a stud connection attaches it.
The user was explicit that friction-only doesn't satisfy "no floating
segments": a refill only counts if it has a real stud connection, top or
bottom.

What "top or bottom" means once you work through which direction gravity
actually flows (same reasoning as weakpoints.py::find_ungrounded_bricks):
an edge to something *above* a candidate cell doesn't hold the candidate
up -- it's the other way around, the thing above would be resting on the
candidate. Only an edge to already-grounded material *below* the
candidate (or the candidate being at y=0) makes the candidate itself
grounded. So this fills bottom-up, one layer at a time: a cell is only
added once whatever's directly beneath it (in the model as already
repaired so far, including anything already refilled this same pass) is
itself grounded. That's not a heuristic -- it's exactly
find_ungrounded_bricks's own definition of grounded, applied constructively
instead of just checked.

Deliberately still using the strict, directed find_ungrounded_bricks here,
even though repair.py/bridge.py were changed to act on the looser,
undirected find_bricks_outside_main_component instead (see weakpoints.py's
module docstring for that whole story). Those two functions have
different jobs: repair/bridge decide what's broken enough to touch at
all, where the strict check was flagging far more than was ever really
at risk; refill decides whether it's *safe to add material back*, where
being conservative is exactly right -- every cell this function adds is,
by construction, reachable from GROUND by a real chain of stud
connections, no exceptions. Re-running analyze() on the result confirms
zero ungrounded bricks remain among what got refilled (whatever couldn't
be reached this way is left pruned, same as before).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from ..model import Brick, Model
from .graph import build_connectivity_graph
from .weakpoints import find_ungrounded_bricks

REFILL_PART_ID = "3024"  # 1x1 plate

# A genuine seam/gap artifact observed in practice (a legalizer tiling
# crevice) was on the order of a handful of cells; a deliberately hollow
# model's interior is in the thousands (measured directly: a real pear
# with a central wireframe had ~15,500 interior cells reported as
# "enclosed" once its shell had no actual gaps left -- the wireframe's
# planes partition that interior, but even without them, a properly
# sealed shell makes its *entire* hollow interior satisfy the same
# "unreachable from outside" test a real small gap does). 200 sits
# comfortably above any observed real artifact and comfortably below any
# real cavity, so it separates the two cases cleanly without needing to
# reason about the wireframe's own geometry at all.
_MAX_VOID_SIZE_TO_CLOSE = 200


@dataclass
class VoidCloseResult:
    model: Model
    filled: list[tuple[int, int, int]]


def close_enclosed_voids(model: Model) -> VoidCloseResult:
    """Fill any empty cell that is fully enclosed by occupied cells --
    unreachable from outside the model's own bounding box by any path of
    empty cells -- regardless of *how* it came to be empty.

    A different, deliberately less strict question than
    `refill_enclosed_holes` above: that function only ever reconsiders
    cells `bridge_unstable` actually removed, and requires a real stud
    chain to already-grounded material below. This function catches
    everything else -- a legalizer/tiling seam, a voxelization crevice, any
    gap that was simply never occupied in the first place and so was never
    a candidate for the stricter function at all. Confirmed necessary, not
    hypothetical: a real model (a pear, after the wireframe-support and
    hollow-interior changes) still had a small visible gap near its
    center after both bridge_unstable and refill_enclosed_holes ran,
    because that cell had never been part of `removed` to begin with.

    Safe by construction, not just by inspection: a cell enclosed on *all
    six* sides (not just boxed in laterally -- the specific weaker rule an
    earlier version of `refill_enclosed_holes` tried and rejected, see its
    own docstring) has occupied material directly beneath it too. Since
    this runs after bridge/refill/prune have already produced a model
    that's a single connected piece with zero critical bricks, that
    material below is, by the same analysis, already grounded -- so
    filling the void it encloses adds nothing ungrounded, it just closes
    a gap that was already structurally inert. Uses a flood fill from the
    bounding box's own boundary (padded by one cell) to find every empty
    cell reachable from outside; whatever's left over is, by definition,
    fully enclosed.

    **Only closes voids up to `_MAX_VOID_SIZE_TO_CLOSE` cells.** A real
    bug, not a hypothetical: "unreachable from outside" doesn't actually
    mean "a defect" -- it's also exactly what a model's *entire,
    deliberately hollow interior* looks like once its shell has no real
    gaps left. Caught directly on a real job: a pear's shell became fully
    sealed (a good thing on its own) and this function responded by
    trying to refill ~15,500 interior cells, silently undoing the entire
    hollowing feature. Splitting the unreachable region into its own
    connected components and only filling the small ones is what actually
    distinguishes "a real seam" from "the hollow interior working as
    intended" -- size, not reachability, is the only signal that
    separates the two, since both satisfy the exact same "enclosed"
    definition."""
    occupied: set[tuple[int, int, int]] = set()
    color_by_cell: dict[tuple[int, int, int], int] = {}
    for brick in model.bricks:
        for cell in brick.occupied_cells():
            occupied.add(cell)
            color_by_cell[cell] = brick.color

    if not occupied:
        return VoidCloseResult(model=model, filled=[])

    xs = [c[0] for c in occupied]
    ys = [c[1] for c in occupied]
    zs = [c[2] for c in occupied]
    x_min, x_max = min(xs) - 1, max(xs) + 1
    y_min, y_max = max(min(ys) - 1, 0), max(ys) + 1  # never explore below the baseplate
    z_min, z_max = min(zs) - 1, max(zs) + 1
    shape = (x_max - x_min + 1, y_max - y_min + 1, z_max - z_min + 1)

    occupied_grid = np.zeros(shape, dtype=bool)
    for x, y, z in occupied:
        occupied_grid[x - x_min, y - y_min, z - z_min] = True
    empty_grid = ~occupied_grid

    reachable_from_outside = np.zeros(shape, dtype=bool)
    start = (0, 0, 0)
    reachable_from_outside[start] = True
    frontier = [start]
    while frontier:
        x, y, z = frontier.pop()
        for nx, ny, nz in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            if not (0 <= nx < shape[0] and 0 <= ny < shape[1] and 0 <= nz < shape[2]):
                continue
            if not empty_grid[nx, ny, nz] or reachable_from_outside[nx, ny, nz]:
                continue
            reachable_from_outside[nx, ny, nz] = True
            frontier.append((nx, ny, nz))

    enclosed = empty_grid & ~reachable_from_outside
    labels, num_labels = ndimage.label(enclosed)
    to_fill: list[tuple[int, int, int]] = []
    for label_id in range(1, num_labels + 1):
        component_mask = labels == label_id
        if component_mask.sum() > _MAX_VOID_SIZE_TO_CLOSE:
            continue  # a legitimate large cavity (e.g. deliberate hollowing), not a defect
        for lx, ly, lz in np.argwhere(component_mask):
            to_fill.append((int(lx) + x_min, int(ly) + y_min, int(lz) + z_min))

    if not to_fill:
        return VoidCloseResult(model=model, filled=[])

    filled_model = Model(catalog=model.catalog)
    for brick in model.bricks:
        filled_model.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    for x, y, z in to_fill:
        neighbor_colors = [
            color_by_cell[n]
            for n in [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1), (x, y - 1, z), (x, y + 1, z)]
            if n in color_by_cell
        ]
        color = neighbor_colors[0] if neighbor_colors else 71  # Light_Bluish_Gray fallback, shouldn't happen
        filled_model.place(REFILL_PART_ID, color, x, y, z)
        color_by_cell[(x, y, z)] = color

    return VoidCloseResult(model=filled_model, filled=to_fill)


@dataclass
class RefillResult:
    model: Model
    refilled: list[tuple[int, int, int]]


def refill_enclosed_holes(model: Model, removed: list[Brick]) -> RefillResult:
    occupied: set[tuple[int, int, int]] = set()
    color_by_cell: dict[tuple[int, int, int], int] = {}
    for brick in model.bricks:
        for cell in brick.occupied_cells():
            occupied.add(cell)
            color_by_cell[cell] = brick.color

    graph = build_connectivity_graph(model)
    ungrounded_idx = find_ungrounded_bricks(graph, model)
    grounded_positions: set[tuple[int, int, int]] = set()
    for i, brick in enumerate(model.bricks):
        if i not in ungrounded_idx:
            grounded_positions.update(brick.occupied_cells())

    removed_cells: set[tuple[int, int, int]] = set()
    for brick in removed:
        removed_cells.update(brick.occupied_cells())
    removed_cells -= occupied  # a cell can be removed by one brick and re-occupied by another

    to_refill: list[tuple[int, int, int]] = []
    frontier = set(removed_cells)
    changed = True
    while changed:
        changed = False
        for cell in list(frontier):
            x, y, z = cell
            below = (x, y - 1, z)
            if y == 0 or below in grounded_positions:
                to_refill.append(cell)
                grounded_positions.add(cell)  # may ground the cell directly above it next pass
                frontier.discard(cell)
                changed = True

    if not to_refill:
        return RefillResult(model=model, refilled=[])

    refilled_model = Model(catalog=model.catalog)
    for brick in model.bricks:
        refilled_model.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    for x, y, z in to_refill:
        neighbor_colors = [
            color_by_cell[n]
            for n in [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1), (x, y - 1, z)]
            if n in color_by_cell
        ]
        color = neighbor_colors[0] if neighbor_colors else 71  # Light_Bluish_Gray fallback, shouldn't happen
        refilled_model.place(REFILL_PART_ID, color, x, y, z)

    return RefillResult(model=refilled_model, refilled=to_refill)
