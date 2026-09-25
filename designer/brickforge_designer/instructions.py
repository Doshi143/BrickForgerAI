"""Build order, parts lists and a stepped LDR for designer models.

The core pipeline's instructions (core/brickforge/pipeline/instructions.py)
work on a grid `Model`; a designer `Design` is different (sideways SNOT
parts, glass/door/wheel attachments, separate assemblies), so it gets its
own small adapter that produces the same three things the PDF renderer
needs: steps, per-step part tallies, and a full bill of materials.

Build order, per section (main model first, then each separate standing
piece, then each vehicle as its own sub-build):
- a part becomes available once anything it connects to is built (so every
  part clicks onto something already there, including parts held from above
  or the side, like a SNOT panel on its anchor brick); the section's lowest
  parts seed the growth
- each step takes up to `max_per_step` available parts, preferring parts
  that sit on something already built, then bottom-up, then back-to-front
- attached details (window glass, door leaf, wheel rim and tyre) always go
  in the same step as the part they fit into
Every part appears in exactly one step (tested), so the parts list and the
steps always add up to the model's part count.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .engine import COLORS, TABLE

# LDConfig.ldr (official LDraw library): name, RGB, transparent -- for every
# colour the designer can use.
COLOR_TABLE = {
    0: ("Black", "#1B2A34", False),
    1: ("Blue", "#1E5AA8", False),
    2: ("Green", "#00852B", False),
    4: ("Red", "#B40000", False),
    6: ("Brown", "#543324", False),
    7: ("Light Grey", "#8A928D", False),
    8: ("Dark Grey", "#545955", False),
    10: ("Bright Green", "#58AB41", False),
    13: ("Pink", "#F6A9BB", False),
    14: ("Yellow", "#FAC80A", False),
    15: ("White", "#F4F4F4", False),
    19: ("Tan", "#D7BA8C", False),
    25: ("Orange", "#D67923", False),
    26: ("Magenta", "#901F76", False),
    27: ("Lime", "#A5CA18", False),
    28: ("Dark Tan", "#897D62", False),
    36: ("Trans Red", "#C91A09", True),
    40: ("Trans Brown", "#635F52", True),
    43: ("Trans Light Blue", "#AEE9EF", True),
    47: ("Trans Clear", "#FCFCFC", True),
    70: ("Reddish Brown", "#5F3109", False),
    71: ("Light Bluish Grey", "#969696", False),
    72: ("Dark Bluish Grey", "#646464", False),
    84: ("Medium Nougat", "#AA7D55", False),
    191: ("Bright Light Orange", "#FCAC00", False),
    288: ("Dark Green", "#00451A", False),
    308: ("Dark Brown", "#352100", False),
    320: ("Dark Red", "#720012", False),
    321: ("Dark Azure", "#469BC3", False),
    322: ("Medium Azure", "#68C3E2", False),
    326: ("Yellowish Green", "#E2F99A", False),
    378: ("Sand Green", "#708E7C", False),
    379: ("Sand Blue", "#70819A", False),
    484: ("Dark Orange", "#91501C", False),
    272: ("Dark Blue", "#19325A", False),
    73: ("Medium Blue", "#7396C8", False),
    330: ("Olive Green", "#77774E", False),
    226: ("Bright Light Yellow", "#FFEC6C", False),
    33: ("Trans Dark Blue", "#0020A0", True),
    41: ("Trans Medium Blue", "#559AB7", True),
}
assert set(COLOR_TABLE) == set(COLORS.values()), "COLOR_TABLE must cover every designer colour"

# LDraw titles that are redirect stubs ("~Moved to ...", "=...") -> the real part's name
NAME_OVERRIDES = {
    "3023": "Plate 1 x 2",
    "4073": "Plate 1 x 1 Round",
    "60603": "Glass for Window 1 x 4 x 3",
}

DEFAULT_MAX_PER_STEP = 8        # matches core's DEFAULT_MAX_BRICKS_PER_STEP


def part_name(pid):
    if pid in NAME_OVERRIDES:
        return NAME_OVERRIDES[pid]
    return re.sub(r"\s+", " ", TABLE[pid]["title"]).strip()


def color_info(code):
    """(name, (r, g, b), transparent)"""
    name, hexv, trans = COLOR_TABLE.get(code, (f"Colour {code}", "#808080", False))
    return name, tuple(int(hexv[i:i + 2], 16) for i in (1, 3, 5)), trans


@dataclass(frozen=True)
class Tally:
    part_id: str
    part_name: str
    color_code: int
    color_name: str
    count: int
    rgb: tuple
    transparent: bool


@dataclass(frozen=True)
class Step:
    index: int                  # 0-based
    section: str                # "Main model", "Vehicle 1", "Separate piece 1", ...
    part_indices: tuple         # indices into Design.parts
    running_total: int


def tally(D, indices):
    counts = Counter((D.parts[i].pid, D.parts[i].color) for i in indices)
    rows = []
    for (pid, code), n in counts.items():
        name, rgb, trans = color_info(code)
        rows.append(Tally(pid, part_name(pid), code, name, n, rgb, trans))
    rows.sort(key=lambda t: (-t.count, t.part_name, t.color_name))
    return rows


def bill_of_materials(D):
    return tally(D, range(len(D.parts)))


def sections(D):
    """[(label, [part indices])], in build order.  Attached details belong to
    their host's section automatically (they are linked in the graph)."""
    from .pipeline import classify_pieces
    comps, _ = D.components()
    main, standing, vehicles, loose = [], [], [], []
    for asm, status, c, _ in classify_pieces(D, comps):
        if status == "main":
            (main if asm == "main" else vehicles).append((asm, c))
        elif status == "standing":
            standing.append(c)
        else:
            loose.append(c)
    out = [("Main model", sorted(i for _, c in main for i in c))] if main else []
    out += [(f"Separate piece {n}", sorted(c)) for n, c in enumerate(standing, 1)]
    out += [(f"Vehicle {n}", sorted(c)) for n, (_, c) in enumerate(sorted(vehicles), 1)]
    if loose:                   # only on a model that failed its checks
        out.append(("Loose parts", sorted(i for c in loose for i in c)))
    return out


def build_steps(D, max_per_step=DEFAULT_MAX_PER_STEP):
    adj = D.graph()
    children = {}
    for i, q in enumerate(D.parts):
        if q.host is not None:
            children.setdefault(q.host, []).append(i)
    steps, running = [], 0
    for label, members in sections(D):
        S = set(members)
        movable = [i for i in members if D.parts[i].host is None or D.parts[i].host not in S]
        rests_on = {i: {m for m in D.supports(D.parts[i]) if m in S and m != i} for i in movable}
        bottom = lambda i: -D.parts[i].box[1][1]            # height of a part's underside (LDraw y is down)
        low = min(bottom(i) for i in movable)
        placed, remaining = set(), set(movable)
        available = {i for i in movable if not rests_on[i] and bottom(i) <= low + 0.5}

        def key(i):
            q = D.parts[i]
            sits = bool(rests_on[i] & placed)
            return (not sits and bool(rests_on[i]), bottom(i), q.box[2][0], q.box[0][0])

        while remaining:
            if not available:
                available = set(remaining)      # nothing connects to what's built: sweep the rest in
            chunk = sorted(available, key=key)[:max_per_step]
            step_parts = []
            for i in chunk:
                placed.add(i)
                remaining.discard(i)
                available.discard(i)
                step_parts.append(i)
                step_parts += children.get(i, [])
            for i in chunk:
                for m in adj[i]:
                    if m in remaining:
                        available.add(m)        # it can click onto something already built
            running += len(step_parts)
            steps.append(Step(len(steps), label, tuple(step_parts), running))
    return steps


def stepped_ldr(D, steps, name=None):
    """The model's LDR with parts reordered into build order and a `0 STEP`
    between steps (what the PDF renderer and Studio walk through)."""
    # the name comes from the user's prompt: keep it to one line so it can't
    # add lines (parts, meta-commands) to the LDR the renderer parses
    name = " ".join((name or D.title).split())
    fmt = lambda v: str(int(round(v))) if abs(v - round(v)) < 1e-6 else f"{v:.3f}".rstrip("0").rstrip(".")
    lines = [f"0 {name}", f"0 Name: {name}.ldr", "0 Author: BrickForgerAI designer",
             "0 !LDRAW_ORG Unofficial_Model", "0 BFC CERTIFY CCW", ""]
    for n, st in enumerate(steps):
        for i in st.part_indices:
            q = D.parts[i]
            lines.append(f"1 {q.color} {fmt(q.pos[0])} {fmt(q.pos[1])} {fmt(q.pos[2])} "
                         f"{' '.join(fmt(v) for v in q.mat)} {q.pid}.dat")
        if n < len(steps) - 1:              # no marker after the last step (same as core's to_ldr)
            lines.append("0 STEP")
    return "\n".join(lines) + "\n"
