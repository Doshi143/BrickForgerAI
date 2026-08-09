"""Simplified gravity-load propagation -- a stand-in for the real force
analysis DESIGN.md sec. 5 describes (a proper static-equilibrium LP/QP
solve over tension, shear, and torque per connection, with capacities
empirically calibrated "with a luggage scale and a jig").

What this actually does: estimate each brick's weight from its volume,
walk the connectivity graph top-down, and at each brick split its
cumulative load (its own weight plus everything resting on it) among its
downward connections in proportion to shared stud count. Compare the
result against a single illustrative capacity-per-stud constant.

This is a real, useful relative signal (which connections are carrying
disproportionate load) but it is NOT the real thing: it has no tension vs.
shear distinction, no torque/moment analysis (so it can't catch a
cantilever snapping under its own leverage, only a straight-down overload),
and the capacity number below is an unverified placeholder, not measured.
Treat every number this module produces as comparative, not load-bearing
engineering fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..lattice import LDU_MM, PLATE_HEIGHT_LDU, STUD_LDU
from ..model import Brick, Model
from .graph import GROUND

# Illustrative only -- see module docstring. Not sourced from any
# measurement. "Weight units" are grams-shaped (derived from a real ABS
# density and a hollow-brick fudge factor below) purely so the numbers are
# in a plausible ballpark, not because this has been validated against a
# real connection.
ILLUSTRATIVE_CAPACITY_PER_STUD = 50.0  # weight-units a single shared stud can carry
PLASTIC_DENSITY_G_PER_MM3 = 0.00105  # real ABS density; parts are treated as solid below, which overestimates mass
HOLLOW_FRACTION = 0.35  # crude correction for real bricks being hollow, not solid


def estimate_brick_weight(brick: Brick) -> float:
    w, d = brick.footprint
    volume_ldu3 = (w * STUD_LDU) * (d * STUD_LDU) * (brick.part.height_plates * PLATE_HEIGHT_LDU)
    volume_mm3 = volume_ldu3 * (LDU_MM**3)
    return volume_mm3 * PLASTIC_DENSITY_G_PER_MM3 * HOLLOW_FRACTION


@dataclass
class LoadResult:
    own_weight: dict[int, float]
    cumulative_load: dict[int, float]
    edge_load: dict[tuple[int, int], float]  # (lower_index, upper_index) -> downward force
    overloaded_edges: list[tuple[int, int, float, float]] = field(default_factory=list)  # (lower, upper, load, capacity)
    floating_bricks: list[int] = field(default_factory=list)  # y > 0 with no downward support at all


def propagate_gravity_load(
    graph: nx.Graph,
    model: Model,
    capacity_per_stud: float = ILLUSTRATIVE_CAPACITY_PER_STUD,
) -> LoadResult:
    own_weight = {i: estimate_brick_weight(b) for i, b in enumerate(model.bricks)}
    cumulative = dict(own_weight)
    edge_load: dict[tuple[int, int], float] = {}
    floating: list[int] = []

    # Top-down: a brick's total load must be known before it can be split
    # among the connections it rests on.
    order = sorted(range(len(model.bricks)), key=lambda i: -model.bricks[i].pos.y)
    for i in order:
        brick = model.bricks[i]
        if graph.has_edge(i, GROUND):
            continue  # externally supported; load terminates here

        # isinstance(n, int) excludes SNOT nodes (structure/graph.py's
        # ("snot", i) tuples) -- this simplified model has no notion yet of
        # a sideways connection bearing gravity load, so a SNOT branch is
        # treated as contributing neither load onto its parent nor support
        # back, rather than crashing on model.bricks[n] with a tuple index.
        # Real SNOT load propagation is future work (see DESIGN.md sec. 5).
        down_neighbors = [
            n
            for n in graph.neighbors(i)
            if n != GROUND and isinstance(n, int) and model.bricks[n].pos.y < brick.pos.y
        ]
        if not down_neighbors:
            floating.append(i)
            continue

        total_studs = sum(graph[i][n]["studs"] for n in down_neighbors)
        load_here = cumulative[i]
        for n in down_neighbors:
            share = graph[i][n]["studs"] / total_studs
            force = load_here * share
            edge_load[(n, i)] = edge_load.get((n, i), 0.0) + force
            cumulative[n] += force

    overloaded = []
    for (lower, upper), load in edge_load.items():
        studs = graph[lower][upper]["studs"]
        capacity = studs * capacity_per_stud
        if load > capacity:
            overloaded.append((lower, upper, load, capacity))

    return LoadResult(
        own_weight=own_weight,
        cumulative_load=cumulative,
        edge_load=edge_load,
        overloaded_edges=overloaded,
        floating_bricks=floating,
    )
