"""Run real prompts through the Detailed pipeline and report, per prompt: pass or
fail, what is connected, cost, time, and a rendered preview.  Spends real
money (Claude API, plus OpenAI when --reference image is used).

    python tools/evaluate.py prompts.txt --out out/eval --variants none,image --parallel 3
    (one prompt per line, optionally "prompt | finish=studs sideways=off size=20";
     needs the LDR viewer served on :8532:
     `python -m http.server 8532` from the repo root)

Keys are read from web/backend/.env (ANTHROPIC_API_KEY, IMAGE_GEN_API_KEY).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Variant -> reference-picture prompt.  "image" is the one production used first
# (stylised and chunky: it pulled designs toward simple shapes); "detail" asks for a
# clear, detailed, true-colour depiction instead.  Keep the production one in step
# with web/backend/app/pipeline/designer_bridge.py::REFERENCE_IMAGE_PROMPT.
IMAGE_PROMPTS = {
    "image": ("{subject}. A simple, stylised 3D figurine with chunky, clearly separated shapes and flat, "
              "true-to-life colours, shown whole in a three-quarter view from the front-left and slightly "
              "above, on a plain light-grey background. No text, no logos."),
    "detail": ("{subject}. A clear, detailed 3D render of the whole subject that shows its characteristic "
               "details, textures and features in true-to-life colours, seen in a three-quarter view from "
               "the front-left and slightly above, evenly lit, on a plain light-grey background. "
               "No text, no logos."),
}
IMAGE_PROMPT = IMAGE_PROMPTS["image"]
# gpt-image-1, 1024x1024: $ per image by quality, used only if the response has no usage block
IMAGE_PRICE_FALLBACK = {"low": 0.011, "medium": 0.042, "high": 0.167}
# gpt-image-1 token prices ($ per 1M): text input, image output
IMAGE_TOKEN_PRICES = {"input": 5.0, "output": 40.0}


def load_keys():
    with open(os.path.join(ROOT, "web", "backend", ".env"), encoding="utf-8") as f:
        for line in f:
            k, _, v = line.strip().partition("=")
            if k in ("ANTHROPIC_API_KEY", "IMAGE_GEN_API_KEY") and v:
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def reference_image(subject, quality, out_path, template=IMAGE_PROMPT):
    import requests
    t0 = time.time()
    r = requests.post("https://api.openai.com/v1/images/generations",
                      headers={"Authorization": f"Bearer {os.environ['IMAGE_GEN_API_KEY']}"},
                      json={"model": "gpt-image-1", "prompt": template.format(subject=subject),
                            "size": "1024x1024", "quality": quality, "n": 1}, timeout=180)
    if not r.ok:
        raise RuntimeError(f"image generation failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    png = base64.b64decode(data["data"][0]["b64_json"])
    with open(out_path, "wb") as f:
        f.write(png)
    u = data.get("usage") or {}
    if u:
        dollars = (u.get("input_tokens", 0) * IMAGE_TOKEN_PRICES["input"]
                   + u.get("output_tokens", 0) * IMAGE_TOKEN_PRICES["output"]) / 1e6
    else:
        dollars = IMAGE_PRICE_FALLBACK[quality]
    return png, round(dollars, 4), round(time.time() - t0, 1)


def connection_summary(D):
    from brickforge_designer.pipeline import classify_pieces
    comps, _ = D.components()
    out = []
    for asm, status, c, _ in classify_pieces(D, comps):
        out.append({"assembly": asm, "status": status, "parts": len(c)})
    return out


def highlight_loose(D, path):
    from brickforge_designer.pipeline import classify_pieces
    comps, _ = D.components()
    loose = set()
    for _, status, c, _ in classify_pieces(D, comps):
        if status == "loose":
            loose |= set(c)
    saved = {}
    for i in loose:
        saved[i] = D.parts[i].color
        D.parts[i].color = 26              # magenta
    with open(path, "w", encoding="utf-8") as f:
        f.write(D.ldr())
    for i, c in saved.items():
        D.parts[i].color = c
    return len(loose)


VIEW = """(args) => { const [az, el, zoom] = args; const {scene,camera,THREE}=window.__bf;
 const g=scene.children.find(o=>o.type==='Group'); const box=new THREE.Box3().setFromObject(g);
 const c=box.getCenter(new THREE.Vector3()); const s=box.getSize(new THREE.Vector3()).length()*zoom;
 const a=az*Math.PI/180, e=el*Math.PI/180;
 camera.position.set(c.x+s*Math.cos(e)*Math.cos(a), c.y+s*Math.sin(e), c.z+s*Math.cos(e)*Math.sin(a));
 camera.lookAt(c); }"""


def render(ldr_paths, port=8532, zoom=0.95):
    """ldr_paths: [(ldr_path, png_path, azimuth)]"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 900, "height": 720})
        for ldr, png, az in ldr_paths:
            rel = os.path.relpath(ldr, ROOT).replace("\\", "/")
            pg.goto(f"http://localhost:{port}/viewer/index.html?model=../{rel}")
            pg.wait_for_function("document.body.innerText.includes('Loaded ')", timeout=180000)
            pg.wait_for_timeout(1200)
            pg.evaluate("document.querySelectorAll('div').forEach(d => { if (d.innerText.includes('Phase 0')) d.style.display='none'; })")
            pg.evaluate(VIEW, [az, 22, zoom])
            pg.wait_for_timeout(600)
            pg.screenshot(path=png)
        b.close()


def slug(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s.lower()).strip("_")[:40]


def main():
    sys.path.insert(0, os.path.join(ROOT, "designer"))
    from brickforge_designer.pipeline import AnthropicDesigner, cost, generate
    ap = argparse.ArgumentParser()
    ap.add_argument("prompts")
    ap.add_argument("--out", default=os.path.join(ROOT, "designer", "out", "eval"))
    ap.add_argument("--variants", default="none", help="comma list of: none, image (stylised picture), detail (detailed picture)")
    ap.add_argument("--quality", default="medium", choices=("low", "medium", "high"))
    ap.add_argument("--finish", default="tiled")
    ap.add_argument("--sideways", default="auto")
    ap.add_argument("--size", type=int, default=24)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--parallel", type=int, default=1)
    a = ap.parse_args()
    load_keys()
    os.makedirs(a.out, exist_ok=True)
    with open(a.prompts, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    results, renders = [], []
    jobs = []
    for n, line in enumerate(lines, 1):
        prompt, _, opts = line.partition("|")
        settings = {"finish": a.finish, "sideways": a.sideways, "size": a.size}
        for kv in opts.split():
            k, _, v = kv.partition("=")
            settings[k] = int(v) if k == "size" else v
        for variant in a.variants.split(","):
            jobs.append((n, prompt.strip(), settings, variant))

    def run_one(job):
        n, prompt, settings, variant = job
        name = f"{n:02d}_{slug(prompt)}_{variant}"
        row = {"n": n, "prompt": prompt, "variant": variant, "name": name, "settings": settings}
        t0 = time.time()
        ref = None
        try:
            if variant in IMAGE_PROMPTS:
                png, dollars, secs = reference_image(prompt, a.quality, os.path.join(a.out, name + "_ref.png"),
                                                     IMAGE_PROMPTS[variant])
                ref = (png, "image/png")
                row.update(image_cost=dollars, image_seconds=secs)
            d = AnthropicDesigner()
            r = generate(prompt, d, a.out, name=name, finish=settings["finish"],
                         sideways=settings["sideways"], size=settings["size"], reference_image=ref)
            with open(os.path.join(a.out, name + ".bfd"), "w", encoding="utf-8") as f:
                f.write(r["spec"])
            row.update(passed=not r["problems"], problems=r["problems"], rounds=r["rounds"],
                       parts=r["stats"].get("parts"), pieces=connection_summary(r["design"]),
                       calls=[(lbl, u, round(cost(u, d.model), 4)) for lbl, u in r["usage"]],
                       claude_cost=r["totals"]["cost_usd"], totals=r["totals"])
            renders.append((r["path"], os.path.join(a.out, name + ".png"), -60))
            if r["problems"] and highlight_loose(r["design"], os.path.join(a.out, name + "_loose.ldr")):
                renders.append((os.path.join(a.out, name + "_loose.ldr"), os.path.join(a.out, name + "_loose.png"), -60))
        except Exception as e:  # noqa: BLE001 -- record and keep going; one bad prompt shouldn't stop the run
            row.update(passed=False, error=f"{type(e).__name__}: {e}")
        row["seconds"] = round(time.time() - t0, 1)
        row["total_cost"] = round(row.get("claude_cost", 0) + row.get("image_cost", 0), 4)
        with lock:
            results.append(row)
            print(json.dumps({k: row.get(k) for k in ("name", "passed", "rounds", "parts", "total_cost",
                                                      "seconds")}), flush=True)
            with open(os.path.join(a.out, "results.json"), "w", encoding="utf-8") as f:
                json.dump(sorted(results, key=lambda r: r["name"]), f, indent=1, default=str)

    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        list(pool.map(run_one, jobs))
    results.sort(key=lambda r: r["name"])
    renders.sort()
    if not a.no_render and renders:
        render(renders)
    by = Counter((r["variant"], r["passed"]) for r in results)
    for v in a.variants.split(","):
        rows = [r for r in results if r["variant"] == v]
        costs = sorted(r["total_cost"] for r in rows)
        print(f"{v}: {by[(v, True)]}/{len(rows)} passed, mean ${sum(costs) / max(1, len(costs)):.3f}, "
              f"max ${costs[-1] if costs else 0:.3f}")


if __name__ == "__main__":
    main()
