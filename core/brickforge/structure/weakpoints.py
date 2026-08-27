"""Cheap structural pre-checks: disconnected pieces, articulation points,
and bridges in the connectivity graph. DESIGN.md sec. 5 is explicit that
this pass should run before any force analysis -- it's nearly free to
compute and catches most real-world breakage (a big appendage hanging off a
single stud is a bridge/articulation point, full stop, no force math
needed to know it's fragile).

**Which check drives repair, and why it changed.** Two different notions
of "is this brick actually held up" live here, and only one of them should
decide what bridge.py/repair.py touch:

- `find_bricks_outside_main_component` (undirected: is this brick part of
  the same rigid, interconnected mass as GROUND, via *any* path -- up,
  down, sideways-through-a-neighbor, whatever) is what actually predicts
  whether a piece stays attached to a dense, shelled sculpture. This is
  the one repair uses.
- `find_ungrounded_bricks` (directed: does this *specific* brick have its
  own unbroken chain of straight-down "resting on" edges to GROUND) is a
  stricter, purely theoretical bar that most bricks in a real interconnected
  shell fail even when they are, in every practical sense, fine -- a brick
  braced by neighbors above and to the side, the way a keystone is held by
  lateral compression rather than resting on the ground itself, has no
  such chain and still isn't going anywhere.

An earlier version of this module used `find_ungrounded_bricks` to drive
bridge/prune/refill and got it wrong at scale, not just by a little: on
the bunny test model it flagged 91-159 bricks as critical (depending on
which legalizer pass), producing large visible holes after repair. The
user pushed back with two independent pieces of real evidence -- the
unrepaired model didn't look obviously broken except at one spot, and
Studio's own built-in stability checker agreed, flagging only a handful of
bricks in 2 small isolated clusters. Checked directly rather than argued:
`find_bricks_outside_main_component` on that same model returns exactly 4
bricks, in exactly 2 clusters -- matching Studio closely. That's not a
coincidence; it's because "part of one rigid mass" is the physically
correct question for a dense sculpture, and "has its own private path
straight down" isn't. `find_ungrounded_bricks` is kept, still correct for
what it actually computes, and still a real (if much more conservative)
signal for anyone who wants it -- it just isn't what determines what gets
bridged, refilled, or pruned anymore.
"""

from __future__ import annotations

import networkx as nx

from ..model import Model
from .graph import GROUND


def find_ungrounded_bricks(graph: nx.Graph, model: Model) -> set[int]:
    """Brick indices with no unbroken chain of "resting on" connections
    down to GROUND. See module docstring: this is a strict, directed,
    single-path notion of support, correct as far as it goes, but NOT what
    drives repair -- use find_bricks_outside_main_component for that.

    Computed with one BFS from GROUND, only ever following an edge from an
    already-grounded node to a neighbor sitting strictly higher (i.e. "this
    grounded brick supports that one"). Anything the BFS never reaches has
    no such chain -- there is no possible path to GROUND for it that
    doesn't at some point require an edge to go the wrong way.

    **SNOT nodes** (see structure/graph.py's `("snot", i)` node ids) are
    skipped as neighbors, not traversed -- this directed, straight-down
    notion of "resting on" doesn't have an equivalent for a sideways
    stud connection, and this check is informational-only (module
    docstring), so a brick reachable from GROUND only via a SNOT branch
    will still show up here as "ungrounded." find_bricks_outside_main_component
    (undirected) is what drives repair and does not have this limitation."""
    grounded: set = {GROUND}
    frontier = [GROUND]
    while frontier:
        node = frontier.pop()
        node_y = None if node == GROUND else model.bricks[node].pos.y
        for neighbor in graph.neighbors(node):
            if neighbor in grounded or not isinstance(neighbor, int):
                continue
            if node == GROUND or model.bricks[neighbor].pos.y > node_y:
                grounded.add(neighbor)
                frontier.append(neighbor)
    grounded.discard(GROUND)
    return set(range(len(model.bricks))) - grounded


def _components_excluding_ground(graph: nx.Graph) -> list[set]:
    """The real, physical notion of "still attached to each other":
    connected components computed with the GROUND node (and every edge
    touching it) removed first.

    **A real bug, reported directly by the founder and confirmed by
    reading this code, not just theorized: GROUND was being counted as a
    real connection for the purposes of "is this one piece" and "is this
    brick part of the main mass".** GROUND connects to EVERY brick
    sitting at y=0 (see build_connectivity_graph) -- which means, with
    GROUND left in, two entirely separate regions that each merely touch
    the floor (two legs of a chair that don't actually connect to each
    other or to a body above, a disconnected fragment sitting next to the
    real sculpture) are seen by `nx.connected_components` as ONE
    component, transitively joined through the shared GROUND node, even
    though nothing physically attaches them to each other. In real life,
    picking up the sculpture would NOT bring that other region along --
    it would just sit there on the table. That is exactly what
    `is_single_piece` and `critical_bricks` are supposed to answer, so
    GROUND must be excluded here, in both functions below.

    GROUND is still used, correctly, by find_articulation_points/
    find_bridges (asking a genuinely different, valid question: "if you
    removed just this one ground-contact edge, would something come
    loose") and by load.py's own gravity-load propagation (a real brick
    resting on the actual floor is correctly credited with that support
    regardless of whether it's part of the sculpture's main mass) -- this
    fix is scoped to only the two functions that decide "is this the same
    physical piece", not a wholesale removal of the GROUND node."""
    nodes = [n for n in graph.nodes if n != GROUND]
    return list(nx.connected_components(graph.subgraph(nodes)))


def find_disconnected_components(graph: nx.Graph) -> list[set]:
    """Every connected component of the model's own real connectivity
    (GROUND excluded, see _components_excluding_ground). More than one
    component (beyond the trivial case of an empty model) means the
    model is literally in separate pieces -- the single worst structural
    failure, since it isn't a matter of a connection being *weak*,
    there's no connection there at all."""
    return _components_excluding_ground(graph)


def find_bricks_outside_main_component(graph: nx.Graph) -> set:
    """Brick indices (int) AND SNOT child node ids (`("snot", i)` tuples,
    see structure/graph.py) not part of the largest connected component
    of the model's own real connectivity (GROUND excluded -- see
    _components_excluding_ground's own docstring for the real bug this
    fixes) -- see module docstring for why this, not find_ungrounded_bricks,
    is what should drive repair decisions.

    Two refinements on top of "just pick the largest component", both
    caught by this project's own test suite while fixing the GROUND bug
    above, not designed in from the start:

    1. "Main" prefers the largest component that ITSELF touches the real
       ground (has an edge to GROUND) over a larger component that
       doesn't touch ground at all. Without this, a hand-built model of
       one small grounded tower plus one larger *floating* pair (nothing
       under it, resting on nothing) picked the floating pair as "main"
       purely for having more nodes -- backwards, since a component with
       no ground contact at all isn't a plausible "main sculpture" to
       measure everything else against. Falls back to the plain largest
       component only if NO component touches ground at all (a fully
       floating model -- shouldn't happen for real generated content,
       since mesh conditioning always grounds the mesh first, but a
       degenerate case worth not crashing on).
    2. A component that isn't "main" but DOES independently touch the
       real ground on its own is still excluded from this result. Two
       genuinely separate pieces that each stand on the floor are still,
       correctly, "not a single piece" (see find_disconnected_components,
       used for that) -- but neither is at risk of FALLING, which is
       what `critical_bricks` and bridge_unstable/prune_unstable's repair
       decisions are actually about. Without this, prune_unstable would
       delete an entire second, perfectly sound, independently-grounded
       structure (e.g. a bridged island that successfully reached the
       ground on its own) just for ending up smaller than whichever
       component is "main" -- also caught by this project's own tests."""
    components = _components_excluding_ground(graph)
    if not components:
        return set()

    grounded_nodes = set(graph.neighbors(GROUND)) if GROUND in graph else set()
    grounded_components = [c for c in components if c & grounded_nodes]
    main = max(grounded_components or components, key=len)

    outside: set = set()
    for component in components:
        if component is main:
            continue
        if component & grounded_nodes:
            continue
        outside.update(component)
    return outside


def find_articulation_points(graph: nx.Graph) -> set[int]:
    """Brick indices whose removal would disconnect some part of the model
    from GROUND (or from the rest of an already-ground-disconnected
    piece). Computed per connected component since networkx's
    articulation_points requires a connected graph."""
    points: set[int] = set()
    for component in nx.connected_components(graph):
        if len(component) < 3:
            continue
        points.update(nx.articulation_points(graph.subgraph(component)))
    points.discard(GROUND)
    return points


def find_bridges(graph: nx.Graph) -> list[tuple]:
    """Edges whose removal would disconnect some part of the model. Every
    edge touching GROUND is included too -- a brick held on by exactly one
    ground-contact edge really is a single point of failure for whatever's
    built on top of it."""
    bridges: list[tuple] = []
    for component in nx.connected_components(graph):
        bridges.extend(nx.bridges(graph.subgraph(component)))
    return bridges
