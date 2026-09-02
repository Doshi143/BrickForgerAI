"""Phase 2 milestone: run structural analysis on the existing example
models and export a stability heatmap LDR next to each one (green = OK,
yellow = single point of failure, red = floating / overloaded connection).

Repair is bridge-then-refill-then-prune: bridge_unstable connects an
ungrounded region with a hidden interior pillar wherever the model's own
original solid silhouette allows one (mesh-derived models only -- see
mesh_to_model_full's solid_grid); refill_enclosed_holes patches back any
single removed cell that's now boxed in on all sides by what's left;
whatever still can't be connected or refilled stays pruned. See
CLAUDE.md / structure/bridge.py and structure/refill.py for why each step
exists and what it does and doesn't guarantee.

Run:
    python examples/structural_report.py
"""

from pathlib import Path

from brickforge import GridPos, RawPlacement, save_ldr
from brickforge.pipeline.mesh_to_model import mesh_to_model_full
from brickforge.pipeline.slopes import substitute_staircase_slopes
from brickforge.pipeline.snot_placement import place_snot_panels
from brickforge.pipeline.surface_refine import substitute_tiles
from brickforge.snot import place_in_frame, snot_frame_for_brick
from brickforge.structure import (
    analyze,
    bridge_unstable,
    build_heatmap_model,
    refill_enclosed_holes,
    summarize,
)
from turret import build as build_turret

OUT_DIR = Path(__file__).parent / "output"


def report_and_save(model, name: str, solid_grid=None) -> None:
    report = analyze(model)
    print(f"--- {name} (before repair) ---")
    print(summarize(report))
    print()

    heatmap = build_heatmap_model(report)
    heatmap_path = OUT_DIR / f"{name}_heatmap.ldr"
    save_ldr(heatmap, heatmap_path, name=f"BrickForgerAI Stability Heatmap - {name}")
    print(f"Wrote {heatmap_path}")

    bridged = bridge_unstable(model, solid_grid=solid_grid)
    refilled = refill_enclosed_holes(bridged.model, removed=bridged.removed)
    structurally_sound = refilled.model

    if bridged.added or bridged.removed or refilled.refilled:
        report_after = analyze(structurally_sound)
        print(
            f"--- {name} (after repair: +{len(bridged.added)} hidden pillar part(s), "
            f"-{len(bridged.removed)} unbridgeable part(s) pruned, "
            f"+{len(refilled.refilled)} of those cells refilled as enclosed holes) ---"
        )
        print(summarize(report_after))
        repaired_path = OUT_DIR / f"{name}_repaired.ldr"
        save_ldr(structurally_sound, repaired_path, name=f"BrickForgerAI Repaired - {name}")
        print(f"Wrote {repaired_path}")

    # Surface refinement runs last, on the final structurally-sound model --
    # neither substitution ever changes connectivity (see surface_refine.py
    # and pipeline/slopes.py: both only remove TOP stud coverage, and only
    # where nothing is already resting there), so no iterative re-validation
    # loop is needed -- just a before/after analyze() sanity check, since
    # "safe by construction" is a claim worth checking, not just trusting.
    #
    # The 2-plate slope tier merges two placed plates into one (see
    # pipeline/slopes.py), unlike every other substitution here, which is a
    # straight 1-to-1 swap. That breaks the index-for-index correspondence
    # a raw `critical_bricks` set-equality check relied on (bricks shift
    # position in the list once any pair merges away), and it means part
    # count can legitimately *decrease* -- by design, not a regression. So
    # the checks below compare counts, not raw index sets, and allow count
    # to drop.
    sloped = substitute_staircase_slopes(structurally_sound)

    # SNOT Phase C.1: runs after slope substitution, not before -- both draw
    # candidates from the same pool of brick-height blocks, so slopes get
    # first pick of a genuine step-edge rather than the two features
    # fighting over the same source material (see snot_placement.py's own
    # module docstring). Tile substitution operates on plates only, so its
    # ordering relative to SNOT doesn't matter either way -- SNOT runs
    # before it here only because it's convenient to report together.
    snot_result = place_snot_panels(sloped.model, solid_grid=solid_grid)
    refined = substitute_tiles(snot_result.model)

    slope_count = sum(1 for b in refined if b.part.category == "slope")
    tile_count = sum(1 for b in refined if b.part.category == "tile")
    if slope_count or tile_count or snot_result.swapped:
        report_pre_refine = analyze(structurally_sound)
        # The real, end-to-end use of Phase B's own snot_children param:
        # confirms the SNOT branches AND the rest of the model are still
        # one connected, non-critical structure together, not just that
        # the ordinary-brick part of refined looks fine on its own.
        report_refined = analyze(refined, snot_result.snot_children)
        assert len(report_refined.critical_bricks) <= len(report_pre_refine.critical_bricks)
        assert report_refined.is_single_piece == report_pre_refine.is_single_piece
        # SNOT swaps and tile substitution are both 1:1 (count-preserving);
        # only the 2-plate slope tier's merge can shrink the model's own
        # part count. snot_children are additional sideways parts, not
        # counted in len(refined) at all (they're not in model.bricks).
        assert len(refined) <= len(structurally_sound)
        print(
            f"--- {name} (surface refinement: {slope_count} step edge(s) -> slopes, "
            f"{tile_count} top-facing plate(s) -> tiles, "
            f"{len(structurally_sound) - len(refined)} part(s) merged away by the 2-plate tier, "
            f"{snot_result.swapped} SNOT anchor(s) with a flush panel attached) ---"
        )
        refined_path = OUT_DIR / f"{name}_refined.ldr"

        raw_placements: list[RawPlacement] = list(sloped.raw_placements)
        for child in snot_result.snot_children:
            parent = refined.bricks[child.parent_index]
            frame = snot_frame_for_brick(parent, parent.part.side_stud_face, face_offset=parent.part.side_stud_offset)
            pos, matrix = place_in_frame(frame, child.part, child.local_pos, child.local_rotation)
            raw_placements.append(RawPlacement(part_id=child.part.id, color=parent.color, pos_ldu=pos, matrix=matrix))

        save_ldr(refined, refined_path, name=f"BrickForgerAI Refined - {name}", raw_placements=raw_placements)
        print(f"Wrote {refined_path} ({len(raw_placements)} SNOT panel(s) as raw placements)")
    print()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    report_and_save(build_turret(), "turret")

    mushroom = mesh_to_model_full(OUT_DIR / "mushroom_source.glb", 24)
    report_and_save(mushroom.model, "mushroom", solid_grid=mushroom.solid_grid)

    bunny = mesh_to_model_full(Path(__file__).parent / "meshes" / "stanford-bunny.obj", 20)
    report_and_save(bunny.model, "bunny", solid_grid=bunny.solid_grid)


if __name__ == "__main__":
    main()
