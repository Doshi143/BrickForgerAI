"""Connectivity graph: nodes are placed bricks (by index into
model.bricks), edges are stud/anti-stud connections between a brick and the
one directly above it, weighted by how many studs they share. A virtual
`GROUND` node is connected to every brick sitting at y=0, standing in for
external support (a table, a base plate) -- this makes "is this brick's
subtree still attached to the ground" the right question for articulation
points and bridges to answer, not just "is the graph still connected to
something."

**Phase B**: optionally also takes a list of `snot.SnotChild` (sideways
sub-assembly parts, anchored to an ordinary brick's molded side stud(s) --
see snot.py's own module docstring for why they live outside `Model`'s
grid). Each becomes a graph node with id `("snot", i)` -- a tuple,
deliberately never a plain int, so it can never collide with an ordinary
brick index or be silently misread as one by code elsewhere in this
package that doesn't (yet) understand SNOT nodes. `weakpoints.py` and
`load.py` were both audited and updated to either handle these node ids
correctly or explicitly, safely ignore them (see their own docstrings) --
if you add a third consumer of this graph, check it against a graph built
WITH snot_children before trusting it, the same discipline this project
already applies to every other structural check.
"""

from __future__ import annotations

import networkx as nx

from ..model import Model
from ..snot import SnotChild, in_plane_axis

GROUND = "GROUND"


def _in_plane_span(child: SnotChild, axis: str) -> tuple[int, int]:
    """The [start, end) range (in stud units, 0-indexed from the frame's
    own corner) this child's footprint covers along the face's in-plane
    axis -- the same corner-based indexing `GridPos.x`/`GridPos.z` already
    use everywhere else in this codebase, not a new convention."""
    eff_w, eff_d = child.local_rotation.rotate_footprint(*child.part.footprint)
    width = eff_d if axis == "z" else eff_w
    start = child.local_pos.z if axis == "z" else child.local_pos.x
    return start, start + width


def _add_snot_edges(graph: nx.Graph, model: Model, snot_children: list[SnotChild]) -> None:
    """Two edge types, both weighted by shared-stud count the exact same
    way the ordinary top/bottom edges above are:

    1. parent <-> child, for every child resting directly against the
       parent's own molded stud(s) (`local_pos.y == 0`) -- weight is how
       many of the parent's `side_stud_count` studs the child's in-plane
       footprint actually overlaps, computed by intersecting the child's
       own in-plane span against [0, side_stud_count). This assumes the
       child's frame was built at the parent's default (along=0)
       face_offset, so the frame's own corner lines up with stud index 0
       -- true for every SNOT part/example in this codebase so far (see
       SnotChild's own docstring), not yet generalized to an arbitrary
       face_offset.
    2. child <-> child, for two children on the SAME parent+face whose
       local_pos.y ranges are exactly adjacent (one's top is the other's
       bottom, along the frame's own outward-stacking axis) AND whose
       in-plane spans overlap -- the sideways equivalent of the ordinary
       top/bottom stud match above, walked in the frame's own local
       coordinate space instead of world Y.

    Raises if a SnotChild references a parent brick with no
    `side_stud_face` -- a caller bug (an ordinary, non-SNOT brick can't be
    a SNOT parent), not a case to silently ignore.
    """
    by_parent_face: dict[tuple[int, str], list[int]] = {}
    for i, child in enumerate(snot_children):
        parent = model.bricks[child.parent_index]
        face = parent.part.side_stud_face
        if face is None:
            raise ValueError(
                f"SnotChild {i} references brick {child.parent_index} "
                f"({parent.part.id!r}), which has no side_stud_face"
            )
        graph.add_node(("snot", i))
        by_parent_face.setdefault((child.parent_index, face), []).append(i)

    for (parent_index, face), child_indices in by_parent_face.items():
        parent = model.bricks[parent_index]
        axis = in_plane_axis(face)
        stud_count = parent.part.side_stud_count

        for ci in child_indices:
            child = snot_children[ci]
            if child.local_pos.y != 0:
                continue
            if child.parent_overlaps is not None:
                # Pre-computed by whoever built this child (region-growing
                # -- see SnotChild's own docstring): a merged panel can
                # rest on several different real parents' studs, not just
                # the one anchoring its own frame, so trust the emitting
                # stage's own measurement instead of recomputing overlap
                # against this single `parent_index` alone.
                for real_parent_index, overlap in child.parent_overlaps:
                    if overlap > 0:
                        graph.add_edge(real_parent_index, ("snot", ci), studs=overlap)
                continue
            lo, hi = _in_plane_span(child, axis)
            overlap = max(0, min(hi, stud_count) - max(lo, 0))
            if overlap > 0:
                graph.add_edge(parent_index, ("snot", ci), studs=overlap)

        by_bottom: dict[int, list[int]] = {}
        by_top: dict[int, list[int]] = {}
        for ci in child_indices:
            child = snot_children[ci]
            by_bottom.setdefault(child.local_pos.y, []).append(ci)
            by_top.setdefault(child.local_pos.y + child.part.height_plates, []).append(ci)

        for y, uppers in by_bottom.items():
            lowers = by_top.get(y)
            if not lowers:
                continue
            for lci in lowers:
                lo_lo, lo_hi = _in_plane_span(snot_children[lci], axis)
                for uci in uppers:
                    up_lo, up_hi = _in_plane_span(snot_children[uci], axis)
                    overlap = max(0, min(lo_hi, up_hi) - max(lo_lo, up_lo))
                    if overlap > 0:
                        graph.add_edge(("snot", lci), ("snot", uci), studs=overlap)


def build_connectivity_graph(model: Model, snot_children: list[SnotChild] | None = None) -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(GROUND)

    for i, brick in enumerate(model.bricks):
        graph.add_node(i)
        if brick.pos.y == 0:
            graph.add_edge(GROUND, i, studs=None)

    by_bottom_y: dict[int, list[int]] = {}
    by_top_y: dict[int, list[int]] = {}
    for i, brick in enumerate(model.bricks):
        by_bottom_y.setdefault(brick.pos.y, []).append(i)
        top_y = brick.pos.y + brick.part.height_plates
        by_top_y.setdefault(top_y, []).append(i)

    for y, upper_indices in by_bottom_y.items():
        lower_indices = by_top_y.get(y)
        if not lower_indices:
            continue

        lower_stud_owner: dict[tuple[int, int], list[int]] = {}
        for li in lower_indices:
            for pos in model.bricks[li].top_stud_world_positions():
                lower_stud_owner.setdefault(pos, []).append(li)

        for ui in upper_indices:
            shared_counts: dict[int, int] = {}
            for pos in model.bricks[ui].bottom_stud_world_positions():
                for li in lower_stud_owner.get(pos, ()):
                    shared_counts[li] = shared_counts.get(li, 0) + 1
            for li, count in shared_counts.items():
                graph.add_edge(li, ui, studs=count)

    if snot_children:
        _add_snot_edges(graph, model, snot_children)

    return graph
