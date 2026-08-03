"""Legalization: turn a colored occupancy grid into a Model of catalog parts
(DESIGN.md pipeline step 8).

v1.2 scope, stated plainly. DESIGN.md sec. 4.2 describes split-and-remerge
simulated annealing (Testuz et al. 2013) with a weighted objective
(part count, price, seam alignment, connectivity, rarity). This
implementation does a scoped-down version of three of those terms:

  Stage A -- per (Y layer, color) region: greedy tiling using only plates,
  scanning cells in a given order, picking at each anchor cell the fitting
  candidate that maximizes `area - seam_penalty` rather than plain area --
  the seam penalty fires when a candidate would exactly reproduce (same
  position AND size) a tile already placed in the layer directly below,
  which is what produces a continuous vertical crack. This runs several
  times per layer with different cell-visiting orders (a scoped-down stand-
  in for Testuz's random-region shatter-and-retile, operating on a whole
  layer at a time rather than an arbitrary region), keeping whichever
  attempt scores best -- see _tile_layer_region_best_of for exactly what
  "best" means and why it changed partway through this project.

  Connectivity-aware ordering: added after `structure/` (Phase 2) and a
  user's own inspection of a real legalized model exposed a real bug --
  greedy tiling, with zero awareness of what's underneath, can carve a
  layer up so that a wide, well-supported tile "steals" the cells a
  neighboring region needed to stay connected to the layer below, even
  though a different (not worse, sometimes even equally cheap) tiling of
  the exact same occupied cells would have preserved the connection. On
  the bunny test model this explained 71 of 111 (64%) of the "ungrounded"
  bricks structure/ was finding -- not a mesh-resolution limit, a tiling
  choice. Fixed with an "unsupported cells first" scan order (so a cell
  with nothing beneath it gets first claim on combining with a supported
  neighbor, before a separate greedy tile from that neighbor's side claims
  the territory first) plus an orphaned-parts count
  (_count_orphaned_parts) added to the restart-selection objective ahead
  of part count -- deliberately: the user was explicit that structural
  soundness outweighs part-count efficiency here, the same trade already
  accepted in structure/bridge.py.

  Stage B -- vertical consolidation: unchanged from v1 (see below).

  NOT implemented: price/rarity terms, true incremental region-level
  shatter-and-remerge (this only randomizes whole-layer scan order), and
  articulation-point-aware structural weighting during tiling itself
  (structure/ handles that after the fact, on the finished Model). There
  is also a real, unresolved tension between seam-staggering and Stage B's
  brick consolidation -- they want opposite things (breaking up repeated
  footprints vs. finding 3 identical ones in a row) -- which this version
  does not resolve architecturally, only by weight tuning. See
  mesh_to_model.py callers / tests for before-after measurements of that
  tradeoff, and CLAUDE.md for the connectivity-aware tiling measurement.
"""

from __future__ import annotations

import random

import numpy as np

from ..lattice import Rotation
from ..model import Model
from ..parts import Part, PartCatalog
from .grid import VoxelGrid

TilePlacement = tuple[int, int, str, Rotation, int]  # (x, z, part_id, rotation, color)
Rect = tuple[int, int, int, int]  # (x, z, w, d)

SEAM_CANDIDATE_PENALTY_WEIGHT = 0.9  # per-candidate: penalty = weight * area, if exact duplicate below
DEFAULT_RESTARTS = 5


def _candidate_footprints(catalog: PartCatalog, category: str) -> list[tuple[Part, Rotation]]:
    """All (part, rotation) pairs of the given category, largest area first.
    Non-square parts get both orientations; square parts only YAW_0."""
    candidates: list[tuple[Part, Rotation]] = []
    for part in catalog:
        if part.category != category:
            continue
        w, d = part.footprint
        candidates.append((part, Rotation.YAW_0))
        if w != d:
            candidates.append((part, Rotation.YAW_90))

    def area(pair: tuple[Part, Rotation]) -> int:
        w, d = pair[0].footprint_at(pair[1])
        return w * d

    candidates.sort(key=area, reverse=True)
    return candidates


def _build_plate_to_brick_map(catalog: PartCatalog) -> dict[str, str]:
    plates = {p.footprint: p for p in catalog if p.category == "plate"}
    bricks = {p.footprint: p for p in catalog if p.category == "brick"}
    return {plates[fp].id: bricks[fp].id for fp in plates if fp in bricks}


def _build_below_grid(nx: int, nz: int, rects: list[Rect]) -> tuple[np.ndarray, dict[int, Rect]]:
    """A per-cell id grid (-1 = nothing) and id -> rect lookup, used to
    detect when a candidate in the current layer would exactly reproduce a
    tile's footprint from the layer below."""
    id_grid = np.full((nx, nz), -1, dtype=np.int32)
    bounds: dict[int, Rect] = {}
    for i, (x, z, w, d) in enumerate(rects):
        id_grid[x : x + w, z : z + d] = i
        bounds[i] = (x, z, w, d)
    return id_grid, bounds


def _is_exact_duplicate_below(
    x: int, z: int, w: int, d: int, below_id_grid: np.ndarray, below_rect_bounds: dict[int, Rect]
) -> bool:
    region = below_id_grid[x : x + w, z : z + d]
    first = region[0, 0]
    if first == -1 or not np.all(region == first):
        return False
    return below_rect_bounds[first] == (x, z, w, d)


def _tile_layer_region(
    mask: np.ndarray,
    candidates: list[tuple[Part, Rotation]],
    below_id_grid: np.ndarray | None,
    below_rect_bounds: dict[int, Rect],
    cell_order: list[tuple[int, int]],
) -> list[tuple[int, int, Part, Rotation]]:
    """Greedy tiling of a single 2D boolean mask (already restricted to one
    color), visiting cells in `cell_order`. At each anchor cell, picks the
    fitting candidate maximizing area minus the seam-duplicate penalty."""
    nx, nz = mask.shape
    claimed = np.zeros_like(mask)
    placements: list[tuple[int, int, Part, Rotation]] = []

    for x, z in cell_order:
        if not mask[x, z] or claimed[x, z]:
            continue
        best: tuple[Part, Rotation, int, int] | None = None
        best_score = None
        for part, rot in candidates:
            w, d = part.footprint_at(rot)
            if x + w > nx or z + d > nz:
                continue
            region_mask = mask[x : x + w, z : z + d]
            region_claimed = claimed[x : x + w, z : z + d]
            if not (region_mask.all() and not region_claimed.any()):
                continue

            area = w * d
            penalty = 0.0
            if below_id_grid is not None and _is_exact_duplicate_below(x, z, w, d, below_id_grid, below_rect_bounds):
                penalty = SEAM_CANDIDATE_PENALTY_WEIGHT * area
            score = area - penalty

            if best_score is None or score > best_score:
                best_score = score
                best = (part, rot, w, d)

        if best is None:
            raise AssertionError(f"No catalog footprint (not even 1x1) fit at cell ({x},{z})")
        part, rot, w, d = best
        claimed[x : x + w, z : z + d] = True
        placements.append((x, z, part, rot))
    return placements


def _count_seam_violations(
    placements: list[tuple[int, int, Part, Rotation]],
    below_id_grid: np.ndarray | None,
    below_rect_bounds: dict[int, Rect],
) -> int:
    if below_id_grid is None:
        return 0
    count = 0
    for x, z, part, rot in placements:
        w, d = part.footprint_at(rot)
        if _is_exact_duplicate_below(x, z, w, d, below_id_grid, below_rect_bounds):
            count += 1
    return count


def _count_orphaned_parts(
    placements: list[tuple[int, int, Part, Rotation]],
    below_id_grid: np.ndarray | None,
) -> int:
    """How many placements in this layer have ZERO overlap with anything in
    the layer below -- a real, direct proxy for "will this specific tile
    choice leave part of the model ungrounded", not the aggregate
    connectivity check structure/weakpoints.py does after the fact. See
    module docstring: found empirically (structure/ package + user
    inspection of a real model) that greedy tiling can genuinely fragment
    a region so that a wide, well-supported tile "steals" cells a
    neighboring region needed to stay connected -- this metric is what lets
    the tiler notice that happened."""
    if below_id_grid is None:
        return 0
    count = 0
    for x, z, part, rot in placements:
        w, d = part.footprint_at(rot)
        if not (below_id_grid[x : x + w, z : z + d] != -1).any():
            count += 1
    return count


def _unsupported_first_order(true_cells: list[tuple[int, int]], below_id_grid: np.ndarray | None) -> list[tuple[int, int]]:
    """Cells with nothing beneath them, first (raster order preserved
    within each group). Processing these first gives them the chance to
    combine with an adjacent, supported cell into one connectivity-
    preserving tile before a separate, wide, greedy tile from the
    supported side claims that territory first and strands them -- see
    module docstring for the concrete case this fixes."""
    if below_id_grid is None:
        return true_cells
    return sorted(true_cells, key=lambda cell: below_id_grid[cell[0], cell[1]] != -1)


def _tile_layer_region_best_of(
    mask: np.ndarray,
    candidates: list[tuple[Part, Rotation]],
    below_id_grid: np.ndarray | None,
    below_rect_bounds: dict[int, Rect],
    rng: random.Random,
    restarts: int,
) -> list[tuple[int, int, Part, Rotation]]:
    """Try the plain deterministic raster-order tiling, the deterministic
    "unsupported cells first" order, then however many random-order
    attempts `restarts` leaves room for, keeping whichever attempt scores
    best on (orphaned_parts, part_count, seam_violations) -- compared
    lexicographically (plain tuple comparison), orphaned_parts first.

    This is a deliberate change from the strict "never cost more parts"
    Pareto rule used for seam violations (see _count_seam_violations'
    history above): here, more parts is an acceptable price for fewer
    orphaned parts, on the user's explicit direction that structural
    soundness outweighs part-count efficiency. That is a different risk
    profile than the seam-violation case, which is why it isn't just
    reusing the same gate: fragmenting into many 1x1s cannot cheaply fake a
    lower orphaned count the way it could fake a lower violation count --
    a genuinely unsupported cell is still unsupported as its own 1x1, it
    doesn't stop being orphaned by being separated from its neighbors."""
    true_cells = list(zip(*np.where(mask)))  # already raster order (row-major)

    orders = [true_cells, _unsupported_first_order(true_cells, below_id_grid)]
    for _ in range(max(0, restarts - len(orders))):
        shuffled = true_cells[:]
        rng.shuffle(shuffled)
        orders.append(shuffled)

    best_placements: list[tuple[int, int, Part, Rotation]] | None = None
    best_metrics: tuple[int, int, int] | None = None
    for order in orders:
        placements = _tile_layer_region(mask, candidates, below_id_grid, below_rect_bounds, order)
        metrics = (
            _count_orphaned_parts(placements, below_id_grid),
            len(placements),
            _count_seam_violations(placements, below_id_grid, below_rect_bounds),
        )
        if best_metrics is None or metrics < best_metrics:
            best_placements = placements
            best_metrics = metrics

    assert best_placements is not None
    return best_placements


def legalize(
    grid: VoxelGrid,
    color_codes: np.ndarray,
    catalog: PartCatalog,
    seed: int = 0,
    restarts: int = DEFAULT_RESTARTS,
) -> Model:
    """Tile a shelled, color-quantized VoxelGrid into a Model of catalog
    parts. `color_codes` is an (nx, ny, nz) int array of LDraw color codes
    (as returned by color.quantize_grid_colors), -1 where unoccupied.
    `seed` makes the randomized-restart search reproducible."""
    rng = random.Random(seed)
    model = Model(catalog=catalog)
    plate_candidates = _candidate_footprints(catalog, "plate")
    plate_to_brick = _build_plate_to_brick_map(catalog)

    nx, ny, nz = grid.shape
    layer_placements: list[list[TilePlacement]] = []
    prev_layer_rects: list[Rect] = []

    for y in range(ny):
        layer_occ = grid.occupied[:, y, :]
        layer_color = color_codes[:, y, :]
        below_id_grid, below_rect_bounds = _build_below_grid(nx, nz, prev_layer_rects)

        this_layer: list[TilePlacement] = []
        this_layer_rects: list[Rect] = []
        if layer_occ.any():
            for color_code in np.unique(layer_color[layer_occ]):
                mask = layer_occ & (layer_color == color_code)
                placements = _tile_layer_region_best_of(
                    mask, plate_candidates, below_id_grid, below_rect_bounds, rng, restarts
                )
                for x, z, part, rot in placements:
                    this_layer.append((x, z, part.id, rot, int(color_code)))
                    w, d = part.footprint_at(rot)
                    this_layer_rects.append((x, z, w, d))
        layer_placements.append(this_layer)
        prev_layer_rects = this_layer_rects

    # Stage B: consolidate runs of 3 identical placements into a brick.
    consumed: list[set[int]] = [set() for _ in range(ny)]
    index_by_key: list[dict[TilePlacement, int]] = [
        {p: i for i, p in enumerate(layer_placements[y])} for y in range(ny)
    ]

    for y in range(ny):
        for i, placement in enumerate(layer_placements[y]):
            if i in consumed[y] or y + 2 >= ny:
                continue
            j1 = index_by_key[y + 1].get(placement)
            j2 = index_by_key[y + 2].get(placement)
            if j1 is None or j2 is None or j1 in consumed[y + 1] or j2 in consumed[y + 2]:
                continue
            x, z, plate_id, rot, color = placement
            brick_id = plate_to_brick.get(plate_id)
            if brick_id is None:
                continue
            model.place(brick_id, color, x, y, z, rotation=rot)
            consumed[y].add(i)
            consumed[y + 1].add(j1)
            consumed[y + 2].add(j2)

    for y in range(ny):
        for i, (x, z, plate_id, rot, color) in enumerate(layer_placements[y]):
            if i in consumed[y]:
                continue
            model.place(plate_id, color, x, y, z, rotation=rot)

    return model
