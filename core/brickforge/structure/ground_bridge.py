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
touch y=0), but they were never actually connected to each other.

**Scope, stated honestly rather than silently limited further than it
is**: this only bridges a stray piece to the main structure where the
two are LATERALLY ADJACENT with matching top heights somewhere along
their shared boundary -- i.e. two neighboring columns where a single
flat connector plate can rest across both without a gap or a step. This
is the common real case described above, and it's one a single new part
can always resolve. It does NOT attempt to span a genuine gap between
two pieces that aren't touching at all -- that's a strictly harder
pathing problem (how long a connector, what height, whether it collides
with anything else) closer in spirit to bridge_unstable's own
elbow+pillar search than to a single adjacency check, and is left as a
disclosed, real limitation (see `unresolved_pieces`) rather than
silently attempted and left buggy. SNOT sub-assemblies are out of scope
too -- the connectivity graph here is built without snot_children, same
as most of this pipeline's other stages.

**A second, real limitation, caught by this module's own test suite, not
just reasoned about**: a connector always sits one layer above whatever
it spans (there's no way around this -- same-layer placements never
connect in this catalog, see the module-level comment on CONNECTOR_PART_ID
in bridge.py's own elbow directions), so welding two pieces together
raises the height of the specific column(s) the connector rests on by
one plate. If a THIRD stray piece's only possible connection point was
that exact column, it can no longer flush-match there after the first
weld -- chains resolve fully in one call only when consecutive bridges
land on genuinely different columns (see
test_a_chain_of_three_adjacent_pieces_fully_resolves_in_one_call for the
case that does work, and its own comment for why a narrower version of
the same setup wouldn't)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..lattice import Rotation
from ..model import Brick, Model, PlacementError
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


def _try_bridge(working: Model, source: set[int], target: set[int]) -> Brick | None:
    """First valid connector plate joining a `source`-owned column to a
    laterally adjacent `target`-owned column at matching top height --
    "first", not "best", matching this project's existing preference for
    a simple, correct default wherever any valid candidate resolves the
    actual problem equally well (unlike bridge.py's own pillar search,
    where minimising added part count is itself the point, a single
    extra 1x2 plate's exact placement doesn't matter which valid one it
    is). Tops are recomputed fresh on every call -- called at most once
    per remaining stray piece per outer pass, so this stays cheap, and
    it means a connector placed for an earlier stray in the same pass is
    immediately visible as new attachable material for the next one."""
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


def bridge_disconnected_pieces(model: Model) -> GroundBridgeResult:
    """Find every case of `find_disconnected_components` reporting more
    than one piece, and try to weld each stray piece onto the main one
    with a single connector plate (see module docstring for exactly
    when that's possible). The largest piece by brick count is treated
    as "main", matching find_bricks_outside_main_component's own
    tie-break elsewhere in this package, for the same reason: it's the
    one a human would call "the sculpture" and everything else "the
    stray bit next to it".

    Runs in a `while` loop, not a single pass: welding one stray onto
    main can turn what used to be main+strayA into a single larger
    target that a DIFFERENT stray, strayB (adjacent to strayA but not
    directly to the original main), can now weld onto in turn -- a
    chain of several mutually-adjacent stray islands can fully resolve
    in one call, not just the one nearest the original main body."""
    graph = build_connectivity_graph(model)  # no snot_children -- see module docstring
    components = find_disconnected_components(graph)
    if len(components) <= 1:
        return GroundBridgeResult(model=model, added=[], unresolved_pieces=[])

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
            connector = _try_bridge(working, stray, main)
            if connector is None:
                next_remaining.append(stray)
                continue
            added.append(connector)
            main |= stray
            # The connector itself is now real, physically-attached
            # material too -- and since it sits one layer above the
            # columns it spans, _column_tops will report IT (not the
            # brick(s) underneath) as those columns' new top. Without
            # adding its own fresh index to `main`, a later stray whose
            # only adjacency is to one of those same columns would look
            # up the connector's index, find it isn't in `main`, and
            # wrongly conclude the column isn't attached after all --
            # caught by test_a_chain_of_three_adjacent_pieces_fully_resolves_in_one_call,
            # not assumed away.
            main.add(len(working.bricks) - 1)
            progressed = True
        remaining = next_remaining

    return GroundBridgeResult(model=working, added=added, unresolved_pieces=remaining)
