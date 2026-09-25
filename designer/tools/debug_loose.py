"""Diagnose loose groups: for each part in a loose component, show its cells
and what is directly below / beside it.  python tools/debug_loose.py specs/x.bfd"""
import sys

from brickforge_designer.pipeline import build


def cells(q):
    (x0, x1), (y0, y1), (z0, z1) = q.box
    return (round(x0 / 20), round(x1 / 20) - 1), (round(-y1 / 8), round(-y0 / 8) - 1), (round(z0 / 20), round(z1 / 20) - 1)


D, it = build(open(sys.argv[1]).read())
comps, adj = D.components()
main = set(comps[0])
for comp in comps[1:5]:
    if D.parts[comp[0]].asm != "main" and len({D.parts[n].asm for n in comp}) == 1 and \
            not any(D.parts[m].asm == D.parts[comp[0]].asm for c in comps if c is not comp for m in c):
        continue
    print(f"--- loose group of {len(comp)}")
    for n in sorted(comp, key=lambda n: D.parts[n].box[1][1], reverse=True):
        q = D.parts[n]
        (xa, xb), (la, lb), (za, zb) = cells(q)
        below = [m for m, p in enumerate(D.parts) if m != n and abs(p.box[1][0] - q.box[1][1]) < 1 and
                 min(p.box[0][1], q.box[0][1]) - max(p.box[0][0], q.box[0][0]) > 1 and
                 min(p.box[2][1], q.box[2][1]) - max(p.box[2][0], q.box[2][0]) > 1]
        print(f"  {q.pid:7s} {q.tag or '-':8s} col {q.color:3d}  x{xa}..{xb} L{la}..{lb} z{za}..{zb}  "
              f"linked={sorted(adj[n])[:4]}  directly-below={[(D.parts[m].pid, D.parts[m].tag or '-', 'MAIN' if m in main else 'loose') for m in below][:4]}")
