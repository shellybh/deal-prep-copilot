"""Regenerates the PDF test fixture (needs Playwright + Chromium and a Hebrew font file, e.g. Heebo, OFL).
Run from the repo root:  HEBREW_FONT=path/to/Heebo.ttf python backend/tests/fixtures/make_fixtures.py
The output (kb_sample_he_en.pdf) is committed, so tests don't need Playwright.
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FONT = Path(os.environ["HEBREW_FONT"]).resolve().as_uri()

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Heebo; src: url('{FONT}'); }}
body {{ font-family: Heebo, sans-serif; font-size: 14px; }}
.he {{ direction: rtl; }}
.page {{ page-break-after: always; }}
</style></head><body>
<div class="page"><h1>NexaStream Partner Guide</h1>
<p>Partners get a 20% discount on the Enterprise tier.</p></div>
<div class="page he"><h1>מדריך שותפים</h1>
<p>שותפים מקבלים הנחה של 20 אחוז על חבילת Enterprise.</p></div>
</body></html>"""


def main() -> None:
    html_path = HERE / "_kb_sample.html"
    html_path.write_text(HTML, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.wait_for_load_state("networkidle")
        page.pdf(path=str(HERE / "kb_sample_he_en.pdf"), format="A5")
        browser.close()
    html_path.unlink()
    print("wrote", HERE / "kb_sample_he_en.pdf")


if __name__ == "__main__":
    main()
