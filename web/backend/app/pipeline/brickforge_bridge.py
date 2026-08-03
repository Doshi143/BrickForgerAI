"""Stage: 3D mesh file -> real, structurally-analyzed, colored LDraw model.

Replaces this backend's original naive coverer (the old voxelize.py /
brick_matcher.py / lego_units.py / ldraw_export.py stack, removed) with
core/brickforge -- the actual part catalog, structural repair, and
slope/tile surface refinement built in the BrickForgerAI project, imported
as a library (installed editable from ../../core; see this package's
README for the setup command).

Mirrors examples/structural_report.py::report_and_save's repair pattern
from core/brickforge exactly (bridge-then-refill, prune whatever's left) --
that logic isn't re-derived here, just reused via the public brickforge API.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import trimesh

from brickforge import save_ldr
from brickforge.pipeline.mesh_to_model import mesh_to_model_full
from brickforge.pipeline.slopes import substitute_staircase_slopes
from brickforge.pipeline.surface_refine import substitute_tiles
from brickforge.structure import analyze, bridge_unstable, refill_enclosed_holes

from .mesh_conditioning import strip_base_slab
from .reference_color import has_color_variation, paint_from_reference_image


def _prepare_colored_mesh(mesh_path: str, reference_image_path: str | None) -> tuple[str, str]:
    """Make sure the mesh brickforge is about to voxelize actually carries
    per-vertex color, since that is the only thing
    brickforge.pipeline.voxelize.voxelize_mesh samples from -- and strip a
    spurious flat base slab first (see mesh_conditioning.py), since that's
    a geometry problem, not a color one, and should never reach the
    voxelizer regardless of which color path below ends up applying.

    Three color cases, in order:
      1. Already texture-mapped -> bake the texture down to vertex colors.
      2. Already vertex-colored with real variation -> use as-is.
      3. Flat/untextured (what this backend's shape-only TRELLIS workflow
         actually produces -- see reference_color.py) -> project the
         reference image onto it.

    Returns (path_to_use, color_source) where color_source is one of
    "texture" | "mesh_vertex_colors" | "reference_image_projection" |
    "none", so the job API can report honestly which one actually applied.
    Always exports to a fresh temp file -- never returns the original
    mesh_path unmodified, since strip_base_slab may have already changed
    the geometry even when no color-path modification is needed.
    """
    mesh = trimesh.load(mesh_path, force="mesh")
    mesh = strip_base_slab(mesh)

    if isinstance(mesh.visual, trimesh.visual.texture.TextureVisuals):
        mesh.visual = mesh.visual.to_color()
        return _export_temp(mesh), "texture"

    if has_color_variation(mesh):
        return _export_temp(mesh), "mesh_vertex_colors"

    if reference_image_path:
        paint_from_reference_image(mesh, reference_image_path)
        return _export_temp(mesh), "reference_image_projection"

    return _export_temp(mesh), "none"


def _export_temp(mesh: trimesh.Trimesh) -> str:
    """mesh_to_model_full takes a path, not a Trimesh, so a modified mesh
    has to round-trip through a file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
    tmp.close()
    mesh.export(tmp.name)
    return tmp.name


def mesh_to_ldr(
    mesh_path: str,
    ldr_out_path: str,
    target_studs: int,
    model_name: str,
    reference_image_path: str | None = None,
) -> dict:
    """Run mesh -> voxelize -> shell -> quantize -> legalize -> repair ->
    surface refinement -> LDR, via core/brickforge. Returns stats for the
    job API to report back to the frontend."""
    prepared_path, color_source = _prepare_colored_mesh(mesh_path, reference_image_path)

    result = mesh_to_model_full(prepared_path, target_studs)
    model = result.model

    report = analyze(model)
    was_repaired = False
    if not report.is_single_piece or report.critical_bricks:
        was_repaired = True
        bridged = bridge_unstable(model, solid_grid=result.solid_grid)
        refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
        model = refilled.model
        report = analyze(model)

    sloped = substitute_staircase_slopes(model)
    refined = substitute_tiles(sloped)

    save_ldr(refined, ldr_out_path, name=model_name)

    return {
        "part_count": len(refined),
        "slope_count": sum(1 for b in refined if b.part.category == "slope"),
        "tile_count": sum(1 for b in refined if b.part.category == "tile"),
        "color_count": len({b.color for b in refined}),
        "color_source": color_source,
        "was_repaired": was_repaired,
        "still_critical_count": len(report.critical_bricks),
        "is_single_piece": report.is_single_piece,
    }
