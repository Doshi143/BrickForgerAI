"""Brick engine: exact LDraw placement in studs-up or sideways (SNOT) frames,
collision on part bodies, and connectivity proven by matching real stud
positions/directions (from parts_table.json) against part undersides.

Grid conventions (main frame): cell (x, z) spans LDU [20x, 20x+20] x [20z, 20z+20];
level L spans LDU y in [-8(L+1), -8L] (LDraw y points down; levels count up).
"""
from __future__ import annotations

import json
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "parts_table.json"), encoding="utf-8") as _f:
    TABLE = json.load(_f)

I3 = (1, 0, 0, 0, 1, 0, 0, 0, 1)
YAW = {0: I3,
       90: (0, 0, 1, 0, 1, 0, -1, 0, 0),
       180: (-1, 0, 0, 0, 1, 0, 0, 0, -1),
       270: (0, 0, -1, 0, 1, 0, 1, 0, 0)}


def mul(m, v):
    return (m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
            m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2])


def mm(a, b):
    return tuple(sum(a[3 * i + k] * b[3 * k + j] for k in range(3)) for i in range(3) for j in range(3))


# ---------------------------------------------------------------- per-part policy
# Parts whose bbox includes things that aren't the gridded body (side studs,
# wheel pins, seat backrest): the footprint that sits on the grid.
FOOTPRINT = {"30414": (4, 1, 0, 0), "87087": (1, 1, 0, 0), "4600": (2, 2, 0, 0), "4079": (2, 2, 0, 0),
             # tooth plates: the plate is the footprint, the tooth sticks out (measured:
             # 49668 reaches a stud past its -z edge, 15208 half a stud, 15070 hangs 2 plates down)
             "49668": (1, 1, 0, 0), "15070": (1, 1, 0, 0), "15208": (2, 1, 0, 0)}
HEIGHT_OVERRIDE = {"32607": 1, "2417": 1, "2435": 1, "4079": 1, "3829c01": 1, "3811": 0, "15070": 1}
ORIGIN_PARTS = {"2423", "2417", "32607", "2435"}          # placed by their attachment stud
FULL_BOX = ORIGIN_PARTS | {"4079", "3829c01", "49668", "15070", "15208"}   # collide with their whole geometry
# Collision body where it differs from the footprint box.  4070's front is
# recessed 4 LDU (measured: its side stud's base is at z=-6, the face at -10),
# so whatever clicks onto that stud sits in the recess, not in the brick.
BODY_BOX = {"4070": ((-10, 10), (0, 24), (-6, 10))}
RECV = {"24201": [(0, 1)], "13547": [(0, 3)],
        "87081": [(a, b) for a in range(4) for b in range(4) if not (a in (0, 3) and b in (0, 3))],
        "3811": []}

# Curved slopes whose tall end is hollow underneath: measured from the LDraw
# geometry strip by strip along the slope (the lowest surface over those cells
# sits one or two plates above the part's bottom), the same notch the core
# pipeline fills for 11477.  Left empty it shows as a dark hole at the end of
# the slope, and the slope doesn't really grip the studs under that end.
# The 4-long ones step: 1 plate deep under their 3rd cell, 2 under the 4th.
# pid -> [(filler plate, offset in the slope's own frame (x, y, z), filler yaw)]
# y = the filler's top: bottom-anchored parts have their bottom at y=0, the
# 3-plate top-anchored ones at y=24; plates are top-anchored, 8 LDU tall.
HOLLOW_END = {
    "11477": [("3024", (0, -8, 10), 0)],
    "15068": [("3023", (0, -8, 10), 0)],
    "50950": [("3024", (0, 16, 20), 0)],
    "24309": [("3023", (0, 16, 20), 0)],
    "61678": [("3023", (0, 16, 20), 90), ("3024", (0, 8, 30), 0)],
    "93606": [("3022", (0, 16, 20), 0), ("3023", (0, 8, 30), 0)],
}

COLORS = {
    "black": 0, "blue": 1, "green": 2, "red": 4, "brown": 6, "light_gray": 7, "dark_gray": 8,
    "bright_green": 10, "pink": 13, "yellow": 14, "white": 15, "tan": 19, "magenta": 26, "lime": 27,
    "dark_tan": 28, "orange": 25, "reddish_brown": 70, "light_bluish_gray": 71, "dark_bluish_gray": 72,
    "medium_nougat": 84, "bright_light_orange": 191, "dark_orange": 484, "dark_red": 320,
    "dark_green": 288, "dark_brown": 308, "sand_green": 378, "sand_blue": 379, "medium_azure": 322,
    "dark_azure": 321, "yellowish_green": 326, "trans_clear": 47, "trans_light_blue": 43,
    "trans_red": 36, "trans_brown": 40,
    # gradient families (water, grass, foliage, sky): TECHNIQUES.md item 1
    "dark_blue": 272, "medium_blue": 73, "olive_green": 330, "bright_light_yellow": 226,
    "trans_dark_blue": 33, "trans_medium_blue": 41,
}


class PartDef:
    def __init__(self, pid):
        if pid not in TABLE:
            raise KeyError(f"unknown part {pid}")
        t = TABLE[pid]
        (x0, x1), (y0, y1), (z0, z1) = t["bbox"]
        self.pid, self.bbox = pid, t["bbox"]
        if pid in HEIGHT_OVERRIDE:
            self.h, self.bottom = HEIGHT_OVERRIDE[pid], False
        elif y1 <= 0.5 and y0 < -6:
            self.h, self.bottom = round(-y0 / 8), True
        else:
            self.h, self.bottom = round(y1 / 8), False
        if self.h < 1 and pid != "3811":
            raise ValueError(f"part {pid} measured as {self.h} plates tall; parts_table is wrong for it")
        if pid in ORIGIN_PARTS:
            self.w, self.d, self.cx, self.cz = 1, 1, 0, 0
        elif pid in FOOTPRINT:
            self.w, self.d, self.cx, self.cz = FOOTPRINT[pid]
        else:
            self.w, self.d = round((x1 - x0) / 20), round((z1 - z0) / 20)
            self.cx, self.cz = round((x0 + x1) / 2 / 10) * 10, round((z0 + z1) / 2 / 10) * 10
        self.studs = [((s[0], s[1], s[2]), (round(s[3]), round(s[4]), round(s[5]))) for s in t["studs"]]
        # plan-view shape for parts that aren't rectangles (wedge plates), local (x, z) LDU
        self.outline = [tuple(p) for p in t["outline"]] if "outline" in t else None
        cells = RECV.get(pid)
        if cells is None and self.outline:
            # a wedge grips only under its studded, full-width column, not under the taper
            x0, z0 = self.cx - 10 * self.w, self.cz - 10 * self.d
            cells = sorted({(int((s[0][0] - x0) // 20), int((s[0][2] - z0) // 20)) for s in self.studs
                            if s[1] == (0, -1, 0)})
        if cells is None:
            cells = [(0, 0)] if pid in ORIGIN_PARTS else [(a, b) for a in range(self.w) for b in range(self.d)]
        ybot = 0.0 if self.bottom else 8.0 * self.h
        self.recv = [(self.cx - 10 * self.w + 20 * a + 10, ybot, self.cz - 10 * self.d + 20 * b + 10) for a, b in cells]

    def body_box(self):
        if self.pid in BODY_BOX:
            return BODY_BOX[self.pid]
        if self.pid in FULL_BOX:
            (x0, x1), (y0, y1), (z0, z1) = self.bbox
            return ((x0, x1), (max(y0, -200), y1), (z0, z1))
        y = (-8 * self.h, 0) if self.bottom else (0, 8 * self.h)
        return ((self.cx - 10 * self.w, self.cx + 10 * self.w), y, (self.cz - 10 * self.d, self.cz + 10 * self.d))


_DEFS: dict = {}


def pdef(pid):
    if pid not in _DEFS:
        _DEFS[pid] = PartDef(pid)
    return _DEFS[pid]


class Frame:
    """A lattice embedded in world LDU space: world = O + R * frame_local."""

    def __init__(self, O=(0, 0, 0), R=I3, name="main"):
        self.O, self.R, self.name = O, R, name


MAIN = Frame()


class Placed:
    __slots__ = ("pid", "color", "pos", "mat", "box", "studs", "recv", "tag", "step", "asm", "host", "src")


def yaw_pointing(frame, want_world, local=(0, 0, 1)):
    for y, Ry in YAW.items():
        if tuple(round(c) for c in mul(frame.R, mul(Ry, local))) == tuple(want_world):
            return y
    raise ValueError(f"no yaw maps {local} to {want_world}")


class Design:
    def __init__(self, title="model"):
        self.title = title
        self.parts: list[Placed] = []
        self.step = 0
        self.studmap = defaultdict(list)
        self.links: list[tuple[int, int]] = []       # non-stud joints: glass, hinges, wheel pins
        self.occ = {}                                # main-frame (x, L, z) -> index
        self._hash = defaultdict(list)
        self.src = None                              # spec line being built (checker reports cite it)
        self.default_asm = "main"                    # assembly for parts placed without one (a wheeled
                                                     # sculpt sets its own vehicle assembly while it builds)

    # ---------------------------------------------------------------- placement
    def new_step(self):
        self.step += 1

    def make(self, pid, color, i, L, k, yaw=0, frame=MAIN, tag="", asm=None):
        asm = asm or self.default_asm
        P = pdef(pid)
        Ry = YAW[yaw]
        w, d = (P.d, P.w) if yaw in (90, 270) else (P.w, P.d)
        if pid in ORIGIN_PARTS:
            ox, oz = 20 * i + 10, 20 * k + 10
        else:
            off = mul(Ry, (-P.cx, 0, -P.cz))
            ox, oz = 20 * i + 10 * w + off[0], 20 * k + 10 * d + off[2]
        oy = -8 * L if P.bottom else -8 * (L + P.h)
        loc = mul(frame.R, (ox, oy, oz))
        pos = (frame.O[0] + loc[0], frame.O[1] + loc[1], frame.O[2] + loc[2])
        M = mm(frame.R, Ry)
        return self._finish(P, color, pos, M, tag, asm)

    def _finish(self, P, color, pos, M, tag, asm, host=None):
        # attached details (glass, door leaf, wheels) use their exact measured extent
        (bx0, bx1), (by0, by1), (bz0, bz1) = P.bbox if host is not None else P.body_box()
        corners = [mul(M, (x, y, z)) for x in (bx0, bx1) for y in (by0, by1) for z in (bz0, bz1)]
        q = Placed()
        q.pid, q.color, q.pos, q.mat, q.tag, q.step, q.asm, q.host = P.pid, color, pos, M, tag, self.step, asm, host
        q.src = self.src
        q.box = tuple((min(c[a] for c in corners) + pos[a], max(c[a] for c in corners) + pos[a]) for a in range(3))
        r1 = lambda v: (round(v[0], 1), round(v[1], 1), round(v[2], 1))
        q.studs = []
        for sp, sd in P.studs:
            wp = mul(M, sp)
            q.studs.append((r1((pos[0] + wp[0], pos[1] + wp[1], pos[2] + wp[2])), tuple(round(c) for c in mul(M, sd))))
        nrm = tuple(round(c) for c in mul(M, (0, 1, 0)))
        q.recv = []
        for rp in P.recv:
            wp = mul(M, rp)
            q.recv.append((r1((pos[0] + wp[0], pos[1] + wp[1], pos[2] + wp[2])), nrm))
        return q

    def add(self, q, cells=None):
        idx = len(self.parts)
        self.parts.append(q)
        for (p, d) in q.studs:
            self.studmap[p].append((idx, d))
        for key in self._buckets(q.box):
            self._hash[key].append(idx)
        for c in cells or ():
            self.occ[c] = idx
        return idx

    def place(self, pid, color, i, L, k, yaw=0, frame=MAIN, tag="", asm=None):
        q = self.make(pid, color, i, L, k, yaw, frame, tag, asm)
        cells = None
        if frame is MAIN and pid not in ORIGIN_PARTS:
            P = pdef(pid)
            w, d = (P.d, P.w) if yaw in (90, 270) else (P.w, P.d)
            cells = [(i + a, l, k + b) for a in range(w) for b in range(d) for l in range(L, L + P.h)]
        self.add(q, cells)
        for plate, offset, fyaw in HOLLOW_END.get(pid, ()):
            self.attach(plate, color, q, offset, YAW[fyaw], tag="filler")
        return q

    def attach(self, pid, color, host: Placed, offset, rel=I3, tag=""):
        """A part joined to `host` by a non-stud connection (glass in a frame,
        door on hinges, wheel on a pin), positioned relative to the host."""
        hidx = self.parts.index(host)
        w = mul(host.mat, offset)
        pos = (host.pos[0] + w[0], host.pos[1] + w[1], host.pos[2] + w[2])
        q = self._finish(pdef(pid), color, pos, mm(host.mat, rel), tag, host.asm, host=hidx)
        idx = self.add(q)
        self.links.append((hidx, idx))
        return q

    # ---------------------------------------------------------------- queries
    @staticmethod
    def _buckets(box):
        (x0, x1), (y0, y1), (z0, z1) = box
        for bx in range(int(x0 // 40), int(x1 // 40) + 1):
            for by in range(int(y0 // 24), int(y1 // 24) + 1):
                for bz in range(int(z0 // 40), int(z1 // 40) + 1):
                    yield (bx, by, bz)

    @staticmethod
    def _overlap(b, c, tol=0.6):
        return all(min(b[a][1], c[a][1]) - max(b[a][0], c[a][0]) > tol for a in range(3))

    def fits(self, q):
        seen = set()
        for key in self._buckets(q.box):
            for m in self._hash.get(key, ()):
                if m not in seen:
                    seen.add(m)
                    if self._overlap(q.box, self.parts[m].box):
                        return False
        return True

    def supports(self, q):
        out = set()
        for (p, nrm) in q.recv:
            want = (-nrm[0], -nrm[1], -nrm[2])
            for (m, d) in self.studmap.get(p, ()):
                if d == want:
                    out.add(m)
        return out


    def rollback(self, n0):
        del self.parts[n0:]
        self.links = [(a, b) for (a, b) in self.links if a < n0 and b < n0]
        self.occ = {c: i for c, i in self.occ.items() if i < n0}
        self._reindex()

    def remove(self, idxs):
        """Delete parts anywhere in the list (their attached details too) and
        renumber everything that refers to part indices."""
        idxs = set(idxs)
        idxs |= {i for i, q in enumerate(self.parts) if q.host in idxs}
        keep = [i for i in range(len(self.parts)) if i not in idxs]
        new = {old: n for n, old in enumerate(keep)}
        self.parts = [self.parts[i] for i in keep]
        for q in self.parts:
            if q.host is not None:
                q.host = new[q.host]
        self.links = [(new[a], new[b]) for (a, b) in self.links if a in new and b in new]
        self.occ = {c: new[i] for c, i in self.occ.items() if i in new}
        self._reindex()

    def _reindex(self):
        self.studmap = defaultdict(list)
        self._hash = defaultdict(list)
        for idx, q in enumerate(self.parts):
            for (p, d) in q.studs:
                self.studmap[p].append((idx, d))
            for key in self._buckets(q.box):
                self._hash[key].append(idx)

    # ---------------------------------------------------------------- checks
    def collisions(self):
        hits, seen = [], set()
        for key, members in self._hash.items():
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    m, n = members[a], members[b]
                    if (m, n) in seen:
                        continue
                    seen.add((m, n))
                    p, q = self.parts[m], self.parts[n]
                    if p.host == n or q.host == m or (p.host is not None and p.host == q.host):
                        continue     # a detail vs its own host, or two details on one host (rim + tyre)
                    tol = 2.0 if (p.host is not None or q.host is not None) else 0.6   # hinge / pin play
                    if self._overlap(p.box, q.box, tol):
                        hits.append((m, n))
        return hits

    def graph(self):
        adj = defaultdict(set)
        for n, q in enumerate(self.parts):
            for (p, nrm) in q.recv:
                want = (-nrm[0], -nrm[1], -nrm[2])
                for (m, d) in self.studmap.get(p, ()):
                    if m != n and d == want:
                        adj[n].add(m)
                        adj[m].add(n)
        for a, b in self.links:
            adj[a].add(b)
            adj[b].add(a)
        return adj

    def is_one_piece(self, idxs):
        """Are these parts all stud/link-connected to each other (ignoring
        whatever else they touch)?"""
        idxs = set(idxs)
        if not idxs:
            return True
        adj = self.graph()
        start = next(iter(idxs))
        seen, stack = {start}, [start]
        while stack:
            n = stack.pop()
            for m in adj[n]:
                if m in idxs and m not in seen:
                    seen.add(m)
                    stack.append(m)
        return seen == idxs

    def components(self):
        adj = self.graph()
        seen, comps = set(), []
        for s in range(len(self.parts)):
            if s in seen:
                continue
            comp, stack = [], [s]
            seen.add(s)
            while stack:
                n = stack.pop()
                comp.append(n)
                for m in adj[n]:
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
            comps.append(comp)
        comps.sort(key=len, reverse=True)
        return comps, adj

    # ---------------------------------------------------------------- output
    def ldr(self):
        fmt = lambda v: str(int(round(v))) if abs(v - round(v)) < 1e-6 else f"{v:.3f}".rstrip("0").rstrip(".")
        lines = [f"0 {self.title}", f"0 Name: {self.title}.ldr", "0 Author: BrickForgerAI designer",
                 "0 !LDRAW_ORG Unofficial_Model", "0 BFC CERTIFY CCW", ""]
        cur = None
        for q in sorted(self.parts, key=lambda q: q.step):
            if cur is not None and q.step != cur:
                lines.append("0 STEP")
            cur = q.step
            lines.append(f"1 {q.color} {fmt(q.pos[0])} {fmt(q.pos[1])} {fmt(q.pos[2])} "
                         f"{' '.join(fmt(v) for v in q.mat)} {q.pid}.dat")
        lines.append("0 STEP")
        return "\n".join(lines) + "\n"


# ==================================================================== tiling
BRICKS = [((6, 2), "2456"), ((4, 2), "3001"), ((3, 2), "3002"), ((2, 2), "3003"), ((6, 1), "3009"),
          ((4, 1), "3010"), ((3, 1), "3622"), ((2, 1), "3004"), ((1, 1), "3005")]
PLATES = [((4, 4), "3031"), ((8, 2), "3034"), ((6, 2), "3795"), ((4, 2), "3020"), ((3, 2), "3021"),
          ((2, 2), "3022"), ((8, 1), "3460"), ((6, 1), "3666"), ((4, 1), "3710"), ((3, 1), "3623"),
          ((2, 1), "3023"), ((1, 1), "3024")]
TILES = [((4, 2), "87079"), ((2, 2), "3068b"), ((4, 1), "2431"), ((3, 1), "63864"), ((2, 1), "3069b"),
         ((1, 1), "3070b")]
HIDDEN_COLOR = 0


def options(sizes, prefer):
    out = []
    for (a, b), pid in sizes:
        pair = [((a, b), 0), ((b, a), 90)] if a != b else [((a, b), 0)]
        if prefer == "z":
            pair.reverse()
        out += [(dims, yaw, pid) for dims, yaw in pair]
    return out


def tile_level(D, cells, L, sizes, prefer="x", frame=MAIN, to_frame=None, tag="", three=None,
               bricks=None, rng=None, mirror=(1, 1), asm=None):
    """Fill {(u, v): colour-or-None} at one level.  None = hidden cell, may take
    any colour.  Each piece is scored by real stud support: sitting on two
    different parts (bridging, like staggered brickwork) beats one, which beats
    none; then bigger wins.  `three` maps cells where a 3-plate part may start
    to the set of colours those 3 levels need.  Returns cells given 3-plate parts."""
    mu, mv = mirror
    base_map = to_frame or (lambda u, v, w, d: (u, v))
    if mirror != (1, 1):
        def mapper(u, v, w, d):
            return base_map(u if mu == 1 else -(u + w - 1), v if mv == 1 else -(v + d - 1), w, d)
        cells = {(mu * u, mv * v): c for (u, v), c in cells.items()}
        three = {(mu * u, mv * v): s for (u, v), s in three.items()} if three else three
    else:
        mapper = base_map
    todo = dict(cells)
    kinds = [(o, 1) for o in options(sizes, prefer)]
    if bricks and three:
        kinds = [(o, 3) for o in options(bricks, prefer)] + kinds
    tall = set()
    # Most-constrained cells first (edges, 1-wide ribs, overhang tips): they get
    # to claim a partner cell before a big interior piece takes it.  A piece may
    # extend from the cell in any direction (the cell can be any of its corners).
    nb4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
    degree = {c: sum((c[0] + a, c[1] + b) in todo for a, b in nb4) for c in todo}
    # A retry (rng set) jitters the order itself, not just tie-breaks: with a
    # strict corners-first order every retry anchors pieces at the same places,
    # so seams that line up with the layer below (a floating car body split in
    # two) come back identically every time.
    jitter = {c: rng.random() * 2.5 for c in todo} if rng else {}
    order = sorted(todo, key=lambda c: (degree[c] + jitter.get(c, 0), c[1], c[0]))
    for (u, v) in order:
        if (u, v) not in todo:
            continue
        best = None
        for ((w, d), yaw, pid), h in kinds:
            for (ou, ov) in {(0, 0), (w - 1, 0), (0, d - 1), (w - 1, d - 1)}:
                u0, v0 = u - ou, v - ov
                blk = [(u0 + a, v0 + b) for a in range(w) for b in range(d)]
                if not all(c in todo for c in blk):
                    continue
                if h == 3:
                    if not all(c in three for c in blk):
                        continue
                    cols = set().union(*(three[c] for c in blk))
                else:
                    cols = {todo[c] for c in blk} - {None}
                if len(cols) > 1:
                    continue
                col = next(iter(cols)) if cols else HIDDEN_COLOR
                i, k = mapper(u0, v0, w, d)
                q = D.make(pid, col, i, L, k, yaw=yaw, frame=frame, tag=tag, asm=asm)
                # crossing courses: pieces lying along this level's preferred axis win,
                # so alternate levels tie parallel strips (and thin ribs) together
                along = 1 if (w >= d if prefer == "x" else d >= w) else 0
                key = (min(len(D.supports(q)), 2), along, w * d * h, rng.random() if rng else 0)
                if best is None or key > best[0]:
                    best = (key, pid, col, i, k, yaw, blk, h)
        _, pid, col, i, k, yaw, blk, h = best
        D.place(pid, col, i, L, k, yaw=yaw, frame=frame, tag=tag, asm=asm)
        for c in blk:
            del todo[c]
            if h == 3:
                tall.add((mu * c[0], mv * c[1]))
    return tall


def verified(D, attempt, tries=40, standalone=False):
    """Self-repair: run `attempt(rng, mirror, flip)` until every part it adds is
    stud-connected (to the rest of the model, or -- standalone -- to each
    other as one separate piece); failed attempts are rolled back and retried
    with a different scan order.  Returns the successful attempt, or -1."""
    n0 = len(D.parts)
    for t in range(tries):
        rng = random.Random(t) if t else None
        mirror = [(1, 1), (-1, 1), (1, -1), (-1, -1)][t % 4]
        attempt(rng, mirror, t % 8 >= 4)
        comps, _ = D.components()
        new = set(range(n0, len(D.parts)))
        ok = any(new <= set(c) for c in comps) if standalone else new <= set(comps[0])
        if ok:
            return t
        D.rollback(n0)
    attempt(None, (1, 1), False)       # keep the best-effort layout; the checker will report it
    return -1
