"""Mesh conditioning + anisotropic voxelization (DESIGN.md pipeline steps 4-5).

Scope note: this is a v1. Real conditioning (orientation detection,
watertight repair via winding-number/TSDF, thin-feature thickening) is
scoped in DESIGN.md sec. 2 as its own substantial piece of work and is NOT
implemented here -- this module assumes the input mesh is already
reasonably watertight and Y-up (true of trimesh primitives and, per
DESIGN.md, typically true of TRELLIS/Tripo output), and only does the parts
needed to get a working end-to-end pipeline: uniform scale-to-target-size,
sit-on-the-ground translation, and voxelization.

Anisotropic voxelization trick: the plate lattice is anisotropic (20 LDU
pitch in X/Z, 8 LDU in Y), but general-purpose mesh voxelizers (trimesh's
included) assume an isotropic pitch. Rather than write a custom voxelizer,
we pre-warp the mesh -- divide X/Z by the stud pitch and Y by the plate
height -- so that one unit in the warped mesh's space is exactly one grid
cell, then voxelize at pitch=1.0 in that warped space. The resulting
integer voxel indices are then directly the internal (x_studs, y_plates,
z_studs) grid coordinates, no further conversion needed.
"""

from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from ..lattice import PLATE_HEIGHT_LDU, STUD_LDU
from .grid import VoxelGrid

DEFAULT_COLOR = (160, 160, 160)  # used where a mesh has no color information


def condition_mesh(mesh: trimesh.Trimesh, target_width_studs: int) -> trimesh.Trimesh:
    """Uniformly scale `mesh` so its largest horizontal (X or Z) extent
    equals `target_width_studs` studs, and translate it to sit on Y=0.
    Returns a new mesh; the input is not modified."""
    mesh = mesh.copy()
    extents = mesh.extents  # (dx, dy, dz)
    horizontal = max(extents[0], extents[2])
    if horizontal <= 0:
        raise ValueError("Mesh has zero horizontal extent; cannot scale")

    target_ldu = target_width_studs * STUD_LDU
    scale = target_ldu / horizontal
    mesh.apply_scale(scale)

    min_y = mesh.bounds[0][1]
    mesh.apply_translation([0, -min_y, 0])
    return mesh


def _ensure_vertex_colors(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Bake a texture-mapped mesh down to per-vertex colors in place, if it
    has a texture but no real vertex colors of its own.

    Real bug, not a hypothetical: trimesh's `TextureVisuals` has no
    `vertex_colors` attribute at all, so `_sample_surface_colors` below was
    silently falling back to flat DEFAULT_COLOR gray for any texture-mapped
    mesh -- confirmed directly on a real glTF sample (Khronos's "Duck"): a
    visibly yellow-and-orange rubber duck came out uniformly
    Light_Bluish_Gray after quantization, because `voxelize_mesh` never
    read the texture at all. `trimesh`'s own `.to_color()` samples the
    texture at each vertex's UV coordinate and returns a real
    `ColorVisuals`, which is exactly what `_sample_surface_colors` already
    knows how to use -- no other change needed once this runs first."""
    if isinstance(mesh.visual, trimesh.visual.texture.TextureVisuals):
        mesh.visual = mesh.visual.to_color()
    return mesh


def _sample_surface_colors(mesh: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    """Return an (N, 3) uint8 RGB array: the color of the mesh surface
    nearest each of `points`. Falls back to DEFAULT_COLOR if the mesh has
    no per-vertex color information.

    Nearest-FACE-CENTROID (via a plain `scipy.spatial.cKDTree`), not
    trimesh's own exact-nearest-surface-point `ProximityQuery.on_surface`
    -- swapped after a real crash, not a hypothetical one. `on_surface`'s
    `nearby_faces` sizes each point's candidate-triangle search box off the
    distance to the mesh's nearest *vertex*, which is a bad proxy the
    moment a point is deep in a solid interior: `voxelize_mesh` below fills
    the *entire* solid volume, and a point near the center of a plump,
    roughly-convex shape (a real job: a pear) can be almost as far from
    every mesh vertex as the object's own radius, so its search box sweeps
    up a large fraction of *all* triangles -- reproduced directly on that
    job's mesh (495,997 faces): a single `on_surface` call over its
    ~50k solid-fill occupied cells tried to materialize a (435,432,643, 3,
    3) candidate array (29 GiB) and crashed the job. Not a triangle-density
    problem -- `subdivide_to_size` on the same mesh added only 78 faces
    (nearly all edges were already short), so denser tessellation wouldn't
    have helped; the distance itself is the real geometric issue for deep
    interior points, regardless of local mesh resolution.

    A KDTree over face centroids has no such failure mode (every query is
    a bounded O(log n) nearest-neighbor lookup, verified directly on the
    same failing job: ~50k points resolved in under 8 seconds) at the cost
    of being an approximation -- nearest centroid isn't always exactly the
    triangle containing the true nearest surface point -- but the caller
    was already only averaging a triangle's 3 vertex colors and rounding,
    never using exact barycentric position, so the practical color
    difference is negligible."""
    n = len(points)
    if not hasattr(mesh.visual, "vertex_colors") or mesh.visual.vertex_colors is None:
        return np.tile(np.array(DEFAULT_COLOR, dtype=np.uint8), (n, 1))

    tree = cKDTree(mesh.triangles_center)
    _, triangle_ids = tree.query(points)
    vertex_colors = np.asarray(mesh.visual.vertex_colors)[:, :3]  # drop alpha
    face_vertex_ids = mesh.faces[triangle_ids]  # (N, 3)
    # Average the 3 vertex colors of the nearest triangle -- cheap
    # approximation of proper barycentric interpolation.
    tri_colors = vertex_colors[face_vertex_ids].astype(np.float32)  # (N, 3, 3)
    return tri_colors.mean(axis=1).round().astype(np.uint8)


def voxelize_mesh(mesh: trimesh.Trimesh) -> VoxelGrid:
    """Voxelize an already-conditioned (scaled, sitting on Y=0) mesh into
    the internal plate lattice, solid-filled, with per-voxel surface color
    sampled from the nearest point on the mesh."""
    mesh = _ensure_vertex_colors(mesh)
    warp = np.diag([1.0 / STUD_LDU, 1.0 / PLATE_HEIGHT_LDU, 1.0 / STUD_LDU, 1.0])
    warped = mesh.copy()
    warped.apply_transform(warp)

    voxel = warped.voxelized(pitch=1.0).fill()
    matrix = np.asarray(voxel.matrix, dtype=bool)

    occupied_idx = np.argwhere(matrix)
    if len(occupied_idx) == 0:
        raise ValueError("Voxelization produced an empty grid -- mesh may not be watertight")
    origin = occupied_idx.min(axis=0)
    maxima = occupied_idx.max(axis=0)
    shape = tuple((maxima - origin + 1).tolist())

    grid = VoxelGrid.empty(*shape)
    shifted_idx = occupied_idx - origin
    grid.occupied[shifted_idx[:, 0], shifted_idx[:, 1], shifted_idx[:, 2]] = True

    # Sample color at each occupied cell's nearest point on the ORIGINAL
    # (unwarped) mesh, using the cell's center converted back to mesh space.
    cell_centers_warped = voxel.indices_to_points(occupied_idx)
    cell_centers_mesh = cell_centers_warped * np.array([STUD_LDU, PLATE_HEIGHT_LDU, STUD_LDU])
    colors = _sample_surface_colors(mesh, cell_centers_mesh)
    grid.color[shifted_idx[:, 0], shifted_idx[:, 1], shifted_idx[:, 2]] = colors

    return grid
