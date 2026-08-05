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

# Exactly pipeline/color.py::CATALOG_RGB's Black entry -- using the precise
# catalog RGB (not an approximate "black-ish" value) guarantees
# quantize_grid_colors resolves this to LDraw code 0 with zero distance,
# never a near-miss. Black is always in bulk/cheap supply and, since this
# structure sits entirely hidden inside the shell, there's no reason to
# spend a rarer color on it just because it happens to match the model's
# own surface color.
WIREFRAME_RGB: tuple[int, int, int] = (27, 42, 52)


def add_wireframe_support(
    grid: VoxelGrid,
    solid_grid: VoxelGrid,
    cross_thickness: int = 2,
) -> VoxelGrid:
    """Return a copy of `grid` (already shelled/hollowed) with a central
    support wireframe added: two full vertical planes through the model's
    horizontal center -- one at fixed X spanning all Y and Z, one at fixed
    Z spanning all Y and X -- restricted to cells where the *original*
    solid silhouette (`solid_grid`, voxelize_mesh's pre-shell output)
    actually has material. Together they form a "+"-shaped cross-section
    repeated at every height, mimicking how real large-scale LEGO
    sculptures are built: a hidden internal skeleton the outer shell is
    anchored to, not a solid-filled interior or a repair-only patch.

    **Full planes, not a thin spine-plus-arms-plus-beams design (an
    earlier version of this function) -- and the reason isn't
    stylistic.** In this catalog's connectivity model (see
    structure/bridge.py's own docstring), only a *vertical* stud/anti-stud
    overlap between two parts at adjacent Y layers ever creates a real
    structural edge; two parts merely touching side-by-side at the same
    layer are structurally inert, no matter how tightly packed they look.
    A thin single-layer horizontal beam reaching sideways to touch the
    shell therefore never actually connects to it -- confirmed directly:
    the previous version relied on `bridge_unstable` silently patching in
    hundreds of extra pillars after the fact to hold the beams and arms
    together, which is exactly the "different segments held together by
    repair, not real design" the user caught in Studio.

    A full plane sidesteps the problem instead of fighting it: every cell
    in the plane has a real neighbor directly above or below it *within
    the same plane* (guaranteeing the whole plane is one connected
    structure by construction), and at the top and bottom of *any* given
    column's own local solid run, that column's topmost/bottommost cell
    is reliably shell (thin/exposed-to-open-air cells fail the erosion
    test that defines "interior"), so the plane's own interior cells are
    Y-adjacent to genuine, pre-existing shell material there -- a real
    weld, not a coincidence of proximity. The two planes share the
    central column by construction, so the whole cross -- and everywhere
    it touches the shell -- is provably one connected piece before
    structural repair ever runs, not after.

    Every cell added is checked against `solid_grid.occupied` first, so
    the wireframe can never poke through the model's own surface into
    open air -- the same interior-only guarantee structure/bridge.py's
    repair pillars already rely on, and for the same reason. Cells the
    shell already kept are left untouched; this only ever *adds* material
    to what would otherwise be hollow interior.

    `cross_thickness` (default 2) matches the spine width of the earlier
    version -- a 2-cell-wide plane still consolidates into real
    `brick`-category parts via legalize.py's Stage B (identical footprint
    at every layer, exactly what Stage B looks for), same as before.

    Meant to run *before* structural repair (bridge_unstable), not replace
    it: a real, then-current bug motivated a proactive central structure
    in the first place, not a hypothetical -- with a fully hollow interior
    (no periodic internal bracing at all) and nothing put in its place, a
    real model's entire stem turned out to have no path to ground and was
    pruned outright, an entire pointed feature deleted rather than left
    standing. It doesn't have to be a 100% guarantee on its own, since the
    existing repair pass is still there as a backstop for whatever it
    doesn't reach."""
    nx, ny, nz = solid_grid.shape
    occupied_xz = solid_grid.occupied.any(axis=1)  # (nx, nz): does this column have any material at all?
    xs, zs = np.where(occupied_xz)
    if len(xs) == 0:
        return grid

    center_x = int(round((int(xs.min()) + int(xs.max())) / 2))
    center_z = int(round((int(zs.min()) + int(zs.max())) / 2))

    cross_xz = np.zeros((nx, nz), dtype=bool)
    for dx in range(cross_thickness):
        x = center_x + dx
        if 0 <= x < nx:
            cross_xz[x, :] = True
    for dz in range(cross_thickness):
        z = center_z + dz
        if 0 <= z < nz:
            cross_xz[:, z] = True

    wireframe_mask = solid_grid.occupied & cross_xz[:, None, :]
    new_cells = wireframe_mask & ~grid.occupied

    result_occupied = grid.occupied | new_cells
    result_color = grid.color.copy()
    result_color[new_cells] = WIREFRAME_RGB
    return VoxelGrid(occupied=result_occupied, color=result_color)


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
