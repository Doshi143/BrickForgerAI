"""Shelling + internal support lattice (DESIGN.md pipeline step 6).

A solid model is enormous in part count (DESIGN.md sec. 3: "a solid 30 cm
sculpture is ~40,000 parts"), so we erode the solid interior away and
replace it with a thin outer shell plus a periodic grid of full-height
internal support walls. The shell and the support walls must share cells
where they meet -- generating them from the same erosion result rather than
independently guarantees that.

v1 simplification: erosion uses scipy's default 6-connected structuring
element in *grid-index* space (not physical LDU space), so `shell_thickness`
cells means shell_thickness studs horizontally but shell_thickness plates
vertically -- anisotropic in the same direction as the lattice itself,
which is a reasonable approximation but not a tuned physical thickness.
Support wall spacing is a plain periodic grid (every `support_pitch`
cells), not the topology-optimized truss DESIGN.md gestures at as a
possible future refinement -- deliberately: grid walls are simple, tile
into long bricks cheaply, and give the Phase 2 structural solver something
concrete to work with.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .grid import VoxelGrid


def shell_and_support(
    grid: VoxelGrid,
    shell_thickness: int = 2,
    support_pitch: int = 5,
) -> VoxelGrid:
    solid = grid.occupied
    eroded = ndimage.binary_erosion(solid, iterations=shell_thickness)
    shell = solid & ~eroded

    nx, ny, nz = solid.shape
    xs = np.arange(nx).reshape(nx, 1, 1)
    zs = np.arange(nz).reshape(1, 1, nz)
    support_mask = (xs % support_pitch == 0) | (zs % support_pitch == 0)
    support = eroded & np.broadcast_to(support_mask, solid.shape)

    kept = shell | support

    result = VoxelGrid.empty(nx, ny, nz)
    result.occupied = kept
    result.color = grid.color.copy()
    result.color[~kept] = 0
    return result
