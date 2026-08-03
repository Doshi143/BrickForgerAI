"""VoxelGrid: the intermediate representation that every pipeline stage
(voxelize -> shell -> color -> legalize) reads and writes. Deliberately a
thin wrapper over two numpy arrays, not a class hierarchy -- every stage is
a pure function VoxelGrid -> VoxelGrid (or VoxelGrid -> Model for the last
one), matching the "every stage is a pure function over a serializable
artifact" rule in CLAUDE.md.

Index convention matches brickforge.lattice's internal grid exactly:
axis 0 (x) and axis 2 (z) are stud units, axis 1 (y) is plate units, y=0 is
the bottom layer. occupied[x, y, z] is True iff that cell is solid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VoxelGrid:
    occupied: np.ndarray  # bool, shape (nx, ny, nz)
    color: np.ndarray  # uint8, shape (nx, ny, nz, 3); meaningless where not occupied

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.occupied.shape

    @classmethod
    def empty(cls, nx: int, ny: int, nz: int) -> "VoxelGrid":
        return cls(
            occupied=np.zeros((nx, ny, nz), dtype=bool),
            color=np.zeros((nx, ny, nz, 3), dtype=np.uint8),
        )

    def count(self) -> int:
        return int(self.occupied.sum())
