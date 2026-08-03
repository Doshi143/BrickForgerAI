"""Stability heatmap: DESIGN.md sec. 5 wants this shipped as a visible
feature ("a heatmap and screenshot-able differentiator"). Rather than build
new visualization code, this reuses the existing LDR/viewer/Studio pipeline
entirely -- it produces a *second* Model with identical geometry to the
original but with each brick's color overridden by its risk classification
(green/yellow/red), so `save_ldr` + the three.js viewer + Studio all work
on it unmodified.
"""

from __future__ import annotations

from ..model import Model
from .report import StabilityReport

COLOR_OK = 2  # Green
COLOR_WARNING = 14  # Yellow
COLOR_CRITICAL = 4  # Red


def classify_bricks(report: StabilityReport) -> dict[int, int]:
    """Brick index -> LDraw color code for the heatmap render."""
    critical = report.critical_bricks
    warning = report.warning_bricks
    colors: dict[int, int] = {}
    for i in range(len(report.model.bricks)):
        if i in critical:
            colors[i] = COLOR_CRITICAL
        elif i in warning:
            colors[i] = COLOR_WARNING
        else:
            colors[i] = COLOR_OK
    return colors


def build_heatmap_model(report: StabilityReport) -> Model:
    """A copy of report.model with every brick recolored by risk level.
    Geometry (part, position, rotation) is untouched."""
    colors = classify_bricks(report)
    heatmap = Model(catalog=report.model.catalog)
    for i, brick in enumerate(report.model.bricks):
        heatmap.place(brick.part.id, colors[i], brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
    return heatmap
