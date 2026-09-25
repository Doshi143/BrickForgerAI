"""Stage (Detailed mode): prompt -> designed brick model, via brickforge_designer.

Claude (Opus 5.5) writes a compact spec; the designer engine builds real
parts from it, checks them (stud connectivity, collisions, size), and sends
any problems back for up to two fix rounds.  A reference image of the
subject is always generated first and shown to the designer (it helped
resemblance in testing: pose, proportions, colours); users never see it.

Separate from brickforge_bridge.py (the Voxel pipeline) on purpose -- the
two share nothing but the instructions PDF renderer.

What the stats mean, stated plainly because the UI shows them:
- `is_single_piece`: no loose parts anywhere (every assembly holds
  together).  A house with a car, or a figure standing on a rock, is still
  "holds together" -- those are separate sub-builds, counted in `piece_count`.
- `was_repaired` / `still_critical_count`: None.  The designer checks stud
  connections and collisions only; it does NOT run the Voxel pipeline's
  force/critical-brick analysis, so it doesn't claim either.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter

from brickforge_designer.pipeline import (AnthropicDesigner, DesignerError, api_available,
                                          classify_pieces, cost, generate)

from .instructions_pdf import render_designer_instructions_pdf

logger = logging.getLogger(__name__)

SLOPE_IDS = {"11477", "15068", "93273", "49307", "54200", "85984", "50950", "61678", "24309", "93606",
             "24201", "13547"}
TILE_IDS = {"3070b", "3069b", "63864", "2431", "3068b", "87079", "6636", "4162", "98138"}

REFERENCE_IMAGE_PROMPT = (
    "{subject}. A simple, stylised 3D figurine with chunky, clearly separated shapes and flat, "
    "true-to-life colours, shown whole in a three-quarter view from the front-left and slightly "
    "above, on a plain light-grey background. No text, no logos."
)
# gpt-image-1 medium quality, 1024x1024 (measured $0.0425-0.0426 per image in testing)
REFERENCE_IMAGE_COST_USD = 0.043

# Size bounds for Detailed mode (the slider's range): models sit on a 32x32 baseplate.
MIN_SIZE, MAX_SIZE = 16, 32


def detailed_enabled_for(email: str | None) -> bool:
    """Detailed mode is off unless DETAILED_MODE_ENABLED=true AND an Anthropic
    key is configured; DETAILED_MODE_ALLOWLIST (comma-separated emails)
    further limits it to those accounts while it is being tried out."""
    if os.environ.get("DETAILED_MODE_ENABLED", "false").lower() != "true" or not api_available():
        return False
    allow = {e.strip().lower() for e in os.environ.get("DETAILED_MODE_ALLOWLIST", "").split(",") if e.strip()}
    return not allow or (email or "").lower() in allow


def design_to_ldr(
    prompt: str,
    ldr_out_path: str,
    target_studs: int,
    finish: str,
    sideways: str,
    model_name: str,
    pdf_out_path: str | None = None,
    reference_image_path: str | None = None,
    on_phase=None,
) -> dict:
    """Design, build, check, write model.ldr (+ best-effort PDF).  Raises
    DesignerError (with a user-safe `user_message`) when no model that
    passes every check could be produced -- the caller fails the job and
    refunds the credits."""
    image = None
    if reference_image_path and os.path.exists(reference_image_path):
        with open(reference_image_path, "rb") as f:
            image = (f.read(), "image/png")
    designer = AnthropicDesigner()
    result = generate(prompt, designer, finish=finish, sideways=sideways, size=target_studs,
                      reference_image=image, on_phase=on_phase)
    usage = {
        "calls": [{"label": label, **{k: v for k, v in u.items() if k != "request_id"},
                   "request_id": u.get("request_id"), "cost_usd": round(cost(u, designer.model), 4)}
                  for label, u in result["usage"]],
        "totals": result["totals"],
        "rounds": result["rounds"],
        "model": designer.model,
        "effort": designer.effort,
    }
    if result["problems"]:
        err = DesignerError(f"design failed its checks after {result['rounds']} fix rounds: {result['problems'][:5]}",
                            "We couldn't design a model for this prompt that holds together. "
                            "Please try rephrasing it or choosing a simpler subject.")
        err.usage = usage
        raise err

    D = result["design"]
    with open(ldr_out_path, "w", encoding="utf-8") as f:
        f.write(D.ldr())
    counts = Counter(q.pid for q in D.parts)
    comps, _ = D.components()
    pieces = classify_pieces(D, comps)
    stats = {
        "part_count": len(D.parts),
        "slope_count": sum(n for pid, n in counts.items() if pid in SLOPE_IDS),
        "tile_count": sum(n for pid, n in counts.items() if pid in TILE_IDS),
        "color_count": len({q.color for q in D.parts}),
        "color_source": "designer",
        "was_repaired": None,
        "still_critical_count": None,
        "is_single_piece": not any(status == "loose" for _, status, _, _ in pieces),
        "piece_count": len(pieces),
        "symmetrized": False,
        "design_usage": usage,
        "spec": result["spec"],
        "pdf_generated": False,
    }
    if pdf_out_path:
        if on_phase:
            on_phase("building")            # the PDF is the slow part once the design has passed
        try:
            render_designer_instructions_pdf(D, pdf_out_path, model_name)
            stats["pdf_generated"] = True
        except Exception:  # noqa: BLE001 -- the .ldr is already the paid-for deliverable
            logger.exception("instructions PDF failed for a Detailed model; shipping without it")
    return stats


def log_usage(job_id: str, usage: dict, image_cost: float) -> float:
    """One structured log line per job (searchable in Railway logs / Sentry
    breadcrumbs); returns the job's total $ cost."""
    total = round(usage.get("totals", {}).get("cost_usd", 0.0) + image_cost, 4)
    logger.info("detailed_job_usage %s", json.dumps({"job_id": job_id, "cost_usd": total,
                                                      "image_cost_usd": image_cost, **usage.get("totals", {}),
                                                      "rounds": usage.get("rounds")}))
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(category="detailed", message=f"job {job_id} cost ${total}", level="info")
    except Exception:  # noqa: BLE001
        pass
    return total
