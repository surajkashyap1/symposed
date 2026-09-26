"""Draft the Publication Guide as a Word document.

The guide is assembled ONLY from retrieved records (rule 1) and is always dated
with when the searches were run. Each paper shows the pipeline's graded estimate
of eligibility with its reason and what was read (rule 2): an estimate for the
user to verify, never a decision. The full 26-section guide comes later (A9).
"""

from __future__ import annotations

from typing import Optional

from docx import Document

from .landscape import Landscape
from .retrieval import RetrievalResult
from .screening import NOT_STATED, STATUSES, ScreenedPaper, ScreeningResult
from .sources.pubmed import Paper
from .workspace import Workspace

DISCLAIMER = (
    "The papers listed in this guide are suggestions, not a complete or exhaustive "
    "set, found by a preliminary search on the date shown. The eligibility shown "
    "for each is an automated estimate, not screening: you must run your own search "
    "and make your own decisions about which papers to include. Search PROSPERO for "
    "an existing protocol before you begin, and register your own."
)

PAPERS_INTRO = (
    "Each paper shows our estimate of its eligibility against the criteria above, "
    "the reason, and what we read to reach it. These are estimates for you to "
    "check, not decisions: you screen the papers and decide what to include."
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


def _attribute_line(s: ScreenedPaper) -> str:
    a = s.attributes
    bits = [
        f"{label}: {a.get(key)}"
        for label, key in (("Design", "design"), ("Sample", "sample_size"), ("Country", "country"))
        if a.get(key) and a.get(key) != NOT_STATED
    ]
    return " · ".join(bits)


def build_guide(
    workspace: Workspace,
    title: str,
    retrieval: RetrievalResult,
    screening: ScreeningResult,
    *,
    search_date: str,
    sources_used: tuple[str, ...] = ("PubMed", "Europe PMC (open-access full text)"),
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
    meta.add_run(f"{retrieval.query}\n")
    meta.add_run("Records retrieved: ").bold = True
    meta.add_run(f"{len(screening.papers)}\n")
    meta.add_run("Assessed from open-access full text: ").bold = True
    meta.add_run(str(screening.full_text_screened))

    if landscape is not None:
        doc.add_heading("Research landscape", level=2)
        lp = doc.add_paragraph()
        lp.add_run("Total literature: ").bold = True
        lp.add_run(f"{landscape.total_literature:,}\n")
        lp.add_run("Existing systematic reviews: ").bold = True
        lp.add_run(f"{landscape.systematic_reviews:,}\n")
        lp.add_run("Existing guidelines: ").bold = True
        lp.add_run(f"{landscape.guidelines:,}")

    doc.add_heading("Eligibility criteria used", level=2)
    for line in screening.criteria.as_text().splitlines():
        doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("Suggested papers", level=2)
    doc.add_paragraph(PAPERS_INTRO)
    for status in STATUSES:
        group = screening.by_status(status)
        if not group:
            continue
        doc.add_heading(f"{status.capitalize()} ({len(group)})", level=3)
        for s in group:
            doc.add_paragraph(_format_citation(s.paper), style="List Bullet")
            note = doc.add_paragraph()
            note.paragraph_format.left_indent = _indent()
            note.add_run("Estimate: ").bold = True
            note.add_run(f"{s.status}. {s.reason} ")
            note.add_run(f"(Read: {s.evidence_basis}.)").italic = True
            attrs = _attribute_line(s)
            if attrs:
                note.add_run(f"\n{attrs}")

    own_access = screening.unclear_without_open_access()
    if own_access:
        doc.add_heading("Papers to retrieve through your own access", level=2)
        doc.add_paragraph(
            "These are unclear from the abstract and have no open-access full text. "
            "Retrieve them through your institution's library to decide."
        )
        for s in own_access:
            link = f"https://doi.org/{s.paper.doi}" if s.paper.doi else f"PMID {s.paper.pmid}"
            doc.add_paragraph(f"{_format_citation(s.paper)} {link}", style="List Bullet")

    h = screening.heterogeneity
    if h is not None and h.distinct_outcomes:
        doc.add_heading("Outcome heterogeneity", level=2)
        verdict = (
            f"More than {h.threshold}: pooling may be difficult, so check the outcomes "
            "carefully before committing to a meta-analysis."
            if h.flagged
            else f"Within the {h.threshold} we consider workable."
        )
        doc.add_paragraph(
            f"The papers estimated eligible or unclear report "
            f"{h.distinct_outcomes} distinct primary outcomes. {verdict}"
        )
        for outcome, pmids in h.outcome_groups.items():
            doc.add_paragraph(f"{outcome}: {len(pmids)} paper(s)", style="List Bullet")

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
