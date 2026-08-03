"""Model: an in-memory collection of placed bricks on the internal Y-up
lattice grid, with collision-checked placement. This is the API example
scripts (and, later, the legalizer) build against; ldr_writer.py turns a
Model into LDR text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .lattice import GridPos, Rotation
from .parts import Part, PartCatalog


class PlacementError(ValueError):
    """Raised when a placement is invalid: unknown part/colour or a collision
    with an already-placed brick."""


@dataclass(frozen=True)
class Brick:
    part: Part
    color: int
    pos: GridPos
    rotation: Rotation = Rotation.YAW_0

    @property
    def footprint(self) -> tuple[int, int]:
        return self.part.footprint_at(self.rotation)

    def occupied_cells(self) -> Iterator[tuple[int, int, int]]:
        """Every internal-grid (x, y, z) cell this brick's bounding box
        covers: x/z in studs, y in plates."""
        w, d = self.footprint
        for dx in range(w):
            for dy in range(self.part.height_plates):
                for dz in range(d):
                    yield (self.pos.x + dx, self.pos.y + dy, self.pos.z + dz)

    def top_stud_world_positions(self) -> list[tuple[int, int]]:
        """World (x, z) stud-grid coordinates of this brick's top studs,
        at the layer immediately above the brick (pos.y + height_plates)."""
        return [(self.pos.x + lx, self.pos.z + lz) for (lx, lz) in self.part.top_studs(self.rotation)]

    def bottom_stud_world_positions(self) -> list[tuple[int, int]]:
        """World (x, z) stud-grid coordinates of this brick's bottom
        anti-studs/tubes, at the brick's own base layer (pos.y)."""
        return [(self.pos.x + lx, self.pos.z + lz) for (lx, lz) in self.part.bottom_studs(self.rotation)]


@dataclass
class Model:
    catalog: PartCatalog
    bricks: list[Brick] = field(default_factory=list)
    _occupied: dict[tuple[int, int, int], int] = field(default_factory=dict, repr=False)

    def place(
        self,
        part_id: str,
        color: int,
        x: int,
        y: int,
        z: int,
        rotation: Rotation = Rotation.YAW_0,
    ) -> Brick:
        """Place a part with its footprint's bottom-front-left corner at
        grid cell (x, y, z). Raises PlacementError on an unknown part/colour
        or if the placement collides with an existing brick."""
        if part_id not in self.catalog:
            raise PlacementError(f"Unknown part id {part_id!r}")
        if not self.catalog.has_color(color):
            raise PlacementError(f"Unknown LDraw color code {color!r}")

        part = self.catalog.get(part_id)
        brick = Brick(part=part, color=color, pos=GridPos(x, y, z), rotation=rotation)

        cells = list(brick.occupied_cells())
        collisions = [c for c in cells if c in self._occupied]
        if collisions:
            other = self.bricks[self._occupied[collisions[0]]]
            raise PlacementError(
                f"Placement of {part.name} ({part_id}) at {(x, y, z)} collides with "
                f"{other.part.name} ({other.part.id}) at "
                f"{(other.pos.x, other.pos.y, other.pos.z)}, cell {collisions[0]}"
            )

        index = len(self.bricks)
        self.bricks.append(brick)
        for c in cells:
            self._occupied[c] = index
        return brick

    def __len__(self) -> int:
        return len(self.bricks)

    def __iter__(self) -> Iterator[Brick]:
        return iter(self.bricks)
