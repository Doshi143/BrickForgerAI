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
                page.evaluate("() => window.__bf.frameAll()")

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


def _parts_rows_html(rows: list[PartTally]) -> str:
    return "\n".join(
        f'<tr><td><span class="swatch" style="{_swatch_style(r.color_code)}"></span></td>'
        f"<td>{html.escape(r.part_name)}</td>"
        f"<td>{html.escape(r.color_name.replace('_', ' '))}</td>"
        f"<td>{html.escape(r.part_id)}</td>"
        f'<td class="qty">{r.count}</td></tr>'
        for r in rows
    )


def _step_page_html(step_number: int, total_steps: int, screenshot_png: bytes, rows: list[PartTally]) -> str:
    b64 = base64.b64encode(screenshot_png).decode("ascii")
    return f"""
    <section class="page step-page">
      <div class="step-header">Step {step_number} of {total_steps}</div>
      <div class="step-body">
        <img class="step-render" src="data:image/png;base64,{b64}" />
        <div class="callout">
          <div class="callout-title">Add these parts</div>
          <table class="parts-table">{_parts_rows_html(rows)}</table>
        </div>
      </div>
    </section>
    """


_BOOKLET_CSS = """
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1b1d21; }
  .page { page-break-after: always; }
  .page:last-child { page-break-after: auto; }
  .cover { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 240mm; text-align: center; }
  .cover h1 { font-size: 28px; margin-bottom: 8px; }
  .cover .meta { color: #666; font-size: 14px; margin-top: 12px; }
  .cover img { max-width: 100%; max-height: 300px; border-radius: 12px; margin-bottom: 24px; }
  .bom h2, .step-header { font-size: 20px; margin-bottom: 16px; }
  .parts-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .parts-table td { padding: 6px 8px; border-bottom: 1px solid #e5e5e5; vertical-align: middle; }
  .parts-table td.qty { text-align: right; font-weight: 700; width: 48px; }
  .swatch { display: inline-block; width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.2); }
  .step-body { display: flex; gap: 20px; align-items: flex-start; }
  .step-render { width: 62%; border-radius: 10px; background: #1b1d21; }
  .callout { flex: 1; background: #f7f7f8; border-radius: 10px; padding: 14px; }
  .callout-title { font-weight: 700; font-size: 14px; margin-bottom: 10px; }
  .footer-note { color: #999; font-size: 10px; margin-top: 24px; }
"""


def _assemble_booklet_html(
    model_name: str,
    part_count: int,
    steps_html: str,
    bom_rows: list[PartTally],
    thumbnail_data_url: str | None,
) -> str:
    thumb_html = f'<img src="{thumbnail_data_url}" />' if thumbnail_data_url else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_BOOKLET_CSS}</style></head>
<body>
  <section class="page cover">
    {thumb_html}
    <h1>{html.escape(model_name)}</h1>
    <div class="meta">{part_count:,} parts &middot; Build instructions generated by BrickForgerAI</div>
    <div class="footer-note">
      Built with real LDraw parts (CCAL 2.0, The LDraw Parts Library). Not affiliated with,
      endorsed, or sponsored by the LEGO Group; LEGO&reg; is a trademark of the LEGO Group.
    </div>
  </section>
  <section class="page bom">
    <h2>Full parts list</h2>
    <table class="parts-table">{_parts_rows_html(bom_rows)}</table>
  </section>
  {steps_html}
</body></html>"""


def render_instructions_pdf(
    model: Model,
    out_pdf_path: str,
    model_name: str,
    thumbnail_png_path: str | None = None,
) -> dict:
    """Generates a full build-instruction PDF for `model` at out_pdf_path.
    Returns {"step_count": int, "part_count": int}.

    Deliberately has no partial/best-effort return -- any failure (a
    Chromium crash, a parse error) should raise, and the caller
    (brickforge_bridge.mesh_to_ldr) is the one that decides whether that's
    fatal to the whole job or just means this job ships without a PDF
    (see that module's own docstring for why it's the latter)."""
    steps = build_steps(model)
    if not steps:
        raise ValueError("model has no bricks to generate instructions for")

    stepped_text = stepped_ldr_text(model, steps, model_name)
    screenshots = _render_step_screenshots(stepped_text, len(steps))

    steps_html_parts = []
    for step, screenshot in zip(steps, screenshots):
        rows = tally(model, step.brick_indices)
        steps_html_parts.append(_step_page_html(step.index + 1, len(steps), screenshot, rows))

    thumbnail_data_url = None
    if thumbnail_png_path and Path(thumbnail_png_path).is_file():
        thumb_b64 = base64.b64encode(Path(thumbnail_png_path).read_bytes()).decode("ascii")
        thumbnail_data_url = f"data:image/png;base64,{thumb_b64}"

    booklet_html = _assemble_booklet_html(
        model_name=model_name,
        part_count=len(model),
        steps_html="\n".join(steps_html_parts),
        bom_rows=bill_of_materials(model),
        thumbnail_data_url=thumbnail_data_url,
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
