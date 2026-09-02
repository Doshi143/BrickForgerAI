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

import logging
import tempfile
from pathlib import Path

import trimesh

from brickforge import Model, save_ldr
from brickforge.pipeline.mesh_to_model import mesh_to_model_full
from brickforge.pipeline.slopes import substitute_staircase_slopes
from brickforge.pipeline.surface_refine import substitute_tiles
from brickforge.pipeline.symmetry import detect_mirror_plane, enforce_symmetry
from brickforge.structure import analyze, bridge_unstable, close_enclosed_voids, refill_enclosed_holes

from .instructions_pdf import render_instructions_pdf
from .mesh_conditioning import strip_base_slab
from .reference_color import has_color_variation, paint_from_reference_image
from .symmetry_classifier import classify_prompt

logger = logging.getLogger(__name__)

# shell.py::WIREFRAME_RGB is set to the catalog's exact Black RGB, so
# quantize_grid_colors always resolves it to LDraw code 0 with zero
# distance -- a reliable "is this wireframe" signal for anything
# downstream of quantization, not a guess.
_WIREFRAME_COLOR_CODE = 0


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


#  brickforge's shell_and_support (core/brickforge/pipeline/shell.py) fills
#  a solid interior with a periodic full-height cross-bracing wall every
#  `support_pitch` cells, *regardless* of whether the source mesh itself
#  was modeled hollow -- voxelize_mesh always solid-fills the volume
#  enclosed by the mesh's outer boundary first, so "make TRELLIS produce
#  hollow meshes" wouldn't actually change final part count (the outer
#  shell is identical either way; only this internal lattice differs).
#  This is therefore the real lever for "hollow interior, fewer parts".
#  Measured, not assumed, on two real jobs before picking this default:
#  a chunky, plump shape (a pear, target_studs=32) drops from ~8930 parts
#  at the core default (support_pitch=5) to ~5380 with no internal
#  bracing at all -- a 40% cut. A thin/spindly shape (a cactus,
#  target_studs=20) barely moves (~2350 -> ~2190, ~7%), since it never
#  had much solid interior to brace in the first place. In both cases,
#  at every pitch tested including fully unbraced, the model stayed a
#  single connected piece with zero remaining critical bricks after the
#  existing bridge/refill repair pass below -- that repair pass is what
#  makes "hollow, but still stable" safe to default to, rather than a
#  hope: anywhere the shell alone can't stay connected, it already adds
#  a bridging pillar or prunes the unsupportable bit, exactly as it does
#  today for shapes that need it regardless of this setting.
_SUPPORT_PITCH = 9999  # larger than any realistic grid extent -> shell only

# Real, then-current bug, not a hypothetical: with periodic internal
# bracing fully disabled (_SUPPORT_PITCH above) and nothing proactive put
# in its place, a real generated pear had its entire stem pruned outright
# -- an isolated feature with no interior-only path to ground, deleted by
# the very repair pass meant to keep things structurally sound. Real LEGO
# large-scale builds solve exactly this with a hidden internal skeleton
# the shell anchors to, not a solid-filled interior -- see
# add_wireframe_support's own docstring for why it's built as two full
# vertical planes through the center (not a thin spine-and-arms design --
# that version relied on bridge_unstable silently gluing it together
# after the fact, which is exactly what the user caught in Studio: beams
# that only *touch* the shell instead of genuinely connecting to it).
_WIREFRAME_CROSS_THICKNESS = 2


def _substitute_tiles_preserving_wireframe(model: Model) -> Model:
    """Tile substitution is a purely cosmetic swap for exterior surfaces a
    person will actually see (DESIGN.md: removes the "visible studs"
    look). The wireframe is hidden internal structure nobody ever sees,
    so there's nothing to gain by spending that substitution on it.

    Uses substitute_tiles's own `exclude` parameter, which still shows it
    the FULL model (wireframe included) for the occupancy/exposed check --
    a real bug, not a hypothetical, was caught here: a first version of
    this function stripped wireframe bricks out of the model entirely
    before calling substitute_tiles, which made the exposed check blind
    to them. A plain plate with a wireframe brick resting directly on top
    of it looked "exposed" and got swapped for a tile anyway, severing
    the connection the wireframe actually depended on -- confirmed on a
    real job (a steampunk balloon), where it silently introduced 155
    critical bricks that the job's own reported stats never caught, since
    nothing re-analyzed the model after tile substitution ran (see the
    fix to that below, in mesh_to_ldr)."""
    return substitute_tiles(model, exclude=lambda brick: brick.color == _WIREFRAME_COLOR_CODE)


def mesh_to_ldr(
    mesh_path: str,
    ldr_out_path: str,
    target_studs: int,
    model_name: str,
    reference_image_path: str | None = None,
    pdf_out_path: str | None = None,
    prompt: str | None = None,
) -> dict:
    """Run mesh -> voxelize -> shell -> quantize -> legalize -> repair ->
    surface refinement -> LDR, via core/brickforge. Returns stats for the
    job API to report back to the frontend.

    `pdf_out_path`, when given, also renders a build-instruction PDF (see
    instructions_pdf.py) from the exact same repaired/refined `refined`
    Model that gets written to the .ldr -- never a re-derived or
    re-repaired copy. This is deliberately best-effort: a Playwright/
    Chromium failure here must not fail the whole job and lose the real,
    already-paid-for .ldr deliverable, so it's caught and logged rather
    than re-raised. `stats["pdf_generated"]` tells the caller (jobs.py)
    whether it actually happened.

    `prompt`, when given, decides whether symmetry gets enforced (see
    symmetry_classifier.py and brickforge.pipeline.symmetry) -- falls
    back to `model_name` if omitted, so existing callers (the standalone
    end-to-end test script) keep working unchanged, just classifying off
    a possibly-truncated string instead of the real prompt."""
    prepared_path, color_source = _prepare_colored_mesh(mesh_path, reference_image_path)

    result = mesh_to_model_full(
        prepared_path,
        target_studs,
        support_pitch=_SUPPORT_PITCH,
        wireframe_cross_thickness=_WIREFRAME_CROSS_THICKNESS,
    )
    model = result.model

    report = analyze(model)
    was_repaired = False
    if not report.is_single_piece or report.critical_bricks:
        was_repaired = True
        bridged = bridge_unstable(model, solid_grid=result.solid_grid)
        refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
        model = refilled.model
        report = analyze(model)

    # Unconditional, not gated on was_repaired: refill_enclosed_holes only
    # ever reconsiders cells bridge_unstable actually removed, so a gap
    # that was simply never occupied to begin with (a legalizer seam, a
    # voxelization crevice) is invisible to it regardless of whether
    # repair fired at all. Confirmed on a real job -- a pear still had a
    # small visible hole near its center after bridge+refill ran clean.
    # See close_enclosed_voids's own docstring for why filling a
    # fully-6-sided-enclosed void is safe by construction, not a guess.
    void_result = close_enclosed_voids(model)
    model = void_result.model

    sloped = substitute_staircase_slopes(model)
    refined = _substitute_tiles_preserving_wireframe(sloped.model)

    # Re-verify (and, if needed, re-repair) the model actually being saved,
    # not an earlier snapshot. A real bug, not a hypothetical: `report`
    # above was previously returned as-is even though slope/tile
    # substitution run *after* it and are only "safe by construction"
    # when their own logic has no bugs -- which held right up until it
    # didn't (see _substitute_tiles_preserving_wireframe's docstring for
    # the real case this caught: 155 critical bricks introduced by tile
    # substitution, invisible in the reported stats because nothing had
    # re-analyzed the model since before slopes and tiles ran at all).
    final_report = analyze(refined)
    if not final_report.is_single_piece or final_report.critical_bricks:
        was_repaired = True
        bridged = bridge_unstable(refined, solid_grid=result.solid_grid)
        refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
        refined = refilled.model
        final_report = analyze(refined)

    # Symmetry enforcement runs LAST, after slopes/tiles, not before --
    # mirroring the fully-refined model (surface details included) copies
    # each already-chosen slope/tile onto its mirror counterpart exactly,
    # rather than letting the slope/tile substitution passes run
    # independently on each half afterward and potentially pick different
    # candidates on each side, which would reintroduce the very asymmetry
    # this stage exists to remove. Gated on classify_prompt -- "organic"
    # subjects (animals, food, landscapes) keep their natural asymmetry;
    # only "ordered" ones (vehicles, buildings, furniture) are candidates
    # at all, and even then only if detect_mirror_plane finds the model is
    # ALREADY close to symmetric (see that function's own conservative
    # threshold) -- this never forces symmetry onto a shape that wasn't
    # already close to it.
    symmetrized = False
    if classify_prompt(prompt if prompt is not None else model_name) == "ordered":
        plane = detect_mirror_plane(refined)
        if plane is not None:
            candidate = enforce_symmetry(refined, plane)
            candidate_report = analyze(candidate)
            if not candidate_report.is_single_piece or candidate_report.critical_bricks:
                was_repaired = True
                bridged = bridge_unstable(candidate, solid_grid=result.solid_grid)
                refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
                candidate = refilled.model
                candidate_report = analyze(candidate)
            refined = candidate
            final_report = candidate_report
            symmetrized = True

    # sloped.raw_placements: cosmetic-only extras (currently just the
    # 11477 backing plate -- see slopes.py's own _NEEDS_ANCHOR_BACKING_PLATE
    # docstring) that must render inside another part's own declared
    # footprint, so they can't go through the normal collision-checked
    # Model.place() path at all. Not re-validated against whatever
    # bridge_unstable/refill_enclosed_holes/symmetry did to `refined`
    # above -- same accepted limitation this codebase's existing SNOT
    # raw_placements already have (see examples/structural_report.py),
    # not a new gap introduced here.
    save_ldr(refined, ldr_out_path, name=model_name, raw_placements=sloped.raw_placements)

    pdf_generated = False
    if pdf_out_path:
        try:
            render_instructions_pdf(refined, pdf_out_path, model_name)
            pdf_generated = True
        except Exception:
            logger.exception(
                "Instructions PDF generation failed for %r -- job still succeeds with .ldr only", model_name
            )

    return {
        "part_count": len(refined),
        "slope_count": sum(1 for b in refined if b.part.category == "slope"),
        "tile_count": sum(1 for b in refined if b.part.category == "tile"),
        "color_count": len({b.color for b in refined}),
        "color_source": color_source,
        "was_repaired": was_repaired,
        "still_critical_count": len(final_report.critical_bricks),
        "is_single_piece": final_report.is_single_piece,
        "symmetrized": symmetrized,
        "pdf_generated": pdf_generated,
    }
