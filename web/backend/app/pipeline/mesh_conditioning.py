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
"""

from __future__ import annotations

import numpy as np
import trimesh


def _footprint_area(vertices: np.ndarray) -> float:
    if len(vertices) == 0:
        return 0.0
    return float(
        (vertices[:, 0].max() - vertices[:, 0].min()) * (vertices[:, 2].max() - vertices[:, 2].min())
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

    return sliced
