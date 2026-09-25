"""Interpreter for the compact design language (.bfd) the designer model
writes.  The model states shape, colour and intent; everything brick-level
(which parts, orientation, slopes, SNOT anchors, interlocking, repair) is done
here.  Nothing in a spec is executed as code.  See PROMPT.md for the language.

Category builders: `sculpt` (organic shapes, animals, aircraft, boats: built
from boxes, balls and tapered cylinders), `building` (walls, floors,
overhangs, windows, doors, roofs), `vehicle` (road vehicles)."""
from __future__ import annotations

import math
import re
from collections import defaultdict, deque

from .engine import (BRICKS, COLORS, HIDDEN_COLOR, I3, MAIN, PLATES, TILES, YAW, Design, Frame, mul, tile_level,
                     verified, yaw_pointing, pdef)


class SpecError(Exception):
    pass


# Hard bounds on what a spec can ask for.  Specs are written by a model the
# user can steer through their prompt, so nothing here may allow unbounded
# work: without these, one line like `ball 0 0 0 5000 5000 5000` or
# `stack 3001 red 0 0 0 1000000` would tie up a worker for hours.  Real specs
# stay far inside them (largest sculpt seen in testing: ~9,400 cells on a
# 32x32 baseplate).
LIMITS = dict(
    coord=512,            # |x|, |z| in studs, |level| in plates
    span=256,             # cells in one a..b range
    rect_cells=4096,      # cells in one x0..x1,z0..z1 rectangle (64 x 64)
    region_cells=4096,    # cells in a whole region (rect +rect -rect ...)
    radius=64,            # ball / cyl radius in studs (ball y radius in plates: 2.5x)
    shape_cells=25000,    # cells one shape may cover
    sculpt_cells=25000,   # cells in one sculpt
    total_cells=60000,    # cells across every sculpt in the spec
    count=100,            # stack / row repeats
    floors=6,             # building floors
    courses=40,           # brick courses in `bricks` / `walls`
)


def _bounded(v, limit, what):
    if abs(v) > limit:
        raise SpecError(f"{what} {v} is out of range (limit {limit})")
    return v


# ================================================================ parsing helpers
def rng_(tok):
    """`a..b` inclusive, or a single `a`.  Cells are whole studs/plates, so a
    decimal end (the model thinking in continuous units) rounds to the
    nearest cell rather than failing the whole line."""
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(?:\.\.(-?\d+(?:\.\d+)?))?", tok)
    if not m:
        raise SpecError(f"bad range '{tok}'")
    a = _bounded(math.floor(float(m.group(1)) + 0.5), LIMITS["coord"], "coordinate")
    b = _bounded(math.floor(float(m.group(2)) + 0.5), LIMITS["coord"], "coordinate") if m.group(2) is not None else a
    if abs(b - a) + 1 > LIMITS["span"]:
        raise SpecError(f"range '{tok}' is too long (limit {LIMITS['span']} cells)")
    return range(min(a, b), max(a, b) + 1)


def rect(tok):
    try:
        xs, zs = tok.split(",")
    except ValueError:
        raise SpecError(f"bad rect '{tok}' (want x0..x1,z0..z1)")
    xr, zr = rng_(xs), rng_(zs)
    if len(xr) * len(zr) > LIMITS["rect_cells"]:
        raise SpecError(f"rect '{tok}' is too big (limit {LIMITS['rect_cells']} cells)")
    return {(x, z) for x in xr for z in zr}


_RANGE = r"-?\d+(?:\.\d+)?(?:\.\.-?\d+(?:\.\d+)?)?"
_RECT_TERM = re.compile(rf"({_RANGE},{_RANGE})")
_FIRST_TERM = re.compile(rf"\+?({_RANGE},{_RANGE})")
_NEXT_TERM = re.compile(rf"([+-])({_RANGE},{_RANGE})")
REGION_HELP = "want x0..x1,z0..z1 then optional +x0..x1,z0..z1 / -x0..x1,z0..z1 terms"


def region_terms(toks):
    """`x0..x1,z0..z1 +rect -rect ...`.  Terms may also be written joined
    (`0..3,0..3+5..6,0..1-1..1,1..1`) or with a spaced sign (`+ rect`): after
    the first rect every term starts with its sign, so either form is
    unambiguous (the first rect may start with a negative coordinate)."""
    out, first, sign = set(), True, None
    for t in toks:
        if t in ("+", "-"):
            sign = t
            continue
        pos = 0
        while pos < len(t):
            if pos == 0 and sign:
                m, op = _RECT_TERM.match(t), sign
            elif first:
                m, op = _FIRST_TERM.match(t, pos), "+"
            else:
                m = _NEXT_TERM.match(t, pos)
                op = m.group(1) if m else None
            if not m:
                raise SpecError(f"bad region '{' '.join(toks)}' ({REGION_HELP})")
            cells = rect(m.group(m.lastindex))
            out = out - cells if op == "-" else out | cells
            if len(out) > LIMITS["region_cells"]:
                raise SpecError(f"region is too big (limit {LIMITS['region_cells']} cells)")
            pos, first, sign = m.end(), False, None
    if first:
        raise SpecError(f"missing region ({REGION_HELP})")
    return out


def color(tok):
    cols = []
    for p in tok.split("|"):
        if p.isdigit():
            cols.append(int(p))
        elif p in COLORS:
            cols.append(COLORS[p])
        else:
            raise SpecError(f"unknown colour '{p}'")
    return cols


def pick(cols, x, z, seed=0):
    if isinstance(cols, dict):               # a precomputed field (gradient): cell -> colour
        return cols[(x, z)]
    if len(cols) == 1:
        return cols[0]
    h = (x * 374761393 + z * 668265263 + seed * 1442695041) & 0xFFFFFF
    return cols[(h >> 8) % len(cols)]


def hash01(*v):
    """Deterministic noise in [0, 1) for integer coordinates."""
    h = 2166136261
    for a in v:
        h = ((h ^ (a & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
        h ^= h >> 15
        h = (h * 2246822519) & 0xFFFFFFFF
        h ^= h >> 13
    return (h & 0xFFFFFF) / float(1 << 24)


GRADIENT_AXES = ("x", "y", "z", "-x", "-y", "-z")


def color_stops(tok):
    """`a>b>c`: gradient stops, each a colour or a mix (`a|b`); at most 6."""
    stops = [color(s) for s in tok.split(">")]
    if len(stops) > 6:
        raise SpecError("a gradient has at most 6 colours")
    return stops


def gradient(stops, cells, pos, blend=0.6, seed=0):
    """Colour per cell for a gradient: `pos(cell)` is the cell's coordinate
    along the gradient; stops are spread evenly from the lowest to the
    highest.  Between two stops the middle `blend` fraction mixes them with
    shifting odds (builders' 80/20 ... 20/80 feathering, by seeded noise),
    so bands read as a natural transition, not stripes."""
    cells = list(cells)
    if len(stops) == 1:
        return {c: pick(stops[0], c[0], c[-1], seed) for c in cells}
    ps = {c: pos(c) for c in cells}
    lo, hi = min(ps.values(), default=0), max(ps.values(), default=0)
    k = len(stops) - 1
    out = {}
    for c in cells:
        t = (ps[c] - lo) / (hi - lo) if hi > lo else 0.0
        s = min(int(t * k), k - 1)
        u = t * k - s
        p = min(1.0, max(0.0, (u - (1 - blend) / 2) / blend)) if blend > 0 else float(u >= 0.5)
        stop = stops[s + 1] if hash01(*c, seed) < p else stops[s]
        out[c] = pick(stop, c[0], c[-1], seed + 7)
    return out


def recolour(D, n0, field, hidden=frozenset()):
    """Gradient cells are tiled as "any colour" so dithering never splits the
    tiling into small, badly-interlocked pieces; afterwards every part placed
    since `n0` that covers only gradient (or hidden) cells takes the majority
    colour of its cells in `field` -- choosing the pieces first and colouring
    each to follow the gradient, as a builder would."""
    cols = defaultdict(list)
    mixed = set()
    for c, i in D.occ.items():
        if i < n0:
            continue
        if c in field:
            cols[i].append(field[c])
        elif c not in hidden:
            mixed.add(i)
    for i, cs in cols.items():
        if i in mixed:
            continue
        counts = defaultdict(int)
        for col in cs:
            counts[col] += 1
        best = max(counts.values())
        tied = sorted(col for col, n in counts.items() if n == best)
        D.parts[i].color = tied[int(hash01(i, len(cs)) * len(tied))]


def axis_pos(axis, dims="xyz"):
    """pos(cell) along `axis` for cells shaped like `dims` ("xyz" or "xz")."""
    if axis not in GRADIENT_AXES or axis.lstrip("-") not in dims:
        raise SpecError(f"gradient axis must be one of {', '.join(a for a in GRADIENT_AXES if a.lstrip('-') in dims)}")
    i, sign = dims.index(axis.lstrip("-")), -1 if axis.startswith("-") else 1
    return lambda c: sign * c[i]


def split_kw(toks):
    pos, kw = [], {}
    for t in toks:
        if "=" in t:
            k, v = t.split("=", 1)
            kw[k] = v
        else:
            pos.append(t)
    return pos, kw


def rot_(kw):
    r = int(kw.get("rot", 0))
    if r not in YAW:
        raise SpecError(f"rot must be 0/90/180/270, got {r}")
    return r


# ================================================================ shapes
# x, z in studs, y in plates (relative to the sculpt base).  Continuous
# coordinates: the centre of cell (x, y, z) is (x+.5, y+.5, z+.5), so a shape
# centred on z=0 is symmetric about the model's centre line.
def shape_cells(kind, p):
    cells = _shape_cells(kind, p)
    if len(cells) > LIMITS["shape_cells"]:
        raise SpecError(f"{kind} is too big (limit {LIMITS['shape_cells']} cells)")
    return cells


def _shape_cells(kind, p):
    R = LIMITS["radius"]
    try:
        if kind in ("col", "box"):
            zs = rng_(p[2]) if len(p) > 2 else rng_("-2..1")
            xs, ys = rng_(p[0]), rng_(p[1])
            if len(xs) * len(ys) * len(zs) > LIMITS["shape_cells"]:
                raise SpecError(f"{kind} is too big (limit {LIMITS['shape_cells']} cells)")
            return {(x, y, z) for x in xs for y in ys for z in zs}
        if kind == "ball":
            cx, cy, cz, rx, ry, rz = (float(v) for v in p[:6])
            for v in (cx, cy, cz):
                _bounded(v, LIMITS["coord"], "centre")
            for v, lim in ((rx, R), (ry, 2.5 * R), (rz, R)):
                _bounded(v, lim, "radius")
            out = set()
            for x in range(math.floor(cx - rx) - 1, math.ceil(cx + rx) + 1):
                for y in range(math.floor(cy - ry) - 1, math.ceil(cy + ry) + 1):
                    for z in range(math.floor(cz - rz) - 1, math.ceil(cz + rz) + 1):
                        if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 + ((z + .5 - cz) / rz) ** 2 <= 1:
                            out.add((x, y, z))
            return out
        if kind == "cyl":
            axis, span, c1, c2 = p[0], rng_(p[1]), float(p[2]), float(p[3])
            r0 = float(p[4])
            r1 = float(p[5]) if len(p) > 5 else r0
            for v in (c1, c2):
                _bounded(v, LIMITS["coord"], "centre")
            for v in (r0, r1):
                _bounded(v, R, "radius")
            out = set()
            n = max(1, span[-1] - span[0])
            for t in span:
                r = r0 + (r1 - r0) * (t - span[0]) / n
                if r <= 0:
                    continue
                if axis == "x":            # c1 = y centre (plates), c2 = z centre
                    for y in range(math.floor(c1 - 2.5 * r) - 1, math.ceil(c1 + 2.5 * r) + 1):
                        for z in range(math.floor(c2 - r) - 1, math.ceil(c2 + r) + 1):
                            if ((y + .5 - c1) / (2.5 * r)) ** 2 + ((z + .5 - c2) / r) ** 2 <= 1:
                                out.add((t, y, z))
                elif axis == "y":          # c1 = x centre, c2 = z centre
                    for x in range(math.floor(c1 - r) - 1, math.ceil(c1 + r) + 1):
                        for z in range(math.floor(c2 - r) - 1, math.ceil(c2 + r) + 1):
                            if ((x + .5 - c1) / r) ** 2 + ((z + .5 - c2) / r) ** 2 <= 1:
                                out.add((x, t, z))
                elif axis == "z":          # c1 = x centre, c2 = y centre (plates)
                    for x in range(math.floor(c1 - r) - 1, math.ceil(c1 + r) + 1):
                        for y in range(math.floor(c2 - 2.5 * r) - 1, math.ceil(c2 + 2.5 * r) + 1):
                            if ((x + .5 - c1) / r) ** 2 + ((y + .5 - c2) / (2.5 * r)) ** 2 <= 1:
                                out.add((x, y, t))
                else:
                    raise SpecError(f"cyl axis must be x, y or z, got '{axis}'")
            return out
    except (IndexError, ValueError):
        raise SpecError(f"bad {kind} arguments: {' '.join(p)}")
    raise SpecError(f"unknown shape '{kind}'")


NB6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def hollowed(core, shell):
    """Keep cells within `shell` studs of the outside sideways, or within
    2*shell+2 plates of it vertically.  The thick vertical crust leaves
    overlapping layers under stepped curved caps, so neighbouring steps can
    still be tied together by plates."""
    vshell = 2 * shell + 2
    keep = set()
    by_level = defaultdict(set)
    for (x, L, z) in core:
        by_level[L].add((x, z))
    for L, cells in by_level.items():
        dist, dq = {}, deque()
        for (x, z) in cells:
            if any((x + a, z + b) not in cells for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                dist[(x, z)] = 1
                dq.append((x, z))
        while dq:
            c = dq.popleft()
            for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + a, c[1] + b)
                if n in cells and n not in dist:
                    dist[n] = dist[c] + 1
                    dq.append(n)
        keep |= {(x, L, z) for (x, z), d in dist.items() if d <= shell}
    for (x, L, z) in core:
        up = next(k for k in range(1, 10 ** 6) if (x, L + k, z) not in core)
        down = next(k for k in range(1, 10 ** 6) if (x, L - k, z) not in core)
        if min(up, down) <= vshell:
            keep.add((x, L, z))
    return {c: col for c, col in core.items() if c in keep}


def line_caps(T, depth, allowed):
    """Curved-slope caps along one line of columns.  T: position -> top level
    (exclusive).  Returns caps [(start, run, height, kind, dir, level)] and
    the positions they cover.  dir = direction the tall end points."""
    caps, covered = [], set()
    ps = sorted(p for p in T if p in allowed)
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[j] + 1 and T[ps[j + 1]] == T[ps[i]]:
            j += 1
        a, b, t = ps[i], ps[j], T[ps[i]]
        p = b - a + 1
        dl, dr = t - T.get(a - 1, -10 ** 6), t - T.get(b + 1, -10 ** 6)
        dep = min(depth[q] for q in range(a, b + 1))
        spec = []
        if dl >= 2 and dr >= 2:
            if p == 4:
                spec.append((a, 4, 2, "93273", 0))
            elif p == 1:
                spec.append((a, 1, 2, "49307", 0))
            else:
                rl, rr = (2 if p >= 5 else 1), (2 if p >= 4 else 1)
                spec += [(a, rl, 2, "slope", +1), (b - rr + 1, rr, 2, "slope", -1)]
        elif dr >= 2:
            r, h = (min(p, 4), 3) if dr >= 3 and p >= 3 else (min(p, 2), 2)
            spec.append((b - r + 1, r, h, "slope", -1))
        elif dl >= 2:
            r, h = (min(p, 4), 3) if dl >= 3 and p >= 3 else (min(p, 2), 2)
            spec.append((a, r, h, "slope", +1))
        for (s0, r, h, kind, d) in spec:
            if dep >= h + 1:
                caps.append((s0, r, h, kind, d, t - h))
                covered |= set(range(s0, s0 + r))
        i = j + 1
    return caps, covered


SLOPE2 = {1: ("54200", "85984"), 2: ("11477", "15068")}
SLOPE3 = {3: ("50950", "24309"), 4: ("61678", "93606")}
BRICK_RUN = {6: "3009", 4: "3010", 3: "3622", 2: "3004", 1: "3005"}
L_FRAME = (1, 0, 0, 0, 0, -1, 0, 1, 0)      # SNOT frame on a -z face (studs point -z)
R_FRAME = (-1, 0, 0, 0, 0, -1, 0, -1, 0)    # SNOT frame on a +z face
# A tile/plate clicked onto a side stud pointing along the host's local -z: its
# up (-y) turns to -z, its x stays x (a proper rotation).
SIDE_STUD_REL = (1, 0, 0, 0, 0, -1, 0, 1, 0)


# Wheels for `wheels` in a sculpt, all on a 2x2 plate with wheel pins (4600).
# lift: plates the body's underside sits above the surface so the tyre rests on
# it (pin centre 5 LDU under the plate top; tyre radius 18 / 25 LDU).
# rim_x / tyre_x: LDU from the plate centre along the pin (the plate is 40 wide;
# the small rim is symmetric, the large one is 28 LDU deep with its origin 20
# from the inner face, so the tyre sits 6 LDU inboard of the rim's origin).
WHEELS = {
    "small": dict(rim="4624", tyre="3641", rim_x=30, tyre_x=30, lift=3),     # the `vehicle` command's wheel
    "large": dict(rim="6014b", tyre="6015", rim_x=42, tyre_x=36, lift=4),
}


def sculpt_cells(spec):
    """The cells a sculpt occupies (adds minus cuts), in main-frame levels."""
    S, cells = spec["base"], set()
    for op, cs in spec["shapes"]:
        shifted = {(x, S + y, z) for (x, y, z) in cs}
        cells = cells | shifted if op == "add" else cells - shifted
    return cells


def studs_up_details(core, spec, S, sides=("L", "R")):
    """sideways=off: panel markings (`ppaint`) and eyes become coloured cells
    in the outermost studs-up surface on each flank (min / max z), instead of
    SNOT panels and side-stud eye bricks.  An eye is a pupil 1 stud wide and
    2 plates tall, fully ringed (sides, above, below) in the ring colour, so
    it reads even when the pupil matches the body colour."""
    core = dict(core)
    flank = {}
    for (x, L, z) in core:
        lo, hi = flank.get((x, L), (z, z))
        flank[(x, L)] = (min(lo, z), max(hi, z))

    def paint(x, L, col):
        if (x, L) in flank:
            lo, hi = flank[(x, L)]
            for z in ([lo] if "L" in sides else []) + ([hi] if "R" in sides else []):
                core[(x, L, z)] = col

    for (col, xs, y0, y1) in spec["ppaint"]:
        for x in xs:
            for L in range(S + y0, S + y1 + 1):
                paint(x, L, col)
    for e in spec["eyes"]:
        y = S + e["y"]
        for L in range(y - 1, y + 3):
            for dx in (-1, 0, 1):
                paint(e["x"] + dx, L, e["pupil"] if dx == 0 and y <= L <= y + 1 else e["ring"])
    return core


def tile_run(length, odd):
    seq, left = [], length
    if odd and length >= 4:
        seq.append(3 if length % 2 else 2)
        left -= seq[0]
    while left:
        for n in (6, 4, 3, 2, 1):
            if n <= left:
                seq.append(n)
                left -= n
                break
    return seq


def _lattice(D, cells, L, pid, w, d, phase):
    """Place `pid` (w x d studs, yaw 0) on a grid with offset `phase` from the
    region's min corner wherever a whole piece fits in single-colour free
    cells; returns the cells still to fill."""
    rest = dict(cells)
    if not rest:
        return rest
    us, vs = [c[0] for c in rest], [c[1] for c in rest]
    for u in range(min(us) + phase[0] % w - w, max(us) + 1, w):
        for v in range(min(vs) + phase[1] % d - d, max(vs) + 1, d):
            blk = [(u + a, v + b) for a in range(w) for b in range(d)]
            if all(c in rest for c in blk) and len({rest[c] for c in blk}) == 1:
                col = rest[blk[0]]
                D.place(pid, HIDDEN_COLOR if col is None else col, u, L, v)
                for c in blk:
                    del rest[c]
    return rest


# ================================================================ interpreter
FINISHES = ("tiled", "studs")
SIDEWAYS = ("off", "auto", "more")


class Interp:
    """`finish`: "tiled" covers exposed flat tops with tiles, "studs" leaves
    plates (studs showing) there instead; slopes are unaffected.
    `sideways`: "off" builds no SNOT at all (no panels, no side-stud anchors;
    eyes and panel markings are painted into the studs-up surface instead),
    "auto" and "more" build whatever panels the spec asks for -- they differ
    only in what the designer model is told (see pipeline.user_message)."""

    def __init__(self, finish="tiled", sideways="auto"):
        if finish not in FINISHES:
            raise ValueError(f"finish must be one of {FINISHES}, got {finish!r}")
        if sideways not in SIDEWAYS:
            raise ValueError(f"sideways must be one of {SIDEWAYS}, got {sideways!r}")
        self.finish, self.sideways = finish, sideways
        self.flat = TILES if finish == "tiled" else PLATES     # what covers an exposed flat top
        self.D = Design()
        self.openings = []     # (cells, L0, L1)
        self.errors = []
        self.repairs = []
        self.nasm = 0
        self.cells_used = 0    # across every sculpt, see LIMITS["total_cells"]
        self.stage = []        # cell sets of baseplates/bases: where land is (see water)

    # ---------------------------------------------------------- click-on support
    def expose_studs(self, bottom):
        """Anything about to stand on an engine-chosen smooth finish (the tiles
        or curved-slope caps a sculpt put on its own top) should click on,
        not just rest there: swap those finish parts for plates under the new
        thing's footprint, keeping the smooth finish around it.  `bottom` =
        the new thing's lowest cells (x, L, z).  Hand-placed parts are left
        alone -- only the engine's own finishing is revised."""
        D = self.D
        hit = set()
        for (x, L, z) in bottom:
            i = D.occ.get((x, L - 1, z))
            if i is not None and D.parts[i].tag in ("top", "cap") and D.parts[i].asm == "main":
                hit.add(i)
        if not hit:
            return 0
        cells = defaultdict(dict)                 # L -> {(x, z): colour}
        for c, i in D.occ.items():
            if i in hit:
                cells[c[1]][(c[0], c[2])] = D.parts[i].color
        src = D.src
        D.src = D.parts[next(iter(hit))].src      # the refill belongs to the thing it replaces
        D.remove(hit)
        covered = {(x, z) for (x, L, z) in bottom}
        top_of = {}
        for L in cells:
            for c in cells[L]:
                top_of[c] = max(top_of.get(c, L), L)
        for L in sorted(cells):
            # a removed cell whose top is open air (not under the new thing) keeps a
            # finished top: tiles, or plates when finish=studs; everything else is plates
            exposed = {c: col for c, col in cells[L].items() if L == top_of[c] and c not in covered}
            tile_level(D, {c: col for c, col in cells[L].items() if c not in exposed}, L, PLATES, "x", tag="refill")
            tile_level(D, exposed, L, self.flat, "x", tag="top")
        D.src = src
        self.repairs.append(("click-on", len(hit)))
        return len(hit)

    def expose_for_part(self, pid, x, L, z, yaw=0):
        P = pdef(pid)
        w, d = (P.d, P.w) if yaw in (90, 270) else (P.w, P.d)
        self.expose_studs({(x + a, L, z + b) for a in range(max(1, w)) for b in range(max(1, d))})

    # ---------------------------------------------------------- simple fills
    def fill(self, kind, L, cols, cells, prefer="x", courses=1, asm=None):
        D = self.D
        self.expose_studs({(c[0], L, c[1]) for c in cells})
        soft = isinstance(cols, dict)             # a gradient: tile as any colour, then recolour
        n0 = len(D.parts)
        field = {}
        if kind in ("tiles", "plates"):
            sizes = self.flat if kind == "tiles" else PLATES
            free = {c: pick(cols, *c) for c in cells if (c[0], L, c[1]) not in D.occ}
            field = {(x, L, z): col for (x, z), col in free.items()}
            tile_level(D, {c: None for c in free} if soft else free, L, sizes, prefer, asm=asm)
        else:
            for n in range(courses):
                lvl = L + 3 * n
                free = {c: pick(cols, *c) for c in cells if all((c[0], lvl + l, c[1]) not in D.occ for l in range(3))}
                field.update({(x, lvl + l, z): col for (x, z), col in free.items() for l in range(3)})
                pr = prefer if n % 2 == 0 else ("z" if prefer == "x" else "x")
                tile_level(D, {c: None for c in free} if soft else free, lvl, [], pr,
                           three={c: set() if soft else {col} for c, col in free.items()}, bricks=BRICKS, asm=asm)
        if soft:
            recolour(D, n0, field)

    def slab(self, cells, L, cols, second):
        """Two crossed layers at L and L+1 (plates, then `second`: PLATES or a
        flat finish): floor slabs and flat roofs.  Over a hollow interior only
        the rim rests on walls, and on a wide footprint (32 studs) the two
        tilings' seams can line up into a closed island that touches nothing
        else -- so it is verified and retried like a base."""
        D = self.D
        self.expose_studs({(c[0], L, c[1]) for c in cells})
        top = ("3031", 4, 4) if second is PLATES else ("87079", 4, 2)
        # Staggered lattice: big pieces on a grid, the upper layer offset by 2
        # studs so each of its pieces bridges up to four below (brick bond, in
        # plan).  Connected by construction, and big pieces keep the count low
        # -- jittered retries also connect but roughly double the parts.
        phases = [((0, 0), (2, 2)), ((0, 0), (2, 1)), ((1, 1), (3, 3)), ((2, 2), (0, 0))]

        def attempt(r, mirror, flip):
            (p0, p1) = phases[0] if r is None else phases[r.randrange(len(phases))]
            for n, ((pid, w, d), phase, sizes, pref) in enumerate(((("3031", 4, 4), p0, PLATES, "x"),
                                                                   (top, p1, second, "z"))):
                free = {c: pick(cols, *c) for c in cells if (c[0], L + n, c[1]) not in D.occ}
                rest = _lattice(D, free, L + n, pid, w, d, phase)
                tile_level(D, rest, L + n, sizes, pref, rng=r)
        t = verified(D, attempt, tries=12)
        if t:
            self.repairs.append(("slab", t))

    def water(self, cells, L, bed, surface, foam, ripples):
        """Water (TECHNIQUES.md item 2): a bed of plates at L whose colour
        deepens with distance from the shore, a smooth transparent surface of
        tiles at L+1 (clear-ish at the shore), a few exposed transparent round
        studs as ripples and white round plates as foam along the shore.
        Shore = a neighbouring cell on the stage (baseplate/base) or already
        built at this height; an edge that runs off the stage is open water."""
        D = self.D
        self.expose_studs({(c[0], L, c[1]) for c in cells})
        stage = set().union(*self.stage) if self.stage else set()

        def land(c):
            return c in stage or any((c[0], L + l, c[1]) in D.occ for l in (0, 1))
        nb4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
        dist, dq = {}, deque()
        for c in cells:
            if any((c[0] + a, c[1] + b) not in cells and land((c[0] + a, c[1] + b)) for a, b in nb4):
                dist[c] = 0
                dq.append(c)
        while dq:
            c = dq.popleft()
            for a, b in nb4:
                n = (c[0] + a, c[1] + b)
                if n in cells and n not in dist:
                    dist[n] = dist[c] + 1
                    dq.append(n)
        if dist:
            depth = lambda c: dist.get(c, max(dist.values()) + 1)
        else:                                     # no shore anywhere: open water, mid depth
            depth = lambda c: 0
            bed = bed[len(bed) // 2:len(bed) // 2 + 1]
        seed = D.src or 0
        free = sorted(c for c in cells if (c[0], L, c[1]) not in D.occ and (c[0], L + 1, c[1]) not in D.occ)
        bed_cols = gradient(bed, free, depth, seed=seed)
        top_cols = gradient(surface, free, depth, blend=1.0, seed=seed + 1)
        shore = {c for c in free if dist and depth(c) == 0}
        dots = {}
        for c in free:
            h = hash01(c[0], c[1], seed + 2)
            if foam is not None and c in shore and h < 0.35:
                dots[c] = foam
            elif c not in shore and h < ripples:
                dots[c] = top_cols[c]

        def attempt(r, mirror, flip):
            tile_level(D, {c: None for c in free}, L, PLATES, "z" if flip else "x", rng=r, mirror=mirror, tag="water")
            for (x, z), col in dots.items():
                D.place("4073", col, x, L + 1, z, tag="water")
            tile_level(D, {c: None for c in free if c not in dots}, L + 1, TILES, "x" if flip else "z", rng=r,
                       mirror=mirror, tag="water")
        n0 = len(D.parts)
        t = verified(D, attempt)
        if t:
            self.repairs.append(("water", t))
        field = {(x, L, z): col for (x, z), col in bed_cols.items()}
        field.update({(x, L + 1, z): col for (x, z), col in top_cols.items() if (x, z) not in dots})
        recolour(D, n0, field)

    def blocked(self, cell, L):
        return any(cell in cells and L < L1 and L + 3 > L0 for cells, L0, L1 in self.openings)

    def walls(self, x0, x1, z0, z1, L0, courses, cols):
        for c in range(courses):
            L = L0 + 3 * c
            own = c % 2 == 0
            ri0, ri1 = (x0, x1) if own else (x0 + 1, x1 - 1)
            sk0, sk1 = (z0 + 1, z1 - 1) if own else (z0, z1)
            lines = [([(x, zz) for x in range(ri0, ri1 + 1)], "x") for zz in (z0, z1)]
            lines += [([(xx, z) for z in range(sk0, sk1 + 1)], "z") for xx in (x0, x1)]
            for cells, axis in lines:
                run = []
                for cell in cells + [None]:
                    if cell is not None and not self.blocked(cell, L) and (cell[0], L, cell[1]) not in self.D.occ:
                        run.append(cell)
                        continue
                    pos = 0
                    for n in tile_run(len(run), odd=c % 2 == 1):
                        cx, cz = run[pos]
                        self.D.place(BRICK_RUN[n], pick(cols, cx * 7 + L, cz * 3 + L), cx, L, cz,
                                     yaw=0 if axis == "x" else 90)
                        pos += n
                    run = []

    def window(self, x, z, axis, L, stack, fcol, gcol):
        yaw = 0 if axis == "x" else 90
        cells = {(x + a, z) if axis == "x" else (x, z + a) for a in range(4)}
        self.openings.append((cells, L, L + 9 * stack))
        for n in range(stack):
            f = self.D.place("60594", fcol, x, L + 9 * n, z, yaw=yaw, tag="window")
            self.D.attach("60603", gcol, f, (0, 8, 0), tag="glass")
        return cells

    def door(self, x, z, axis, L, fcol, lcol):
        yaw = 0 if axis == "x" else 90
        cells = {(x + a, z) if axis == "x" else (x, z + a) for a in range(4)}
        self.openings.append((cells, L, L + 18))
        f = self.D.place("60596", fcol, x, L, z, yaw=yaw, tag="door")
        self.D.attach("60623", lcol, f, (-31, 0, 5), tag="door leaf")
        return cells

    def tree(self, x, z, L, col, trunk):
        self.expose_studs({(x, L, z)})
        self.D.place("3062b", trunk, x, L, z)
        self.D.place("3062b", trunk, x, L + 3, z)
        self.D.place("2435", col, x, L + 6, z, tag="tree")

    def stump(self, x, z, L0, L1, col, band, bands):
        self.expose_for_part("87081", x, L0, z)
        for n, L in enumerate(range(L0, L1, 3)):
            self.D.place("87081", band if n in bands else col, x, L, z)

    def roots(self, x, z, L, col):
        for (dx, dz, yaw) in ((-2, 1, 90), (-2, 3, 90), (4, 2, 270), (4, 0, 270), (1, -2, 0), (2, 4, 180)):
            self.D.place("11477", col, x + dx, L, z + dz, yaw=yaw)

    def scatter(self, pid, cols, cells, L, every, shift, density, seed):
        D = self.D
        for (x, z) in sorted(cells):
            if every:
                if (x + z + shift) % every:
                    continue
            elif ((x * 73856093 ^ z * 19349663 ^ seed * 83492791) & 0xFFFF) / 65536.0 >= density:
                continue
            q = D.make(pid, pick(cols, x, z, seed + 1), x, L, z)
            if D.fits(q) and D.supports(q):
                D.place(pid, q.color, x, L, z)

    def base(self, cells, cols, top, rim):
        """Free-standing display base: two crossed plate layers (one piece),
        optional tile rim; things stand on its top at level 2."""
        D = self.D

        def attempt(r, mirror, flip):
            tile_level(D, {c: pick(cols, *c) for c in cells}, 0, PLATES, "z" if flip else "x", rng=r, mirror=mirror)
            tile_level(D, {c: pick(top or cols, *c, seed=5) for c in cells}, 1, PLATES, "x" if flip else "z",
                       rng=r, mirror=mirror)
        self.repairs.append(("base", verified(D, attempt, standalone=True)))
        if rim is not None:
            xs, zs = [c[0] for c in cells], [c[1] for c in cells]
            ring = {c for c in cells if c[0] in (min(xs), max(xs)) or c[1] in (min(zs), max(zs))}
            tile_level(D, {c: rim for c in ring}, 2, self.flat, "x")

    # ---------------------------------------------------------- buildings
    def building(self, cells, L, kw):
        self.expose_studs({(c[0], L, c[1]) for c in cells})
        xs, zs = sorted({c[0] for c in cells}), sorted({c[1] for c in cells})
        x0, x1, z0, z1 = xs[0], xs[-1], zs[0], zs[-1]
        floors = _bounded(int(kw.get("floors", 2)), LIMITS["floors"], "floors")
        wall = color(kw.get("color", "white"))
        trim = color(kw.get("trim", kw.get("color", "white")))[0]
        style = kw.get("style", "plain")
        jetty = int(kw.get("jetty", 0))
        frame = color(kw.get("frame", "black"))[0]
        glass = color(kw.get("glass", "trans_clear"))[0]
        gap = {"sparse": 3, "normal": 2, "dense": 1, "none": None}[kw.get("windows", "normal")]
        door = kw.get("door", "front")
        if kw.get("base"):
            self.fill("plates", L, color(kw["base"]), {(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)})
            L += 1
        for f in range(floors):
            courses = 6 if f == 0 else 5
            used = set()
            if f == 0 and door != "none":
                mx, mz = (x0 + x1) // 2 - 1, (z0 + z1) // 2 - 1
                spot = {"front": (mx, z0, "x"), "back": (mx, z1, "x"), "left": (x0, mz, "z"), "right": (x1, mz, "z")}[door]
                used |= self.door(*spot[:2], spot[2], L, frame, color(kw.get("leaf", "reddish_brown"))[0])
            posts = {(x0, z0), (x0, z1), (x1, z0), (x1, z1)}
            if gap is not None:
                sides = [((x0 + 1, x1 - 1), z0, "x"), ((x0 + 1, x1 - 1), z1, "x"),
                         ((z0 + 1, z1 - 1), x0, "z"), ((z0 + 1, z1 - 1), x1, "z")]
                for (a, b), fixed, axis in sides:
                    n = b - a + 1
                    k = max(0, (n - 1 + gap) // (4 + gap))
                    start = a + (n - (k * 4 + (k - 1) * gap)) // 2
                    for w in range(k):
                        s = start + w * (4 + gap)
                        cells_w = {(s + i, fixed) if axis == "x" else (fixed, s + i) for i in range(4)}
                        near = {(c[0] + dx, c[1] + dz) for c in used for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
                        if cells_w & near:
                            continue
                        x_, z_ = (s, fixed) if axis == "x" else (fixed, s)
                        used |= self.window(x_, z_, axis, L + 3, 1, frame, glass)
                        ends = [(s - 1, fixed), (s + 4, fixed)] if axis == "x" else [(fixed, s - 1), (fixed, s + 4)]
                        posts |= set(ends)
            if style == "timber":
                for (px, pz) in sorted(posts):
                    if all((px, L + l, pz) not in self.D.occ for l in range(3 * courses)) and (px, pz) not in used:
                        for c in range(courses):
                            self.D.place("3005", trim, px, L + 3 * c, pz)
            self.walls(x0, x1, z0, z1, L, courses, wall)
            L += 3 * courses
            if f < floors - 1:
                x0, x1, z0, z1 = x0 - jetty, x1 + jetty, z0 - jetty, z1 + jetty
                self.slab({(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)}, L, [trim], PLATES)
                L += 2
        roof = kw.get("roof", "gable")
        self.roof(x0, x1, z0, z1, L, roof, kw.get("ridge", "x"),
                  color(kw.get("roofcolor", "dark_bluish_gray"))[0],
                  color(kw.get("gable", kw.get("color", "white")))[0], int(kw.get("overhang", 1)))

    def roof(self, x0, x1, z0, z1, L, kind, ridge, rcol, gcol, o=1):
        X0, X1, Z0, Z1 = x0 - o, x1 + o, z0 - o, z1 + o
        area = {(x, z) for x in range(X0, X1 + 1) for z in range(Z0, Z1 + 1)}
        if kind == "none":
            return
        if kind == "flat":
            self.slab(area, L, [rcol], self.flat)
            return
        cells, heights = set(), {}
        for (x, z) in area:
            if kind == "hip":
                d = min(x - X0, X1 - x, z - Z0, Z1 - z)
            elif ridge == "x":
                d = min(z - Z0, Z1 - z)
            else:
                d = min(x - X0, X1 - x)
            heights[(x, z)] = h = 2 * d + 2
            cells |= {(x, y, z) for y in range(h)}
        spec = dict(base=L, color=rcol, shapes=[("add", cells)], paint=[], panels=[], ppaint=[], eyes=[],
                    hollow=2, caps="both" if kind == "hip" else ("z" if ridge == "x" else "x"))
        if kind == "gable":
            ends = [(x, z) for (x, z) in area if (x in (X0, X1) if ridge == "x" else z in (Z0, Z1))]
            spec["paint"].append((gcol, "set", {(x, y, z) for (x, z) in ends for y in range(heights[(x, z)] - 2)}))
        self.sculpt(spec)

    # ---------------------------------------------------------- vehicles
    def vehicle(self, X, Z, vtype, n, body, trim, on=1):
        self.nasm += 1
        asm = f"vehicle{self.nasm}"
        self.repairs.append((asm, verified(
            self.D, lambda r, m, f: self._vehicle(X, Z, vtype, n, body, trim, on, asm, r, m), standalone=True)))

    def _vehicle(self, X, Z, vtype, n, body, trim, on, asm, r, mirror):
        """4-wide road vehicle along +z, nose at Z (facing -z), on its own wheels,
        tyres resting on a surface whose top is at level `on`."""
        D = self.D
        F = Frame((0, -31 - 8 * (on - 1), 0), I3, asm)
        P = lambda pid, col, dx, dz, L, yaw=0: D.place(pid, col, X + dx, L, Z + dz, yaw=yaw, frame=F, asm=asm)
        T = lambda cells, L, sizes, pref="x": tile_level(D, {(X + a, Z + b): c for (a, b), c in cells.items()}, L,
                                                         sizes, pref, frame=F, asm=asm, rng=r, mirror=mirror)
        black, clear, tred, tint = 0, 47, 36, 40
        # rows: 0 lights, 1-2 windscreen, glass up to `cab`, cabin ends at `cab_end`
        cab = {"car": 6, "van": 4, "pickup": 6, "truck": 6, "bus": n - 3}[vtype]
        cab_end = {"car": n - 1, "van": n - 1, "pickup": 7, "truck": 7, "bus": n - 1}[vtype]
        axles = [1, n - 3] + ([n - 6] if vtype in ("truck", "bus") and n >= 14 else [])
        arches = {dz for a in axles for dz in (a, a + 1)}
        for a in axles:
            ax = P("4600", black, 1, a, -1)
            for side in (-30, 30):
                D.attach("4624", 71, ax, (side, 5, 0), YAW[90], tag="rim")
                D.attach("3641", black, ax, (side, 5, 0), YAW[90], tag="tyre")
        T({(a, b): black for a in (1, 2) for b in range(n)}, 0, PLATES, "z")
        T({(a, b): (black if a in (1, 2) else body) for a in range(4) for b in range(n)
           if not (a in (0, 3) and b in arches)}, 1, PLATES, "z")
        T({(a, b): body for a in range(4) for b in range(n)}, 2, PLATES, "x")
        # course L3: lights, sides, dashboard and seat
        P("3005", clear, 0, 0, 3)
        P("3004", black, 1, 0, 3)
        P("3005", clear, 3, 0, 3)
        P("3005", tred, 0, n - 1, 3)
        P("3004", body, 1, n - 1, 3)
        P("3005", tred, 3, n - 1, 3)
        side = {(X + a, Z + b): body for a in (0, 3) for b in range(1, n - 1)}
        tile_level(D, side, 3, [], "z", frame=F, three={k: {v} for k, v in side.items()}, bricks=BRICKS, asm=asm)
        P("3004", black, 1, 1, 3)
        P("3829c01", black, 1, 3, 3)
        P("4079", black, 1, 4, 3)
        # hood and windscreen
        P("2431", body, 0, 0, 6)
        P("3823", tint, 0, 1, 6)
        for c0 in (6, 9):
            for a in (0, 3):
                b = 3
                while b <= cab_end - 1:
                    if b + 1 <= cab_end - 1:
                        glassy = b + 1 <= cab
                        P("3065" if glassy else "3004", tint if glassy else body, a, b, c0, 90)
                        b += 2
                    else:
                        P("3005", body, a, b, c0)
                        b += 1
            if cab_end == n - 1:
                P("3065", tint, 0, n - 1, c0)
                P("3065", tint, 2, n - 1, c0)
            else:
                P("3004", body, 0, cab_end, c0)
                P("3004", body, 2, cab_end, c0)
        roof = {(a, b): body for a in range(4) for b in range(2, cab_end + 1)}
        T(roof, 12, PLATES, "x")
        T({k: (trim if trim is not None else black) for k in roof}, 13, self.flat, "x")
        if vtype == "pickup":
            bed_top = {(a, b): body for a in (0, 3) for b in range(cab_end + 1, n - 1)}
            bed_top.update({(a, n - 1): body for a in range(4)})
            T(bed_top, 6, self.flat, "z")
        if vtype == "truck":
            box = {(a, b) for a in range(4) for b in range(cab_end + 1, n)}
            ring = {(a, b) for (a, b) in box if a in (0, 3) or b in (cab_end + 1, n - 1)}
            for c0 in (6, 9, 12):
                cells_ = {(X + a, Z + b): trim if trim is not None else body for (a, b) in ring}
                tile_level(D, cells_, c0, [], "z" if c0 % 2 else "x", frame=F,
                           three={k: {v} for k, v in cells_.items()}, bricks=BRICKS, asm=asm)
            T({k: (trim if trim is not None else body) for k in box}, 15, PLATES, "x")
            T({k: (trim if trim is not None else body) for k in box}, 16, self.flat, "x")

    # ---------------------------------------------------------- sculpt
    def sculpt(self, spec):
        n = len(sculpt_cells(spec))
        if n > LIMITS["sculpt_cells"]:
            raise SpecError(f"sculpt is too big ({n} cells, limit {LIMITS['sculpt_cells']})")
        self.cells_used += n
        if self.cells_used > LIMITS["total_cells"]:
            raise SpecError(f"the model is too big (limit {LIMITS['total_cells']} sculpted cells in total)")
        if spec.get("wheels"):
            return self.wheeled_sculpt(spec)
        cells = sculpt_cells(spec) - set(self.D.occ)
        self.expose_studs({c for c in cells if (c[0], c[1] - 1, c[2]) not in cells})
        self._sculpt_with_retry(spec)

    def wheeled_sculpt(self, spec):
        """A sculpt with `wheels` is a vehicle: its own separate piece (like
        the `vehicle` command's), standing on real wheels.  The body is moved
        up or down so the tyres rest on whatever is below its footprint."""
        D = self.D
        cells = sculpt_cells(spec)
        if not cells:
            raise SpecError("sculpt has no cells")
        foot = {(x, z) for (x, _, z) in cells}
        low = min(c[1] for c in cells)
        for X in spec["wheels"]["xs"]:          # the tyres stand outside the body: include their columns
            zs = [z for (x, L, z) in cells if L == low and x == X]
            if zs:
                foot |= {(x, z) for x in range(X - 1, X + 3) for z in (min(zs) - 2, min(zs) - 1, max(zs) + 1,
                                                                         max(zs) + 2)}
        below = [L for (x, L, z) in D.occ if (x, z) in foot and L < max(c[1] for c in cells)]
        ground = max(below) + 1 if below else 0
        bottom = ground + WHEELS[spec["wheels"]["size"]]["lift"]
        shift = bottom - min(c[1] for c in cells)
        spec = dict(spec, base=spec["base"] + shift)
        if shift:
            self.repairs.append(("vehicle lifted onto its wheels", shift))
        self.nasm += 1
        D.default_asm = f"vehicle{self.nasm}"
        try:
            self._sculpt_with_retry(spec)
            self.mount_wheels(spec, bottom)
        finally:
            D.default_asm = "main"

    def mount_wheels(self, spec, B):
        """Per axle: a 2x2 plate with wheel pins under each flank of the body's
        underside (level B), with a rim and tyre on its outer pin."""
        D = self.D
        w = WHEELS[spec["wheels"]["size"]]
        body = {(c[0], c[2]) for c, i in D.occ.items() if c[1] == B and D.parts[i].asm == D.default_asm}
        for X in spec["wheels"]["xs"]:
            zs = sorted(z for (x, z) in body if x == X) or [None]
            zmin, zmax = zs[0], zs[-1]
            flat = zmin is not None and zmax - zmin >= 3 and all(
                (x, z) in body for x in (X, X + 1) for z in (zmin, zmin + 1, zmax - 1, zmax))
            if not flat:
                self.errors.append(f"wheels at x={X}: the body's underside (level {B - spec['base']} of the "
                                   f"sculpt) must be flat and at least 4 studs wide across x={X}..{X + 1}")
                continue
            for z, side in ((zmin, 1), (zmax - 1, -1)):        # side: which of the plate's pins faces out
                plate = D.place("4600", 0, X, B - 1, z, yaw=90, tag="axle")
                rel = YAW[90] if side == 1 else YAW[270]       # rim's outer face points away from the body
                D.attach(w["rim"], 71, plate, (side * w["rim_x"], 5, 0), rel, tag="rim")
                D.attach(w["tyre"], 0, plate, (side * w["tyre_x"], 5, 0), rel, tag="tyre")

    def plan_lights(self, core, reserved, front):
        """Where a wheeled sculpt's front and back faces are flat and exposed
        for one brick course (3 plates) across at least 2 studs: returns
        [(sign, z run, level, face x)] for the highest such course at each end
        (sign +1 = the +x end), i.e. just under the bonnet's rounded edge.
        Rounded noses with no flat patch get none."""
        out = []
        levels = sorted({c[1] for c in core})
        for sign in (1, -1):
            best = None
            tip = max(c[0] for c in core) if sign > 0 else min(c[0] for c in core)
            for Lc in reversed(levels):              # highest first: lights sit just under the bonnet
                if any(Lc + l not in levels for l in range(3)):
                    continue
                ext = {}
                for (x, L, z) in core:
                    if Lc <= L < Lc + 3:
                        k = (L, z)
                        ext[k] = x if k not in ext else (max(ext[k], x) if sign > 0 else min(ext[k], x))
                if not ext:
                    continue
                X = max(ext.values()) if sign > 0 else min(ext.values())
                if abs(X - tip) > 1:
                    continue                          # the nose or tail itself, not a cabin further back
                # a flat, exposed face with body behind it and something to sit on
                ok = sorted(z for z in {k[1] for k in ext}
                            if all(ext.get((Lc + l, z)) == X and (X, Lc + l, z) not in reserved
                                   and (X + sign, Lc + l, z) not in self.D.occ and (X - sign, Lc + l, z) in core
                                   for l in range(3))
                            and (Lc == levels[0] or (X, Lc - 1, z) in core))
                runs, cur = [], []
                for z in ok:
                    if cur and z != cur[-1] + 1:
                        runs.append(cur)
                        cur = []
                    cur.append(z)
                if cur:
                    runs.append(cur)
                run = max(runs, key=len, default=[])
                if 2 <= len(run):
                    best = (sign, run[:8], Lc, X)
                    break
            if best:
                out.append(best)
        return out

    def dress_lights(self, sign, run, Lc, X, front):
        """Round lamps on the outer headlight bricks (clear at the front, red
        at the back) and 1x2 tiles across the inner pairs (a black grille at
        the front, body-coloured at the back).  Each clicks onto its brick's
        side stud, which sits 4 LDU inside the brick's face (measured)."""
        D = self.D
        host = {z: D.parts[D.occ[(X, Lc, z)]] for z in run}
        lamp = COLORS["trans_clear"] if front else COLORS["trans_red"]
        for z in (run[0], run[-1]):
            D.attach("98138", lamp, host[z], (0, 10, -14), SIDE_STUD_REL, tag="lamp")
        inner = run[1:-1]
        while inner:
            q = host[inner[0]]
            if len(inner) >= 2:
                dx = 10 if tuple(round(c) for c in mul(q.mat, (1, 0, 0))) == (0, 0, 1) else -10
                pid, col = ("2412b", 0) if front else ("3069b", q.color)
                D.attach(pid, col, q, (dx, 10, -14), SIDE_STUD_REL, tag="grille" if front else "trim")
                inner = inner[2:]
            else:
                D.attach("3070b", 0 if front else q.color, q, (0, 10, -14), SIDE_STUD_REL, tag="trim")
                inner = inner[1:]

    def rescue_loose(self, n0, hidden, max_group=12, rounds=4):
        """Targeted repair after a sculpt fill that left small loose groups.
        Typical case: a surface cell on a ball's diagonal near its widest
        point has nothing below it (the ball curves in) and its neighbours
        were taken by 3-plate bricks, so it ends up as a stack of 1x1 plates
        under a cap, held by nothing (side-by-side parts never connect).
        Re-lay the group's fill parts and the fill parts beside them as
        plates only -- plates can bridge sideways where bricks cannot --
        and keep the result only if the group is now attached; otherwise
        restore.  Returns how many groups were rescued."""
        D = self.D
        nb4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
        movable = lambda i: i >= n0 and D.parts[i].tag == "" and D.parts[i].host is None
        rescued = 0
        for _ in range(rounds):
            comps, _ = D.components()
            own = [c for c in comps if D.parts[c[0]].asm == D.default_asm]
            if len(own) <= 1:
                break
            main = set(max(own, key=len))
            groups = [set(c) for c in own if len(c) <= max_group and min(c) >= n0 and not set(c) & main]
            progress = False
            for g in groups:
                if any(i >= len(D.parts) for i in g):
                    break                          # indices moved: recompute in the next round
                gcells = [c for c, i in D.occ.items() if i in g]
                nbr = {D.occ.get((x + a, L, z + b)) for (x, L, z) in gcells for a, b in nb4}
                remove = {i for i in (g | nbr) if i is not None and movable(i)}
                if not remove:
                    continue
                snap = (list(D.parts), [q.host for q in D.parts], dict(D.occ), list(D.links))
                cells = {c: (None if c in hidden else D.parts[i].color) for c, i in D.occ.items() if i in remove}
                D.remove(remove)                                  # caps etc. stay where they are
                for n, L in enumerate(sorted({c[1] for c in cells})):
                    tile_level(D, {(x, z): col for (x, l, z), col in cells.items() if l == L}, L, PLATES,
                               "x" if n % 2 == 0 else "z")
                comps2, _ = D.components()
                own2 = [c for c in comps2 if D.parts[c[0]].asm == D.default_asm]
                main2 = set(max(own2, key=len))
                back = {D.occ[c] for c in gcells if c in D.occ}
                if len(own2) < len(own) and back <= main2:
                    rescued += 1
                    progress = True
                    break                              # indices changed: recompute groups
                parts, hosts, occ, links = snap
                D.parts, D.occ, D.links = parts, occ, links
                for q, h in zip(D.parts, hosts):
                    q.host = h
                D._reindex()
            if not progress:
                break
        if rescued:
            self.repairs.append(("loose rescued", rescued))
        return rescued

    def _sculpt_with_retry(self, spec):
        n0, r0, e0 = len(self.D.parts), len(self.repairs), len(self.errors)
        ok = self._sculpt(spec)
        wheels = spec.get("wheels")
        if wheels and wheels.get("lights") and not self.D.is_one_piece(range(n0, len(self.D.parts))):
            # the lights are dressing: a body that falls apart with them is rebuilt without
            self.D.rollback(n0)
            del self.repairs[r0:]
            del self.errors[e0:]
            spec = dict(spec, wheels=dict(wheels, lights=False))
            ok = self._sculpt(spec)
            self.repairs.append(("lights dropped", 0))
        # rebuild solid only if hollow really fell apart, not when it is one
        # piece that simply stands on something without clicking on
        if not ok and spec.get("hollow") and not self.D.is_one_piece(range(n0, len(self.D.parts))):
            self.D.rollback(n0)
            del self.repairs[r0:]
            del self.errors[e0:]
            self._sculpt(dict(spec, hollow=0))
            self.repairs.append(("sculpt rebuilt solid", 0))

    def _sculpt(self, spec):
        D = self.D
        S = spec["base"]
        default = spec["color"]
        core = {}
        for op, cells in spec["shapes"]:
            for (x, y, z) in cells:
                if op == "add":
                    core[(x, S + y, z)] = default
                else:
                    core.pop((x, S + y, z), None)
        # nothing can be under level 0: that is the table, or a baseplate's top
        under = [c for c in core if c[1] < 0]
        for c in under:
            del core[c]
        if under:
            self.repairs.append(("clipped below the table", len(under)))
        soft = {}                                 # gradient-coloured cells (see recolour)
        if spec.get("grad"):
            stops, axis = spec["grad"]
            soft = gradient(stops, core, axis_pos(axis), seed=S)
            core.update(soft)
        for n, (col, kind, data) in enumerate(spec["paint"]):
            if kind == "set":
                targets = [(x, S + y, z) for (x, y, z) in data if (x, S + y, z) in core]
            else:
                xs, ys, zs = data
                targets = [(x, L, z) for (x, L, z) in core if x in xs and (L - S) in ys and (zs is None or z in zs)]
            if isinstance(col, tuple):
                g = gradient(col[0], targets, axis_pos(col[1]), seed=S + 31 * (n + 1))
                core.update(g)
                soft.update(g)
            else:
                for c in targets:
                    core[c] = col
                    soft.pop(c, None)
        # a sculpt that overlaps something already built (a tail resting on a
        # rock, a head sunk into a body built earlier) merges into it: the cells
        # already taken keep what is there
        taken = [c for c in core if c in D.occ]
        for c in taken:
            del core[c]
        if taken:
            self.repairs.append(("sculpt overlap merged", len(taken)))
        if self.sideways == "off":
            core = studs_up_details(core, spec, S)
            spec = dict(spec, panels=[], ppaint=[], eyes=[])
        if spec.get("hollow"):
            core = hollowed(core, spec["hollow"])
        if not core:
            raise SpecError("sculpt has no cells")
        flex = {c for c in core if all((c[0] + a, c[1] + b, c[2] + e) in core for a, b, e in NB6)}
        reserved = set()
        placements = []                         # (pid, col, x, L, z, yaw, tag, cells)

        # ---- top caps along x, then along z for tops still flat
        top, bot = {}, {}
        for (x, L, z) in core:
            top[(x, z)] = max(top.get((x, z), -10 ** 6), L + 1)
            bot[(x, z)] = min(bot.get((x, z), 10 ** 6), L)
        depth = {}
        for (x, z), t in top.items():
            d = 0
            while (x, t - 1 - d, z) in core:
                d += 1
            depth[(x, z)] = d
        cols_xz = set(top)
        capped, caps = set(), []
        mode = spec.get("caps", "both")
        if mode in ("x", "both"):
            for z in {c[1] for c in cols_xz}:
                T = {x: top[(x, zz)] for (x, zz) in cols_xz if zz == z}
                dp = {x: depth[(x, z)] for x in T}
                cs, cov = line_caps(T, dp, set(T))
                caps += [("x", z) + c for c in cs]
                capped |= {(x, z) for x in cov}
        if mode in ("z", "both"):
            for x in {c[0] for c in cols_xz}:
                T = {z: top[(xx, z)] for (xx, z) in cols_xz if xx == x}
                dp = {z: depth[(x, z)] for z in T}
                cs, cov = line_caps(T, dp, {z for z in T if (x, z) not in capped})
                caps += [("z", x) + c for c in cs]
                capped |= {(x, z) for z in cov}
        # A tile has no studs on top and holds on only by its underside, so an
        # overhanging top cell (nothing below it) is left to the plate fill,
        # which can bridge it to supported neighbours instead of a lone tile.
        held = lambda x, L, z: L == 0 or (x, L - 1, z) in core or (x, L - 1, z) in D.occ
        tiles_top = {(x, top[(x, z)] - 1, z): core[(x, top[(x, z)] - 1, z)] for (x, z) in cols_xz
                     if (x, z) not in capped and held(x, top[(x, z)] - 1, z)}
        grouped = defaultdict(list)
        for c in caps:
            grouped[(c[0],) + c[2:]].append(c[1])
        for (axis, s0, r, h, kind, d, lvl), lines in grouped.items():
            used = set()
            for ln in sorted(lines):
                if ln in used:
                    continue
                if axis == "x":
                    colat = lambda l2: {core[(s, lvl + h - 1, l2)] for s in range(s0, s0 + r)}
                else:
                    colat = lambda l2: {core[(l2, lvl + h - 1, s)] for s in range(s0, s0 + r)}
                width = 2 if (ln + 1 in lines and ln + 1 not in used and kind == "slope"
                              and colat(ln) == colat(ln + 1) and len(colat(ln)) == 1) else 1
                used |= set(range(ln, ln + width))
                if axis == "x":
                    cells = {(s, lvl + l, w) for s in range(s0, s0 + r) for l in range(h) for w in range(ln, ln + width)}
                    x0, z0 = s0, ln
                else:
                    cells = {(w, lvl + l, s) for s in range(s0, s0 + r) for l in range(h) for w in range(ln, ln + width)}
                    x0, z0 = ln, s0
                reserved |= cells
                col = core[(x0, lvl + h - 1, z0)]
                if kind == "slope":
                    pid = (SLOPE2 if h == 2 else SLOPE3)[r][1 if width == 2 else 0]
                    want = (d, 0, 0) if axis == "x" else (0, 0, d)
                    placements.append((pid, col, x0, lvl, z0, yaw_pointing(MAIN, want), "cap", cells))
                else:
                    placements.append((kind, col, x0, lvl, z0, 90 if axis == "x" else 0, "cap", cells))
        reserved |= set(tiles_top)
        # tops of lower segments in gapped columns (e.g. under an overhanging leaf) get tiles too
        for (x, L, z), col in core.items():
            if (x, L + 1, z) not in core and (x, L, z) not in reserved and held(x, L, z):
                tiles_top[(x, L, z)] = col
                reserved.add((x, L, z))

        # ---- undersides: inverted curved slopes on gentle bottom steps (along x)
        bdepth = {}
        for (x, z), b in bot.items():
            d = 0
            while (x, b + d, z) in core:
                d += 1
            bdepth[(x, z)] = d
        for z in {c[1] for c in cols_xz}:
            Bz = {x: bot[(x, zz)] for (x, zz) in cols_xz if zz == z}
            xs = sorted(Bz)
            i = 0
            while i < len(xs):
                j = i
                while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1 and Bz[xs[j + 1]] == Bz[xs[i]]:
                    j += 1
                a, b, B = xs[i], xs[j], Bz[xs[i]]
                for (edge, nbx, d) in ((b, b + 1, -1), (a, a - 1, +1)):
                    if nbx not in Bz or not (2 <= Bz[nbx] - B <= 4) or (b - a + 1) < 2:
                        continue
                    cols_ = [edge - 1, edge] if d == -1 else [edge, edge + 1]
                    cells = {(x, B + l, z) for x in cols_ for l in range(2)}
                    if cells & reserved or any((x, B - 1, z) in D.occ for x in cols_):
                        continue
                    if any(bdepth[(x, z)] < 5 for x in cols_):
                        continue
                    reserved |= cells
                    placements.append(("24201", core[(cols_[0], B, z)], cols_[0], B, z,
                                       yaw_pointing(MAIN, (d, 0, 0)), "underside", cells))
                    break
                i = j + 1

        # ---- SNOT panels and their anchor bricks
        panels = []
        for pn in spec["panels"]:
            xs, (y0, y1), thick = pn["x"], pn["y"], pn["thick"]
            Ls = S + y0 + 2
            inreg = [c for c in core if c[0] in xs and S + y0 <= c[1] <= S + y1]
            if not inreg:
                continue
            zmin, zmax = min(c[2] for c in inreg), max(c[2] for c in inreg)
            vs = [v for v in range(-1, 40) if Ls + 0.5 + 2.5 * v >= S + y0 and Ls + 3 + 2.5 * v <= S + y1 + 1]
            for side, zside in (("L", zmin), ("R", zmax)):
                pcells = []
                for u in xs:
                    for v in vs:
                        lo = Ls + 0.5 + 2.5 * v
                        need = range(math.floor(lo) - 1, math.ceil(lo + 2.5) + 1)
                        if all((u, l, zside) in core for l in need):
                            pcells.append((u, v))
                cellset = set(pcells)
                for k in range(0, 20):
                    lvl, v = Ls + 5 * k, 2 * k
                    if v not in vs:
                        break
                    x = min(xs)
                    while x <= max(xs):
                        span = [x + a for a in range(4)]
                        free = lambda xx: all((xx, lvl + l, zside) in core and (xx, lvl + l, zside) not in reserved
                                              for l in range(3))
                        if all((xx, v) in cellset and free(xx) for xx in span):
                            pid, x_next = "30414", x + 4
                        elif (x, v) in cellset and free(x):
                            pid, span, x_next = "87087", [x], x + 1
                        else:
                            x += 1
                            continue
                        cells = {(xx, lvl + l, zside) for xx in span for l in range(3)}
                        reserved |= cells
                        ends = [e for e in (span[-1] + 1, span[0] - 1) if (e, lvl + 1, zside) not in core]
                        cx = span[-1] if ends and ends[0] == span[-1] + 1 else span[0]
                        placements.append((pid, core[(cx, lvl + 1, zside)], span[0], lvl, zside,
                                           0 if side == "L" else 180, "anchor", cells))
                        x = x_next
                panels.append(dict(side=side, zside=zside, Ls=Ls, cells=pcells, thick=pn["thick"]))

        # ---- eyes that are not on a panel: side-stud brick in the surface + round tile
        surface_eyes = []
        for e in spec["eyes"]:
            if any(e["x"] in pn["x"] and pn["y"][0] <= e["y"] <= pn["y"][1] for pn in spec["panels"]):
                continue
            for side in ("L", "R"):
                done = False
                for L0 in (S + e["y"] - 1, S + e["y"] - 2, S + e["y"]):
                    zc = [c[2] for c in core if c[0] == e["x"] and c[1] == L0 + 1]
                    if not zc:
                        continue
                    zside = min(zc) if side == "L" else max(zc)
                    out = zside - 1 if side == "L" else zside + 1
                    cells = {(e["x"], L0 + l, zside) for l in range(3)}
                    if all(c in core and c not in reserved and (c[0], c[1], out) not in core for c in cells):
                        reserved |= cells
                        placements.append(("87087", e["ring"], e["x"], L0, zside, 0 if side == "L" else 180, "eye", cells))
                        surface_eyes.append((side, e, L0, zside))
                        done = True
                        break
                if not done:
                    # no flat patch for a side-stud eye here: paint it into the surface instead
                    core.update(studs_up_details(core, dict(spec, ppaint=[], eyes=[e]), S, sides=(side,)))
                    self.repairs.append((f"eye painted {side}", 1))

        # ---- vehicle lights: headlight bricks across the front and back faces
        light_plan = []
        if spec.get("wheels") and spec["wheels"].get("lights") and self.sideways != "off":
            light_plan = self.plan_lights(core, reserved, spec["wheels"]["front"])
            for (sign, run, Lc, X) in light_plan:
                for z in run:
                    cells = {(X, Lc + l, z) for l in range(3)}
                    reserved |= cells
                    placements.append(("4070", core[(X, Lc + 1, z)], X, Lc, z,
                                       yaw_pointing(MAIN, (sign, 0, 0), local=(0, 0, -1)), "light", cells))

        # ---- place fixed parts, then fill the rest (self-repairing)
        D.new_step()
        n_sculpt = len(D.parts)
        for (pid, col, x, L, z, yaw, tag, cells) in placements:
            D.place(pid, col, x, L, z, yaw=yaw, tag=tag)
        for (sign, run, Lc, X) in light_plan:
            self.dress_lights(sign, run, Lc, X, front=(sign > 0) == (spec["wheels"]["front"] == "+x"))
        by_level = defaultdict(dict)
        for (x, L, z), col in tiles_top.items():
            by_level[L][(x, z)] = col
        for L, cells in by_level.items():
            tile_level(D, cells, L, self.flat, "x", tag="top")

        soft = {c: col for c, col in soft.items() if core.get(c) == col and c not in reserved}
        fill_cells = {c: (None if c in flex or c in soft else col) for c, col in core.items() if c not in reserved}

        def fill(r, mirror, flip):
            taken = set()
            for L in sorted({c[1] for c in fill_cells}):
                free = {(x, z): col for (x, l, z), col in fill_cells.items() if l == L and (x, l, z) not in taken}
                if not free:
                    continue
                three = {}
                if (L - S) % 3 == 0:
                    for (x, z), col in free.items():
                        cs = [fill_cells.get((x, L + l, z), "X") for l in range(3)]
                        if "X" in cs or any((x, L + l, z) in taken for l in range(3)):
                            continue
                        s = {c for c in cs if c is not None}
                        if len(s) <= 1:
                            three[(x, z)] = s
                pref = "x" if ((L - S) // 3) % 2 == 0 else "z"
                if flip:
                    pref = "z" if pref == "x" else "x"
                tall = tile_level(D, free, L, PLATES, pref, three=three, bricks=BRICKS, rng=r, mirror=mirror)
                taken |= {(x, L, z) for (x, z) in free}
                taken |= {(x, L + l, z) for (x, z) in tall for l in (1, 2)}
        D.new_step()
        n_fill = len(D.parts)
        fill_ok = verified(D, fill, standalone=D.default_asm != "main")
        self.repairs.append(("sculpt fill", fill_ok))
        if fill_ok < 0:
            self.rescue_loose(n_sculpt, flex | set(soft))
        if soft:
            recolour(D, n_fill, soft, hidden=flex)

        # ---- panels, then surface eyes' pupils
        D.new_step()
        for pnl in panels:
            self.build_panel(pnl, spec, S)
        for side, e, L0, zside in surface_eyes:
            Oy = -8 * (L0 + 3) + 20
            if side == "L":
                F, i = Frame((0, Oy, 20 * zside), L_FRAME, "eyeL"), e["x"]
            else:
                F, i = Frame((0, Oy, 20 * (zside + 1)), R_FRAME, "eyeR"), -e["x"] - 1
            D.place("98138", e["pupil"], i, 0, 0, frame=F, tag="pupil")
        return fill_ok >= 0

    def build_panel(self, pnl, spec, S):
        D = self.D
        side, zside, Ls, cells, thick = pnl["side"], pnl["zside"], pnl["Ls"], pnl["cells"], pnl["thick"]
        if not cells:
            return
        Oy = -8 * (Ls + 3) + 20
        if side == "L":
            frame = Frame((0, Oy, 20 * zside), L_FRAME, f"L{Ls}")
            to_frame = lambda u, v, w, d: (u, v)
        else:
            frame = Frame((0, Oy, 20 * (zside + 1)), R_FRAME, f"R{Ls}")
            to_frame = lambda u, v, w, d: (-u - w, v)
        default = spec["color"]
        top = {}
        for (u, v) in cells:
            centre = Ls + 0.5 + 2.5 * v + 1.25 - S
            col = default
            for (c, xs, y0, y1) in spec["ppaint"]:
                if u in xs and y0 <= centre < y1 + 1:
                    col = c
            top[(u, v)] = col
        eye = None
        for e in spec["eyes"]:
            for (u, v) in cells:
                lo = Ls + 0.5 + 2.5 * v - S
                if u == e["x"] and lo <= e["y"] < lo + 2.5:
                    eye = ((u, v), e)
        if eye:
            (eu, ev), e = eye
            for c in ((eu - 1, ev), (eu + 1, ev), (eu, ev - 1)):
                if c in top:
                    top[c] = e["skin"]

        def attempt(r, mirror, flip):
            if thick == 2:
                base = {c: default for c in cells}
                if eye:
                    base[eye[0]] = eye[1]["ring"]
                tile_level(D, base, 0, PLATES, "x" if flip else "z", frame=frame, to_frame=to_frame, tag="panel",
                           rng=r, mirror=mirror)
                mosaic = {c: col for c, col in top.items() if not eye or c != eye[0]}
                tile_level(D, mosaic, 1, self.flat, "z" if flip else "x", frame=frame, to_frame=to_frame, tag="panel",
                           rng=r, mirror=mirror)
                pupil_level = 1
            else:
                tile_level(D, {c: default for c in cells}, 0, PLATES, "x" if flip else "z", frame=frame,
                           to_frame=to_frame, tag="panel", rng=r, mirror=mirror)
                l1, l2 = {}, {}
                for u in sorted({c[0] for c in cells}):
                    vs = sorted(v for (uu, v) in cells if uu == u)
                    if len(vs) >= 4:
                        for (v0, want) in ((vs[-2], (0, 1, 0)), (vs[0], (0, -1, 0))):
                            i, k = to_frame(u, v0, 1, 2)
                            D.place("11477", top[(u, v0)], i, 1, k, yaw=yaw_pointing(frame, want), frame=frame, tag="panel")
                        for v in vs[2:-2]:
                            l1[(u, v)] = default
                            l2[(u, v)] = top[(u, v)]
                    else:
                        for v in vs:
                            l1[(u, v)] = default
                tile_level(D, l1, 1, PLATES, "z" if flip else "x", frame=frame, to_frame=to_frame, tag="panel",
                           rng=r, mirror=mirror)
                tops = dict(l2)
                tops.update({c: top[c] for c in l1 if c not in l2})
                if eye and eye[0] in tops:
                    del tops[eye[0]]
                tile_level(D, tops, 2, self.flat, "x", frame=frame, to_frame=to_frame, tag="panel", rng=r, mirror=mirror)
                pupil_level = 2
            if eye:
                i, k = to_frame(eye[0][0], eye[0][1], 1, 1)
                D.place("98138", eye[1]["pupil"], i, pupil_level, k, frame=frame, tag="eye")

        n0 = len(D.parts)
        ok = verified(D, attempt, standalone=D.default_asm != "main")
        self.repairs.append((f"panel {side} y{Ls - S}", ok))
        if ok < 0:
            # a panel is surface dressing: keep what attached, drop what could not
            comps, _ = D.components()
            body = max((c for c in comps if D.parts[c[0]].asm == D.default_asm), key=len)
            drop = [i for i in range(n0, len(D.parts)) if i not in set(body)]
            D.remove(drop)
            self.repairs.append((f"panel {side} y{Ls - S} trimmed", len(drop)))

    # ---------------------------------------------------------- driver
    def run(self, text):
        lines = text.splitlines()
        deferred = []
        n = 0
        while n < len(lines):
            raw = lines[n].split("#", 1)[0].strip()
            n += 1
            if not raw:
                continue
            toks = raw.split()
            cmd, args = toks[0], toks[1:]
            self.D.src = n
            try:
                if cmd == "sculpt":
                    block, start = [], n
                    while n < len(lines) and lines[n].split("#", 1)[0].strip() != "end":
                        block.append((n + 1, lines[n].split("#", 1)[0].strip()))
                        n += 1
                    if n >= len(lines):
                        raise SpecError(f"sculpt starting line {start} has no 'end'")
                    n += 1
                    self.sculpt(self.parse_sculpt(args, block))
                elif cmd == "scatter":
                    deferred.append((n, args))           # decorations go last, around everything else
                else:
                    self.command(cmd, args)
            except SpecError as e:
                self.errors.append(f"line {n}: {e}")
            except (KeyError, ValueError, IndexError) as e:
                self.errors.append(f"line {n}: {type(e).__name__}: {e}")
        for ln, args in deferred:
            self.D.src = ln
            try:
                self.command("scatter", args)
            except (SpecError, KeyError, ValueError, IndexError) as e:
                self.errors.append(f"line {ln}: {e}")
        return self.D

    def parse_sculpt(self, args, block):
        pos, kw = split_kw(args)
        ctok = kw.get("color", "black")
        # color=a>b: a gradient over the whole sculpt (along=y by default); the
        # first colour stands in wherever one colour is needed (panels, skin)
        grad = (color_stops(ctok), kw.get("along", "y")) if ">" in ctok else None
        if grad:
            axis_pos(grad[1])                     # validate now: report the bad axis on this line
        spec = dict(base=int(kw.get("base", 0)), color=(grad[0][0] if grad else color(ctok))[0], grad=grad,
                    hollow=int(kw.get("hollow", 0)), caps=kw.get("caps", "both"),
                    shapes=[], paint=[], panels=[], ppaint=[], eyes=[], wheels=None)
        for ln, raw in block:
            if not raw:
                continue
            t = raw.split()
            p, k = split_kw(t[1:])
            try:
                if t[0] in ("col", "box", "ball", "cyl"):
                    spec["shapes"].append(("add", shape_cells(t[0], p)))
                elif t[0] == "cut":
                    spec["shapes"].append(("cut", shape_cells(p[0], p[1:])))
                elif t[0] == "paint":
                    if ">" in p[0]:                   # gradient paint: (stops, axis)
                        c = (color_stops(p[0]), k.get("along", "y"))
                        axis_pos(c[1])
                    else:
                        c = color(p[0])[0]
                    if p[1] in ("box", "ball", "cyl", "col"):
                        spec["paint"].append((c, "set", shape_cells(p[1], p[2:])))
                    else:
                        spec["paint"].append((c, "ranges", (rng_(p[1]), rng_(p[2]), rng_(p[3]) if len(p) > 3 else None)))
                elif t[0] == "panel":
                    ys = rng_(p[1])
                    spec["panels"].append(dict(x=rng_(p[0]), y=(ys.start, ys.stop - 1), thick=int(k.get("thick", 2))))
                elif t[0] == "ppaint":
                    ys = rng_(p[2])
                    spec["ppaint"].append((color(p[0])[0], rng_(p[1]), ys.start, ys.stop - 1))
                elif t[0] == "wheels":
                    size = k.get("size", "small")
                    if size not in WHEELS:
                        raise SpecError("wheels size must be small or large")
                    front = k.get("front", "+x")
                    if front not in ("+x", "-x"):
                        raise SpecError("wheels front must be +x or -x")
                    spec["wheels"] = dict(xs=[int(v) for v in p[0].split(",")], size=size, front=front,
                                          lights=k.get("lights", "1") != "0")
                elif t[0] == "eye":
                    spec["eyes"].append(dict(x=int(p[0]), y=int(p[1]),
                                             pupil=color(k.get("pupil", "black"))[0],
                                             ring=color(k.get("ring", "medium_azure"))[0],
                                             skin=color(k.get("skin", "orange"))[0]))
                else:
                    raise SpecError(f"unknown sculpt command '{t[0]}'")
            except (SpecError, IndexError, ValueError) as e:
                self.errors.append(f"line {ln}: {e}")
        return spec

    def colours(self, tok, cells, kw):
        """A fill's colours: a colour or mix (`a|b`), or a gradient (`a>b>c`)
        along `along=x|z|-x|-z` (default x) over the region's cells."""
        if ">" not in tok:
            return color(tok)
        return gradient(color_stops(tok), cells, axis_pos(kw.get("along", "x"), "xz"), seed=self.D.src or 0)

    def command(self, cmd, args):
        D = self.D
        p, kw = split_kw(args)
        if cmd == "model":
            D.title = "_".join(args) or "model"
        elif cmd == "step":
            D.new_step()
        elif cmd == "baseplate":
            D.add(D.make("3811", color(p[2])[0], int(p[0]), 0, int(p[1])))
            self.stage.append({(int(p[0]) + a, int(p[1]) + c) for a in range(32) for c in range(32)})
        elif cmd in ("plates", "tiles", "bricks"):
            courses = _bounded(int(kw.get("courses", 1)), LIMITS["courses"], "courses")
            cells = region_terms(p[2:])
            self.fill(cmd, _bounded(int(p[0]), LIMITS["coord"], "level"), self.colours(p[1], cells, kw), cells,
                      kw.get("prefer", "x"), courses)
        elif cmd == "part":
            self.expose_for_part(p[0], int(p[2]), int(p[4]), int(p[3]), rot_(kw))
            D.place(p[0], color(p[1])[0], int(p[2]), int(p[4]), int(p[3]), yaw=rot_(kw))
        elif cmd == "stack":
            pid, col, x, z, L, n = p[0], color(p[1])[0], int(p[2]), int(p[3]), int(p[4]), int(p[5])
            _bounded(n, LIMITS["count"], "count")
            self.expose_for_part(pid, x, L, z, rot_(kw))
            for a in range(n):
                D.place(pid, col, x, L + a * pdef(pid).h, z, yaw=rot_(kw))
        elif cmd == "row":
            pid, col, x, z, L, n = p[0], color(p[1])[0], int(p[2]), int(p[3]), int(p[4]), int(p[5])
            _bounded(n, LIMITS["count"], "count")
            dx, dz = int(kw.get("dx", 1)), int(kw.get("dz", 0))
            for a in range(n):
                self.expose_for_part(pid, x + a * dx, L, z + a * dz, rot_(kw))
                D.place(pid, col, x + a * dx, L, z + a * dz, yaw=rot_(kw))
        elif cmd == "base":
            cells = rect(p[0])
            self.stage.append(cells)
            self.base(cells, self.colours(p[1], cells, kw), self.colours(kw["top"], cells, kw) if "top" in kw else None,
                      color(kw["rim"])[0] if "rim" in kw else None)
        elif cmd == "scatter":
            self.scatter(p[0], color(p[1]), region_terms(p[2:-1]), int(p[-1]), int(kw.get("every", 0)),
                         int(kw.get("shift", 0)), float(kw.get("density", 0.3)), int(kw.get("seed", 0)))
        elif cmd == "water":
            ripples = float(kw.get("ripples", 0.06))
            if not 0 <= ripples <= 0.5:
                raise SpecError("ripples must be between 0 and 0.5")
            self.water(region_terms(p[1:]), _bounded(int(p[0]), LIMITS["coord"], "level"),
                       color_stops(kw.get("bed", "medium_azure>blue>dark_blue")),
                       color_stops(kw.get("surface", "trans_clear|trans_light_blue>trans_light_blue>trans_medium_blue")),
                       None if kw.get("foam") == "none" else color(kw.get("foam", "white"))[0], ripples)
        elif cmd == "walls":
            cells = rect(p[0])
            xs, zs = sorted({c[0] for c in cells}), sorted({c[1] for c in cells})
            self.walls(xs[0], xs[-1], zs[0], zs[-1], int(p[1]), _bounded(int(p[2]), LIMITS["courses"], "courses"),
                       color(p[3]))
        elif cmd == "window":
            self.window(int(p[0]), int(p[1]), p[2], int(p[3]), int(kw.get("stack", 1)),
                        color(kw.get("frame", "black"))[0], color(kw.get("glass", "trans_clear"))[0])
        elif cmd == "door":
            self.door(int(p[0]), int(p[1]), p[2], int(p[3]), color(kw.get("frame", "black"))[0],
                      color(kw.get("leaf", "reddish_brown"))[0])
        elif cmd == "tree":
            self.tree(int(p[0]), int(p[1]), int(p[2]), color(p[3])[0], color(kw.get("trunk", "reddish_brown"))[0])
        elif cmd == "car":
            self.vehicle(int(p[0]), int(p[1]), "car", 10, color(kw.get("color", "red"))[0], None, int(kw.get("on", 1)))
        elif cmd == "vehicle":
            vtype = kw.get("type", "car")
            if vtype not in ("car", "van", "pickup", "truck", "bus"):
                raise SpecError(f"vehicle type must be car/van/pickup/truck/bus, got '{vtype}'")
            n = int(kw.get("length", {"car": 10, "van": 11, "pickup": 13, "truck": 16, "bus": 16}[vtype]))
            if n < 9 or n > 24:
                raise SpecError("vehicle length must be 9..24")
            trim = color(kw["trim"])[0] if "trim" in kw else None
            self.vehicle(int(p[0]), int(p[1]), vtype, n, color(kw.get("color", "red"))[0], trim, int(kw.get("on", 1)))
        elif cmd == "building":
            self.building(rect(p[0]), int(p[1]), kw)
        elif cmd == "roof":
            cells = rect(p[0])
            xs, zs = sorted({c[0] for c in cells}), sorted({c[1] for c in cells})
            self.roof(xs[0], xs[-1], zs[0], zs[-1], int(p[1]), kw.get("type", "gable"), kw.get("ridge", "x"),
                      color(kw.get("color", "dark_bluish_gray"))[0], color(kw.get("gable", "white"))[0],
                      int(kw.get("overhang", 1)))
        elif cmd == "stump":
            bands = [int(b) for b in kw.get("bands", "").split(",") if b]
            self.stump(int(p[0]), int(p[1]), int(p[2]), int(p[3]), color(p[4])[0],
                       color(kw.get("band", p[4]))[0], bands)
        elif cmd == "roots":
            self.roots(int(p[0]), int(p[1]), int(p[2]), color(p[3])[0])
        else:
            raise SpecError(f"unknown command '{cmd}'")
