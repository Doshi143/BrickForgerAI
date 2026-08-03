"""Quality metrics for a legalized Model, used to measure the effect of
legalizer changes rather than just eyeballing renders. Not part of the
generation pipeline itself.
"""

from __future__ import annotations

from collections import defaultdict

from ..model import Model


def count_seam_violations(model: Model) -> int:
    """Count parts whose entire footprint (position AND shape) exactly
    matches a part directly beneath them -- a full-width, unbroken vertical
    seam across that whole boundary, the worst case DESIGN.md sec. 4
    calls out. This is a coarse proxy (only catches *exact* full-footprint
    duplication, not partial edge alignment) but is enough to compare
    "before" and "after" for a legalizer change."""
    footprint_cells_by_bottom: dict[tuple[int, frozenset], list] = defaultdict(list)
    footprint_cells_by_top: dict[tuple[int, frozenset], list] = defaultdict(list)

    for brick in model:
        w, d = brick.footprint
        cells = frozenset((brick.pos.x + dx, brick.pos.z + dz) for dx in range(w) for dz in range(d))
        y_top = brick.pos.y + brick.part.height_plates
        footprint_cells_by_bottom[(brick.pos.y, cells)].append(brick)
        footprint_cells_by_top[(y_top, cells)].append(brick)

    violations = 0
    for key, upper_bricks in footprint_cells_by_bottom.items():
        if footprint_cells_by_top.get(key):
            violations += len(upper_bricks)
    return violations
