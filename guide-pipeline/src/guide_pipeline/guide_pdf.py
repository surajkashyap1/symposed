"""Render the guide model as a designed PDF (WeasyPrint).

The page design lives in `assets/guide.html.j2` and `assets/guide.css`: a claret
cover with the Symposed mark, a contents page with page numbers, the Symposed
watermark on every page, a full width coloured banner opening each numbered
step, red boxes for disclaimers and SVG diagrams drawn by `diagrams.py`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from . import diagrams
from .alternatives import HOLD_DAYS, SWAP_PRICE
from .guide_content import (
    ACKNOWLEDGEMENT_WORDING,
    AUTHOR_AI_NOTE,
    COLLABORATION_PROMPT,
    DISCLAIMERS,
    GREY_LITERATURE,
    NOVELTY_STATEMENT,
    REGISTRATION_URGENCY,
    rejection_reasons,
)

ASSETS = Path(__file__).parent / "assets"

GUIDELINE_LINKS = {
    "PRISMA 2020": "https://www.prisma-statement.org/prisma-2020",
    "PRISMA-S": "https://www.prisma-statement.org/prisma-search",
    "PRISMA-ScR": "https://www.prisma-statement.org/scoping",
    "TRIPOD-SRMA": "https://www.tripod-statement.org/",
    "SWiM": "https://doi.org/10.1136/bmj.l6890",
    "SANRA": "https://doi.org/10.1186/s41073-019-0064-8",
    "JBI": "https://jbi-global-wiki.refined.site/space/MANUAL",
}


def guideline_link(text: str) -> str:
    for key, url in GUIDELINE_LINKS.items():
        if text.startswith(key):
            return url
    return ""


def pubmed_url(query: str, *, reviews_only: bool = False) -> str:
    url = f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}"
    return url + "&filter=pubt.systematicreview" if reviews_only else url


def fmt_date(value: str) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%-d %B %Y")
    except ValueError:
        return str(value)


def short_url(url: str) -> str:
    u = urlparse(url)
    return (u.netloc.removeprefix("www.") + u.path).rstrip("/")


def profile_line(m: dict[str, Any]) -> str:
    p = m["profile"]
    bits = [p.get("grade") or "", f"a team of {p.get('team')}" if p.get("team") else "",
            f"{p['hours'].lower()} hours a week each" if p.get("hours") else "",
            f"statistics: {p['stats'].lower()}" if p.get("stats") else "",
            f"timeline: {p['timeline'].lower()}" if p.get("timeline") else ""]
    return ", ".join(b for b in bits if b) or "your proforma answers"


def render_html(m: dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(ASSETS)),
                      autoescape=select_autoescape(["html", "j2"]),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("guide.html.j2")
    search_for_check = next((s["query"] for s in m["searches"]
                             if s["number"] == (m.get("papers_search_number") or 1)),
                            m["searches"][0]["query"] if m["searches"] else m["title"])
    return tpl.render(
        m=m,
        colour=diagrams.step_colour,
        fmt_date=fmt_date,
        pubmed_url=pubmed_url,
        short_url=short_url,
        guideline_link=guideline_link,
        profile_line=profile_line(m),
        review_check_url=pubmed_url(search_for_check, reviews_only=True),
        novelty_statement=NOVELTY_STATEMENT.format(date=m["novelty_date"]),
        registration_urgency=REGISTRATION_URGENCY,
        disclaimers=DISCLAIMERS,
        grey=GREY_LITERATURE,
        rejection=rejection_reasons(m["publication_type"]),
        acknowledgement=ACKNOWLEDGEMENT_WORDING,
        ai_note=AUTHOR_AI_NOTE,
        collaboration=COLLABORATION_PROMPT,
        hold_days=HOLD_DAYS,
        swap_price=SWAP_PRICE,
        gantt_svg=diagrams.gantt([{"number": t["number"], "name": t["name"],
                                   "start_week": t["start_week"], "end_week": t["end_week"]}
                                  for t in m["timeline"]]),
        tree_svg=diagrams.decision_tree(m["decision_tree"]) if m["decision_tree"] else "",
        rob_svg=diagrams.rob_tree(m["rob_tools"][0]) if m["rob_tools"] else "",
        prisma_svg=diagrams.prisma(m["prisma"]) if m.get("prisma") else "",
    )


def write_pdf(m: dict[str, Any], path: str | Path) -> Path:
    from weasyprint import HTML  # imported lazily: it loads system libraries

    path = Path(path)
    HTML(string=render_html(m), base_url=str(ASSETS) + "/").write_pdf(str(path))
    return path
