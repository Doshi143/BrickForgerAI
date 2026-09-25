"""Build-time only: reads part geometry from the official LDraw library
(bounding boxes and every stud's position + direction, resolved through
subparts and stud-group primitives).  Used by build_parts_table.py; the
runtime engine never touches this -- it loads the generated parts_table.json."""
from __future__ import annotations

import functools
import os
import subprocess
import time

BASE = "https://library.ldraw.org/library/official/"
CACHE = os.environ.get("LDRAW_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".ldraw_cache")
os.makedirs(CACHE, exist_ok=True)

# Primitives that ARE a single stud pointing along the primitive's local -y.
STUD_PRIMS = {"stud.dat", "stud2.dat", "stud2a.dat", "stud6.dat", "stud6a.dat",
              "stud10.dat", "stud15.dat", "stud17a.dat", "stud20.dat", "stud22a.dat",
              "stud2s.dat", "stud7.dat"}
# Anti-stud / tube primitives: never studs, never recursed into.
ANTI_PRIMS = {"stud3.dat", "stud3a.dat", "stud4.dat", "stud4a.dat", "stud4o.dat",
              "stud4s.dat", "stud4h.dat", "stud4f1s.dat", "stud4f2n.dat", "stud12.dat",
              "stud16.dat", "stud18a.dat", "stud21a.dat"}


MISSING: set = set()        # files referenced but not in the library (checked by build_parts_table)


def fetch(name: str) -> str:
    name = name.replace("\\", "/").lower().strip()
    key = name.replace("/", "__")
    path = os.path.join(CACHE, "c_" + key)
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    for prefix in ("parts/", "p/"):
        code = ""
        for attempt in range(9):
            time.sleep(0.3)                             # be polite: the server rate-limits bursts
            r = subprocess.run(["curl", "-s", "-o", "-", "-w", "\n%{http_code}", BASE + prefix + name],
                               capture_output=True)
            body, _, code = r.stdout.rpartition(b"\n")
            code = code.decode("ascii", errors="replace").strip()
            if code == "200" and body and not body.lstrip().startswith(b"<"):
                txt = body.decode("utf-8", errors="replace")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(txt)
                return txt
            if code == "404":
                break                                   # not under this prefix: try the next one
            time.sleep(min(30, 2 ** attempt))           # rate limit / server error / network: back off
        else:
            # Never let a refused download pass as "this file has no geometry":
            # that silently produced empty wedge plates once (2026-09-25).
            raise RuntimeError(f"LDraw server kept failing for {name} (last HTTP status {code or 'none'})")
    raise FileNotFoundError(name)


def _mul(m, v):
    return (m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
            m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2])


def _mm(a, b):
    return tuple(sum(a[3 * i + k] * b[3 * k + j] for k in range(3)) for i in range(3) for j in range(3))


@functools.lru_cache(maxsize=None)
def _walk(name: str, depth: int = 0):
    """Returns (points, studs) in the file's own frame."""
    pts, studs = [], []
    try:
        txt = fetch(name)
    except FileNotFoundError:
        MISSING.add(name)                             # a genuine 404: reported by build_parts_table
        return (), ()
    for line in txt.splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "1" and len(t) >= 15:
            off = tuple(map(float, t[2:5]))
            m = tuple(map(float, t[5:14]))
            sub = " ".join(t[14:]).replace("\\", "/").lower()
            base = sub.split("/")[-1]
            if base in STUD_PRIMS:
                d = _mul(m, (0.0, -1.0, 0.0))
                n = max(abs(c) for c in d) or 1.0
                studs.append((off, tuple(round(c / n, 3) for c in d)))
            if depth > 7:
                continue     # anti-stud primitives still count as geometry (round plates are built from stud4)
            spts, sstuds = _walk(sub, depth + 1)
            for p in spts:
                q = _mul(m, p)
                pts.append((q[0] + off[0], q[1] + off[1], q[2] + off[2]))
            if base not in STUD_PRIMS:
                for (sp, sd) in sstuds:
                    q = _mul(m, sp)
                    dd = _mul(m, sd)
                    n = max(abs(c) for c in dd) or 1.0
                    studs.append(((q[0] + off[0], q[1] + off[1], q[2] + off[2]),
                                  tuple(round(c / n, 3) for c in dd)))
        elif t[0] in ("2", "3", "4", "5"):
            n = {"2": 2, "3": 3, "4": 4, "5": 2}[t[0]]
            v = list(map(float, t[2:2 + 3 * n]))
            for i in range(n):
                pts.append((v[3 * i], v[3 * i + 1], v[3 * i + 2]))
    pts = tuple(set((round(a, 2), round(b, 2), round(c, 2)) for a, b, c in pts))
    uniq = {}
    for (p, d) in studs:
        uniq[(tuple(round(c, 2) for c in p), d)] = 1
    return pts, tuple(uniq.keys())


BALL_PRIMS = {"joint8ball.dat"}                 # a Joint-8 ball: its centre is the primitive's origin
SOCKET_PRIMS = {"joint8socket1.dat"}            # a Joint-8 socket: the ball's centre is its origin; it opens
                                                # toward the primitive's -z (measured: its body spans z -5..10)


def joints(name: str, depth: int = 0, M=(1, 0, 0, 0, 1, 0, 0, 0, 1), O=(0.0, 0.0, 0.0)):
    """Ball-joint connectors in the file's own frame: (balls, sockets) where a
    ball is its centre (a joint8ball primitive, or an 8-8sphe sphere of radius
    8 -- the Joint-8 ball size) and a socket is (centre, opening direction)."""
    balls, sockets = [], []
    try:
        txt = fetch(name)
    except FileNotFoundError:
        return balls, sockets
    for line in txt.splitlines():
        t = line.split()
        if len(t) < 15 or t[0] != "1":
            continue
        off = tuple(map(float, t[2:5]))
        m = tuple(map(float, t[5:14]))
        sub = " ".join(t[14:]).replace("\\", "/").lower()
        base = sub.split("/")[-1]
        wo = _mul(M, off)
        pos = (O[0] + wo[0], O[1] + wo[1], O[2] + wo[2])
        MM = _mm(M, m)
        radius = (m[0] ** 2 + m[3] ** 2 + m[6] ** 2) ** 0.5          # the sphere's scale, however rotated
        if base in BALL_PRIMS or (base == "8-8sphe.dat" and abs(radius - 8) < 0.01):
            balls.append(tuple(round(c, 2) for c in pos))
        elif base in SOCKET_PRIMS:
            d = _mul(MM, (0.0, 0.0, -1.0))
            n = max(abs(c) for c in d) or 1.0
            sockets.append((tuple(round(c, 2) for c in pos), tuple(round(c / n, 3) for c in d)))
        elif depth < 4 and not base.startswith(("stud", "4-4", "8-8", "1-4", "2-4", "3-4", "box", "rect")):
            b2, s2 = joints(sub, depth + 1, MM, pos)
            balls += b2
            sockets += s2
    return balls, sockets


def bbox(pid: str):
    pts, _ = _walk(pid + ".dat")
    xs, ys, zs = zip(*pts)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def studs(pid: str):
    return list(_walk(pid + ".dat")[1])


def title(pid: str) -> str:
    return fetch(pid + ".dat").splitlines()[0][2:].strip()


if __name__ == "__main__":
    import sys
    for pid in sys.argv[1:]:
        (x0, x1), (y0, y1), (z0, z1) = bbox(pid)
        s = studs(pid)
        ups = [p for p, d in s if d == (0.0, -1.0, 0.0)]
        side = [(p, d) for p, d in s if d != (0.0, -1.0, 0.0)]
        print(f"{pid:7s} {title(pid)[:44]:44s} X[{x0:6.1f},{x1:6.1f}] Y[{y0:6.1f},{y1:6.1f}] Z[{z0:6.1f},{z1:6.1f}]"
              f"  up-studs={len(ups)}" + (f" other={side}" if side else ""))
