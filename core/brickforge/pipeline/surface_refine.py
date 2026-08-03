"""Surface refinement (DESIGN.md pipeline step: "surface refinement runs
after box tiling and loops back into structural analysis"). This module is
the tile half of that; slope substitution is separate (see
pipeline/slopes.py once it exists).

Tile substitution: replace a load-free, top-exposed plate with the tile of
the same footprint -- removes the "pixelated staircase with visible studs"
look DESIGN.md sec. 4.4 calls out, at zero structural cost. Unlike slopes,
this genuinely never needs the "loop back into structural analysis" DESIGN.md
warns about: a tile keeps the exact same footprint, position, and bottom
connector coverage as the plate it replaces (bottom: full on every tile in
this catalog, same as every plate), so nothing about its own downward
connection changes. The only thing a tile substitution ever removes is TOP
stud coverage -- and this function only substitutes where nothing is
already resting there, so there is nothing to disconnect. (Still worth
verifying this empirically rather than just trusting the argument -- see
tests/test_pipeline_surface_refine.py's before/after analyze() checks.)
"""

from __future__ import annotations

from ..model import Model
from ..parts import PartCatalog


def _build_plate_to_tile_map(catalog: PartCatalog) -> dict[str, str]:
    plates = {p.footprint: p for p in catalog if p.category == "plate"}
    tiles = {p.footprint: p for p in catalog if p.category == "tile"}
    return {plates[fp].id: tiles[fp].id for fp in plates if fp in tiles}


def substitute_tiles(model: Model) -> Model:
    """Return a copy of `model` with every top-exposed plate (nothing
    resting on its top studs) swapped for the matching tile, where the
    catalog has one. Plates with no matching tile footprint, or with
    something already resting on top, are left as plates."""
    plate_to_tile = _build_plate_to_tile_map(model.catalog)
    if not plate_to_tile:
        return model

    occupied_at_y: dict[tuple[int, int, int], int] = {}
    for i, brick in enumerate(model.bricks):
        for cell in brick.occupied_cells():
            occupied_at_y[cell] = i

    refined = Model(catalog=model.catalog)
    for brick in model.bricks:
        tile_id = plate_to_tile.get(brick.part.id) if brick.part.category == "plate" else None
        if tile_id is not None:
            w, d = brick.footprint
            top_y = brick.pos.y + brick.part.height_plates
            exposed = all(
                (brick.pos.x + dx, top_y, brick.pos.z + dz) not in occupied_at_y
                for dx in range(w)
                for dz in range(d)
            )
            if exposed:
                refined.place(tile_id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)
                continue
        refined.place(brick.part.id, brick.color, brick.pos.x, brick.pos.y, brick.pos.z, rotation=brick.rotation)

    return refined
