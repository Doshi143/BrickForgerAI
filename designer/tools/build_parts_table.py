"""Generate parts_table.json (bbox + studs per part) from the official LDraw
library.  Run once when the part vocabulary changes; the engine loads the JSON.

    LDRAW_CACHE=/some/dir python tools/build_parts_table.py
"""
import json
import os

from ldraw_geometry import MISSING, bbox, studs, title

PARTS = [
    # bricks
    "3005", "3004", "3622", "3010", "3009", "3001", "3002", "3003", "2456", "3007",
    # plates
    "3024", "3023", "3623", "3710", "3666", "3460", "3022", "3021", "3020", "3795", "3034",
    "3031", "3032", "3035", "3958", "3030",
    # tiles
    "3070b", "3069b", "63864", "2431", "3068b", "87079", "6636", "4162", "98138",
    # curved / cheese slopes (2-plate, bottom-anchored) and 3-plate curved, inverted
    "11477", "15068", "93273", "49307", "54200", "85984", "50950", "61678", "24309", "93606",
    "24201", "13547",
    # round, SNOT
    "87081", "3941", "3062b", "4073", "33291", "30414", "87087",
    # plants
    "2423", "2417", "32607", "2435",
    # house / vehicle parts
    "3811", "60594", "60603", "60596", "60623", "4865b", "4600", "4624", "3641", "3823",
    "4079", "3829c01", "3065", "6014b", "6015",
    # Batch 1 techniques (TECHNIQUES.md): vehicle lights and grilles, teeth and
    # spikes, wedge plates for sleek outlines
    "4070", "2412b", "4589", "49668", "15070", "15208",
    "43722a", "43723a", "41769a", "41770a", "24299", "24307",
]

if __name__ == "__main__":
    table = {}
    for pid in PARTS:
        (x0, x1), (y0, y1), (z0, z1) = bbox(pid)
        table[pid] = {"title": title(pid),
                      "bbox": [[x0, x1], [y0, y1], [z0, z1]],
                      "studs": [[*p, *d] for p, d in studs(pid)]}
        print(f"{pid:8s} {table[pid]['title'][:40]:40s} studs={len(table[pid]['studs'])}")
    # Sanity: every stud-bearing part's body must reach a whole plate below its top.
    # A short body means geometry was dropped, which would seat the part too low.
    bad = []
    for pid, t in table.items():
        (x0, x1), (y0, y1), (z0, z1) = t["bbox"]
        if pid in ("3811",) or y1 <= 0.5:
            continue
        if y1 < 7.5:
            bad.append((pid, y1))
    if MISSING:
        raise SystemExit(f"files referenced but not found in the LDraw library (geometry incomplete): {sorted(MISSING)}")
    if bad:
        raise SystemExit(f"parts with a body shorter than one plate (geometry not resolved?): {bad}")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brickforge_designer", "parts_table.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(table, f, separators=(",", ":"))
    print("wrote", out)
