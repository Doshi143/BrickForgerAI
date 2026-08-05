"""Paint per-vertex colors onto an untextured mesh by projecting the
reference image onto it.

**Why this exists at all** -- measured, not assumed: the TRELLIS workflow
this backend ships (`app/clients/trellis_workflow_api.json`) is
**shape-only**. Its node chain is ImageCond -> Sparse -> Shape ->
ShapeCascade -> DecodeLatents -> Simplify -> FillHoles -> Simplify ->
MeshWithVoxelToTrimesh -> ExportMesh: there is no texture/appearance
generation node anywhere in it. Confirmed against a real prior job output
in the original backend zip (`jobs/8305f2d9.../model.glb`): every one of
its 231,917 vertices is the exact same gray, RGB (102, 102, 102), even
though its own reference image is an obviously brown wooden table.

So `brickforge`'s color quantization was never getting anything to work
with -- it faithfully quantized "uniform gray" to a single LDraw color for
the whole model. That is not a bug in the quantizer; the color simply was
not in its input. This module supplies it.

**What this is and isn't.** This is an orthographic front projection: each
vertex's (X, Y) position in the mesh's own bounding box maps to a (u, v)
pixel in the reference image, and that pixel's color becomes the vertex's
color. That is a genuine approximation with real, known limitations:

- The reference images this backend generates are three-quarter views (see
  `clients/image_gen.py`'s prompt template), not orthographic front
  elevations, so the mapping is skewed rather than exact.
- The (X, Y) mapping used to apply to *every* vertex regardless of which
  way it faces -- a back-facing vertex got whatever pixel happened to sit
  at that (X, Y) in the FRONT photo, which is only correct by coincidence
  (e.g. a car's trunk could pick up its windshield's color, since both can
  land at a similar (X, Y) from the front). That is not really "mirrored"
  colors, which would at least be a *consistent* wrong answer -- it's an
  arbitrary lookup. Fixed below using vertex normals: only vertices whose
  surface faces toward the camera trust the projected pixel.

  Untrusted vertices do NOT get one flat fallback color -- tried that
  first, and it broke something real: on the actual cactus test job, top
  (cactus tip, should read green) and bottom (terracotta pot, should read
  orange) came out as the *same* muddy brown, because ~70% of vertices
  were untrusted and every single one collapsed to one global average,
  swamping the real green/orange variation that only the ~30% confident
  set carried. Fixed properly with nearest-confident-neighbor propagation
  (`scipy.spatial.cKDTree`): each untrusted vertex copies the color of
  whichever *trusted* vertex is nearest to it in 3D space, so the cactus
  tip still reads green and the pot still reads orange even though neither
  region is 100% camera-facing -- see test_reference_color.py, which pins
  exactly this (top-region and bottom-region means must differ) as a real
  regression test, not just a manual check during development.

It is nonetheless a large, real improvement over uniform gray for this
pipeline's actual purpose, because the whole model is quantized down to a
curated LDraw palette immediately afterward: getting a brown table brown and
a red car red is what matters here, and small per-face projection error
mostly disappears in that quantization step.

**The real fix, when you want it**, is to add TRELLIS's texture/appearance
stage to the ComfyUI workflow so the mesh arrives genuinely textured; this
module then stops firing on its own (see `has_color_variation`), with no
code change needed.
"""

from __future__ import annotations

import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import cKDTree

# Below this many distinct vertex colors, a mesh is treated as untextured.
# A genuinely textured mesh has thousands; the shape-only TRELLIS output
# measured during development had exactly 1.
_FLAT_COLOR_THRESHOLD = 4

# How far a sampled pixel must be from the image's background color to
# count as "part of the object" rather than backdrop bleed near the
# silhouette. Same idea (and same rough threshold) as the original
# backend's own reference-image sampling used.
_BACKGROUND_DISTANCE = 18

# A vertex's surface normal Z-component must exceed this to be treated as
# "facing the camera" (the reference photo is a front view along the mesh's
# Z axis -- see paint_from_reference_image's own comment on the X/Y mapping,
# which axis carries "depth" is not new here). Which SIGN of Z is actually
# "toward the camera" is not independently verified -- tested a
# geometric-detail heuristic (more surface curvature = more likely the
# genuinely-photographed side, a smoothly-hallucinated back should have
# less) on two real meshes and got an inconclusive result (near-identical
# normal variance on both sides), so this is a best-effort convention, not
# a confirmed fact. It still provides real value even if the sign is
# backwards: either way, confident vertices get real per-position sampled
# color and everything else gets one coherent fallback instead of an
# arbitrary, often-wrong pixel lookup -- which side of the object ends up
# in which bucket may be swapped, but the noise reduction itself holds
# regardless.
_CAMERA_FACING_THRESHOLD = 0.15


def has_color_variation(mesh: trimesh.Trimesh) -> bool:
    """True if `mesh` carries real per-vertex color information, i.e. it is
    genuinely textured rather than a flat shape-only output."""
    visual = getattr(mesh, "visual", None)
    colors = getattr(visual, "vertex_colors", None)
    if colors is None:
        return False
    rgb = np.asarray(colors)[:, :3]
    if len(rgb) == 0:
        return False
    return len(np.unique(rgb, axis=0)) >= _FLAT_COLOR_THRESHOLD


def _background_rgb(image: np.ndarray) -> np.ndarray:
    """Median color of the image's outer border -- the backdrop."""
    border = np.concatenate(
        [image[0, :, :], image[-1, :, :], image[:, 0, :], image[:, -1, :]],
        axis=0,
    )
    return np.median(border, axis=0).astype(np.int16)


def _subject_bounds(image: np.ndarray, background: np.ndarray) -> tuple[int, int, int, int]:
    """Pixel bounds (x0, x1, y0, y1) of the actual subject within the
    image, i.e. everything far enough from the backdrop color.

    This matters more than it looks: the generated reference images are
    studio-style product shots where the subject occupies only the middle
    ~half of a 1024x1024 frame. Mapping the mesh's bounding box onto the
    *whole* image therefore projects most of the model onto empty
    backdrop -- measured on a real job, that turned a plainly brown table
    into a mostly-dark-gray brick model. Mapping onto the subject's own
    bounds instead is what makes the projected colors actually track the
    object.
    """
    foreground = np.abs(image.astype(np.int16) - background).max(axis=2) > _BACKGROUND_DISTANCE
    rows = np.flatnonzero(foreground.any(axis=1))
    cols = np.flatnonzero(foreground.any(axis=0))
    if len(rows) == 0 or len(cols) == 0:
        return 0, image.shape[1] - 1, 0, image.shape[0] - 1
    return int(cols[0]), int(cols[-1]), int(rows[0]), int(rows[-1])


def paint_from_reference_image(mesh: trimesh.Trimesh, image_path: str) -> trimesh.Trimesh:
    """Return `mesh` with vertex colors sampled from an orthographic front
    projection of the reference image at `image_path`. The mesh is modified
    in place and also returned."""
    with Image.open(image_path) as img:
        image = np.asarray(img.convert("RGB"), dtype=np.uint8)

    height, width, _ = image.shape
    background = _background_rgb(image)
    x0, x1, y0, y1 = _subject_bounds(image, background)

    vertices = np.asarray(mesh.vertices, dtype=float)
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    span = np.where((upper - lower) > 0, upper - lower, 1.0)

    # brickforge's own conditioning stage (pipeline/voxelize.py::condition_mesh)
    # treats the mesh as Y-up -- it scales by the X/Z horizontal extent and
    # drops the model onto Y=0 -- so the image's vertical axis maps to mesh Y
    # and its horizontal axis to mesh X. Image row 0 is the TOP, hence the
    # 1.0 - v flip. Both map onto the SUBJECT's pixel bounds, not the whole
    # frame -- see _subject_bounds.
    u = (vertices[:, 0] - lower[0]) / span[0]
    v = (vertices[:, 1] - lower[1]) / span[1]
    px = np.clip((x0 + u * (x1 - x0)).astype(int), 0, width - 1)
    py = np.clip((y0 + (1.0 - v) * (y1 - y0)).astype(int), 0, height - 1)

    sampled = image[py, px].astype(np.int16)

    # Only trust the projected pixel for vertices whose surface actually
    # faces the camera -- see _CAMERA_FACING_THRESHOLD's docstring for why
    # this matters more than it looks: without it, a back-facing vertex
    # gets whatever pixel happens to sit at its (X, Y) in the FRONT photo,
    # which is only correct by coincidence, not a real color for that
    # surface. "Camera-facing but landed on the backdrop" (silhouette
    # bleed) is folded into the same "don't trust it" bucket.
    normals = np.asarray(mesh.vertex_normals, dtype=float)
    camera_facing = normals[:, 2] > _CAMERA_FACING_THRESHOLD
    is_background = np.abs(sampled - background).max(axis=1) <= _BACKGROUND_DISTANCE
    trust_pixel = camera_facing & ~is_background

    result = sampled.copy()
    if trust_pixel.any() and not trust_pixel.all():
        # Untrusted vertices copy their nearest TRUSTED vertex's color (by
        # 3D position), not one flat global average -- see the module
        # docstring for why a flat fallback measurably breaks spatially
        # varying objects (a two-tone cactus+pot, a rocket with a dark
        # window). This keeps real spatial variation even where the
        # camera-facing test rejects the majority of the mesh.
        tree = cKDTree(vertices[trust_pixel])
        _, nearest_idx = tree.query(vertices[~trust_pixel])
        result[~trust_pixel] = sampled[trust_pixel][nearest_idx]
    elif not trust_pixel.any():
        # No vertex was confidently camera-facing at all (degenerate mesh
        # or a very shallow/edge-on view) -- fall back to a flat neutral
        # gray rather than trusting any of the raw (unconfident) samples.
        result[:] = np.array([160, 160, 160], dtype=np.int16)

    mesh.visual = trimesh.visual.ColorVisuals(
        mesh=mesh, vertex_colors=result.astype(np.uint8)
    )
    return mesh
