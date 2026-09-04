"""Builds examples/output/ground_bridge_demo.ldr -- a minimal, real
before/after demonstration of structure/ground_bridge.py, the same
"small hand-built file, confirm visually in Studio" pattern this
project uses throughout (see e.g. slope11477_backing_plate_demo.py).

Two separate 1x1 plates, each independently touching y=0 (both
individually "grounded" by the old, incomplete notion), sitting in
laterally adjacent grid columns with nothing physically connecting
them -- exactly the case find_bricks_outside_main_component's own
docstring says bridge_unstable/prune_unstable correctly leave alone
(neither is at fall risk), and exactly the case Studio's own stability
checker would flag as two separate pieces, not one buildable model.
"""
from __future__ import annotations

from brickforge import Model, PartCatalog, save_ldr
from brickforge.structure import analyze, bridge_disconnected_pieces, summarize

RED = 4


def main() -> None:
    catalog = PartCatalog.load_default()
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)

    before = analyze(model)
    print("--- before ---")
    print(summarize(before))
    save_ldr(model, "examples/output/ground_bridge_demo_before.ldr", name="Ground Bridge Demo (before)")
    print("wrote examples/output/ground_bridge_demo_before.ldr")

    result = bridge_disconnected_pieces(model)
    after = analyze(result.model)
    print()
    print(f"--- after ({len(result.added)} connector plate(s) added, {len(result.unresolved_pieces)} unresolved) ---")
    print(summarize(after))
    save_ldr(result.model, "examples/output/ground_bridge_demo_after.ldr", name="Ground Bridge Demo (after)")
    print("wrote examples/output/ground_bridge_demo_after.ldr")


if __name__ == "__main__":
    main()
