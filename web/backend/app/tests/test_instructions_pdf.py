"""Tests for app/pipeline/instructions_pdf.py -- plain script style (assert +
print), matching this backend's existing test_reference_color.py convention
rather than pulling in pytest as a new dependency for this sub-project.
Uses a real headless-Chromium render (Playwright is already a real
dependency of this module) rather than asserting against the HTML string,
since the actual bug this pins (silent clipping by `.page`'s
`overflow: hidden`) only shows up in the real rendered/paginated output,
not in the HTML source.

Also needs `pypdf` (test-only -- reads the rendered PDF back to check page
count/text, not a production dependency, so it's deliberately not in
requirements.txt; `pip install pypdf` before running this file).

Run: python app/tests/test_instructions_pdf.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.pipeline.instructions_pdf import _BOOKLET_CSS, _bom_pages_html
from brickforge.pipeline.instructions import PartTally

_PART_NAMES = [
    "Plate 1 x 1", "Plate 1 x 2", "Plate 1 x 3", "Plate 2 x 2", "Plate 2 x 3",
    "Brick 1 x 1", "Brick 1 x 2", "Brick 1 x 3", "Tile 1 x 1", "Tile 1 x 2",
    "Slope Brick 31 1 x 1 with Groove", "Slope Brick 45 2 x 1", "Plate 2 x 6",
]
_COLOR_NAMES = [
    "Dark Orange", "Dark Tan", "Reddish Brown", "Black", "Dark Green",
    "Red", "Dark Brown", "Tan", "Nougat", "Olive Green", "Medium Nougat",
    "Light Bluish Gray", "Bright Light Yellow", "Dark Bluish Gray",
]


def _synthetic_bom(n: int) -> list[PartTally]:
    """Real part/colour name lengths (not placeholder text) so chip
    wrapping behaves the same way it would on a real generated model --
    a short synthetic name would understate how many rows actually fit
    per column and defeat the point of an empirical check."""
    return [
        PartTally(
            part_id=f"p{i}",
            part_name=_PART_NAMES[i % len(_PART_NAMES)],
            color_code=i % len(_COLOR_NAMES),
            color_name=_COLOR_NAMES[i % len(_COLOR_NAMES)],
            count=n - i,
        )
        for i in range(n)
    ]


def _render_bom_pdf(rows: list[PartTally], out_path: str) -> None:
    from playwright.sync_api import sync_playwright

    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_BOOKLET_CSS}</style></head>
<body>{_bom_pages_html(rows)}</body></html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html_doc)
            page.pdf(path=out_path, format="A4", print_background=True)
        finally:
            browser.close()


def test_a_large_parts_list_spans_multiple_pages_with_nothing_clipped() -> None:
    """Regression pin for a real, founder-reported bug: `.page` has a
    fixed A4 height and `overflow: hidden`, and the parts grid used to be
    a single such page with no fallback -- a dense model's Full Parts
    List page ran past the page boundary and the excess was silently
    clipped, invisible in the final PDF. This renders a real 150-row BOM
    (well past the ~45-row threshold that used to still fit on one
    4-column page) through the real Playwright pipeline and confirms
    every single row's quantity marker survives into the extracted PDF
    text -- a clipped chip wouldn't be painted at all, so its quantity
    simply wouldn't appear anywhere in the extracted text if the bug
    were still present."""
    import pypdf

    rows = _synthetic_bom(150)
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "bom.pdf")
        _render_bom_pdf(rows, pdf_path)

        reader = pypdf.PdfReader(pdf_path)
        page_count = len(reader.pages)
        full_text = "".join(page.extract_text() for page in reader.pages)

        print(f"150-row BOM rendered as {page_count} page(s)")
        assert page_count > 1, "a 150-row BOM should need more than one page"

        found_counts = sorted(int(c) for c in re.findall(r"×\s*(\d+)", full_text))
        expected_counts = list(range(1, 151))
        missing = sorted(set(expected_counts) - set(found_counts))
        print(f"found {len(found_counts)}/150 quantity markers across {page_count} pages")
        assert not missing, f"these rows never made it into any page (clipped): {missing}"
        assert found_counts == expected_counts


def test_a_small_parts_list_still_renders_as_a_single_unlabelled_page() -> None:
    """No regression for the common case: a short BOM shouldn't grow an
    unnecessary "(page 1 of 1)" suffix or split into multiple pages just
    because pagination now exists."""
    import pypdf

    rows = _synthetic_bom(10)
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "bom.pdf")
        _render_bom_pdf(rows, pdf_path)

        reader = pypdf.PdfReader(pdf_path)
        assert len(reader.pages) == 1
        text = reader.pages[0].extract_text()
        assert "Full parts list" in text
        assert "page 1 of" not in text.lower()


def main() -> None:
    tests = [
        test_a_large_parts_list_spans_multiple_pages_with_nothing_clipped,
        test_a_small_parts_list_still_renders_as_a_single_unlabelled_page,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
