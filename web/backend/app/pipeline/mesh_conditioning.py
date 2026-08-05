"""Mesh conditioning: strip a spurious flat "base slab" some single-image
reconstructions bake in as real geometry.

Traced directly on a real job (a small brown table): the raw TRELLIS
output's bottom ~1% of height has a full-width flat disc (its (X, Z)
footprint matches the mesh's entire bounding box), fused seamlessly onto
the actual object -- not a separate piece (checked with `mesh.split()`:
one connected component already spans the full bounding box, so this
can't be fixed by dropping a disconnected island). Just above that 1%
mark, the footprint drops to, and then stays flat at, the true object's
width the rest of the way up. That "sudden area cliff within the first
few percent of height, then a flat plateau" shape is a specific signature:
a real tapering object (a cone, a pyramid, a chair with splayed legs)
narrows *gradually* over a large fraction of its height, not within a
handful of percent. Likely cause: the reference photo's contact
shadow/supporting-surface cue under the object gets reconstructed as
literal geometry by the shape model.

Deliberately conservative: this only fires when both (1) the very bottom
is disproportionately wider than a "core" measurement further up the
mesh, AND (2) it narrows back down to near that core width within a short
height budget. A genuinely wide-based object that tapers gradually over
more of its height fails condition (2) and is left untouched -- guessing
wrong here would look much worse (silently decapitating a real design
feature) than leaving a base slab in occasionally.

**`mesh.slice_plane(..., cap=True)` silently drops per-vertex color.**
Invisible for as long as this backend's TRELLIS workflow was shape-only
(every mesh reaching this function was already flat gray, so losing color
lost nothing) -- surfaced only once the workflow gained a real texturing
stage (`Trellis2MeshTexturing`, baking real per-vertex color): a mesh with
106k+ distinct vertex colors going in came out with exactly 1 (trimesh's
default mid-gray, (102,102,102) -- the exact same flat value the
shape-only case already had a name for) coming out of the slice. trimesh's
slicer rebuilds geometry from the clip/cap operation and has no path for
carrying arbitrary per-vertex attributes across it. Fixed by remapping
color separately: each vertex of the sliced mesh copies its nearest
pre-slice vertex's color by 3D position -- exact for the retained
(unmoved) vertices, a close approximation for the new vertices the cap
introduces exactly on the cut plane.
"""

from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def _footprint_area(vertices: np.ndarray) -> float:
    if len(vertices) == 0:
        return 0.0
    return float(
        (vertices[:, 0].max() - vertices[:, 0].min()) * (vertices[:, 2].max() - vertices[:, 2].min())
    )


def _carry_vertex_colors_across_slice(original: trimesh.Trimesh, sliced: trimesh.Trimesh) -> None:
    """Mutates `sliced` in place, copying nearest-original-vertex color onto
    every vertex of `sliced` -- see module docstring for why this is needed
    at all. No-op if `original` never had real per-vertex color to begin
    with (nothing to preserve, avoid the KDTree cost)."""
    original_colors = getattr(original.visual, "vertex_colors", None)
    if original_colors is None or len(original_colors) != len(original.vertices):
        return
    original_rgb = np.asarray(original_colors)[:, :3]
    if len(np.unique(original_rgb, axis=0)) < 2:
        return  # flat/uncolored already -- nothing worth preserving

    tree = cKDTree(original.vertices)
    _, nearest_idx = tree.query(sliced.vertices)
    sliced.visual = trimesh.visual.ColorVisuals(
        mesh=sliced, vertex_colors=np.asarray(original_colors)[nearest_idx]
    )


def strip_base_slab(
    mesh: trimesh.Trimesh,
    core_height_frac: float = 0.10,
    band_frac: float = 0.001,
    area_ratio_threshold: float = 1.3,
    max_base_height_frac: float = 0.05,
    margin_frac: float = 0.003,
) -> trimesh.Trimesh:
    """Return a copy of `mesh` with a spurious flat base slab removed, or
    `mesh` unchanged if no such slab is detected. Assumes Y-up (matches
    core/brickforge's own convention and the mesh as TRELLIS returns it,
    before core/brickforge's own condition_mesh ever runs)."""
    vertices = mesh.vertices
    if len(vertices) == 0:
        return mesh

    y_min, y_max = float(vertices[:, 1].min()), float(vertices[:, 1].max())
    height = y_max - y_min
    if height <= 0:
        return mesh

    core_band = vertices[
        (vertices[:, 1] >= y_min + (core_height_frac - band_frac) * height)
        & (vertices[:, 1] <= y_min + (core_height_frac + band_frac) * height)
    ]
    core_area = _footprint_area(core_band)
    if core_area <= 0:
        return mesh

    bottom_band = vertices[vertices[:, 1] <= y_min + band_frac * height]
    bottom_area = _footprint_area(bottom_band)
    if bottom_area <= area_ratio_threshold * core_area:
        return mesh  # bottom isn't disproportionately wide -- nothing to strip

    cut_frac = None
    frac = band_frac
    while frac <= max_base_height_frac:
        y0 = y_min + frac * height
        band = vertices[(vertices[:, 1] >= y0 - band_frac * height) & (vertices[:, 1] <= y0 + band_frac * height)]
        if len(band) >= 10 and _footprint_area(band) <= area_ratio_threshold * core_area:
            cut_frac = frac
            break
        frac += band_frac * 2

    if cut_frac is None:
        # Wide at the bottom, but never narrows within the height budget --
        # could be a genuinely wide-based object tapering slowly. Don't
        # guess; leave it.
        return mesh

    cut_y = y_min + cut_frac * height + margin_frac * height
    try:
        sliced = mesh.slice_plane(plane_origin=[0, cut_y, 0], plane_normal=[0, 1, 0], cap=True)
    except Exception:
        return mesh  # fail safe to the original mesh rather than crash the job

    if sliced is None or len(sliced.vertices) == 0:
        return mesh

    _carry_vertex_colors_across_slice(mesh, sliced)
    return sliced
