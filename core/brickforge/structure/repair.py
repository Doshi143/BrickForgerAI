"""A minimal repair action, not the full DESIGN.md sec. 5 repair loop.

DESIGN.md's repair loop enlarges parts, adds hidden braces, and thickens
locally to *fix* a weak connection -- that requires either mesh-level
thin-feature handling (DESIGN.md sec. 2) before voxelization, or local
re-legalization after bridging a gap in the occupancy grid. Neither is
implemented here.

What this does instead, deliberately simpler: a brick that isn't part of
the model's main connected mass at all
(weakpoints.find_bricks_outside_main_component) is, by definition, never
actually attached to the model during a real build -- there is no repair
to attempt, it just falls off. Pruning it is a safe, honest floor: it
never ships a part that is guaranteed to separate.

Uses undirected connectivity, not the stricter directed
find_ungrounded_bricks -- see weakpoints.py's module docstring for why:
the stricter, single-path check flags the majority of bricks in any dense,
richly-interconnected shell as "unsupported" even when they're braced by
neighbors on every side and going nowhere, which is a bad model of real
structural soundness and, measured directly against both a user's visual
inspection and Studio's own stability checker, produced far more pruning
(hence far more visible holes) than was ever actually necessary.

Single pass, not an iterative loop, and that's not a simplification --
it's provably complete in one shot. Removing exactly the set of bricks
outside the main component cannot strand anything that was inside it,
because nothing inside the main component was ever reachable only through
something outside it (that's what "different component" means).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Brick, Model
from .graph import build_connectivity_graph
from .weakpoints import find_bricks_outside_main_component


@dataclass
class PruneResult:
    model: Model
    removed: list[Brick]


def prune_unstable(model: Model) -> PruneResult:
    graph = build_connectivity_graph(model)
    to_remove = find_bricks_outside_main_component(graph)

    if not to_remove:
        return PruneResult(model=model, removed=[])

    removed = [model.bricks[i] for i in sorted(to_remove)]
    pruned = Model(catalog=model.catalog)
    for i, brick in enumerate(model.bricks):
        if i in to_remove:
            continue
        pruned.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    return PruneResult(model=pruned, removed=removed)
