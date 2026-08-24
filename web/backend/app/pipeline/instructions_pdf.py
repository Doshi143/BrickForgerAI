"""Headless-Chromium renderer + HTML->PDF assembler for auto-generated
build instructions (DESIGN.md's "### Instructions" section). Reuses the
exact three.js/LDrawLoader setup already proven in
web/frontend/components/Viewer3D.tsx (see render_assets/render.js's own
docstring for the details) instead of inventing a second rendering
approach -- DESIGN.md explicitly calls sharing one code path between the
interactive viewer and the PDF export "a big saving".

Runs entirely inside the RQ worker process (see jobs.py::process_job).
Playwright + a headless Chromium binary are real, sizeable dependencies
(see requirements.txt / Dockerfile) -- this must never be imported or run
from the request-serving API process.

Build order and parts tallies come from core/brickforge's own
pipeline.instructions module (pure, rendering-agnostic); this module's
only job is turning that into pictures and a PDF.
"""

from __future__ import annotations

import base64
import functools
import html
import http.server
import logging
import threading
from pathlib import Path

from brickforge.model import Model
from brickforge.pipeline.color import CATALOG_RGB
from brickforge.pipeline.instructions import (
    PartTally,
    bill_of_materials,
    build_steps,
    stepped_ldr_text,
    tally,
)

logger = logging.getLogger(__name__)

_RENDER_ASSETS_DIR = Path(__file__).parent / "render_assets"

# Headless Chromium has no real GPU in a container -- these ANGLE/
# SwiftShader flags force software WebGL rendering. Without them,
# WebGLRenderer silently fails to get a context in headless mode (a real,
# documented Chromium quirk, not a guess) and every screenshot would be
# the flat background color with no geometry.
_CHROMIUM_ARGS = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
]

_VIEWPORT = {"width": 1000, "height": 800}


def _start_static_server() -> tuple[http.server.ThreadingHTTPServer, threading.Thread, int]:
    """Serves render_assets/ (render.html, render.js, the ldraw-overrides
    .dat files) on an ephemeral localhost port -- needed because the page
    fetches those files itself (via LDrawLoader's URL modifier and the
    <script type=module> tag), and a bare file:// origin is a real,
    documented source of fetch/CORS quirks in headless Chromium that a
    same-origin http:// server sidesteps entirely. The stepped LDR model
    text itself is NOT served this way -- see loadStepped, which passes it
    directly via page.evaluate, since LDrawLoader.parse() takes raw text."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(_RENDER_ASSETS_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def _data_url_to_bytes(data_url: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ValueError(f"expected a data:image/png;base64 URL from the renderer, got {data_url[:40]!r}")
    return base64.b64decode(data_url[len(prefix):])


def _render_step_screenshots(stepped_text: str, num_steps: int) -> list[bytes]:
    """Boots the headless renderer once, parses the stepped LDR once, then
    captures one screenshot per build step -- reusing the same parsed
    scene/loader across steps (LDrawLoader caches common subpart geometry,
    e.g. stud primitives, internally) rather than re-launching per step,
    which is what actually keeps a several-hundred-step model's render
    time from blowing up."""
    from playwright.sync_api import sync_playwright

    server, thread, port = _start_static_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
            try:
                page = browser.new_page(viewport=_VIEWPORT)
                page.goto(f"http://127.0.0.1:{port}/render.html")
                page.evaluate("() => window.__bf.boot()")
                page.wait_for_function("() => window.__bf && window.__bf.ready")
                page.evaluate("(text) => window.__bf.loadStepped(text)", stepped_text)

                screenshots: list[bytes] = []
                for step_index in range(num_steps):
                    data_url = page.evaluate("(i) => window.__bf.showStepAndCapture(i)", step_index)
                    screenshots.append(_data_url_to_bytes(data_url))
                return screenshots
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _swatch_style(color_code: int) -> str:
    r, g, b = CATALOG_RGB.get(color_code, (128, 128, 128))
    return f"background: rgb({r},{g},{b});"


# --- Compact multi-column parts display -------------------------------
#
# The original single-column <table> (one ~30px-tall row per part/colour
# combo) genuinely overflowed a page for any step with more than ~15
# distinct combos -- confirmed on a real 67-step production job, not a
# guess: one busy step's table ran onto a second, mostly-empty page,
# which is exactly the "not fitting on one page" complaint this replaces.
# A CSS multi-column flow (below) packs many short chip rows across 2-4
# columns instead of one, using the full page width rather than just the
# ~38% a side-by-side table+render layout left for it -- the real fix,
# not a font-size hack.


def _parts_chip_html(row: PartTally) -> str:
    return (
        '<div class="chip">'
        f'<span class="swatch" style="{_swatch_style(row.color_code)}"></span>'
        f'<span class="chip-name">{html.escape(row.part_name)} '
        f'<span class="chip-color">{html.escape(row.color_name.replace("_", " "))}</span></span>'
        f'<span class="chip-qty">&times;{row.count}</span>'
        "</div>"
    )


def _parts_grid_html(rows: list[PartTally], *, columns: int) -> str:
    return f'<div class="parts-grid cols-{columns}">' + "\n".join(_parts_chip_html(r) for r in rows) + "</div>"


def _columns_for_row_count(n: int) -> int:
    """More columns for a busier parts list -- keeps any single step or
    the full BOM within one page's height regardless of how many distinct
    (part, colour) combinations it has, rather than a fixed column count
    that only happens to work for typical cases."""
    if n > 45:
        return 4
    if n > 18:
        return 3
    return 2


def _step_page_html(step_number: int, total_steps: int, screenshot_png: bytes, rows: list[PartTally]) -> str:
    b64 = base64.b64encode(screenshot_png).decode("ascii")
    columns = _columns_for_row_count(len(rows))
    return f"""
    <section class="page step-page">
      {_scene_svg(prominent=False)}
      <div class="content">
        <div class="content-card">
          <div class="step-header">Step {step_number} of {total_steps}</div>
          <div class="step-render-frame">
            <img class="step-render" src="data:image/png;base64,{b64}" />
          </div>
          <div class="callout-title">Add these parts</div>
          {_parts_grid_html(rows, columns=columns)}
        </div>
      </div>
    </section>
    """


# --- Static, print-friendly scene backdrop -----------------------------
#
# A plain-SVG, non-animated version of the landing page's voxel-art sky /
# sun / mountains / hills / birds backdrop (see
# web/frontend/components/Scenery.tsx and app/theme.ts's lightColors --
# same palette, reused directly, not eyeballed) -- a print PDF has no use
# for Scenery.tsx's div-grid animations, but the founder asked for the
# same visual identity instead of a plain white page. Rendered as real
# SVG shapes (not a CSS background-image) so it stays crisp at print
# resolution and needs no external asset.

_SKY_TOP = "#eaf4fb"
_SKY_BOTTOM = "#cfe9f7"
_SUN_FILL = "#f5a35c"
_SUN_GLOW = "rgba(245,163,92,0.35)"
_MOUNTAIN_COLOR = "#b8c9d9"
_HILL_FAR = "#a8c98a"
_HILL_NEAR = "#8fb96e"
_BIRD_COLOR = "#1e2233"

# (width, height) pairs, same shape as app/theme.ts's own `mountains`
# array -- reused as a repeating pattern rather than copied verbatim,
# since this SVG's coordinate space (0-1000 wide) doesn't match that
# array's original px tuning for a live browser viewport.
_MOUNTAIN_PATTERN = [
    (70, 100), (95, 150), (60, 85), (105, 175), (75, 115), (90, 140),
    (65, 95), (100, 160), (70, 105), (85, 130), (60, 90),
]

_SVG_W = 1000
_SVG_H = 1414  # A4 aspect (210:297), scaled to a round width


def _mountain_polygon(baseline: float, scale: float) -> str:
    points: list[tuple[float, float]] = [(-40.0, _SVG_H)]
    x = -40.0
    i = 0
    while x < _SVG_W + 40:
        w, h = _MOUNTAIN_PATTERN[i % len(_MOUNTAIN_PATTERN)]
        w, h = w * scale, h * scale
        points.append((x, baseline))
        points.append((x + w, baseline - h))
        x += 2 * w
        i += 1
    points.append((x, baseline))
    points.append((x, _SVG_H))
    return " ".join(f"{px:.1f},{py:.1f}" for px, py in points)


_BIRD_POSITIONS = [(150, 190), (330, 260), (560, 160), (230, 340), (420, 380)]


def _bird_svg(x: float, y: float) -> str:
    return (
        f'<path d="M{x-16},{y} q16,-18 16,0 q0,-18 16,0" '
        f'fill="none" stroke="{_BIRD_COLOR}" stroke-width="4" stroke-linecap="round" opacity="0.55" />'
    )


def _scene_svg(*, prominent: bool) -> str:
    """The cover page gets the full scene (sun, birds, hills, mountains);
    every other page gets only the sky gradient plus a single, quiet
    mountain silhouette along the very bottom -- enough to feel like the
    same product, without competing with the parts grids and renders
    that actually need to stay legible on those pages."""
    parts = [
        f'<svg class="scene" viewBox="0 0 {_SVG_W} {_SVG_H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">',
        f'<stop offset="0%" stop-color="{_SKY_TOP}" />',
        f'<stop offset="70%" stop-color="{_SKY_BOTTOM}" />',
        "</linearGradient>",
        '<radialGradient id="glow" cx="50%" cy="50%" r="50%">',
        f'<stop offset="0%" stop-color="{_SUN_GLOW}" />',
        '<stop offset="100%" stop-color="rgba(245,163,92,0)" />',
        "</radialGradient>",
        "</defs>",
        f'<rect width="{_SVG_W}" height="{_SVG_H}" fill="url(#sky)" />',
    ]

    if prominent:
        parts.append('<circle cx="780" cy="230" r="160" fill="url(#glow)" />')
        parts.append(f'<circle cx="780" cy="230" r="60" fill="{_SUN_FILL}" />')
        for x, y in _BIRD_POSITIONS:
            parts.append(_bird_svg(x, y))
        # Mountains painted first (background), hills painted over their
        # base afterwards (foreground) -- a real layering bug, caught
        # from actual rendered output, lived here the other way around:
        # with hills drawn *before* the mountain polygon, the polygon's
        # own valley points (which dip back down to its baseline) painted
        # over the hills there, leaving odd green wedges poking up through
        # gaps in the mountain silhouette instead of a clean foreground
        # band covering the mountains' base the way a real parallax
        # landscape reads.
        parts.append(f'<polygon points="{_mountain_polygon(_SVG_H - 260, 1.6)}" fill="{_MOUNTAIN_COLOR}" opacity="0.9" />')
        parts.append(f'<ellipse cx="500" cy="{_SVG_H - 40}" rx="900" ry="240" fill="{_HILL_FAR}" opacity="0.95" />')
        parts.append(f'<ellipse cx="500" cy="{_SVG_H + 10}" rx="900" ry="200" fill="{_HILL_NEAR}" opacity="0.95" />')
    else:
        parts.append(f'<polygon points="{_mountain_polygon(_SVG_H - 55, 0.9)}" fill="{_MOUNTAIN_COLOR}" opacity="0.35" />')

    parts.append("</svg>")
    return "\n".join(parts)


_BOOKLET_CSS = f"""
  @page {{ size: A4; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1b1d21; }}
  .page {{
    position: relative;
    width: 210mm;
    height: 297mm;
    overflow: hidden;
    page-break-after: always;
  }}
  .page:last-child {{ page-break-after: auto; }}
  .scene {{ position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0; display: block; }}
  .content {{ position: relative; z-index: 1; height: 100%; padding: 18mm 16mm; }}

  .cover .content {{ display: flex; align-items: center; justify-content: center; }}
  .cover-card {{
    background: rgba(255,255,255,0.9);
    border-radius: 20px;
    padding: 36px 48px;
    text-align: center;
    max-width: 130mm;
  }}
  .cover-card h1 {{ font-size: 28px; margin: 0 0 10px; }}
  .cover-card .meta {{ color: #555; font-size: 14px; margin: 0 0 18px; }}
  .footer-note {{ color: #888; font-size: 10px; line-height: 1.5; }}

  .content-card {{
    background: rgba(255,255,255,0.94);
    border-radius: 20px;
    padding: 22px 26px;
    min-height: 100%;
  }}
  .bom h2, .step-header {{ font-size: 20px; margin: 0 0 16px; }}

  .step-render-frame {{
    width: 100%;
    height: 100mm;
    border-radius: 14px;
    overflow: hidden;
    background: #1b1d21;
    margin-bottom: 16px;
  }}
  .step-render {{ width: 100%; height: 100%; object-fit: contain; }}
  .callout-title {{ font-weight: 700; font-size: 14px; margin-bottom: 10px; }}

  .parts-grid {{ column-gap: 18px; }}
  .parts-grid.cols-2 {{ column-count: 2; }}
  .parts-grid.cols-3 {{ column-count: 3; }}
  .parts-grid.cols-4 {{ column-count: 4; }}
  .chip {{
    break-inside: avoid;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 0;
    border-bottom: 1px solid rgba(0,0,0,0.08);
    font-size: 11px;
    line-height: 1.3;
  }}
  .chip-name {{ flex: 1; }}
  .chip-color {{ color: #777; }}
  .chip-qty {{ font-weight: 700; padding-left: 6px; white-space: nowrap; }}
  .swatch {{ flex: 0 0 auto; display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.2); }}
"""


def _assemble_booklet_html(
    model_name: str,
    part_count: int,
    steps_html: str,
    bom_rows: list[PartTally],
) -> str:
    bom_columns = _columns_for_row_count(len(bom_rows))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_BOOKLET_CSS}</style></head>
<body>
  <section class="page cover">
    {_scene_svg(prominent=True)}
    <div class="content">
      <div class="cover-card">
        <h1>{html.escape(model_name)}</h1>
        <div class="meta">{part_count:,} parts &middot; Build instructions generated by BrickForgerAI</div>
        <div class="footer-note">
          Built with real LDraw parts (CCAL 2.0, The LDraw Parts Library). Not affiliated with,
          endorsed, or sponsored by the LEGO Group; LEGO&reg; is a trademark of the LEGO Group.
        </div>
      </div>
    </div>
  </section>
  <section class="page bom">
    {_scene_svg(prominent=False)}
    <div class="content">
      <div class="content-card">
        <h2>Full parts list</h2>
        {_parts_grid_html(bom_rows, columns=bom_columns)}
      </div>
    </div>
  </section>
  {steps_html}
</body></html>"""


def render_instructions_pdf(
    model: Model,
    out_pdf_path: str,
    model_name: str,
) -> dict:
    """Generates a full build-instruction PDF for `model` at out_pdf_path.
    Returns {"step_count": int, "part_count": int}.

    Deliberately has no partial/best-effort return -- any failure (a
    Chromium crash, a parse error) should raise, and the caller
    (brickforge_bridge.mesh_to_ldr) is the one that decides whether that's
    fatal to the whole job or just means this job ships without a PDF
    (see that module's own docstring for why it's the latter).

    The cover page deliberately has no reference-photo thumbnail -- an
    earlier version showed the AI-generated prompt image there, which the
    founder asked to remove: it's a stylized reference render, not the
    actual brick model, and looked misleading at the top of a *build*
    guide."""
    steps = build_steps(model)
    if not steps:
        raise ValueError("model has no bricks to generate instructions for")

    stepped_text = stepped_ldr_text(model, steps, model_name)
    screenshots = _render_step_screenshots(stepped_text, len(steps))

    steps_html_parts = []
    for step, screenshot in zip(steps, screenshots):
        rows = tally(model, step.brick_indices)
        steps_html_parts.append(_step_page_html(step.index + 1, len(steps), screenshot, rows))

    booklet_html = _assemble_booklet_html(
        model_name=model_name,
        part_count=len(model),
        steps_html="\n".join(steps_html_parts),
        bom_rows=bill_of_materials(model),
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
        try:
            page = browser.new_page()
            page.set_content(booklet_html)
            page.pdf(path=out_pdf_path, format="A4", print_background=True)
        finally:
            browser.close()

    return {"step_count": len(steps), "part_count": len(model)}
