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

from ..model import Brick, Model
from .graph import build_connectivity_graph
from .weakpoints import find_ungrounded_bricks

REFILL_PART_ID = "3024"  # 1x1 plate


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
