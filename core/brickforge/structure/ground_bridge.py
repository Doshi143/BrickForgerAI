"""Repairs a model that is CORRECTLY reported as multiple physical pieces
(find_disconnected_components / is_single_piece -- see weakpoints.py's own
module docstring for why GROUND is excluded from that question), in the
specific case where none of those pieces are individually at fall risk --
each one already touches the real ground on its own.

This is deliberately a DIFFERENT repair target than bridge_unstable /
prune_unstable, which only ever act on find_bricks_outside_main_component
(a component with NO ground contact of its own -- see weakpoints.py). A
second, independently-grounded region is, correctly, left completely
alone by that pass: it isn't going to fall, so there's nothing for
bridge_unstable to fix and nothing prune_unstable should delete (deleting
a second, perfectly sound structure just for being smaller than "main"
would be a real regression -- already guarded against by
find_bricks_outside_main_component's own second refinement, see its
docstring). But "won't fall down" and "is actually one buildable model"
are different questions. Two grounded regions sitting next to each other
on the baseplate, never physically connected to each other, is exactly
what Studio's own stability checker flags as multiple separate pieces,
and exactly what is_single_piece (report.py) already correctly detects --
until this module, nothing acted on it.

**Root cause this most often fires on**: the legalizer's own greedy
tiling runs independently per layer with no cross-region awareness (see
CLAUDE.md's own tiling-artifact history), so two adjacent patches of the
same ground layer can end up as separate tiles with nothing above them
yet to bind them into one piece -- each is individually grounded (both
touch y=0), but they were never actually connected to each other. A
second, real-world-reported cause: an OVERHANGING segment (a branch, a
wing, an eave) that legalizes with its own independent support column some
distance from the model's main mass -- the segment and its column are
internally connected to each other and to y=0, so bridge_unstable
correctly leaves them alone, but nothing ever bound that whole assembly to
the rest of the model.

**Two-tier repair, cheapest first**:

1. **Lateral weld** (original mechanism, unchanged): where a stray piece
   and the main structure are LATERALLY ADJACENT with matching top
   heights somewhere along their shared boundary, a single flat connector
   plate (1x2) resting across both resolves it in one part -- the common
   legalizer-seam case above.
2. **Hidden pillar / elbow** (new): where lateral adjacency doesn't apply
   -- the overhang case above, where the two pieces don't touch at all --
   search every column of the stray piece, both straight down and straight
   up, for a route through the model's own solid interior (same
   `solid_grid`-gated discipline as `bridge.py`'s own island search) that
   lands specifically on the MAIN structure. A wide (2x2) pillar is
   preferred over a thin (1x1) one for stiffness, matching bridge.py's own
   preference order; a single-hop lateral "elbow" (bridge.py's own
   mechanism) is tried as a last resort before giving up on this piece for
   this pass.

   **This intentionally does NOT reuse bridge.py's raw pillar-search
   functions unmodified**, despite the obvious temptation: those treat
   reaching y=0 as an always-valid landing (correct for an island with no
   ground contact of its own) and treat ANY existing material as a valid
   landing (correct when there's only one other component to reach). Both
   assumptions are wrong here -- a stray piece in THIS module is already
   grounded, so a new column quietly reaching y=0 elsewhere connects it to
   nothing new and must be rejected, not accepted; and a landing on some
   OTHER remaining stray (not `main`) would need this module's simpler
   main-only bookkeeping to become incorrect. The search functions below
   are new, narrower versions built for exactly this: a candidate path
   succeeds only by landing on a cell owned by `main` specifically, is
   blocked (fails outright, does not tunnel through) by a cell owned by
   anyone else, and never treats bare ground as a landing.

**Scope, stated honestly rather than silently limited further than it
is**: only ever targets `main` (the largest piece), not arbitrary
cross-stray merges -- two strays that could only ever reach each other,
never main, won't merge directly in one pass (though each may still
separately resolve against main once it grows). The elbow fallback is a
single lateral hop, same limit as bridge.py's own version -- a gap wide
enough to need two or more lateral hops chained together is a strictly
harder pathing problem (true multi-hop pathfinding through the lattice)
and is left as a disclosed, real limitation, same spirit as
`unresolved_pieces` already reports rather than hides. SNOT
sub-assemblies remain out of scope, same as before -- the connectivity
graph here is built without snot_children, same as most of this
pipeline's other stages.

**A real limitation carried over from bridge.py, applying identically
here**: a lone thin pillar is a genuine physical single point of failure
for whatever hangs off its far end, even though it's graph-connected.
Unlike bridge.py, this module does not add a second independent thin
pillar as mitigation -- a stray piece here is, by definition, already a
complete, independently-grounded structure in its own right (not a bare
island hanging entirely off one new connection), so a single weld adding
one more attachment point to an already-self-supporting piece is a much
smaller risk than bridge.py's own case of an entire ungrounded island
resting on nothing else at all.

A second, real limitation, caught by this module's own test suite, not
just reasoned about: a connector always sits one layer above (or, for a
pillar, spans several layers past) whatever it lands on -- there's no way
around this (same-layer placements never connect in this catalog, see the
module-level comment on CONNECTOR_PART_ID/BRIDGE_PART_ID_ELBOW in
bridge.py's own elbow directions), so welding two pieces together can
raise the height of the specific column(s) a connector rests on. If a
THIRD stray piece's only possible connection point was that exact column,
it can no longer flush-match there after the first weld -- chains resolve
fully in one call only when consecutive bridges land on genuinely
different columns (see
test_a_chain_of_three_adjacent_pieces_fully_resolves_in_one_call for the
case that does work, and its own comment for why a narrower version of
the same setup wouldn't)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..lattice import Rotation
from ..model import Brick, Model, PlacementError
from .bridge import (
    BRIDGE_PART_ID,
    BRIDGE_PART_ID_ELBOW,
    BRIDGE_PART_ID_WIDE,
    _ELBOW_DIRECTIONS,
    _WIDE_ANCHOR_OFFSETS,
    _is_interior_factory,
)
from .graph import build_connectivity_graph
from .weakpoints import find_disconnected_components

CONNECTOR_PART_ID = "3023"  # 1x2 plate -- the only single part that can span two adjacent columns

_LATERAL_NEIGHBORS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


@dataclass
class GroundBridgeResult:
    model: Model
    added: list[Brick] = field(default_factory=list)
    # Pieces (as sets of the ORIGINAL model's brick indices) that could not
    # be bridged this pass -- see module docstring's own "Scope" section.
    # Never silently dropped: reported so a caller can decide what to do
    # (or just report it), the same "don't hide an unresolved case"
    # discipline bridge_unstable's own fallback-to-prune already follows
    # for its own unresolved islands.
    unresolved_pieces: list[set[int]] = field(default_factory=list)


def _column_tops(model: Model) -> dict[tuple[int, int], tuple[int, int]]:
    """(x, z) -> (top_y, owning brick index) for whichever brick occupies
    the topmost cell of that column. Same "top = base + height_plates"
    convention already used throughout this codebase (e.g. pipeline/
    slopes.py's own column-top tracking) -- a column with nothing placed
    in it at all is simply absent from the returned dict."""
    tops: dict[tuple[int, int], tuple[int, int]] = {}
    for i, brick in enumerate(model.bricks):
        top = brick.pos.y + brick.part.height_plates
        w, d = brick.footprint
        for dx in range(w):
            for dz in range(d):
                col = (brick.pos.x + dx, brick.pos.z + dz)
                current = tops.get(col)
                if current is None or top > current[0]:
                    tops[col] = (top, i)
    return tops


def _place_connector(
    working: Model,
    col_a: tuple[int, int],
    col_b: tuple[int, int],
    y: int,
    color: int,
) -> Brick | None:
    """Try to place a single CONNECTOR_PART_ID plate spanning col_a and
    col_b, its own bottom at layer y (resting directly on top of whatever
    already occupies both columns, per _column_tops' "top" meaning).
    Returns None if the two target cells turn out not to actually be
    free -- rare, since they're one layer above two already-topmost
    columns, but a third, taller neighbouring brick could still overhang
    into the same cell, so this is checked by the real collision system
    (Model.place's own PlacementError), not assumed clear."""
    (xa, za), (xb, zb) = col_a, col_b
    if xa == xb:
        rotation = Rotation.YAW_90  # this part's footprint [2, 1] -> [1, 2], spans z
        x0, z0 = xa, min(za, zb)
    else:
        rotation = Rotation.YAW_0  # footprint [2, 1] as declared, spans x
        x0, z0 = min(xa, xb), za

    try:
        return working.place(CONNECTOR_PART_ID, color, x0, y, z0, rotation=rotation)
    except PlacementError:
        return None


def _try_lateral_weld(working: Model, source: set[int], target: set[int]) -> Brick | None:
    """First valid connector plate joining a `source`-owned column to a
    laterally adjacent `target`-owned column at matching top height --
    "first", not "best", matching this project's existing preference for
    a simple, correct default wherever any valid candidate resolves the
    actual problem equally well. Tops are recomputed fresh on every call --
    called at most once per remaining stray piece per outer pass, so this
    stays cheap, and it means a connector placed for an earlier stray in
    the same pass is immediately visible as new attachable material for
    the next one."""
    tops = _column_tops(working)
    for col, (top_y, idx) in tops.items():
        if idx not in source:
            continue
        x, z = col
        for dx, dz in _LATERAL_NEIGHBORS:
            neighbor = (x + dx, z + dz)
            neighbor_info = tops.get(neighbor)
            if neighbor_info is None:
                continue
            neighbor_top_y, neighbor_idx = neighbor_info
            if neighbor_idx not in target or neighbor_top_y != top_y:
                continue
            color = working.bricks[idx].color
            connector = _place_connector(working, col, neighbor, top_y, color)
            if connector is not None:
                return connector
    return None


# --- Hidden pillar / elbow search, restricted to landing on `target` only ---
#
# Deliberately NOT bridge.py's own _find_pillar/_find_wide_pillar/etc: those
# treat reaching y=0 as an always-valid landing and treat ANY existing
# material as a valid landing, both wrong here -- see module docstring.


def _find_target_pillar_down(
    x0: int, z0: int, y_start: int, target_cells: set, all_occupied: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Cells a straight-down pillar from (x0, y_start, z0) would need to
    add to land on `target_cells` specifically. None if it goes out of the
    solid interior, is blocked by material that ISN'T the target, or
    reaches y=0 without ever touching the target -- reaching bare ground
    connects a piece that's already grounded to nothing new."""
    path: list[tuple[int, int, int]] = []
    y = y_start
    while y >= 0:
        if not is_interior(x0, y, z0):
            return None
        cell = (x0, y, z0)
        if cell in target_cells:
            return path
        if cell in all_occupied:
            return None  # blocked by someone else's material -- can't tunnel through it
        path.append(cell)
        y -= 1
    return None  # reached y=0 without ever landing on target


def _find_target_pillar_up(
    x0: int, z0: int, y_start: int, y_max: int, target_cells: set, all_occupied: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Upward mirror of `_find_target_pillar_down`. There's no ground-like
    "always valid" ceiling either way, so this needs no equivalent
    rejection -- reaching y_max without landing on target is already a
    plain, correct failure."""
    path: list[tuple[int, int, int]] = []
    y = y_start
    while y <= y_max:
        if not is_interior(x0, y, z0):
            return None
        cell = (x0, y, z0)
        if cell in target_cells:
            return path
        if cell in all_occupied:
            return None
        path.append(cell)
        y += 1
    return None


def _find_target_wide_pillar_down(
    x0: int, z0: int, y_start: int, target_cells: set, all_occupied: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Like `_find_target_pillar_down`, but for a rigid 2x2 column anchored
    at (x0, z0)-(x0+1, z0+1). All 4 sub-cells must land on target together
    -- a lopsided landing where only some corners touch target (and none
    are blocked) is rejected, same reasoning bridge.py's own wide search
    already applies: an unsupported corner defeats the point of a wider,
    stiffer pillar."""
    cells = [(x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1)]
    layers: list[tuple[int, int, int]] = []
    y = y_start
    while y >= 0:
        if not all(is_interior(cx, y, cz) for cx, cz in cells):
            return None
        on_target = [(cx, y, cz) in target_cells for cx, cz in cells]
        blocked = [(cx, y, cz) in all_occupied and not t for (cx, cz), t in zip(cells, on_target)]
        if any(blocked):
            return None
        if all(on_target):
            return layers
        if any(on_target):
            return None  # some corners on target, others still open -- lopsided, reject
        layers.append((x0, y, z0))
        y -= 1
    return None


def _find_target_wide_pillar_up(
    x0: int, z0: int, y_start: int, y_max: int, target_cells: set, all_occupied: set, is_interior
) -> list[tuple[int, int, int]] | None:
    """Upward mirror of `_find_target_wide_pillar_down`."""
    cells = [(x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1)]
    layers: list[tuple[int, int, int]] = []
    y = y_start
    while y <= y_max:
        if not all(is_interior(cx, y, cz) for cx, cz in cells):
            return None
        on_target = [(cx, y, cz) in target_cells for cx, cz in cells]
        blocked = [(cx, y, cz) in all_occupied and not t for (cx, cz), t in zip(cells, on_target)]
        if any(blocked):
            return None
        if all(on_target):
            return layers
        if any(on_target):
            return None
        layers.append((x0, y, z0))
        y += 1
    return None


@dataclass
class _ElbowCandidate:
    elbow_pos: tuple[int, int, int]
    elbow_rotation: Rotation
    continuation: list[tuple[int, int, int]]

    @property
    def cost(self) -> int:
        return 2 + len(self.continuation)


def _find_target_elbow(
    x0: int,
    z0: int,
    y_start: int,
    dx: int,
    dz: int,
    rotation: Rotation,
    target_cells: set,
    all_occupied: set,
    is_interior,
    upward: bool,
    y_max: int,
) -> _ElbowCandidate | None:
    """Single-hop elbow: a 1x2 plate at (x0, z0)-(x1, z1), both cells new
    and empty, then a straight target-seeking pillar continuing from the
    neighbor column. `upward` picks which direction the continuation (and
    the elbow's own placement relative to the stray's own material)
    searches -- see bridge.py's own _find_elbow/_find_elbow_upward for the
    non-target-restricted original this mirrors."""
    x1, z1 = x0 + dx, z0 + dz
    if not (is_interior(x0, y_start, z0) and is_interior(x1, y_start, z1)):
        return None
    if (x0, y_start, z0) in all_occupied or (x1, y_start, z1) in all_occupied:
        return None
    if upward:
        continuation = _find_target_pillar_up(x1, z1, y_start + 1, y_max, target_cells, all_occupied, is_interior)
    else:
        continuation = _find_target_pillar_down(x1, z1, y_start - 1, target_cells, all_occupied, is_interior)
    if continuation is None:
        return None
    corner_x, corner_z = min(x0, x1), min(z0, z1)
    return _ElbowCandidate(elbow_pos=(corner_x, y_start, corner_z), elbow_rotation=rotation, continuation=continuation)


def _find_hidden_bridge(
    stray_bricks: list[Brick], target_cells: set, all_occupied: set, is_interior, y_max: int
) -> list[tuple[str, int, int, int, Rotation | None]] | None:
    """Search every column of `stray_bricks`' own footprint for a hidden
    (solid_grid-interior-only) pillar or single-hop elbow landing
    specifically on `target_cells`. Wide (2x2) pillars are preferred over
    thin (1x1) for stiffness; elbow is tried only once neither pillar
    shape works anywhere. Returns a list of (part_id, x, y, z, rotation)
    placements to make, cheapest (fewest parts) option found, or None if
    nothing connects this piece to target at all this pass."""
    columns: set[tuple[int, int]] = set()
    for brick in stray_bricks:
        w, d = brick.footprint
        for dx in range(w):
            for dz in range(d):
                columns.add((brick.pos.x + dx, brick.pos.z + dz))

    def y_start_down(x0: int, z0: int) -> int:
        return (
            min(
                b.pos.y
                for b in stray_bricks
                if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
            )
            - 1
        )

    def y_start_up(x0: int, z0: int) -> int:
        return max(
            b.pos.y + b.part.height_plates
            for b in stray_bricks
            if b.pos.x <= x0 < b.pos.x + b.footprint[0] and b.pos.z <= z0 < b.pos.z + b.footprint[1]
        )

    best_wide: list[tuple[int, int, int]] | None = None
    for x0, z0 in columns:
        for ox, oz in _WIDE_ANCHOR_OFFSETS:
            ax, az = x0 + ox, z0 + oz
            yd = y_start_down(x0, z0)
            if yd >= 0:
                down = _find_target_wide_pillar_down(ax, az, yd, target_cells, all_occupied, is_interior)
                if down is not None and (best_wide is None or len(down) < len(best_wide)):
                    best_wide = down
            up = _find_target_wide_pillar_up(ax, az, y_start_up(x0, z0), y_max, target_cells, all_occupied, is_interior)
            if up is not None and (best_wide is None or len(up) < len(best_wide)):
                best_wide = up
    if best_wide is not None:
        return [(BRIDGE_PART_ID_WIDE, x, y, z, None) for x, y, z in best_wide]

    best_thin: list[tuple[int, int, int]] | None = None
    for x0, z0 in columns:
        yd = y_start_down(x0, z0)
        if yd >= 0:
            down = _find_target_pillar_down(x0, z0, yd, target_cells, all_occupied, is_interior)
            if down is not None and (best_thin is None or len(down) < len(best_thin)):
                best_thin = down
        up = _find_target_pillar_up(x0, z0, y_start_up(x0, z0), y_max, target_cells, all_occupied, is_interior)
        if up is not None and (best_thin is None or len(up) < len(best_thin)):
            best_thin = up
    if best_thin is not None:
        return [(BRIDGE_PART_ID, x, y, z, None) for x, y, z in best_thin]

    best_elbow: _ElbowCandidate | None = None
    for x0, z0 in columns:
        yd = y_start_down(x0, z0)
        yu = y_start_up(x0, z0)
        for dx, dz, rotation in _ELBOW_DIRECTIONS:
            if yd >= 0:
                down = _find_target_elbow(
                    x0, z0, yd, dx, dz, rotation, target_cells, all_occupied, is_interior, upward=False, y_max=y_max
                )
                if down is not None and (best_elbow is None or down.cost < best_elbow.cost):
                    best_elbow = down
            up = _find_target_elbow(
                x0, z0, yu, dx, dz, rotation, target_cells, all_occupied, is_interior, upward=True, y_max=y_max
            )
            if up is not None and (best_elbow is None or up.cost < best_elbow.cost):
                best_elbow = up
    if best_elbow is not None:
        ex, ey, ez = best_elbow.elbow_pos
        placements: list[tuple[str, int, int, int, Rotation | None]] = [
            (BRIDGE_PART_ID_ELBOW, ex, ey, ez, best_elbow.elbow_rotation)
        ]
        placements.extend((BRIDGE_PART_ID, x, y, z, None) for x, y, z in best_elbow.continuation)
        return placements

    return None


def _try_bridge(working: Model, source: set[int], target: set[int], is_interior) -> list[Brick] | None:
    """Weld `source` onto `target`: the cheap lateral weld first, falling
    back to a hidden pillar/elbow search only where that fails (see module
    docstring's "Two-tier repair" section for why, and for exactly what
    the hidden search will and won't find)."""
    lateral = _try_lateral_weld(working, source, target)
    if lateral is not None:
        return [lateral]

    all_occupied: set[tuple[int, int, int]] = set()
    for brick in working.bricks:
        all_occupied.update(brick.occupied_cells())
    if not all_occupied:
        return None
    target_cells: set[tuple[int, int, int]] = set()
    for i in target:
        target_cells.update(working.bricks[i].occupied_cells())
    y_max = max(y for _, y, _ in all_occupied)

    source_bricks = [working.bricks[i] for i in source]
    placements = _find_hidden_bridge(source_bricks, target_cells, all_occupied, is_interior, y_max)
    if placements is None:
        return None

    color = source_bricks[0].color
    placed: list[Brick] = []
    for part_id, x, y, z, rotation in placements:
        kwargs = {} if rotation is None else {"rotation": rotation}
        try:
            brick = working.place(part_id, color, x, y, z, **kwargs)
        except PlacementError:
            # A cell that looked free during the search was claimed by an
            # earlier placement in this SAME placements list (can only
            # happen for the elbow's own two cells, immediately adjacent)
            # -- bail out rather than leave a half-placed connector.
            return None
        placed.append(brick)
    return placed


def bridge_disconnected_pieces(model: Model, solid_grid=None) -> GroundBridgeResult:
    """Find every case of `find_disconnected_components` reporting more
    than one piece, and try to weld each stray piece onto the main one
    (see module docstring for exactly when that's possible, and via which
    of the two repair tiers). The largest piece by brick count is treated
    as "main", matching find_bricks_outside_main_component's own
    tie-break elsewhere in this package, for the same reason: it's the
    one a human would call "the sculpture" and everything else "the
    stray bit next to it".

    `solid_grid`, if supplied (mesh_to_model.py::mesh_to_model_full
    exposes it), gates the hidden pillar/elbow search exactly the way
    bridge.py's own bridge_unstable already uses it -- every cell a
    candidate connector would occupy must be part of the mesh's original
    solid silhouette, so a repair can never poke a visible strut through
    open air. Omitted, the interior check is skipped (same fallback
    bridge_unstable itself uses for a hand-built Model with no mesh).

    Runs in a `while` loop, not a single pass: welding one stray onto
    main can turn what used to be main+strayA into a single larger
    target that a DIFFERENT stray, strayB (adjacent or hidden-reachable
    from strayA but not directly from the original main), can now weld
    onto in turn -- a chain of several such islands can fully resolve in
    one call, not just the one nearest the original main body."""
    graph = build_connectivity_graph(model)  # no snot_children -- see module docstring
    components = find_disconnected_components(graph)
    if len(components) <= 1:
        return GroundBridgeResult(model=model, added=[], unresolved_pieces=[])

    is_interior = _is_interior_factory(solid_grid)

    working = Model(catalog=model.catalog)
    for brick in model.bricks:
        working.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    pieces = sorted((set(c) for c in components), key=len, reverse=True)
    main = pieces[0]
    remaining = pieces[1:]

    added: list[Brick] = []
    progressed = True
    while remaining and progressed:
        progressed = False
        next_remaining: list[set[int]] = []
        for stray in remaining:
            connectors = _try_bridge(working, stray, main, is_interior)
            if connectors is None:
                next_remaining.append(stray)
                continue
            added.extend(connectors)
            main |= stray
            # Every newly-added connector is now real, physically-attached
            # material too, and (for a pillar/elbow) may become the new
            # topmost/bottommost cell of whatever column it occupies --
            # without adding its own fresh index to `main`, a later stray
            # whose only route is through one of those same cells would
            # look it up, find it isn't in `main`, and wrongly conclude
            # the column isn't attached after all. Same bug class this
            # module's own test suite already caught once for the plain
            # lateral-weld case (see test_a_chain_of_three_adjacent_pieces
            # _fully_resolves_in_one_call), reapplied here for every new
            # connector, not just a single plate.
            first_new_index = len(working.bricks) - len(connectors)
            main.update(range(first_new_index, len(working.bricks)))
            progressed = True
        remaining = next_remaining

    return GroundBridgeResult(model=working, added=added, unresolved_pieces=remaining)
