"""Screenshots of each search strategy entered into PubMed, for the guide.

Opens the PubMed results page for every numbered search in a headless browser
and captures the top of the page: the search box with the strategy in it and
the results count. A failed screenshot never stops the guide; that search is
simply shown without a picture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .guide_pdf import pubmed_url

VIEWPORT = {"width": 1280, "height": 800}
# The search box, the result count and the first result: enough to show what to
# type and what to expect, small enough to sit beside the strategy on one page.
CLIP = {"x": 120, "y": 0, "width": 1040, "height": 400}


def capture_searches(model: dict[str, Any], directory: str | Path, *,
                     say: Callable[[str], None] = print) -> dict[str, str]:
    """Save search-<n>.png for each search; return {number: file URI}."""
    out: dict[str, str] = {}
    searches = [s for s in model.get("searches", []) if s.get("query")]
    if not searches:
        return out
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        say("Screenshots skipped: playwright is not installed")
        return out
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1.5,
                                    locale="en-GB")
            for s in searches:
                path = d / f"search-{s['number']}.png"
                try:
                    page.goto(pubmed_url(s["query"]), wait_until="domcontentloaded",
                              timeout=45_000)
                    page.wait_for_selector("#id_term", timeout=20_000)
                    page.wait_for_timeout(1200)
                    _hide_banners(page)
                    page.screenshot(path=str(path), clip=CLIP)
                    out[str(s["number"])] = path.resolve().as_uri()
                except Exception as exc:  # noqa: BLE001  one bad page never stops a guide
                    say(f"Screenshot of search strategy {s['number']} failed: {exc}")
            browser.close()
    except Exception as exc:  # noqa: BLE001  e.g. no browser installed
        say(f"Screenshots skipped: {exc}")
    return out


def _hide_banners(page) -> None:
    page.add_style_tag(content=(
        ".usa-banner, .ncbi-alerts, #ncbi-alerts, .survey-banner, .cookie-banner, "
        "[class*='feedback'], .usa-alert { display: none !important; }"))
