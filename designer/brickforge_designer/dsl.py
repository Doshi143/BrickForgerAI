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

from .engine import (BRICKS, COLORS, HIDDEN_COLOR, I3, MAIN, PLATES, TILES, YAW, Design, Frame, mm, mul, tile_level,
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
        if kind == "poly":                 # poly Y0..Y1 x,z x,z x,z ...: a plan-view polygon, extruded
            ys = rng_(p[0])
            pts = []
            for tok in p[1:]:
                a, b = tok.split(",")
                pts.append((_bounded(float(a), LIMITS["coord"], "vertex"), _bounded(float(b), LIMITS["coord"], "vertex")))
            if not 3 <= len(pts) <= 16:
                raise SpecError("poly needs 3 to 16 x,z corners")
            x0, x1 = math.floor(min(q[0] for q in pts)), math.ceil(max(q[0] for q in pts))
            z0, z1 = math.floor(min(q[1] for q in pts)), math.ceil(max(q[1] for q in pts))
            if (x1 - x0) * (z1 - z0) * len(ys) > LIMITS["shape_cells"]:
                raise SpecError(f"poly is too big (limit {LIMITS['shape_cells']} cells)")
            plan = set()
            for x in range(x0, x1):
                for z in range(z0, z1):
                    cx, cz, hit = x + .5, z + .5, False
                    for (ax, az), (bx, bz) in zip(pts, pts[1:] + pts[:1]):
                        if (az > cz) != (bz > cz) and cx < ax + (cz - az) * (bx - ax) / (bz - az):
                            hit = not hit
                    if hit:
                        plan.add((x, z))
            return {(x, y, z) for (x, z) in plan for y in ys}
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


WEDGES = {2: ("24299", "24307"), 3: ("43722", "43723"), 4: ("41769", "41770")}   # tread length -> L/R pair


def _cell_cover(q, outline):
    """cover(cell) -> share of the (x, z) cell's area inside part q's top
    outline (local (x, z) LDU points, transformed by q's placement)."""
    M, P = q.mat, q.pos
    poly = [(P[0] + M[0] * x + M[2] * z, P[2] + M[6] * x + M[8] * z) for x, z in outline]

    def inside(px, pz):
        hit = False
        for (x1, z1), (x2, z2) in zip(poly, poly[1:] + poly[:1]):
            if (z1 > pz) != (z2 > pz) and px < x1 + (pz - z1) * (x2 - x1) / (z2 - z1):
                hit = not hit
        return hit

    def cover(cell):
        pts = [(20 * cell[0] + 2 + 4 * a, 20 * cell[1] + 2 + 4 * b) for a in range(5) for b in range(5)]
        return sum(inside(x, z) for x, z in pts) / len(pts)
    return cover


def wall_run(length, odd):
    """Textured walls: mostly 1x2 bricks (the textured part), a 1x1 or 1x3 to
    stagger odd courses and use up an odd length."""
    seq, left = [], length
    if odd and left >= 3:
        seq.append(3 if left % 2 else 1)
        left -= seq[0]
    while left >= 2:
        seq.append(2)
        left -= 2
    if left:
        seq.append(1)
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

    def walls(self, x0, x1, z0, z1, L0, courses, cols, texture="plain", quoins=None):
        """Brick courses around a rectangle, corners interlocked course by
        course.  texture: "masonry"/"log" lay the walls in textured 1x2 bricks
        (98283 embossed bricks / 30136 log).  quoins: a colour for the corner
        blocks -- the face that owns the corner in a course gets a 3-long
        block there, the other face shows its 1-stud end, swapping every
        course, so both faces show the long-short stonework pattern."""
        corners = {(x0, z0), (x0, z1), (x1, z0), (x1, z1)}
        two = {"masonry": "98283", "log": "30136"}.get(texture)
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
                    head = min(3, len(run)) if quoins is not None and run and run[0] in corners else 0
                    tail = min(3, len(run) - head) if quoins is not None and run and run[-1] in corners else 0
                    mid = len(run) - head - tail
                    body = (wall_run if two else tile_run)(mid, odd=c % 2 == 1) if mid > 0 else []
                    seq = ([head] if head else []) + body + ([tail] if tail else [])
                    pos = 0
                    for k, n in enumerate(seq):
                        cx, cz = run[pos]
                        corner = (k == 0 and head) or (k == len(seq) - 1 and tail)
                        col = quoins if corner else pick(cols, cx * 7 + L, cz * 3 + L)
                        pid = two if two and n == 2 and not corner else BRICK_RUN[n]
                        self.D.place(pid, col, cx, L, cz, yaw=0 if axis == "x" else 90)
                        pos += n
                    run = []

    # kind -> (frame, glass, glass offset in the frame's own coordinates, width, height in plates)
    WINDOWS = {"wide": ("60594", "60603", (0, 8, 0), 4, 9), "tall": ("60593", "60602", (0, 0, 0), 2, 9),
               "small": ("60592", "60601", (0, 0, 0), 2, 6), "arched": ("60594", "60603", (0, 8, 0), 4, 9)}

    def window(self, x, z, axis, L, stack, fcol, gcol, kind="wide"):
        """A window (and its glass): wide 1x4x3, tall 1x2x3, small 1x2x2, or
        arched (1x4x3 under a 1x4 arch brick, 12 plates).  Glass for the 1x2
        frames sits at the frame's own origin (measured: the pane's extent,
        y 2..41 / 2..65 inside the frame's 0..48 / 0..72)."""
        fid, gid, goff, w, h = self.WINDOWS[kind]
        yaw = 0 if axis == "x" else 90
        cells = {(x + a, z) if axis == "x" else (x, z + a) for a in range(w)}
        top = L + h * stack + (3 if kind == "arched" else 0)
        self.openings.append((cells, L, top))
        for n in range(stack):
            f = self.D.place(fid, fcol, x, L + h * n, z, yaw=yaw, tag="window")
            self.D.attach(gid, gcol, f, goff, tag="glass")
        if kind == "arched":
            self.D.place("3659", fcol, x, L + h * stack, z, yaw=yaw, tag="window")
        return cells

    def door(self, x, z, axis, L, fcol, lcol):
        yaw = 0 if axis == "x" else 90
        cells = {(x + a, z) if axis == "x" else (x, z + a) for a in range(4)}
        self.openings.append((cells, L, L + 18))
        f = self.D.place("60596", fcol, x, L, z, yaw=yaw, tag="door")
        self.D.attach("60623", lcol, f, (-31, 0, 5), tag="door leaf")
        return cells

    def tree(self, x, z, L, cols, trunk, style="pine", height=2, layers=3):
        """Trees (TECHNIQUES.md item 3).  pine: the pyramid part on a round
        trunk.  round: a 1x1 round-brick trunk with 6x5 leaf layers threaded
        on it, each turned a quarter (the leaf's attachment point carries a
        stud, measured, so the trunk continues through it), capped with a
        leafy plate.  bush: a 2x2 round brick with leaf sprays on opposite
        studs.  Leaf colours can be a mix (dark
        inside, lighter outside reads as depth)."""
        D = self.D
        self.expose_studs({(x, L, z)} if style != "bush" else {(x + a, L, z + b) for a in (0, 1) for b in (0, 1)})
        if style == "bush":
            D.place("3941", pick(cols, x, z), x, L, z, tag="tree")
            D.place("2423", pick(cols, x, z, 1), x, L + 3, z, yaw=0, tag="tree")
            D.place("2423", pick(cols, x, z, 2), x + 1, L + 3, z + 1, yaw=180, tag="tree")
            return
        for n in range(height):
            D.place("3062b", trunk, x, L + 3 * n, z)
        lv = L + 3 * height
        if style == "palm":
            # four swordleaves stacked on the trunk's top stud, a quarter turn each;
            # each leaf's root has an anti-stud (0, 8, 10) and a stud (0, 0, 10) above it
            # (measured), so each clicks onto the one below; they droop over each other
            host = D.parts[D.occ[(x, lv - 1, z)]]
            stud = (host.pos[0], host.pos[1], host.pos[2])
            for k, yaw in enumerate((0, 90, 180, 270)):
                M = YAW[yaw]
                a_ = mul(M, (0, 8, 10))
                pos = (stud[0] - a_[0], stud[1] - a_[1], stud[2] - a_[2])
                q = D._finish(pdef("10884"), pick(cols, x, z, k), pos, M, "tree", host.asm, host=D.parts.index(host))
                D.links.append((D.parts.index(host), D.add(q)))
                s_ = mul(M, (0, 0, 10))
                stud = (pos[0] + s_[0], pos[1] + s_[1], pos[2] + s_[2])
                host = q
            return
        if style == "pine":
            D.place("2435", pick(cols, x, z), x, lv, z, tag="tree")
            return
        for k in range(layers):
            D.place("2417", pick(cols, x, z, k), x, lv, z, yaw=(0, 180, 90, 270)[k % 4], tag="tree")
            lv += 1
            if k < layers - 1:
                D.place("3062b", trunk, x, lv, z)
                lv += 3
        D.place("32607", pick(cols, x, z, 9), x, lv, z, tag="tree")

    def stump(self, x, z, L0, L1, col, band, bands):
        self.expose_for_part("87081", x, L0, z)
        for n, L in enumerate(range(L0, L1, 3)):
            self.D.place("87081", band if n in bands else col, x, L, z)

    def roots(self, x, z, L, col):
        for (dx, dz, yaw) in ((-2, 1, 90), (-2, 3, 90), (4, 2, 270), (4, 0, 270), (1, -2, 0), (2, 4, 180)):
            self.D.place("11477", col, x + dx, L, z + dz, yaw=yaw)

    def scatter(self, pid, cols, cells, L, every, shift, density, seed, rot=0):
        """Decorations at level L, or with L="top" on whatever is highest at
        each cell (spikes along a back, teeth along a jaw, flowers on a
        hedge): the engine's smooth finish there becomes a studded plate so
        the part clicks on.  rot: a yaw, or "alt" to point parts out to
        either side of the row, alternating (teeth along a ridge)."""
        D = self.D
        xs, zs = [c[0] for c in cells], [c[1] for c in cells]
        # "alt": point out to either side of the row, i.e. across its long axis
        across = (0, 180) if cells and max(xs) - min(xs) >= max(zs) - min(zs) else (90, 270)
        tops = {}
        if L == "top":
            for (x, l, z) in D.occ:
                tops[(x, z)] = max(tops.get((x, z), l), l)
        for (x, z) in sorted(cells):
            if every:
                if (x + z + shift) % every:
                    continue
            elif ((x * 73856093 ^ z * 19349663 ^ seed * 83492791) & 0xFFFF) / 65536.0 >= density:
                continue
            lvl = L if L != "top" else (tops[(x, z)] + 1 if (x, z) in tops else None)
            if lvl is None:
                continue
            yaw = across[(x + z) % 2] if rot == "alt" else rot
            q = D.make(pid, pick(cols, x, z, seed + 1), x, lvl, z, yaw=yaw)
            if not D.fits(q):
                continue
            if L == "top":
                self.expose_for_part(pid, x, lvl, z, yaw)
                q = D.make(pid, q.color, x, lvl, z, yaw=yaw)
            if pid == "87747":
                # a horn/claw: the curved blade's bar goes into the open stud of a 1x1
                # round plate (measured: the bar runs 10 LDU down from the blade's
                # origin, the stud's top is 4 above the plate); rot aims the curve
                plate = D.make("85861", q.color, x, lvl, z)
                if not D.supports(plate):
                    continue
                host = D.place("85861", q.color, x, lvl, z, tag="horn")
                blade = D._finish(pdef("87747"), q.color, (host.pos[0], host.pos[1] - 4, host.pos[2]), YAW[yaw],
                                  "horn", host.asm, host=D.parts.index(host))
                if any(D._collide(blade, D.parts[m]) for key in D._buckets(blade.box) for m in D._hash.get(key, ())
                       if D.parts[m] is not host):
                    D.remove([D.parts.index(host)])
                    continue
                D.links.append((D.parts.index(host), D.add(blade)))
            elif D.supports(q):
                D.place(pid, q.color, x, lvl, z, yaw=yaw)

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
        wintype = kw.get("wintype", "wide")
        if wintype not in self.WINDOWS:
            raise SpecError(f"wintype must be one of {', '.join(self.WINDOWS)}")
        texture = kw.get("texture", "plain")
        if texture not in ("plain", "masonry", "log"):
            raise SpecError("texture must be plain, masonry or log")
        quoins = color(kw["quoins"])[0] if "quoins" in kw else None
        ww = self.WINDOWS[wintype][3]
        wl = 6 if wintype == "small" else 3                  # small windows sit higher in the storey
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
                    k = max(0, (n - 1 + gap) // (ww + gap))
                    start = a + (n - (k * ww + (k - 1) * gap)) // 2
                    for w in range(k):
                        s = start + w * (ww + gap)
                        cells_w = {(s + i, fixed) if axis == "x" else (fixed, s + i) for i in range(ww)}
                        near = {(c[0] + dx, c[1] + dz) for c in used for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
                        if cells_w & near:
                            continue
                        x_, z_ = (s, fixed) if axis == "x" else (fixed, s)
                        used |= self.window(x_, z_, axis, L + wl, 1, frame, glass, wintype)
                        ends = [(s - 1, fixed), (s + ww, fixed)] if axis == "x" else [(fixed, s - 1), (fixed, s + ww)]
                        posts |= set(ends)
            if style == "timber":
                for (px, pz) in sorted(posts):
                    if all((px, L + l, pz) not in self.D.occ for l in range(3 * courses)) and (px, pz) not in used:
                        for c in range(courses):
                            self.D.place("3005", trim, px, L + 3 * c, pz)
            self.walls(x0, x1, z0, z1, L, courses, wall, texture, quoins)
            L += 3 * courses
            if f < floors - 1:
                x0, x1, z0, z1 = x0 - jetty, x1 + jetty, z0 - jetty, z1 + jetty
                self.slab({(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)}, L, [trim], PLATES)
                L += 2
        roof = kw.get("roof", "gable")
        rstyle = kw.get("roofstyle", "smooth")
        if rstyle not in ("smooth", "slope"):
            raise SpecError("roofstyle must be smooth or slope")
        self.roof(x0, x1, z0, z1, L, roof, kw.get("ridge", "x"),
                  color(kw.get("roofcolor", "dark_bluish_gray"))[0],
                  color(kw.get("gable", kw.get("color", "white")))[0], int(kw.get("overhang", 1)), rstyle)

    def slope_roof(self, X0, X1, Z0, Z1, L, ridge, rcol, gcol):
        """A gable roof of real 45-degree slope bricks, as in official sets
        (TECHNIQUES.md item 9): a slab ties the walls together, then brick
        courses step in one stud per course, each eave row a 2x2/2x1 slope
        (3039/3040b) facing out, the gable-coloured core between them, and
        double slopes (3043/3044b) along the ridge.  An odd span gets one
        extra row of overhang on the far side so the ridge closes evenly."""
        D = self.D
        if ridge == "x":
            A0, A1, B0, B1 = X0, X1, Z0, Z1
            at = lambda a, b: (a, b)
            down = lambda s: yaw_pointing(MAIN, (0, 0, s), local=(0, 0, -1))
            dbl = 0
        else:
            A0, A1, B0, B1 = Z0, Z1, X0, X1
            at = lambda a, b: (b, a)
            down = lambda s: yaw_pointing(MAIN, (s, 0, 0), local=(0, 0, -1))
            dbl = 90
        if (B1 - B0 + 1) % 2:
            B1 += 1
        self.slab({at(a, b) for a in range(A0, A1 + 1) for b in range(B0, B1 + 1)}, L, [rcol], PLATES)
        lvl, b0, b1 = L + 2, B0, B1
        while b1 - b0 + 1 >= 4:
            for bs, s in ((b0, -1), (b1, 1)):
                bmin = min(bs, bs - s)
                a = A0
                while a <= A1:
                    n = 2 if a + 1 <= A1 else 1
                    x, z = at(a, bmin) if ridge == "x" else at(a, bmin)
                    D.place("3039" if n == 2 else "3040b", rcol, x, lvl, z, yaw=down(s), tag="roof")
                    a += n
            core = {at(a, b): (gcol if a in (A0, A1) else None) for a in range(A0, A1 + 1)
                    for b in range(b0 + 2, b1 - 1)}
            if core:
                tile_level(D, core, lvl, [], "x" if ridge == "z" else "z",
                           three={c: set() if col is None else {col} for c, col in core.items()}, bricks=BRICKS)
            lvl, b0, b1 = lvl + 3, b0 + 1, b1 - 1
        a = A0
        while a <= A1:                                   # the ridge: double slopes over the last two rows
            n = 2 if a + 1 <= A1 else 1
            x, z = at(a, b0)
            D.place("3043" if n == 2 else "3044b", rcol, x, lvl, z, yaw=dbl, tag="roof")
            a += n

    def roof(self, x0, x1, z0, z1, L, kind, ridge, rcol, gcol, o=1, style="smooth"):
        X0, X1, Z0, Z1 = x0 - o, x1 + o, z0 - o, z1 + o
        area = {(x, z) for x in range(X0, X1 + 1) for z in range(Z0, Z1 + 1)}
        if kind == "none":
            return
        if kind == "flat":
            self.slab(area, L, [rcol], self.flat)
            return
        if style == "slope" and kind == "gable":
            self.slope_roof(X0, X1, Z0, Z1, L, ridge, rcol, gcol)
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
        n0 = len(self.D.parts)
        self._sculpt_with_retry(spec)
        if spec.get("texture") == "rock":
            self.rockify(n0, spec)
        elif spec.get("texture") == "greeble":
            self.greeble(n0)

    def greeble(self, n0):
        """Greebling (TECHNIQUES.md item 11): small relief on the flat tops of
        machines, robots and vehicles.  About 40% of the top tiles are split
        into grille tiles (2412b, 1x2, same colour) with dark round tiles on
        odd cells.  A top tile can be what ties the plates under it together,
        so each swap is kept only if the model stays in as many pieces."""
        D = self.D
        tops = [i for i in range(n0, len(D.parts)) if D.parts[i].tag == "top" and hash01(i, 11) < 0.4]
        done = 0
        for i in sorted(tops, reverse=True):
            if i >= len(D.parts) or D.parts[i].tag != "top":
                continue
            before = len(D.components()[0])
            snap = (list(D.parts), [q.host for q in D.parts], dict(D.occ), list(D.links))
            q = D.parts[i]
            cells = sorted(c for c, j in D.occ.items() if j == i)
            L = cells[0][1]
            todo = {(c[0], c[2]) for c in cells}
            D.remove([i])
            along = "x" if len({x for x, _ in todo}) >= len({z for _, z in todo}) else "z"
            for (x, z) in sorted(todo):
                if (x, z) not in todo:
                    continue
                nxt = (x + 1, z) if along == "x" else (x, z + 1)
                if nxt in todo:
                    D.place("2412b", q.color, x, L, z, yaw=0 if along == "x" else 90, tag="greeble")
                    todo -= {(x, z), nxt}
                else:
                    D.place("98138", COLORS["dark_bluish_gray"], x, L, z, tag="greeble")
                    todo.discard((x, z))
            if len(D.components()[0]) > before:
                parts, hosts, occ, links = snap
                D.parts, D.occ, D.links = parts, occ, links
                for p_, h in zip(D.parts, hosts):
                    p_.host = h
                D._reindex()
            else:
                done += 1
        if done:
            self.repairs.append(("greebled", done))

    def rockify(self, n0, spec):
        """Rockwork (TECHNIQUES.md item 10): builders avoid any repeating
        pattern -- mixed greys/browns, slopes facing every way.  Every visible
        part of the sculpt takes a seeded colour from the rock palette (per
        part, so the tiling is never fragmented), and most smooth top tiles
        become 1x1 cheese slopes turned at random, where they fit."""
        D = self.D
        mix = spec.get("mix") or [spec["color"]]
        tops = []
        for i in range(n0, len(D.parts)):
            q = D.parts[i]
            if q.color != HIDDEN_COLOR and q.host is None and q.tag not in ("eye", "pupil", "anchor", "panel"):
                q.color = mix[int(hash01(i, 77) * len(mix))]
            if q.tag == "top" and q.pid in ("3070b", "3069b", "3068b", "2431", "63864", "87079"):
                tops.append(i)
        drop, swaps = [], []
        for i in tops:
            q = D.parts[i]
            cells = [c for c, j in D.occ.items() if j == i]
            if hash01(i, 5) < 0.3 or not cells:
                continue
            drop.append(i)
            swaps += [(c, q.color) for c in cells]
        if not drop:
            return
        D.remove(drop)
        for (x, L, z), col in swaps:
            yaw = (0, 90, 180, 270)[int(hash01(x, z, L) * 4)]
            q = D.make("54200", mix[int(hash01(x, L, z, 3) * len(mix))], x, L, z, yaw=yaw)
            if D.fits(q):
                D.place("54200", q.color, x, L, z, yaw=yaw, tag="rock")
            else:
                D.place("3070b", col, x, L, z, tag="top")
        self.repairs.append(("rockwork", len(swaps)))

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

    def plan_wedges(self, core, reserved, placements, polys):
        """Wedge plates on diagonal staircase edges (TECHNIQUES.md item 5).
        On each level, along each side of the outline, a tread of 2-4 cells
        followed by a one-stud step outward is a diagonal the grid can only
        show as a staircase: a 2x2/2x3/2x4 wedge plate lays its studded
        column on the tread and its tapered column over the empty cells
        beside it, so the edge reads as a straight diagonal.  The part and
        its rotation are chosen by testing the part's measured top outline
        (parts_table "outline") against the step, never assumed.  Only on
        `poly` cells: edges the spec drew as diagonals (wings, bows, fins); on
        balls and cylinders the staircase is the intended curve and wedges
        mostly just cost a rebuild (measured on the 15 evaluation specs)."""
        D = self.D
        claimed = set()
        by_level = defaultdict(set)
        for (x, L, z) in core:
            by_level[L].add((x, z))
        cands = []
        for L in sorted(by_level):
            S = by_level[L]
            for axis in ("z", "x"):                       # the tread runs along this axis
                to_xz = (lambda p, a: (p, a)) if axis == "z" else (lambda p, a: (a, p))
                rows = defaultdict(list)
                for (x, z) in S:
                    a, p = (z, x) if axis == "z" else (x, z)
                    rows[a].append(p)
                for s in (1, -1):
                    edge = {a: (max(ps) if s > 0 else min(ps)) for a, ps in rows.items()}
                    as_ = sorted(edge)
                    treads, cur = [], [as_[0]] if as_ else []
                    for a in as_[1:]:
                        if a == cur[-1] + 1 and edge[a] == edge[cur[0]]:
                            cur.append(a)
                        else:
                            treads.append(cur)
                            cur = [a]
                    if cur:
                        treads.append(cur)
                    for tr in treads:
                        e = edge[tr[0]]
                        nxt, prv = edge.get(tr[-1] + 1), edge.get(tr[0] - 1)
                        up_next, up_prev = nxt == e + s, prv == e + s
                        if up_next == up_prev or len(tr) < 2:
                            continue                      # no single outward step, or a notch
                        seg = tr[-4:] if up_next else tr[:4]
                        wide, narrow = (seg[-1], seg[0]) if up_next else (seg[0], seg[-1])
                        full = tuple(to_xz(e, a) for a in seg)
                        cands.append((L, full, tuple(to_xz(e + s, a) for a in seg), to_xz(e + s, wide),
                                      to_xz(e + s, narrow)))
        # A 1-stud-wide wedge column is held only by what crosses it above or
        # below; wedges stacked on the same cells would form a closed island.
        # So per vertical run only the bottom one is kept, with body over its
        # studded column: the layer above (plates or the smooth top tiles)
        # bridges it to the rest, as builders tuck a wing plate under tiles.
        at = defaultdict(set)
        for L, full, *_ in cands:
            at[full].add(L)
        for L, full, tri, wide, narrow in sorted(cands, key=lambda c: c[0]):
            if L - 1 in at[full] or not all((x, L + 1, z) in core for (x, z) in full):
                continue
            if not all((x, L, z) in polys for (x, z) in full):
                continue                              # only edges drawn as diagonals (poly shapes)
            cells3 = {(x, L, z) for (x, z) in full + tri}
            if (cells3 & claimed or any((x, L, z) in reserved for (x, z) in full)
                    or any(c in by_level[L] or (c[0], L, c[1]) in D.occ for c in tri)):
                continue
            cols = {core[(x, L, z)] for (x, z) in full}
            if len(cols) != 1:
                continue
            fit = self._fit_wedge(len(full), L, list(full), wide, narrow)
            if fit:
                pid, i, k, yaw = fit
                claimed |= cells3
                placements.append((pid, cols.pop(), i, L, k, yaw, "wedge", {(x, L, z) for (x, z) in full}))
        return claimed

    def _fit_wedge(self, n, L, full, wide, narrow):
        """The (part, origin cell, yaw) whose real outline covers the `full`
        cells and the `wide` end of the tapered column but not the `narrow`
        end -- found by transforming the measured outline, not assumed."""
        xs = [c[0] for c in full] + [wide[0], narrow[0]]
        zs = [c[1] for c in full] + [wide[1], narrow[1]]
        i, k = min(xs), min(zs)
        for pid in WEDGES[n]:
            outline = pdef(pid).outline
            for yaw in (0, 90, 180, 270):
                q = self.D.make(pid, 0, i, L, k, yaw=yaw)
                cover = _cell_cover(q, outline)
                if all(cover(c) > 0.9 for c in full) and cover(wide) > 0.5 and cover(narrow) < 0.5:
                    return pid, i, k, yaw
        return None

    def plan_limb_anchor(self, core, reserved, lb, S):
        """Where a limb leaves the body: 2 exposed body cells side by side at
        the start point's level, on the face (+-x / +-z) that points most
        toward the tip, for a 1x2 plate whose ball (14417, measured: 10 LDU
        past its long edge) sticks out of that face."""
        (sx, sy, sz), (tx, ty, tz) = lb["start"], lb["end"]
        L = S + int(math.floor(sy))
        dx, dz = tx - sx, tz - sz
        if abs(dx) < 1e-6 and abs(dz) < 1e-6:
            dx, dz = 1.0, 0.0
        faces = sorted(((1, 0), (-1, 0), (0, 1), (0, -1)), key=lambda f: -(f[0] * dx + f[1] * dz))
        taken = lambda c: c in core or c in self.D.occ
        for L in (L0, L0 + 1, L0 - 1, L0 + 2, L0 - 2) if (L0 := L) is not None else ():
            for fx, fz in faces[:2]:
                best = None
                for (x, l, z) in core:
                    if l != L:
                        continue
                    pair = [(x, z), (x, z + 1)] if fx else [(x, z), (x + 1, z)]
                    # the plate's 2 cells on the surface, and room outward (a link is 3 studs
                    # long and reaches a plate above and below its joint) for the first link
                    ok = all((px, L, pz) in core and (px, L, pz) not in reserved
                             and not any(taken((px + k * fx, L + dl, pz + k * fz)) for k in (1, 2, 3) for dl in (-1, 0, 1))
                             for px, pz in pair)
                    if not ok:
                        continue
                    cx, cz = (x + (0.5 if fz else 0) + 0.5, z + (0.5 if fx else 0) + 0.5)
                    dist = (cx - sx) ** 2 + (cz - sz) ** 2
                    if best is None or dist < best[0]:
                        cells = {(px, L, pz) for px, pz in pair}
                        best = (dist, ((x, L, z), yaw_pointing(MAIN, (fx, 0, fz), local=(0, 0, -1)), cells, (fx, fz)))
                if best and best[0] <= 9:                  # within 3 studs of the asked point
                    return best[1]
        return None

    def grow_limb(self, anchor, lb, face, S, default):
        """A chain of ball-and-socket plates (14419) from the anchor's ball to
        the tip (TECHNIQUES.md item 17): each link's socket clicks onto the
        previous ball (measured: socket at local (30, 4, 0) opening +x, ball at
        (-30, 4, 0), 60 LDU apart), its axis follows a curve that leaves the
        body level along the face and ends at the tip, turning at most 40
        degrees per joint, studs kept as close to up as the turn allows.  A
        link that would hit anything, or go under the table, ends the limb
        there (reported as a repair, not an error)."""
        D = self.D
        P = pdef("14419")
        (Sx, Sy, Sz), _ = P.sockets[0]
        Bx, By, Bz = P.balls[0]
        ball = mul(anchor.mat, pdef("14417").balls[0])
        J = (anchor.pos[0] + ball[0], anchor.pos[1] + ball[1], anchor.pos[2] + ball[2])
        tx, ty, tz = lb["end"]
        T = (20 * tx, -8 * (S + ty), 20 * tz)
        f = (face[0], 0.0, face[1])
        dist = sum((T[i] - J[i]) ** 2 for i in range(3)) ** 0.5
        C = tuple(J[i] + f[i] * dist * 0.4 for i in range(3))
        bend = math.radians(lb["bend"])
        n = max(1, min(24, round(dist / 60)))
        col = lb["color"] if lb["color"] is not None else default
        host, prev = anchor, f
        unit = lambda v: (lambda m: tuple(c / m for c in v) if m > 1e-9 else (1.0, 0.0, 0.0))(sum(c * c for c in v) ** 0.5)
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        cross = lambda a, b: (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        placed = 0
        for i in range(n):
            s = (i + 1) / n
            aim = tuple((1 - s) ** 2 * J[k] + 2 * (1 - s) * s * C[k] + s * s * T[k] for k in range(3)) \
                if i < n - 1 else T
            d = f if i == 0 else unit(tuple(aim[k] - J[k] for k in range(3)))    # first link: straight out
            if bend and i >= n // 2:                        # curl the tip over (downward in LDraw = +y)
                d = unit((d[0] * math.cos(bend), d[1] * math.cos(bend) + math.sin(bend), d[2] * math.cos(bend)))
            cosang = max(-1.0, min(1.0, dot(prev, d)))
            if cosang < math.cos(math.radians(40)):         # a Joint-8 ball turns about 40 degrees
                axis = unit(cross(prev, d))
                th = math.radians(40)
                # rotate prev toward d by 40 degrees (Rodrigues)
                d = unit(tuple(prev[k] * math.cos(th) + cross(axis, prev)[k] * math.sin(th)
                               + axis[k] * dot(axis, prev) * (1 - math.cos(th)) for k in range(3)))
            up = (0.0, -1.0, 0.0)
            u = tuple(up[k] - dot(up, d) * d[k] for k in range(3))
            if sum(c * c for c in u) < 1e-6:
                u = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 0.0, 1.0)
            u = unit(u)
            cx, cy = tuple(-c for c in d), tuple(-c for c in u)        # local +x -> -d, local +y -> -u
            cz = cross(cx, cy)
            M = (cx[0], cy[0], cz[0], cx[1], cy[1], cz[1], cx[2], cy[2], cz[2])
            so = mul(M, (Sx, Sy, Sz))
            pos = (J[0] - so[0], J[1] - so[1], J[2] - so[2])
            q = D._finish(P, col, pos, M, "limb", host.asm, host=D.parts.index(host))
            clash = any(D._collide(q, D.parts[m]) for key in D._buckets(q.box) for m in D._hash.get(key, ())
                        if D.parts[m] is not host and D.parts[m].host != D.parts.index(host))
            if clash or q.box[1][1] > 1:
                break
            idx = D.add(q)
            D.links.append((D.parts.index(host), idx))
            if lb.get("thick"):
                # a 1x2 curved slope on the link's two studs rounds the limb out
                # (11477 is 2 long along its local z: turned a quarter to lie along the link)
                cap = D._finish(pdef("11477"), col, pos, mm(M, YAW[90]), "limb", q.asm, host=idx)
                if not any(D._collide(cap, D.parts[m]) for key in D._buckets(cap.box) for m in D._hash.get(key, ())
                           if m != idx and D.parts[m].host != idx and m != D.parts.index(host)):
                    D.links.append((idx, D.add(cap)))
            bo = mul(M, (Bx, By, Bz))
            J = (pos[0] + bo[0], pos[1] + bo[1], pos[2] + bo[2])
            host, prev = q, d
            placed += 1
        if placed < n:
            self.repairs.append(("limb shortened", n - placed))

    def build_flap(self, fl, default):
        """A hinged panel (TECHNIQUES.md item 16): wings with dihedral, ears,
        fins.  A 1x2 hinge base (3937) clicks onto the body's top at the flap's
        two columns; the hinge top (3938) turns about their shared axis
        (measured: along the pair's x, through (0, 10, 0) in both parts) by
        `angle` from flat; a plate panel LENGTH studs out and WIDTH studs
        along the axis is built on its two studs in that tilted frame.  If
        any of it would hit something, the flap is left off (reported)."""
        D = self.D
        x, z, d = fl["x"], fl["z"], fl["dir"]
        col = fl["color"] if fl["color"] is not None else default
        axis_x = d in ("+z", "-z")                      # the hinge axis runs across the flap's direction
        pair = [(x, z), (x + 1, z)] if axis_x else [(x, z), (x, z + 1)]
        tops = {}
        for (cx, l, cz) in D.occ:
            if (cx, cz) in pair:
                tops[(cx, cz)] = max(tops.get((cx, cz), l), l)
        if len(tops) < 2 or len(set(tops.values())) != 1:
            self.errors.append(f"flap at {x},{z}: needs a flat top two studs wide there to click its hinge onto")
            return False
        L = next(iter(tops.values())) + 1
        n0 = len(D.parts)
        self.expose_studs({(cx, L, cz) for cx, cz in pair})
        yaw = 0 if axis_x else 90
        base = D.make("3937", col, min(c[0] for c in pair), L, min(c[1] for c in pair), yaw=yaw)
        if not D.fits(base) or not D.supports(base):
            self.errors.append(f"flap at {x},{z}: no room for its hinge")
            return False
        base = D.place("3937", col, min(c[0] for c in pair), L, min(c[1] for c in pair), yaw=yaw, tag="flap")
        bi = D.parts.index(base)
        # which way the panel runs in the hinge's own frame (+-z local), and the tilt that raises it
        out_world = {"+z": (0, 0, 1), "-z": (0, 0, -1), "+x": (1, 0, 0), "-x": (-1, 0, 0)}[d]
        local_out = 1 if tuple(round(c) for c in mul(base.mat, (0, 0, 1))) == out_world else -1
        phi = math.radians(fl["angle"]) * local_out
        c_, s_ = math.cos(phi), math.sin(phi)
        Rx = (1, 0, 0, 0, c_, -s_, 0, s_, c_)
        pivot = (0, 10, 0)
        rp = mul(Rx, pivot)
        off = mul(base.mat, (pivot[0] - rp[0], pivot[1] - rp[1], pivot[2] - rp[2]))
        M = mm(base.mat, Rx)
        top = D._finish(pdef("3938"), col, (base.pos[0] + off[0], base.pos[1] + off[1], base.pos[2] + off[2]),
                        M, "flap", base.asm, host=bi)
        ti = D.add(top)
        D.links.append((bi, ti))
        # the panel: plates in the hinge top's frame, cell (i, k) spans local x 20i..20i+20 and
        # z 20k-10..20k+10 around the top's own studs (x = +-10, z = 0), level 0 on its top
        w, n = fl["width"], fl["length"]
        o = mul(M, (0, 0, -10))
        F = Frame((top.pos[0] + o[0], top.pos[1] + o[1], top.pos[2] + o[2]), M, "flap")
        i0 = -(w // 2)
        cells = {(i, k * local_out if local_out > 0 else -k): col for i in range(i0, i0 + w) for k in range(n)}
        cells = {(i, k): col for (i, k), col in cells.items()}
        n1 = len(D.parts)

        def attempt(r, mirror, flip):
            # two crossed layers: side-by-side plates never connect, so a one-layer
            # panel only holds where each piece happens to reach the hinge
            tile_level(D, cells, 0, PLATES, "x" if flip else "z", frame=F, tag="flap", rng=r)
            tile_level(D, cells, 1, self.flat, "z" if flip else "x", frame=F, tag="flap", rng=r)
        verified(D, attempt, tries=16)
        for i in range(n1, len(D.parts)):
            D.parts[i].host = ti                        # the panel rides on the hinge top
        new = range(n0, len(D.parts))
        clash = any(D._collide(D.parts[m], D.parts[o_]) for m in new if m != bi
                    for key in D._buckets(D.parts[m].box) for o_ in D._hash.get(key, ())
                    if o_ not in new and o_ != bi and D.parts[o_].host != bi)
        if clash or not D.is_one_piece(list(new)):
            D.remove(list(new))
            self.errors.append(f"flap at {x},{z}: its panel would hit the model; move it or make it shorter")
            return False
        self.repairs.append(("flap", len(new)))
        return True

    def dress_gear(self, g, side, L0, zside):
        """An axle pin (3749) in the Technic brick's hole and a gear on its
        axle, flat against the flank (TECHNIQUES.md item 18: Technic as
        texture).  Measured: 3700's hole runs along z through (0, 10, +-10);
        3749 is pin for x -20..0 and axle for 0..19.5; the gear (3647 8-tooth,
        3648b 24-tooth) turns about its z, about 20 LDU thick."""
        D = self.D
        brick = D.parts[D.occ[(g["x"], L0, zside)]]
        out = -1 if side == "L" else 1
        face = mul(brick.mat, (0, 10, 10 * out))               # the hole's mouth, between the brick's two cells
        mouth = (brick.pos[0] + face[0], brick.pos[1] + face[1], brick.pos[2] + face[2])
        # 3749: local +x outward (world +-z), so its pin half (local x < 0) is in the hole
        Rp = (0, 0, -out, 0, 1, 0, out, 0, 0)
        pin = D._finish(pdef("3749"), COLORS["dark_bluish_gray"], mouth, Rp, "gear", brick.asm,
                        host=D.parts.index(brick))
        pi = D.add(pin)
        D.links.append((D.parts.index(brick), pi))
        gid = "3648b" if g["size"] == "large" else "3647"
        centre = (mouth[0], mouth[1], mouth[2] + out * 10)
        gear = D._finish(pdef(gid), g["color"], centre, I3, "gear", brick.asm, host=pi)
        if any(D._collide(gear, D.parts[m]) for key in D._buckets(gear.box) for m in D._hash.get(key, ())
               if D.parts[m] is not brick and m != pi):
            D.remove([pi])
            self.repairs.append((f"gear left off {side}", 1))
            return
        D.links.append((pi, D.add(gear)))

    def plan_large_eye(self, core, reserved, e, side, S, clear=0):
        """A flat, exposed patch 2 studs wide and 3 plates tall on the flank at
        the eye's height (for two side-stud bricks), with nothing sticking out
        under it for the 2.5 plates the round plate hangs down."""
        xs = (e["x"], e["x"] + 1)
        for L0 in (S + e["y"] - 1, S + e["y"] - 2, S + e["y"]):
            zc = [c[2] for c in core if c[0] in xs and c[1] == L0 + 1]
            if not zc:
                continue
            zside = min(zc) if side == "L" else max(zc)
            out = zside - 1 if side == "L" else zside + 1
            cells = {(x, L0 + l, zside) for x in xs for l in range(3)}
            if not all(c in core and c not in reserved and (c[0], c[1], out) not in core
                       and (c[0], c[1], out) not in self.D.occ for c in cells):
                continue
            if any((x, l, out) in core or (x, l, out) in self.D.occ for x in xs for l in range(L0 - 3, L0)):
                continue
            if clear and any((x, l, out) in core or (x, l, out) in self.D.occ
                             for x in range(xs[0] - clear // 2, xs[1] + clear // 2 + 1)
                             for l in range(L0 - clear, L0 + 3 + clear)):
                continue                                   # room for a gear's teeth around the hole
            return L0, zside, cells
        return None

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
        if spec.get("round") and not self.D.is_one_piece(range(n0, len(self.D.parts))):
            # round columns join the body only through their end studs; a sculpt
            # that isn't one piece with them is rebuilt with square columns
            self.D.rollback(n0)
            del self.repairs[r0:]
            del self.errors[e0:]
            spec = dict(spec, round=[])
            ok = self._sculpt(spec)
            self.repairs.append(("round columns dropped", 0))
        if spec.get("wedges", True) and not self.D.is_one_piece(range(n0, len(self.D.parts))) and any(
                q.tag == "wedge" for q in self.D.parts[n0:]):
            # wedges are dressing too: rebuild without them rather than fall apart
            self.D.rollback(n0)
            del self.repairs[r0:]
            del self.errors[e0:]
            spec = dict(spec, wedges=False)
            ok = self._sculpt(spec)
            self.repairs.append(("wedges dropped", 0))
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

        # ---- thin round columns (legs, posts, stands): 2x2 round bricks and round
        # plates where the column stands free of the body (TECHNIQUES.md item 12)
        for (cx, cz, y0, y1) in spec.get("round", ()):
            quad = [(cx - 1, cz - 1), (cx, cz - 1), (cx - 1, cz), (cx, cz)]
            ring = [(cx + a, cz + b) for a in range(-2, 2) for b in range(-2, 2) if (cx + a, cz + b) not in quad]
            free = [L for L in range(S + y0, S + y1 + 1)
                    if all((x, L, z) in core and (x, L, z) not in reserved for x, z in quad)
                    and not any((x, L, z) in core for x, z in ring)
                    and len({core[(x, L, z)] for x, z in quad}) == 1]
            L = free[0] if free else None
            while free:
                run = [L]
                while run[-1] + 1 in free:
                    run.append(run[-1] + 1)
                pos = 0
                while pos < len(run):
                    lvl = run[pos]
                    n = 3 if pos + 3 <= len(run) and len({core[(cx - 1, lvl + l, cz - 1)] for l in range(3)}) == 1 else 1
                    cells = {(x, lvl + l, z) for x, z in quad for l in range(n)}
                    placements.append(("3941" if n == 3 else "4032", core[(cx - 1, lvl, cz - 1)], cx - 1, lvl, cz - 1, 0,
                                       "round", cells))
                    for c in cells:
                        core.pop(c, None)
                    pos += n
                free = [f for f in free if f > run[-1]]
                L = free[0] if free else None
        if spec.get("round"):
            flex = {c for c in flex if c in core}

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
        if spec.get("wedges", True) and spec.get("poly"):
            polys = {(x, S + y, z) for (x, y, z) in spec["poly"]}
            wedged = {c for c in self.plan_wedges(core, reserved, placements, polys) if c in core}
            reserved |= wedged
            for c in wedged:
                tiles_top.pop(c, None)
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
                if e.get("size") == "large":
                    big = self.plan_large_eye(core, reserved, e, side, S)
                    if big:
                        L0, zside, cells = big
                        reserved |= cells
                        for xx in (e["x"], e["x"] + 1):
                            placements.append(("87087", core[(xx, L0 + 1, zside)], xx, L0, zside,
                                               0 if side == "L" else 180, "eye", {c for c in cells if c[0] == xx}))
                        surface_eyes.append((side, e, L0, zside))
                        continue
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

        # ---- Technic gears on the flanks: a Technic brick with a hole in the surface
        gear_plan = []
        for g in spec.get("gears", ()):
            for side in ("L", "R"):
                spot = self.plan_large_eye(core, reserved, g, side, S, clear=4 if g["size"] == "large" else 2)
                if not spot:
                    self.repairs.append((f"gear left off {side}", 1))
                    continue
                L0, zside, cells = spot
                reserved |= cells
                placements.append(("3700", core[(g["x"], L0 + 1, zside)], g["x"], L0, zside, 0, "gear", cells))
                gear_plan.append((g, side, L0, zside))

        # ---- limbs: a ball plate built into the body's edge for each
        limb_plan = []
        for lb in spec.get("limbs", ()):
            anchor = self.plan_limb_anchor(core, reserved, lb, S)
            if anchor is None:
                self.errors.append(f"limb from {lb['start']}: no free edge of the body near that point for its ball plate "
                                   f"(it needs 2 exposed cells side by side on the face toward the tip)")
                continue
            (x, L, z), yaw, cells, face = anchor
            reserved |= cells
            placements.append(("14417", core[(x, L, z)], x, L, z, yaw, "limb", cells))
            limb_plan.append((lb, (x, L, z), face))

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

        soft = {c: col for c, col in soft.items() if core.get(c) == col and c not in reserved}
        fill_cells = {c: (None if c in flex or c in soft else col) for c, col in core.items() if c not in reserved}

        # Cells of thin features (under 3 plates tall: wings, fins, ledges).  A
        # brick right beside one blocks it: a 2-plate wing can only tie into the
        # body through plates that reach across the joint at its own levels.
        run = {}
        for (x, L, z) in core:
            if (x, L - 1, z) not in core:
                n = 0
                while (x, L + n, z) in core:
                    n += 1
                for l in range(n):
                    run[(x, L + l, z)] = n
        thin = {c for c, n in run.items() if n < 3}

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
                        if any((x + a, L + l, z + b) in thin for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))
                               for l in range(3)):
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
            # the smooth top last, so each tile can bridge the plates under it
            # (and change with every retry): laid first, tops could only line up
            # with the fill's joins, and thin parts (wings) fell apart
            for L2, cells in by_level.items():
                tile_level(D, cells, L2, self.flat, "x", tag="top", rng=r, mirror=mirror)
        D.new_step()
        n_fill = len(D.parts)
        fill_ok = verified(D, fill, standalone=D.default_asm != "main")
        self.repairs.append(("sculpt fill", fill_ok))
        if fill_ok < 0:
            self.rescue_loose(n_sculpt, flex | set(soft))
        if soft:
            recolour(D, n_fill, soft, hidden=flex)
        for g, side, L0, zside in gear_plan:
            self.dress_gear(g, side, L0, zside)
        # limbs last, so each link is checked against the finished body
        for lb, (x, L, z), face in limb_plan:
            self.grow_limb(D.parts[D.occ[(x, L, z)]], lb, face, S, spec["color"])
        for fl in spec.get("flaps", ()):
            # the asked spot first, then nearby ones: on a dome, the body just inward
            # of the hinge can stand taller than it and block the tilting panel
            spots = sorted(((dx, dz) for dx in range(-3, 4) for dz in range(-3, 4)), key=lambda o: o[0] ** 2 + o[1] ** 2)
            e0 = len(self.errors)
            first = None
            for dx, dz in spots:
                if self.build_flap(dict(fl, x=fl["x"] + dx, z=fl["z"] + dz), spec["color"]):
                    del self.errors[e0:]
                    break
                first = first or self.errors[e0:e0 + 1]
                del self.errors[e0:]
            else:
                self.errors += first or []

        # ---- panels, then surface eyes' pupils
        D.new_step()
        for pnl in panels:
            self.build_panel(pnl, spec, S)
        for side, e, L0, zside in surface_eyes:
            Oy = -8 * (L0 + 3) + 20
            if side == "L":
                F, i = Frame((0, Oy, 20 * zside), L_FRAME, "eyeL"), e["x"]
                u = lambda x, w=1: x                      # frame column of world column x
            else:
                F, i = Frame((0, Oy, 20 * (zside + 1)), R_FRAME, "eyeR"), -e["x"] - 1
                u = lambda x, w=1: -x - w
            if e.get("size") == "large" and (e["x"] + 1, L0, zside) in D.occ and                     D.parts[D.occ[(e["x"] + 1, L0, zside)]].tag == "eye":
                # a white 2x2 round plate across the two side studs (its top row of
                # anti-studs on them, hanging 2.5 plates below), and a round pupil
                # on its front-upper stud, looking the way the animal faces
                plate = D.make("4032", e["ring"], u(e["x"], 2), 0, -1, frame=F, tag="eye")
                front = e["x"] + 1 if e.get("look", "+x") == "+x" else e["x"]
                pupil = D.make("98138", e["pupil"], u(front), 1, 0, frame=F, tag="pupil")
                if D.fits(plate) and D.fits(pupil):
                    D.place("4032", e["ring"], u(e["x"], 2), 0, -1, frame=F, tag="eye")
                    D.place("98138", e["pupil"], u(front), 1, 0, frame=F, tag="pupil")
                    continue
                self.repairs.append((f"large eye made small {side}", 1))
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
        texture = kw.get("texture", "plain")
        if texture not in ("plain", "rock", "greeble"):
            raise SpecError("sculpt texture must be plain, rock or greeble")
        spec = dict(base=int(kw.get("base", 0)), color=(grad[0][0] if grad else color(ctok))[0], grad=grad,
                    texture=texture, mix=None if grad else color(ctok),
                    hollow=int(kw.get("hollow", 0)), caps=kw.get("caps", "both"), wedges=kw.get("wedges", "1") != "0",
                    shapes=[], paint=[], panels=[], ppaint=[], eyes=[], wheels=None, poly=set(), round=[], limbs=[], flaps=[], gears=[])
        for ln, raw in block:
            if not raw:
                continue
            t = raw.split()
            p, k = split_kw(t[1:])
            try:
                if t[0] in ("col", "box", "ball", "cyl", "poly"):
                    spec["shapes"].append(("add", shape_cells(t[0], p)))
                    if t[0] == "cyl" and p[0] == "y" and max(float(v) for v in p[4:6]) <= 1.3 \
                            and float(p[2]).is_integer() and float(p[3]).is_integer():
                        ys = rng_(p[1])                 # a thin round column on a stud corner
                        spec["round"].append((int(float(p[2])), int(float(p[3])), ys.start, ys.stop - 1))
                    if t[0] == "poly":                # diagonal edges drawn on purpose: wedge them
                        spec["poly"] |= spec["shapes"][-1][1]
                elif t[0] == "cut":
                    spec["shapes"].append(("cut", shape_cells(p[0], p[1:])))
                elif t[0] == "paint":
                    if ">" in p[0]:                   # gradient paint: (stops, axis)
                        c = (color_stops(p[0]), k.get("along", "y"))
                        axis_pos(c[1])
                    else:
                        c = color(p[0])[0]
                    if p[1] in ("box", "ball", "cyl", "col", "poly"):
                        spec["paint"].append((c, "set", shape_cells(p[1], p[2:])))
                    else:
                        spec["paint"].append((c, "ranges", (rng_(p[1]), rng_(p[2]), rng_(p[3]) if len(p) > 3 else None)))
                elif t[0] == "panel":
                    ys = rng_(p[1])
                    spec["panels"].append(dict(x=rng_(p[0]), y=(ys.start, ys.stop - 1), thick=int(k.get("thick", 2))))
                elif t[0] == "ppaint":
                    ys = rng_(p[2])
                    spec["ppaint"].append((color(p[0])[0], rng_(p[1]), ys.start, ys.stop - 1))
                elif t[0] == "gear":
                    size = k.get("size", "small")
                    if size not in ("small", "large"):
                        raise SpecError("gear size must be small or large")
                    spec["gears"].append(dict(x=_bounded(int(p[0]), LIMITS["coord"], "gear x"),
                                              y=_bounded(int(p[1]), LIMITS["coord"], "gear y"), size=size,
                                              color=color(k.get("color", "light_bluish_gray"))[0]))
                    if len(spec["gears"]) > 8:
                        raise SpecError("at most 8 gears per sculpt")
                elif t[0] == "flap":
                    x, z, length, width = int(p[0]), int(p[1]), int(p[2]), int(p[3])
                    for v, lim, what in ((length, 12, "length"), (width, 12, "width")):
                        if not 1 <= v <= lim:
                            raise SpecError(f"flap {what} must be 1..{lim}")
                    _bounded(x, LIMITS["coord"], "flap x")
                    _bounded(z, LIMITS["coord"], "flap z")
                    angle = _bounded(float(k.get("angle", 30)), 90, "angle")
                    d = k.get("dir", "+z")
                    if d not in ("+x", "-x", "+z", "-z"):
                        raise SpecError("flap dir must be +x, -x, +z or -z")
                    spec["flaps"].append(dict(x=x, z=z, length=length, width=width, angle=angle, dir=d,
                                              color=color(k["color"])[0] if "color" in k else None))
                    if len(spec["flaps"]) > 8:
                        raise SpecError("at most 8 flaps per sculpt")
                elif t[0] == "limb":
                    vals = [_bounded(float(v), LIMITS["coord"], "limb point") for v in p[:6]]
                    if len(vals) != 6:
                        raise SpecError("limb needs X Y Z TX TY TZ")
                    bend = _bounded(float(k.get("bend", 0)), 90, "bend")
                    spec["limbs"].append(dict(start=tuple(vals[:3]), end=tuple(vals[3:]), bend=bend,
                                              color=color(k["color"])[0] if "color" in k else None,
                                              thick=k.get("thick", "0") == "1"))
                    if len(spec["limbs"]) > 12:
                        raise SpecError("at most 12 limbs per sculpt")
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
                    size, look = k.get("size", "small"), k.get("look", "+x")
                    if size not in ("small", "large") or look not in ("+x", "-x"):
                        raise SpecError("eye size must be small or large, look +x or -x")
                    spec["eyes"].append(dict(x=int(p[0]), y=int(p[1]),
                                             pupil=color(k.get("pupil", "black"))[0],
                                             ring=color(k.get("ring", "medium_azure"))[0],
                                             skin=color(k.get("skin", "orange"))[0], size=size, look=look))
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
            rot = kw.get("rot", "0")
            rot = "alt" if rot == "alt" else rot_(kw)
            level = "top" if p[-1] == "top" else _bounded(int(p[-1]), LIMITS["coord"], "level")
            self.scatter(p[0], color(p[1]), region_terms(p[2:-1]), level, int(kw.get("every", 0)),
                         int(kw.get("shift", 0)), float(kw.get("density", 0.3)), int(kw.get("seed", 0)), rot)
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
            texture = kw.get("texture", "plain")
            if texture not in ("plain", "masonry", "log"):
                raise SpecError("texture must be plain, masonry or log")
            self.walls(xs[0], xs[-1], zs[0], zs[-1], int(p[1]), _bounded(int(p[2]), LIMITS["courses"], "courses"),
                       color(p[3]), texture, color(kw["quoins"])[0] if "quoins" in kw else None)
        elif cmd == "window":
            kind = kw.get("type", "wide")
            if kind not in self.WINDOWS:
                raise SpecError(f"window type must be one of {', '.join(self.WINDOWS)}")
            self.window(int(p[0]), int(p[1]), p[2], int(p[3]), _bounded(int(kw.get("stack", 1)), 8, "stack"),
                        color(kw.get("frame", "black"))[0], color(kw.get("glass", "trans_clear"))[0], kind)
        elif cmd == "door":
            self.door(int(p[0]), int(p[1]), p[2], int(p[3]), color(kw.get("frame", "black"))[0],
                      color(kw.get("leaf", "reddish_brown"))[0])
        elif cmd == "tree":
            style = kw.get("style", "pine")
            if style not in ("pine", "round", "bush", "palm"):
                raise SpecError("tree style must be pine, round, bush or palm")
            self.tree(int(p[0]), int(p[1]), int(p[2]), color(p[3]), color(kw.get("trunk", "reddish_brown"))[0], style,
                      _bounded(int(kw.get("height", 2)), 8, "height"), _bounded(int(kw.get("layers", 3)), 6, "layers"))
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
            rstyle = kw.get("style", "smooth")
            if rstyle not in ("smooth", "slope"):
                raise SpecError("roof style must be smooth or slope")
            self.roof(xs[0], xs[-1], zs[0], zs[-1], int(p[1]), kw.get("type", "gable"), kw.get("ridge", "x"),
                      color(kw.get("color", "dark_bluish_gray"))[0], color(kw.get("gable", "white"))[0],
                      _bounded(int(kw.get("overhang", 1)), 4, "overhang"), rstyle)
        elif cmd == "stump":
            bands = [int(b) for b in kw.get("bands", "").split(",") if b]
            self.stump(int(p[0]), int(p[1]), int(p[2]), int(p[3]), color(p[4])[0],
                       color(kw.get("band", p[4]))[0], bands)
        elif cmd == "roots":
            self.roots(int(p[0]), int(p[1]), int(p[2]), color(p[3])[0])
        else:
            raise SpecError(f"unknown command '{cmd}'")
