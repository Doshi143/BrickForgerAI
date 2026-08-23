"""Surface refinement (DESIGN.md pipeline step: "surface refinement runs
after box tiling and loops back into structural analysis"). This module is
the tile half of that; slope substitution is separate (see
pipeline/slopes.py once it exists).

Tile substitution: replace a load-free, top-exposed, VISIBLE plate with the
tile of the same footprint -- removes the "pixelated staircase with visible
studs" look DESIGN.md sec. 4.4 calls out, at zero structural cost. Unlike
slopes, this genuinely never needs the "loop back into structural analysis"
DESIGN.md warns about: a tile keeps the exact same footprint, position, and
bottom connector coverage as the plate it replaces (bottom: full on every
tile in this catalog, same as every plate), so nothing about its own
downward connection changes. The only thing a tile substitution ever
removes is TOP stud coverage -- and this function only substitutes where
nothing is already resting there, so there is nothing to disconnect. (Still
worth verifying this empirically rather than just trusting the argument --
see tests/test_pipeline_surface_refine.py's before/after analyze() checks.)

**"Nothing resting on it" is not the same question as "visible."** A plate
whose top faces the model's own hollow interior (a cavity, not open air)
also has nothing resting on it -- by the plain occupancy check alone, it
looks identical to a plate on the true outward-facing shell. But DESIGN.md
is explicit that aesthetic parts belong on the outward-facing shell only,
never spent on a surface nobody can see, and a tile is exactly that: an
aesthetic swap, not a structural one. So exposure alone was too permissive
a bar for tile substitution specifically, even though it's exactly the
right bar for the connectivity argument above. `_exterior_reachable_cells`
answers the second question: a boundary-flood-fill through empty cells,
reusing the identical technique structure/refill.py::close_enclosed_voids
already uses to tell "a real gap" from "a deliberately hollow interior" --
the same distinction, just applied here to decide what's *worth
decorating* rather than what's *safe to fill*. A candidate only
substitutes when every cell above it is both unoccupied AND reachable
from outside the model's own bounding box. This can only ever make
substitution MORE conservative than the occupancy-only check alone (it's
an additional required condition, never a new permission), so it carries
no new structural risk on top of the argument above -- it just stops
spending real, purchasable tile parts on surfaces this model's own owner
will never actually see once it's built.

Measured, not assumed: on the same three real models used to measure the
legalize.py Stage B / slopes.py stacked-plate changes (mushroom, duck, a
synthetic ribbed pumpkin), this cut tile_count by 24-32% (250->191,
67->61, 367->250 respectively) with is_single_piece, critical-brick
count, slope_count, and total part_count all byte-for-byte unchanged --
exactly what the safety argument above predicts (a tile and the plate it
would have replaced occupy the identical cell either way, so nothing
about total count or connectivity can move). A real, substantial fraction
of tiles on these models were being spent on hidden interior cavity
walls before this, not the visible shell.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from ..model import Brick, Model
from ..parts import PartCatalog


def _build_plate_to_tile_map(catalog: PartCatalog) -> dict[str, str]:
    plates = {p.footprint: p for p in catalog if p.category == "plate"}
    tiles = {p.footprint: p for p in catalog if p.category == "tile"}
    return {plates[fp].id: tiles[fp].id for fp in plates if fp in tiles}


def _exterior_reachable_cells(model: Model) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Boolean grid (True = empty AND reachable from outside the model's
    own padded bounding box by a path of empty cells), plus the (x, y, z)
    offset mapping grid indices back to world coordinates. Identical
    flood-fill technique to structure/refill.py::close_enclosed_voids,
    reused rather than re-derived: both need the same "is this empty
    space part of the true exterior, or a sealed-off interior cavity"
    answer, just for different downstream decisions (safe-to-fill there,
    worth-decorating here)."""
    occupied: set[tuple[int, int, int]] = set()
    for brick in model.bricks:
        occupied.update(brick.occupied_cells())

    if not occupied:
        return np.zeros((1, 1, 1), dtype=bool), (0, 0, 0)

    xs = [c[0] for c in occupied]
    ys = [c[1] for c in occupied]
    zs = [c[2] for c in occupied]
    x_min, x_max = min(xs) - 1, max(xs) + 1
    y_min, y_max = max(min(ys) - 1, 0), max(ys) + 1  # never explore below the baseplate
    z_min, z_max = min(zs) - 1, max(zs) + 1
    shape = (x_max - x_min + 1, y_max - y_min + 1, z_max - z_min + 1)

    occupied_grid = np.zeros(shape, dtype=bool)
    for x, y, z in occupied:
        occupied_grid[x - x_min, y - y_min, z - z_min] = True
    empty_grid = ~occupied_grid

    reachable = np.zeros(shape, dtype=bool)
    start = (0, 0, 0)
    reachable[start] = True
    frontier = [start]
    while frontier:
        x, y, z = frontier.pop()
        for nx, ny, nz in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            if not (0 <= nx < shape[0] and 0 <= ny < shape[1] and 0 <= nz < shape[2]):
                continue
            if not empty_grid[nx, ny, nz] or reachable[nx, ny, nz]:
                continue
            reachable[nx, ny, nz] = True
            frontier.append((nx, ny, nz))

    return reachable, (x_min, y_min, z_min)


def _is_exterior(x: int, y: int, z: int, reachable: np.ndarray, offset: tuple[int, int, int]) -> bool:
    ox, oy, oz = offset
    gx, gy, gz = x - ox, y - oy, z - oz
    if not (0 <= gx < reachable.shape[0] and 0 <= gy < reachable.shape[1] and 0 <= gz < reachable.shape[2]):
        return True  # past the padded bounding box entirely -- open air by definition
    return bool(reachable[gx, gy, gz])


def substitute_tiles(model: Model, exclude: Callable[[Brick], bool] | None = None) -> Model:
    """Return a copy of `model` with every top-exposed plate (nothing
    resting on its top studs) swapped for the matching tile, where the
    catalog has one. Plates with no matching tile footprint, or with
    something already resting on top, are left as plates.

    `exclude`, if given, skips *substituting* any brick it returns True
    for -- but that brick still counts toward the occupancy the exposed
    check uses for every OTHER brick. This distinction is load-bearing,
    not a nicety: an earlier caller (the web backend's own
    wireframe-preserving wrapper) instead removed excluded bricks from the
    model entirely before calling this function, which made the exposed
    check blind to them -- a plain plate with an excluded brick resting
    directly on top of it looked "exposed" (nothing else there) and got
    swapped for a tile anyway, silently severing the top-stud connection
    the excluded brick actually depended on. Confirmed on a real job: a
    steampunk balloon's wireframe went from single-piece/zero-critical to
    155 critical bricks purely from that blind spot, invisible until the
    model was re-analyzed *after* tile substitution -- which nothing in
    the pipeline was doing at the time (see brickforge_bridge.py)."""
    plate_to_tile = _build_plate_to_tile_map(model.catalog)
    if not plate_to_tile:
        return model

    occupied_at_y: dict[tuple[int, int, int], int] = {}
    for i, brick in enumerate(model.bricks):
        for cell in brick.occupied_cells():
            occupied_at_y[cell] = i

    reachable, offset = _exterior_reachable_cells(model)

    refined = Model(catalog=model.catalog)
    for brick in model.bricks:
        excluded = exclude is not None and exclude(brick)
        tile_id = plate_to_tile.get(brick.part.id) if brick.part.category == "plate" and not excluded else None
        if tile_id is not None:
            w, d = brick.footprint
            top_y = brick.pos.y + brick.part.height_plates
            exposed = all(
                (brick.pos.x + dx, top_y, brick.pos.z + dz) not in occupied_at_y
                and _is_exterior(brick.pos.x + dx, top_y, brick.pos.z + dz, reachable, offset)
                for dx in range(w)
                for dz in range(d)
            )
            if exposed:
                refined.place(tile_id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
                continue
        refined.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    return refined
