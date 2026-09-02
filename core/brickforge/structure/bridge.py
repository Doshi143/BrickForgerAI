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

Every candidate column is searched in BOTH directions, not just down to
ground: an island's nearest real material is often directly above it, not
several plates below. A thin protruding limb (a leg, a tail, an ear) is
frequently disconnected from the very thing it visually belongs to by a
single missing cell -- a voxelization/legalization seam, not a genuine
gap -- and a downward-only search would walk straight past that one-cell
fix, either finding a much longer route to bare ground or finding nothing
at all and losing the piece to prune_unstable entirely. `_find_pillar` /
`_find_wide_pillar` (down, with y=0 as an always-valid landing) and
`_find_pillar_upward` / `_find_wide_pillar_upward` (up, which must land on
real existing material -- there's no equivalent "always valid" ceiling)
are tried at every candidate column, and the shorter of the two wins.
Purely additive relative to the downward-only version: everything it used
to find, it still finds identically; this only adds routes it used to
miss.

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

One (occasionally two) pillars per island, not one per brick: everything in
an "island" (a connected component consisting entirely of ungrounded
bricks) is already internally connected to everything else in it -- that's
the definition of a connected component -- so grounding any single point in
the island grounds the whole thing. Every (x, z) column the island itself
occupies is tried as a candidate anchor, and the shortest interior-only
pillar among the ones that work is kept -- more material stays, but only
where it's genuinely invisible.

A single pillar is graph-theoretically sufficient the moment it lands, but
when the only anchor available is the single-stud-wide fallback (no 2x2
column exists anywhere in the island's own footprint -- always true for a
thin, isolated feature like a carved detail or a small interior prop), that
one stud is a real single point of failure for however much material sits
on the far end of it: connected by this module's own definition, but not
necessarily by a real one, since a lone stud's clutch power doesn't scale
with what's resting on it. Measured on a real production job (a carved
pumpkin with a lantern inside, part_count 6509) before this was added:
`analyze()` reported it as one fully connected piece with zero critical
bricks, and it was still reported as having detached-looking sections --
because every successful bridge repair on that job used the thin pillar
exclusively, an isolated interior feature never having a wide-enough
footprint to anchor the stiffer 2x2 kind. So whenever only the thin pillar
is available, a second, fully independent thin pillar through a different
column of the same island is added too, if the island's footprint offers
one -- giving the reconnected section two attachment points instead of
one wherever the geometry allows it. A genuinely single-column sliver has
nowhere else to attach and is left with just the one pillar, same as
before.

Before giving up on an island, one more shape is tried: an "elbow" --
`_find_elbow` / `_find_elbow_upward`. A straight pillar only ever searches
the island's OWN column, but a whole island can fail purely because that
one column pokes outside the solid silhouette somewhere along its length,
even when a neighboring column, one cell over, has a clean interior path
the island simply never touches. A single wide plate (1x2), placed at one
layer, naturally connects to whatever's directly above/below it at BOTH
columns it spans -- so it can act as a hinge: one end lands on the island
in its own column, the other end lands in the neighbor column, and the
straight run to ground continues from THAT column instead. Two separate
1x1 plates side by side could never do this (this catalog has no lateral
clutch -- see this module's own earlier point on that), so the elbow has
to be one real, single part spanning both cells.

An earlier attempt at reducing pruning (peeling individual bricks out of a
failed island and retrying the same straight-column search on the
remainder) was tried and reverted before this: it turned out to be
provably inert given this model's vertical-only connectivity -- any column
that could ever succeed already gets tried in the very first, whole-island
search, since that search iterates every column in the combined footprint
independently of which specific bricks are "in the group". The elbow is a
genuinely different mechanism, not a smarter search over the same one: it
adds a real new column to the search space (the neighbor), which a
same-column-only search, however cleverly retried, can never reach.

Tried only as a fallback, after the existing wide/thin straight search
finds nothing at all for the island -- a straight pillar is cheaper (fewer
parts) and simpler, so it's always preferred when it works.

Whatever has no interior-only pillar or elbow at all gets pruned
(repair.py::prune_unstable) as a last resort -- same reasoning as before:
an unbridgeable, unsupported part is guaranteed to separate, so it's safer
gone than shipped as a visible external strut or a floating piece.

Proven to work, not just plausible: a deliberate, isolated test
(test_elbow_reaches_a_neighboring_column_when_its_own_column_is_blocked)
constructs a column that's blocked below the elbow layer with a clean
neighbor right beside it, and confirms the elbow finds and uses it.
Measured, not assumed, on the real example models, though: re-run on
turret/mushroom/bunny, pruned-part counts are byte-for-byte identical to
before this was added (mushroom -34, bunny -3, same as the straight-only
version). Not a bug -- this pipeline's few remaining disconnected islands
on these two models (13/13/4/4 on the mushroom, 2/1 on the bunny) just
don't happen to have the specific "own column blocked, neighbor column
clear" shape this mechanism targets, at least not on these two fixtures.
Left in because it's a genuinely different, real capability (adds an
actual new column to the search space, unlike the peeling approach tried
and reverted before this -- see git history), not because it's been
observed helping on real output yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..lattice import Rotation
from ..model import Brick, Model
from .graph import build_connectivity_graph
from .repair import prune_unstable
from .weakpoints import find_bricks_outside_main_component

BRIDGE_PART_ID = "3024"  # 1x1 plate: guaranteed to fit any single-cell path, last-resort fallback
BRIDGE_PART_ID_WIDE = "3022"  # 2x2 plate: preferred whenever a hidden 2x2 column fits
BRIDGE_PART_ID_ELBOW = "3023"  # 1x2 plate: the only single part that can span two adjacent columns

# (dx, dz, rotation): the 4 lateral directions an elbow can reach from a
# given island column, and the Rotation that makes a "3023" 1x2 plate span
# that direction -- footprint_at(YAW_0) is [2, 1] (spans x), footprint_at
# (YAW_90) is [1, 2] (spans z), per this catalog's own "second number runs
# along local X" convention (see CLAUDE.md). Whichever of x0/x0+dx (or
# z0/z0+dz) is smaller becomes the part's own placement corner -- place()
# always takes the footprint's min corner, regardless of rotation.
_ELBOW_DIRECTIONS = [
    (1, 0, Rotation.YAW_0),
    (-1, 0, Rotation.YAW_0),
    (0, 1, Rotation.YAW_90),
    (0, -1, Rotation.YAW_90),
]

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


def _find_pillar_upward(
    x0: int, z0: int, y_start: int, y_max: int, occupied_cells: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """The upward mirror of `_find_pillar`: cells a straight-up pillar from
    (x0, y_start, z0) would need to add to reach EXISTING material above --
    an island's nearest reconnection point is often the thing directly
    above it (a foot a single cell short of the leg it belongs to), not
    the ground several plates below, and a shorter pillar is both cheaper
    and more reliably interior-only than a longer detour down to y=0.
    Unlike the downward search, there is no "always valid" landing
    equivalent to y=0 -- reaching `y_max` (the model's own current highest
    occupied cell) without finding real material means this direction
    genuinely has nothing to connect to, and returns None rather than
    treating open sky as a valid landing."""
    path: list[tuple[int, int, int]] = []
    y = y_start
    while y <= y_max:
        if not is_interior(x0, y, z0):
            return None
        cell = (x0, y, z0)
        if cell in occupied_cells:
            return path
        path.append(cell)
        y += 1
    return None


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


def _find_wide_pillar_upward(
    x0: int, z0: int, y_start: int, y_max: int, occupied_cells: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Upward mirror of `_find_wide_pillar`, same "no always-valid landing"
    difference `_find_pillar_upward` has relative to `_find_pillar`."""
    cells = [(x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1)]
    layers: list[tuple[int, int, int]] = []
    y = y_start
    while y <= y_max:
        if not all(is_interior(cx, y, cz) for cx, cz in cells):
            return None
        occupied_here = [(cx, y, cz) in occupied_cells for cx, cz in cells]
        if any(occupied_here):
            return layers if all(occupied_here) else None
        layers.append((x0, y, z0))
        y += 1
    return None


@dataclass
class ElbowCandidate:
    """One elbow bridge: a single 1x2 plate at `elbow_pos` (its own min
    corner, per Model.place's own convention) with `elbow_rotation`, whose
    two cells land on the island's own column at one end and a fresh
    neighbor column at the other -- plus `continuation`, the straight
    pillar cells (BRIDGE_PART_ID, same as a plain thin bridge) that carry
    the neighbor column the rest of the way to ground or existing
    material. `cost` (2 elbow cells + len(continuation)) is what
    _search_elbow compares candidates by, the same "fewer new parts wins"
    principle _search_group already uses for straight pillars."""

    elbow_pos: tuple[int, int, int]
    elbow_rotation: Rotation
    continuation: list[tuple[int, int, int]]

    @property
    def cost(self) -> int:
        return 2 + len(self.continuation)


def _find_elbow(
    x0: int, z0: int, y_start: int, dx: int, dz: int, rotation: Rotation, occupied_cells: set, is_interior
) -> ElbowCandidate | None:
    """Downward elbow candidate anchored at island column (x0, z0), layer
    y_start (one below the island's own lowest brick at this column --
    same meaning as _search_group's y_start_for), reaching into the
    neighbor column (x0+dx, z0+dz). Both of the elbow plate's own cells
    must be interior and currently empty (it's new material, same
    requirement a straight pillar's own cells have); the neighbor column
    then continues via a plain _find_pillar from one layer below the
    elbow -- reusing the exact same downward search a straight bridge
    already uses, just anchored at a different column."""
    x1, z1 = x0 + dx, z0 + dz
    if not (is_interior(x0, y_start, z0) and is_interior(x1, y_start, z1)):
        return None
    if (x0, y_start, z0) in occupied_cells or (x1, y_start, z1) in occupied_cells:
        return None
    continuation = _find_pillar(x1, z1, y_start - 1, occupied_cells, is_interior)
    if continuation is None:
        return None
    corner_x, corner_z = min(x0, x1), min(z0, z1)
    return ElbowCandidate(elbow_pos=(corner_x, y_start, corner_z), elbow_rotation=rotation, continuation=continuation)


def _find_elbow_upward(
    x0: int, z0: int, y_start: int, y_max: int, dx: int, dz: int, rotation: Rotation, occupied_cells: set, is_interior
) -> ElbowCandidate | None:
    """Upward mirror of `_find_elbow` -- y_start here is one ABOVE the
    island's own highest brick at (x0, z0) (matching y_start_for_upward's
    own meaning), and the neighbor column continues via _find_pillar_upward
    from one layer above the elbow, which (like every upward search in
    this module) must land on real existing material -- there's no
    always-valid ceiling the way y=0 is for the downward direction."""
    x1, z1 = x0 + dx, z0 + dz
    if not (is_interior(x0, y_start, z0) and is_interior(x1, y_start, z1)):
        return None
    if (x0, y_start, z0) in occupied_cells or (x1, y_start, z1) in occupied_cells:
        return None
    continuation = _find_pillar_upward(x1, z1, y_start + 1, y_max, occupied_cells, is_interior)
    if continuation is None:
        return None
    corner_x, corner_z = min(x0, x1), min(z0, z1)
    return ElbowCandidate(elbow_pos=(corner_x, y_start, corner_z), elbow_rotation=rotation, continuation=continuation)


def _search_elbow(
    island_bricks: list[Brick], occupied_cells: set, is_interior, y_max: int
) -> ElbowCandidate | None:
    """Tried only as a fallback from bridge_unstable, after the existing
    straight wide/thin search (_search_group) has already failed on every
    column in the island's own footprint -- see this module's own
    docstring for why a straight pillar is always preferred when it works.
    Tries every (island column) x (lateral direction) x (up/down)
    combination and keeps whichever valid elbow has the lowest `cost`,
    the same "fewer new parts" preference _search_group already applies
    to straight pillars."""
    columns: set[tuple[int, int]] = set()
    for brick in island_bricks:
        w, d = brick.footprint
        for bx in range(w):
            for bz in range(d):
                columns.add((brick.pos.x + bx, brick.pos.z + bz))

    def y_start_for(x0: int, z0: int) -> int:
        return (
            min(
                b.pos.y
                for b in island_bricks
                if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
            )
            - 1
        )

    def y_start_for_upward(x0: int, z0: int) -> int:
        return max(
            b.pos.y + b.part.height_plates
            for b in island_bricks
            if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
        )

    best: ElbowCandidate | None = None
    for x0, z0 in columns:
        y_down = y_start_for(x0, z0)
        y_up = y_start_for_upward(x0, z0)
        for dx, dz, rotation in _ELBOW_DIRECTIONS:
            down = _find_elbow(x0, z0, y_down, dx, dz, rotation, occupied_cells, is_interior)
            if down is not None and (best is None or down.cost < best.cost):
                best = down
            up = _find_elbow_upward(x0, z0, y_up, y_max, dx, dz, rotation, occupied_cells, is_interior)
            if up is not None and (best is None or up.cost < best.cost):
                best = up
    return best


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

        def y_start_for(x0: int, z0: int) -> int:
            # start one layer below whichever of this island's bricks
            # bottoms out at this (x, z) column
            return min(
                b.pos.y
                for b in island_bricks
                if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
            ) - 1

        def y_start_for_upward(x0: int, z0: int) -> int:
            # the mirror of y_start_for: one layer ABOVE whichever of this
            # island's bricks tops out at this column -- pos.y +
            # height_plates is already the first cell above that brick, so
            # no +1/-1 adjustment is needed the way the downward version has.
            return max(
                b.pos.y + b.part.height_plates
                for b in island_bricks
                if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
            )

        # An island's nearest reconnection point is just as often directly
        # above it (a foot a single cell short of its own leg) as it is
        # straight down to the ground -- see _find_pillar_upward's own
        # docstring. y_max bounds that search at the model's own current
        # ceiling: nothing exists to land on above it anyway.
        y_max = max(y for _, y, _ in occupied_cells)

        def best_wide_candidate(x0: int, z0: int, y_start_down: int, y_start_up: int) -> list[tuple[int, int, int]] | None:
            best: list[tuple[int, int, int]] | None = None
            for ox, oz in _WIDE_ANCHOR_OFFSETS:
                down = _find_wide_pillar(x0 + ox, z0 + oz, y_start_down, occupied_cells, is_interior)
                if down is not None and (best is None or len(down) < len(best)):
                    best = down
                up = _find_wide_pillar_upward(x0 + ox, z0 + oz, y_start_up, y_max, occupied_cells, is_interior)
                if up is not None and (best is None or len(up) < len(best)):
                    best = up
            return best

        def best_thin_candidate(x0: int, z0: int, y_start_down: int, y_start_up: int) -> list[tuple[int, int, int]] | None:
            down = _find_pillar(x0, z0, y_start_down, occupied_cells, is_interior)
            up = _find_pillar_upward(x0, z0, y_start_up, y_max, occupied_cells, is_interior)
            if down is None:
                return up
            if up is None:
                return down
            return down if len(down) <= len(up) else up

        best_wide_path: list[tuple[int, int, int]] | None = None
        best_path: list[tuple[int, int, int]] | None = None
        best_path_col: tuple[int, int] | None = None
        for x0, z0 in columns:
            y_start_down = y_start_for(x0, z0)
            y_start_up = y_start_for_upward(x0, z0)

            wide_candidate = best_wide_candidate(x0, z0, y_start_down, y_start_up)
            if wide_candidate is not None and (best_wide_path is None or len(wide_candidate) < len(best_wide_path)):
                best_wide_path = wide_candidate

            candidate = best_thin_candidate(x0, z0, y_start_down, y_start_up)
            if candidate is not None and (best_path is None or len(candidate) < len(best_path)):
                best_path = candidate
                best_path_col = (x0, z0)

        if best_wide_path is not None:
            for x, y, z in best_wide_path:
                new_brick = working.place(BRIDGE_PART_ID_WIDE, color, x, y, z)
                added.append(new_brick)
                occupied_cells.update(new_brick.occupied_cells())
            continue

        if best_path is None:
            # No straight column works anywhere in the island's own
            # footprint -- try an elbow into a neighboring column before
            # conceding to prune_unstable (see this module's own docstring
            # for why this is a genuinely different search, not a smarter
            # retry of the one that just failed).
            elbow = _search_elbow(island_bricks, occupied_cells, is_interior, y_max)
            if elbow is None:
                continue  # no hidden route found; leave ungrounded, prune_unstable will remove it
            ex, ey, ez = elbow.elbow_pos
            elbow_brick = working.place(BRIDGE_PART_ID_ELBOW, color, ex, ey, ez, rotation=elbow.elbow_rotation)
            added.append(elbow_brick)
            occupied_cells.update(elbow_brick.occupied_cells())
            for x, y, z in elbow.continuation:
                new_brick = working.place(BRIDGE_PART_ID, color, x, y, z)
                added.append(new_brick)
                occupied_cells.add((x, y, z))
            continue

        for x, y, z in best_path:
            new_brick = working.place(BRIDGE_PART_ID, color, x, y, z)
            added.append(new_brick)
            occupied_cells.add((x, y, z))

        # A single 1-stud-wide pillar is the ONLY option _find_wide_pillar
        # couldn't beat -- which only happens when nowhere in this island's
        # own footprint is a full 2x2 available to anchor a stiffer
        # connection, i.e. the island itself is thin (a carved detail, a
        # slim interior feature -- see this function's own module
        # docstring on why a 2x2 column is preferred at all). That means
        # the ENTIRE island now hangs off a single stud at each end of a
        # single pillar -- graph-connected (satisfies analyze()'s own
        # definition, matching Studio's stability check per this project's
        # established history), but a lone stud is a real, physical single
        # point of failure for however much material sits on the other end
        # of it, not just a theoretical one. Measured directly on a real
        # production job (a carved pumpkin with a lantern inside, part_count
        # 6509): every successful bridge repair used this thin pillar
        # exclusively -- zero used the wide one -- because an isolated
        # interior feature like a lantern is exactly the "no 2x2 available"
        # shape this branch exists for. Reported as "detached sections"
        # even though analyze() correctly saw the model as one connected
        # piece: a single stud is not fragile in the graph sense, but it is
        # fragile in the physical one.
        #
        # Mitigation, not a redesign: try once more for a SECOND, fully
        # independent thin pillar through a different column in the same
        # island's own footprint, so the reconnected section has two
        # separate attachment points instead of one wherever the geometry
        # allows it. Deliberately still bounded to "this island's own
        # columns" (never searches a neighboring island's footprint) and
        # deliberately silent if none exists (a genuinely 1-column-wide
        # sliver has nowhere else to attach and is left exactly as before)
        # -- this can only ever ADD hidden, interior-only material on top
        # of an already-accepted connection, never change or remove the
        # primary pillar, so it carries the same safety argument as the
        # rest of this function.
        second_best_path: list[tuple[int, int, int]] | None = None
        for x0, z0 in columns:
            if (x0, z0) == best_path_col:
                continue
            candidate = best_thin_candidate(x0, z0, y_start_for(x0, z0), y_start_for_upward(x0, z0))
            if candidate is not None and (second_best_path is None or len(candidate) < len(second_best_path)):
                second_best_path = candidate

        if second_best_path is not None:
            for x, y, z in second_best_path:
                new_brick = working.place(BRIDGE_PART_ID, color, x, y, z)
                added.append(new_brick)
                occupied_cells.add((x, y, z))

    prune_result = prune_unstable(working)
    return BridgeResult(model=prune_result.model, added=added, removed=prune_result.removed)
