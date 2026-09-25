"""Generate parts_table.json (bbox + studs per part) from the official LDraw
library.  Run once when the part vocabulary changes; the engine loads the JSON.

    LDRAW_CACHE=/some/dir python tools/build_parts_table.py
"""
import json
import os
import re
import subprocess
import time

from ldraw_geometry import MISSING, _walk, bbox, joints, studs, title

MIRROR = "https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/complete/ldraw/parts/"

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
    "43722", "43723", "41769", "41770", "24299", "24307",
    # large eyes: 2x2 round plate (original number, as the mirror has it)
    "4032",
    # facades: textured 1x2 bricks, 1x2 windows + glass, arch over a window
    "98283", "30136", "60592", "60601", "60593", "60602", "3659",
    # slope-brick roofs: 45 degree 2x1 / 2x2 slopes and double (ridge) slopes
    "3040b", "3039", "3044b", "3043",
    # ball-joint chains (limbs): ball on side, socket, socket + ball (the chain link)
    "14417", "14418", "14419",
    # horns and claws: curved blade on a bar, in a 1x1 round plate's open stud
    "87747", "85861",
    # hinged panels: 1x2 hinge base (brick) and top (plate), tilting about a shared x axis
    "3937", "3938",
    # palm trees: swordleaf (stud and anti-stud at its root, the leaf droops ~4 plates)
    "10884",
]
JOINTS = {"14417", "14418", "14419"}           # store measured ball centres and sockets
# Parts whose plan-view shape isn't their bounding rectangle: store the top
# face's outline (convex hull of the geometry at local y=0, as (x, z) LDU) so
# the engine can fit them to a diagonal edge by their real shape.
# Wedges use their original LDraw numbers (now "~Moved to ...a" redirects in the
# official library, measured through the redirect): the web viewer's and PDF
# renderer's parts mirror only has the original files, and they are also the
# BrickLink numbers.
OUTLINE = {"43722", "43723", "41769", "41770", "24299", "24307"}


def top_outline(pid):
    pts = sorted({(round(x, 1), round(z, 1)) for x, y, z in _walk(pid + ".dat")[0] if abs(y) < 0.01})
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1] + upper[:-1]]


if __name__ == "__main__":
    table = {}
    for pid in PARTS:
        (x0, x1), (y0, y1), (z0, z1) = bbox(pid)
        table[pid] = {"title": title(pid),
                      "bbox": [[x0, x1], [y0, y1], [z0, z1]],
                      "studs": [[*p, *d] for p, d in studs(pid)]}
        if pid in OUTLINE:
            table[pid]["outline"] = top_outline(pid)
        if pid in JOINTS:
            balls, sockets = joints(pid + ".dat")
            table[pid]["balls"] = [list(c) for c in balls]
            table[pid]["sockets"] = [[*c, *d] for c, d in sockets]
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
    # The web viewer and the PDF renderer load parts from a mirror that lags the
    # official library (it lacks renamed "...a" files, and 7825/7835, which are
    # self-hosted as overrides); a part missing there stops the whole model from
    # rendering on the site.  Every part must be on the mirror or overridden.
    viewer = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web", "frontend", "components",
                          "Viewer3D.tsx")
    with open(viewer, encoding="utf-8") as f:
        overridden = set(re.findall(r'"parts/([^"/]+)\.dat":', f.read()))
    absent = []
    for pid in PARTS:
        if pid in overridden:
            continue
        for attempt in range(5):
            time.sleep(0.2)
            r = subprocess.run(["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", MIRROR + pid + ".dat"],
                               capture_output=True, text=True)
            if r.stdout.strip() in ("200", "404"):
                break
            time.sleep(2 ** attempt)
        if r.stdout.strip() != "200":
            absent.append((pid, r.stdout.strip()))
    if absent:
        raise SystemExit(f"parts the site's viewer mirror can't load (use another LDraw number, or self-host an "
                         f"override in Viewer3D.tsx and render.js): {absent}")
    if bad:
        raise SystemExit(f"parts with a body shorter than one plate (geometry not resolved?): {bad}")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brickforge_designer", "parts_table.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(table, f, separators=(",", ":"))
    print("wrote", out)
