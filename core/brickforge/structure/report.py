"""Ties the connectivity graph, weak-point detection, and load propagation
together into one report, plus a human-readable summary."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Model
from .graph import GROUND, build_connectivity_graph
from .load import LoadResult, propagate_gravity_load
from .weakpoints import (
    find_articulation_points,
    find_bricks_outside_main_component,
    find_bridges,
    find_disconnected_components,
    find_ungrounded_bricks,
)


@dataclass
class StabilityReport:
    model: Model
    components: list[set]
    outside_main_component: set[int]  # undirected connectivity -- what critical_bricks actually uses
    ungrounded_bricks: set[int]  # informational only -- see weakpoints.py module docstring; NOT what critical_bricks uses
    articulation_points: set[int]
    bridges: list[tuple]
    load: LoadResult

    @property
    def is_single_piece(self) -> bool:
        return len(self.components) == 1

    @property
    def critical_bricks(self) -> set[int]:
        """Bricks with no plausible way to be structurally sound: not part
        of the model's main connected mass at all (see
        weakpoints.find_bricks_outside_main_component -- undirected
        connectivity, not the stricter directed find_ungrounded_bricks;
        see that module's docstring for why the stricter check turned out
        to be the wrong one to act on), or sitting on an overloaded
        connection."""
        critical = set(self.outside_main_component)
        for lower, upper, _, _ in self.load.overloaded_edges:
            critical.add(lower)
            critical.add(upper)
        return critical

    @property
    def warning_bricks(self) -> set[int]:
        """Bricks that aren't currently overloaded but are a single point
        of failure (articulation point) or sit on a bridge edge."""
        warning = set(self.articulation_points)
        for a, b in self.bridges:
            if a != GROUND:
                warning.add(a)
            if b != GROUND:
                warning.add(b)
        return warning - self.critical_bricks


def analyze(model: Model) -> StabilityReport:
    graph = build_connectivity_graph(model)
    return StabilityReport(
        model=model,
        components=find_disconnected_components(graph),
        outside_main_component=find_bricks_outside_main_component(graph),
        ungrounded_bricks=find_ungrounded_bricks(graph, model),
        articulation_points=find_articulation_points(graph),
        bridges=find_bridges(graph),
        load=propagate_gravity_load(graph, model),
    )


def summarize(report: StabilityReport) -> str:
    lines = [f"Stability report: {len(report.model)} parts"]

    if not report.is_single_piece:
        piece_sizes = sorted((len(c) for c in report.components), reverse=True)
        lines.append(f"  CRITICAL: model is in {len(report.components)} disconnected pieces (sizes: {piece_sizes})")
    else:
        lines.append("  OK: model is a single connected piece")

    if report.load.overloaded_edges:
        lines.append(f"  CRITICAL: {len(report.load.overloaded_edges)} connection(s) over the illustrative capacity threshold")

    n_warn = len(report.warning_bricks)
    if n_warn:
        lines.append(f"  WARNING: {n_warn} brick(s) are single points of failure (articulation points / bridges)")

    if report.ungrounded_bricks:
        lines.append(
            f"  INFO: {len(report.ungrounded_bricks)} brick(s) lack a private straight-down stud chain to ground "
            "but may still be part of the main connected mass (not used to drive repair -- see weakpoints.py)"
        )

    n_crit = len(report.critical_bricks)
    if n_crit == 0 and n_warn == 0 and report.is_single_piece:
        lines.append("  No issues found by this (simplified) analysis.")

    return "\n".join(lines)
