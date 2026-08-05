"""Tests for app/pipeline/reference_color.py -- plain script style (assert +
print), matching this backend's existing test_pipeline_end_to_end.py
convention rather than pulling in pytest as a new dependency for this
sub-project.

Run: python app/tests/test_reference_color.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.pipeline.reference_color import has_color_variation, paint_from_reference_image


def _make_two_tone_image(path: str) -> None:
    """A 200x200 image: gray backdrop border, with a central subject region
    whose top half is green (cactus-like) and bottom half is orange
    (terracotta-pot-like) -- a minimal synthetic stand-in for a real
    two-color photographed object."""
    img = np.full((200, 200, 3), (200, 200, 200), dtype=np.uint8)  # backdrop
    img[40:160, 60:140] = (40, 140, 40)  # subject region, default green
    img[100:160, 60:140] = (200, 110, 40)  # bottom half of subject: orange
    Image.fromarray(img).save(path)


def _make_two_tone_mesh() -> trimesh.Trimesh:
    """A tall box, subdivided for enough vertices to exercise nearest-
    neighbor propagation meaningfully (a bare box's 8 vertices wouldn't)."""
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 1.0))
    mesh = mesh.subdivide().subdivide()
    return mesh


def test_top_and_bottom_regions_get_genuinely_different_colors() -> None:
    """Regression pin for a real bug: a flat single fallback color for
    every non-camera-facing vertex collapsed a two-tone object (a green
    cactus in an orange pot) into one muddy average for both the top and
    bottom of the model. Nearest-confident-neighbor propagation should
    keep the real top/bottom distinction."""
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "ref.png")
        _make_two_tone_image(image_path)

        mesh = _make_two_tone_mesh()
        paint_from_reference_image(mesh, image_path)

        vertices = mesh.vertices
        colors = np.asarray(mesh.visual.vertex_colors)[:, :3].astype(int)
        y_min, y_max = vertices[:, 1].min(), vertices[:, 1].max()
        top = colors[vertices[:, 1] > y_min + 0.7 * (y_max - y_min)]
        bottom = colors[vertices[:, 1] < y_min + 0.3 * (y_max - y_min)]

        top_mean = top.mean(axis=0)
        bottom_mean = bottom.mean(axis=0)
        distance = np.linalg.norm(top_mean - bottom_mean)

        print(f"top mean: {top_mean}, bottom mean: {bottom_mean}, distance: {distance:.1f}")
        assert distance > 40, (
            "top and bottom regions collapsed to nearly the same color -- "
            "the flat-fallback bug is back"
        )
        # top should read greener than bottom, bottom should read more
        # orange/red than top (green channel higher relatively at top;
        # red channel higher relatively at bottom).
        assert top_mean[1] > bottom_mean[1], "top should be greener than bottom"
        assert bottom_mean[0] > top_mean[0], "bottom should be redder/oranger than top"


def test_background_pixels_do_not_leak_into_object_color() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "ref.png")
        _make_two_tone_image(image_path)

        mesh = _make_two_tone_mesh()
        paint_from_reference_image(mesh, image_path)

        colors = np.asarray(mesh.visual.vertex_colors)[:, :3].astype(int)
        backdrop = np.array([200, 200, 200])
        # no vertex should end up exactly the flat backdrop gray -- every
        # vertex should have picked up subject color (real or propagated).
        matches_backdrop = np.all(np.abs(colors - backdrop) < 5, axis=1)
        print(f"vertices matching backdrop color: {matches_backdrop.sum()} / {len(colors)}")
        assert matches_backdrop.sum() == 0


def test_has_color_variation_still_detects_flat_shape_only_meshes() -> None:
    # has_color_variation itself is untouched by this pass -- this just
    # confirms the flat, uniform-gray case (the real shape-only TRELLIS
    # signature) still reads correctly as "no variation."
    flat = trimesh.creation.box()
    flat.visual = trimesh.visual.ColorVisuals(
        mesh=flat, vertex_colors=np.tile([102, 102, 102, 255], (len(flat.vertices), 1))
    )
    assert has_color_variation(flat) is False


def test_painting_introduces_real_color_variation() -> None:
    # A simple 2-region synthetic mesh doesn't have enough vertices to
    # clear has_color_variation's thousands-of-colors threshold (that
    # threshold is calibrated for real meshes) -- this checks the more
    # direct thing: painting genuinely produced more than one color, not
    # a single flat result.
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "ref.png")
        _make_two_tone_image(image_path)
        mesh = _make_two_tone_mesh()
        paint_from_reference_image(mesh, image_path)
        colors = np.asarray(mesh.visual.vertex_colors)[:, :3]
        assert len(np.unique(colors, axis=0)) > 1


def main() -> None:
    tests = [
        test_top_and_bottom_regions_get_genuinely_different_colors,
        test_background_pixels_do_not_leak_into_object_color,
        test_has_color_variation_still_detects_flat_shape_only_meshes,
        test_painting_introduces_real_color_variation,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
