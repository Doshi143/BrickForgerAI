"""Turn an evaluate.py run into review sheets: per prompt, the reference
picture, the rendered build (and the loose-parts view if it failed), with
pass/fail, cost, fix rounds and what is connected.

    python tools/contact_sheet.py out/eval15            # -> out/eval15/sheet_1.png, sheet_2.png, ...
    python tools/contact_sheet.py out/eval15 --render   # first re-render each build from front and back
                                                        # (needs the viewer on :8532, see evaluate.py)
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROWS_PER_SHEET = 5
CELL_W, CELL_H, TEXT_W = 400, 320, 440
BG, FG, OK, BAD, DIM = (27, 29, 33), (232, 232, 232), (120, 200, 120), (240, 120, 100), (160, 160, 160)


def font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def pieces_text(pieces):
    if not pieces:
        return "-"
    parts = []
    for p in pieces:
        label = {"main": "main piece", "standing": "separate standing piece", "loose": "LOOSE"}[p["status"]]
        where = "" if p["assembly"] == "main" else f" ({p['assembly']})"
        parts.append(f"{label}{where}: {p['parts']} parts")
    return "; ".join(parts)


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def thumb(path):
    if not path or not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGB")
    im.thumbnail((CELL_W, CELL_H))
    return im


def rerender(out_dir, results):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluate import render
    jobs = []
    for r in results:
        ldr = os.path.abspath(os.path.join(out_dir, r["name"] + ".ldr"))
        for suffix, az in (("_front.png", -60), ("_back.png", 120)):
            png = os.path.abspath(os.path.join(out_dir, r["name"] + suffix))
            if os.path.exists(ldr) and not os.path.exists(png):      # already rendered: keep it
                jobs.append((ldr, png, az))
    if jobs:
        render(jobs, zoom=1.15)


def main(out_dir, do_render=False):
    with open(os.path.join(out_dir, "results.json"), encoding="utf-8") as f:
        results = sorted(json.load(f), key=lambda r: r["name"])
    if do_render:
        rerender(out_dir, results)
    f_title, f_body, f_small = font(22), font(17), font(15)
    sheets = []
    for start in range(0, len(results), ROWS_PER_SHEET):
        chunk = results[start:start + ROWS_PER_SHEET]
        W = TEXT_W + 4 * CELL_W + 40
        H = len(chunk) * (CELL_H + 20) + 20
        sheet = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(chunk):
            y = 20 + i * (CELL_H + 20)
            x = 20
            s = r.get("settings", {})
            status = "PASS" if r.get("passed") else "FAIL"
            d.text((x, y), f"{r['n']}. {r['prompt']}", font=f_title, fill=FG)
            yy = y + 34
            for line in wrap(d, f"settings: finish={s.get('finish')} sideways={s.get('sideways')} "
                                f"size={s.get('size')}", f_small, TEXT_W - 20):
                d.text((x, yy), line, font=f_small, fill=DIM)
                yy += 20
            d.text((x, yy + 6), status, font=f_title, fill=OK if r.get("passed") else BAD)
            yy += 40
            info = [f"cost ${r.get('total_cost', 0):.3f}  (image ${r.get('image_cost', 0):.3f})",
                    f"fix rounds {r.get('rounds', '-')}   parts {r.get('parts', '-')}   {r.get('seconds')}s",
                    f"connected: {pieces_text(r.get('pieces'))}"]
            if r.get("problems"):
                info.append("problems: " + " | ".join(p[:110] for p in r["problems"][:3]))
            if r.get("error"):
                info.append("error: " + r["error"][:160])
            for text in info:
                for line in wrap(d, text, f_body, TEXT_W - 20):
                    d.text((x, yy), line, font=f_body, fill=FG)
                    yy += 22
            front = os.path.join(out_dir, r["name"] + "_front.png")
            cells = [os.path.join(out_dir, r["name"] + "_ref.png"),
                     front if os.path.exists(front) else os.path.join(out_dir, r["name"] + ".png"),
                     os.path.join(out_dir, r["name"] + "_back.png"),
                     os.path.join(out_dir, r["name"] + "_loose.png")]
            for c, path in enumerate(cells):
                im = thumb(path)
                if im:
                    cx = TEXT_W + 20 + c * CELL_W
                    sheet.paste(im, (cx + (CELL_W - im.width) // 2, y + (CELL_H - im.height) // 2))
        path = os.path.join(out_dir, f"sheet_{start // ROWS_PER_SHEET + 1}.png")
        sheet.save(path)
        sheets.append(path)
    passed = sum(1 for r in results if r.get("passed"))
    costs = [r.get("total_cost", 0) for r in results]
    print(f"{passed}/{len(results)} passed; total ${sum(costs):.2f}, mean ${sum(costs) / max(1, len(costs)):.3f}, "
          f"max ${max(costs, default=0):.3f}")
    print("\n".join(sheets))


if __name__ == "__main__":
    main(sys.argv[1], "--render" in sys.argv[2:])
