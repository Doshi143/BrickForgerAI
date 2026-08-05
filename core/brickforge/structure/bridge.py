"""Bridging repair: connect a disconnected island to the rest of the model
instead of deleting it (repair.py::prune_unstable's approach), but only
where the connector can be entirely hidden inside the sculpture's own
silhouette -- an earlier version of this function dropped a pillar
straight down from an arbitrary point in each island without checking
that, and for anything sticking out past the model's core silhouette (an
ear, say) the pillar spent most of its length in open air, visibly poking
out of the model. Confirmed directly on the bunny: the ear-tip island's
pillar needed 13 plates and landed on bare ground without touching
anything else along the way -- that's 13 plates of exposed pole, not a
hidden brace.

"Island" here means undirected-disconnected from the model's main mass
(weakpoints.find_bricks_outside_main_component), not the much larger,
stricter "has no private straight-down stud chain" set
(find_ungrounded_bricks) an earlier version used -- see weakpoints.py's
module docstring for why that stricter check was the wrong one to act on.
In practice this means bridge_unstable now runs against a handful of
genuinely isolated bricks instead of potentially 10%+ of the whole model.

Why a straight vertical pillar at all, not a sideways patch: side-by-side
parts at the same layer never share a stud connection in this catalog
(matches real LEGO -- plates don't clutch a neighbor without studs), so a
connector placed next to an ungrounded region does nothing for it, even
though it looks touching. The only thing that ever creates a new graph
edge is a part landing in the exact same (x, z) column as the layer above
or below it.

`solid_grid`, if supplied (mesh_to_model.py::mesh_to_model_full exposes
it), is the pre-shell, pre-legalize solid occupancy in the same index
space as the final Model -- the only way to tell "this empty cell is
hollow interior, a pillar through it would be hidden" apart from "this
empty cell is open air outside the sculpture entirely, a pillar through it
would be a visible pole," since a shelled/hollow Model's occupancy alone
can't distinguish the two. Every cell a candidate pillar would occupy,
including the one it finally lands on at y=0, is checked against it. If
`solid_grid` is omitted (there's no mesh -- e.g. a hand-built Model), the
interior check is skipped and this behaves like the plain "any pillar
that connects" version.

One pillar per island, not one per brick: everything in an "island" (a
connected component consisting entirely of ungrounded bricks) is already
internally connected to everything else in it -- that's the definition of
a connected component -- so grounding any single point in the island
grounds the whole thing. Every (x, z) column the island itself occupies is
tried as a candidate anchor, and the shortest interior-only pillar among
the ones that work is kept -- more material stays, but only where it's
genuinely invisible.

Whatever has no interior-only pillar at all gets pruned
(repair.py::prune_unstable) as a last resort -- same reasoning as before:
an unbridgeable, unsupported part is guaranteed to separate, so it's safer
gone than shipped as a visible external strut or a floating piece.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..model import Brick, Model
from .graph import build_connectivity_graph
from .repair import prune_unstable
from .weakpoints import find_bricks_outside_main_component

BRIDGE_PART_ID = "3024"  # 1x1 plate: guaranteed to fit any single-cell path, last-resort fallback
BRIDGE_PART_ID_WIDE = "3022"  # 2x2 plate: preferred whenever a hidden 2x2 column fits

# A single-stud-wide pillar has almost no bending stiffness -- fine for
# pull-apart strength, but a real, physical weak point against lateral
# force (being picked up, jostled) the taller it gets, and hollowing the
# model's interior (dropping the periodic internal support lattice --
# see web/backend's own brickforge_bridge.py) means more islands now rely
# on a bridge pillar for their only connection to the rest of the model,
# not less. A 2x2 column is dramatically stiffer for the same reason a
# fence post outlasts a dowel of the same height. Tried first at every
# candidate anchor; only falls back to the single-stud pillar below where
# no uniform, fully-interior 2x2 path exists anywhere in the island's own
# footprint.
_WIDE_ANCHOR_OFFSETS = [(0, 0), (-1, 0), (0, -1), (-1, -1)]


@dataclass
class BridgeResult:
    model: Model
    added: list[Brick] = field(default_factory=list)
    removed: list[Brick] = field(default_factory=list)


def _is_interior_factory(solid_grid):
    if solid_grid is None:
        return lambda x, y, z: True
    nx_, ny_, nz_ = solid_grid.shape

    def is_interior(x: int, y: int, z: int) -> bool:
        if not (0 <= x < nx_ and 0 <= y < ny_ and 0 <= z < nz_):
            return False
        return bool(solid_grid.occupied[x, y, z])

    return is_interior


def _find_pillar(x0: int, z0: int, y_start: int, occupied_cells: set, is_interior) -> list[tuple[int, int, int]] | None:
    """The cells a straight-down pillar from (x0, y_start, z0) would need to
    add, or None if no valid pillar exists along this column: it must stay
    inside the silhouette (is_interior) at every step, including the cell it
    finally lands on, and either reach y=0 or hit an existing occupied cell."""
    path: list[tuple[int, int, int]] = []
    y = y_start
    while y >= 0:
        if not is_interior(x0, y, z0):
            return None
        cell = (x0, y, z0)
        if cell in occupied_cells:
            return path
        path.append(cell)
        y -= 1
    return path


def _find_wide_pillar(
    x0: int, z0: int, y_start: int, occupied_cells: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Like `_find_pillar`, but for a rigid 2x2 column anchored at
    (x0, z0)-(x0+1, z0+1) instead of a single stud. Returns one
    (x0, y, z0) entry per Y layer -- the corner to place a 2x2 plate at,
    one part per layer, not four separate 1x1 parts -- or None if no
    valid path exists. All 4 sub-cells must be interior and unoccupied at
    every layer; a landing where only *some* of the 4 corners rest on
    existing material is rejected outright rather than accepted lopsided,
    since an unsupported corner would defeat the entire point of using a
    wider, stiffer pillar in the first place."""
    cells = [(x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1)]
    layers: list[tuple[int, int, int]] = []
    y = y_start
    while y >= 0:
        if not all(is_interior(cx, y, cz) for cx, cz in cells):
            return None
        occupied_here = [(cx, y, cz) in occupied_cells for cx, cz in cells]
        if any(occupied_here):
            return layers if all(occupied_here) else None
        layers.append((x0, y, z0))
        y -= 1
    return layers


def bridge_unstable(model: Model, solid_grid=None) -> BridgeResult:
    graph = build_connectivity_graph(model)
    disconnected = find_bricks_outside_main_component(graph)
    if not disconnected:
        return BridgeResult(model=model, added=[], removed=[])

    is_interior = _is_interior_factory(solid_grid)
    islands = list(nx.connected_components(graph.subgraph(disconnected)))

    working = Model(catalog=model.catalog)
    for brick in model.bricks:
        working.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    occupied_cells: set[tuple[int, int, int]] = set()
    for brick in working.bricks:
        occupied_cells.update(brick.occupied_cells())

    added: list[Brick] = []
    for island in islands:
        island_bricks = [model.bricks[i] for i in island]
        color = island_bricks[0].color

        columns: set[tuple[int, int]] = set()
        for brick in island_bricks:
            w, d = brick.footprint
            for dx in range(w):
                for dz in range(d):
                    columns.add((brick.pos.x + dx, brick.pos.z + dz))

        best_wide_path: list[tuple[int, int, int]] | None = None
        best_path: list[tuple[int, int, int]] | None = None
        for x0, z0 in columns:
            # start one layer below whichever of this island's bricks
            # bottoms out at this (x, z) column
            y_start = min(b.pos.y for b in island_bricks if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]) - 1

            for ox, oz in _WIDE_ANCHOR_OFFSETS:
                wide_candidate = _find_wide_pillar(x0 + ox, z0 + oz, y_start, occupied_cells, is_interior)
                if wide_candidate is not None and (best_wide_path is None or len(wide_candidate) < len(best_wide_path)):
                    best_wide_path = wide_candidate

            candidate = _find_pillar(x0, z0, y_start, occupied_cells, is_interior)
            if candidate is not None and (best_path is None or len(candidate) < len(best_path)):
                best_path = candidate

        if best_wide_path is not None:
            for x, y, z in best_wide_path:
                new_brick = working.place(BRIDGE_PART_ID_WIDE, color, x, y, z)
                added.append(new_brick)
                occupied_cells.update(new_brick.occupied_cells())
            continue

        if best_path is None:
            continue  # no hidden route found; leave ungrounded, prune_unstable will remove it

        for x, y, z in best_path:
            new_brick = working.place(BRIDGE_PART_ID, color, x, y, z)
            added.append(new_brick)
            occupied_cells.add((x, y, z))

    prune_result = prune_unstable(working)
    return BridgeResult(model=prune_result.model, added=added, removed=prune_result.removed)
