"""Connectivity graph: nodes are placed bricks (by index into
model.bricks), edges are stud/anti-stud connections between a brick and the
one directly above it, weighted by how many studs they share. A virtual
`GROUND` node is connected to every brick sitting at y=0, standing in for
external support (a table, a base plate) -- this makes "is this brick's
subtree still attached to the ground" the right question for articulation
points and bridges to answer, not just "is the graph still connected to
something."
"""

from __future__ import annotations

import networkx as nx

from ..model import Model

GROUND = "GROUND"


def build_connectivity_graph(model: Model) -> nx.Graph:
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

    return graph
