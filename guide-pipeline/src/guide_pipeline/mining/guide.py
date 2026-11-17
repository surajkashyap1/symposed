"""Step 8 of the update pipeline: the guide for the chosen update.

The guide itself is unchanged (Samarth, 2026-10-25: "all of the things that were
originally part of the plan"). What makes it a true update is what goes in:
  - the question is the original review's question, titled as its update;
  - the criteria are the original review's own, read from its full text;
  - the search is the original's own strategy, translated and recall tested
    (steps 5 and 7), and it is the search behind the papers listed;
  - the papers are the new records since the original search ended, each with
    its screening status and reason.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..candidates import Candidate, CandidateAssessment
from ..gates import PASS, SYSTEMATIC, GateVerdict, TriageCounts
from ..guide_content import assemble
from ..guide_model import build_model
from ..retrieval import RetrievalResult
from ..sources.pubmed import Paper
from ..workspace import create_workspace
from .count import UpdateCount
from .extract import Extraction
from .reviews import citation

UPDATE_AXIS = "Update of an existing systematic review"
# The same review question and methods applied to a new population or region
# (Samarth, 2026-10-26: the India version of the sub-Saharan Africa arrhythmia review).
PARALLEL_AXIS = "Parallel of an existing systematic review in a new setting"
# A reworked version of an existing review chosen by Step 5b (mining/agent.py).
ANGLE_AXIS = "Alternative angle on an existing systematic review"
_SUFFIX = re.compile(
    r"\s*[:.\-–—]\s*(an?\s+)?(updated\s+)?(cochrane\s+)?(systematic\s+(literature\s+)?review"
    r"|meta[\s-]?analysis|review)(\s+(and|with)\s+(an?\s+)?(network\s+)?"
    r"(meta[\s-]?analysis|meta[\s-]?regression|trial sequential analysis))*\.?\s*$",
    re.IGNORECASE)


def update_title(original: str) -> str:
    core = _SUFFIX.sub("", original.strip().rstrip(".")).strip() or original.strip()
    return f"{core}: an updated systematic review"


def build_guide(*, review: Paper, extraction: Extraction, count: UpdateCount,
                query: str, request: Any, settings: Any, sources: Any,
                llms: dict[str, Any], warnings: list[str], screenshots: bool = True,
                say: Callable[[str], None] = print, title: str = "",
                axis: str = UPDATE_AXIS, rationale: str = "",
                kind: str = "update", parallel: str = "",
                parallel_difference: str = "",
                extra_results: dict | None = None) -> dict[str, Any]:
    """`title`, `axis`, `rationale` and `kind` default to an update of `review`. A
    parallel review passes its own (see PARALLEL_AXIS), plus `parallel`: a sentence
    naming the review it mirrors, which opens the rationale and the PROSPERO
    question, and `parallel_difference` for that review's row under similar work."""
    title = title or update_title(review.title)
    screening = count.screening
    papers = [s.paper for s in screening.papers] if screening else []
    # The quick screen never looks for free full texts: find them here, so the
    # tracker can say which papers need a library.
    europepmc = getattr(sources, "europepmc", None)
    if screening and europepmc is not None:
        try:
            free = europepmc.open_access_pmcids([p.pmid for p in papers])
        except httpx.HTTPError:
            free = {}
            warnings = [*warnings, "Europe PMC could not be reached, so no paper is marked "
                        "free to read: check access yourself."]
        for sp in screening.papers:
            sp.open_access_pmcid = sp.open_access_pmcid or free.get(sp.paper.pmid)
    since = count.since.isoformat() if count.since else "the original search date"
    rationale = rationale or (f"An update of {citation(review)} Its search ended "
                              f"{extraction.search_end_as_written or since}. "
                              f"{len(count.possibly_eligible)} possibly eligible studies have "
                              f"been added to PubMed since then.")
    assessment = CandidateAssessment(
        candidate=Candidate(title, axis, query, rationale=rationale),
        counts=TriageCounts(records_to_screen=count.hits,
                            eligible_studies=len(count.possibly_eligible),
                            recent_reviews=0, trials_reporting_soon=None),
        verdict=GateVerdict(PASS, []), prospero=None, searches=list(count.searches))
    dated = query
    if count.since:  # the same window step 5 used: added to PubMed since the old search
        dated = f'({query}) AND ("{count.since:%Y/%m/%d}"[EDAT] : "3000"[EDAT])'
    retrieval = RetrievalResult(query=dated, papers=papers, identified=count.hits,
                                fetched=len(papers))
    today = datetime.now(timezone.utc).date().isoformat()
    say("Writing the guide (search strategies, protocol, PROSPERO entry)...")
    content = assemble(title=title, publication_type=SYSTEMATIC, criteria=extraction.criteria,
                       assessment=assessment, retrieval=retrieval, screening=screening,
                       preferences=request.preferences, proforma=request.proforma,
                       search_date=today, pubmed=sources.pubmed, llms=llms,
                       screened_all=True)
    content.warnings[:0] = warnings
    workspace = create_workspace(title, base=settings.output_dir,
                                 request_id=f"{request.order_id or 'request'}-{kind}-{review.pmid}")
    model = build_model(content, proforma=request.proforma, retrieval_query=retrieval.query,
                        retrieval_count=retrieval.identified, alternatives=[])
    if parallel:
        model["rationale"] = f"{parallel} {model['rationale']}"
        model["similar"].insert(0, {"title": review.title,
                                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{review.pmid}/",
                                    "difference": parallel_difference or parallel})
        if model.get("prospero"):
            model["prospero"]["review_question"] += f" {parallel}"
    say("Rendering the Word guide, tracker, protocol and PROSPERO draft...")
    from ..deliver import build_outputs

    outputs: dict[str, Any] = build_outputs(workspace, model, screenshots=screenshots, say=say)
    content.warnings.extend(outputs.pop("warnings"))
    workspace.write_results({
        "title": title, "kind": kind, "original_review": citation(review),
        "original_pmid": review.pmid,
        "query": query, "warnings_for_reviewer": content.warnings,
        "update": count.as_dict(), "extraction": extraction.as_dict(),
        "proforma": request.proforma, **(extra_results or {}),
    })
    return {"title": title, "workspace": workspace.dir,
            "outputs": {k: str(v) for k, v in outputs.items()}, "warnings": content.warnings}
