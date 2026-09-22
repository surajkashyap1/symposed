"""Step 5 — draft the Publication Guide as a Word document.

The guide is assembled ONLY from the records retrieved in Step 4 (rule 1) and is
always dated with when the searches were run. It suggests how each paper might be
used but never decides inclusion (rule 2); the closing section makes clear that a
human must screen the papers and check PROSPERO before anything is used.
"""

from __future__ import annotations

from typing import Optional

from docx import Document

from .landscape import Landscape
from .retrieval import USE_CATEGORIES, RetrievalResult
from .sources.pubmed import Paper
from .workspace import Workspace

DISCLAIMER = (
    "This is an automatically drafted starting point, not a finished review. Every "
    "paper below was found by a database search on the date shown and must be "
    "screened by a person — the suggested uses are hints, not decisions. Search "
    "PROSPERO for an existing protocol before you begin, and register your own."
)

NEXT_STEPS = (
    "Search PROSPERO to confirm no one has registered this question.",
    "Register your protocol (PROSPERO) before screening.",
    "Screen the suggested papers yourself — decide what to include.",
    "Extract data and appraise risk of bias for the studies you include.",
)


def _format_citation(paper: Paper) -> str:
    authors = list(paper.authors)
    if not authors:
        who = "[No author listed]"
    elif len(authors) > 3:
        who = ", ".join(authors[:3]) + ", et al."
    else:
        who = ", ".join(authors)
    year = f" ({paper.year})" if paper.year else ""
    journal = f" {paper.journal}." if paper.journal else ""
    ids = f" PMID: {paper.pmid}." if paper.pmid else ""
    if paper.doi:
        ids += f" DOI: {paper.doi}."
    return f"{who}{year}. {paper.title}.{journal}{ids}".strip()


def _grouped_by_use(result: RetrievalResult) -> dict[str, list]:
    groups: dict[str, list] = {}
    for tagged in result.papers:
        groups.setdefault(tagged.suggested_use, []).append(tagged)
    # Controlled-vocabulary categories first (in their canonical order), then any
    # unexpected labels, then "(untagged)" last.
    ordered: dict[str, list] = {}
    for category in USE_CATEGORIES:
        if category in groups:
            ordered[category] = groups[category]
    for label, papers in groups.items():
        if label not in ordered and label != "(untagged)":
            ordered[label] = papers
    if "(untagged)" in groups:
        ordered["(untagged)"] = groups["(untagged)"]
    return ordered


def build_guide(
    workspace: Workspace,
    title: str,
    result: RetrievalResult,
    *,
    search_date: str,
    sources_used: tuple[str, ...] = ("PubMed",),
    landscape: Optional[Landscape] = None,
) -> str:
    """Write the guide to `workspace.guide_path` and return that path."""
    doc = Document()
    doc.add_heading("Publication Guide", level=0)
    doc.add_heading(title, level=1)

    doc.add_heading("Search details", level=2)
    meta = doc.add_paragraph()
    meta.add_run("Searches run: ").bold = True
    meta.add_run(f"{search_date}\n")
    meta.add_run("Sources: ").bold = True
    meta.add_run(f"{', '.join(sources_used)}\n")
    meta.add_run("PubMed query: ").bold = True
    meta.add_run(f"{result.query}\n")
    meta.add_run("Records retrieved: ").bold = True
    meta.add_run(str(len(result.papers)))

    if landscape is not None:
        doc.add_heading("Research landscape", level=2)
        lp = doc.add_paragraph()
        lp.add_run("Total literature: ").bold = True
        lp.add_run(f"{landscape.total_literature:,}\n")
        lp.add_run("Existing systematic reviews: ").bold = True
        lp.add_run(f"{landscape.systematic_reviews:,}\n")
        lp.add_run("Existing guidelines: ").bold = True
        lp.add_run(f"{landscape.guidelines:,}")

    doc.add_heading("Suggested papers", level=2)
    doc.add_paragraph(
        "Grouped by how each paper might be used. These are suggestions — you decide "
        "what to include.",
        style="Intense Quote" if _has_style(doc, "Intense Quote") else None,
    )
    for use, papers in _grouped_by_use(result).items():
        doc.add_heading(use, level=3)
        for tagged in papers:
            para = doc.add_paragraph(style="List Bullet")
            para.add_run(_format_citation(tagged.paper))
            if tagged.reason:
                note = doc.add_paragraph(tagged.reason)
                note.paragraph_format.left_indent = _indent()

    doc.add_heading("Next steps", level=2)
    for step in NEXT_STEPS:
        doc.add_paragraph(step, style="List Number")

    doc.add_heading("Important", level=2)
    doc.add_paragraph(DISCLAIMER)

    doc.save(str(workspace.guide_path))
    return str(workspace.guide_path)


def _has_style(doc: Document, name: str) -> bool:
    return any(s.name == name for s in doc.styles)


def _indent():
    from docx.shared import Pt

    return Pt(18)
