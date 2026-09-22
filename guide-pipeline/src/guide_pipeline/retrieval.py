"""Step 4 — deep retrieval for the chosen title.

For the one chosen review question, pull the actual records (with abstracts),
remove duplicates, and ask the LLM to suggest how each paper might be used.

Two rules hold throughout: every record here is fetched from PubMed, never
invented (rule 1); and the tags are *suggested uses*, never an include/exclude
decision — the user decides what goes in their review (rule 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .llm import LLMClient, LLMError
from .sources.pubmed import Paper, PubMedClient

_TAG_BATCH = 10  # papers per LLM tagging call
_ABSTRACT_CHARS = 600  # abstract chars sent to the model per paper
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_TAG_SYSTEM = (
    "You help a clinician triage papers for a review. You return ONLY valid JSON. "
    "For each paper you SUGGEST how it might be used (e.g. 'primary RCT evidence', "
    "'background/context', 'methods reference', 'related but different population'). "
    "You do NOT decide inclusion or exclusion — the user decides that."
)


@dataclass(frozen=True)
class TaggedPaper:
    paper: Paper
    suggested_use: str
    reason: str


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    papers: list[TaggedPaper]

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "count": len(self.papers),
            "papers": [
                {
                    "pmid": t.paper.pmid,
                    "title": t.paper.title,
                    "year": t.paper.year,
                    "journal": t.paper.journal,
                    "doi": t.paper.doi,
                    "authors": list(t.paper.authors),
                    "suggested_use": t.suggested_use,
                    "reason": t.reason,
                }
                for t in self.papers
            ],
        }


def _title_key(paper: Paper) -> str:
    return _NON_ALNUM.sub(" ", paper.title.lower()).strip()


def dedupe(papers: list[Paper]) -> list[Paper]:
    """Remove duplicates, preferring DOI, then PMID, then normalised title+year."""
    seen_doi: set[str] = set()
    seen_pmid: set[str] = set()
    seen_title: set[tuple[str, Optional[int]]] = set()
    out: list[Paper] = []
    for paper in papers:
        doi = paper.doi.lower() if paper.doi else None
        title_key = (_title_key(paper), paper.year)
        if doi and doi in seen_doi:
            continue
        if paper.pmid and paper.pmid in seen_pmid:
            continue
        if title_key[0] and title_key in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        if paper.pmid:
            seen_pmid.add(paper.pmid)
        if title_key[0]:
            seen_title.add(title_key)
        out.append(paper)
    return out


def tag_papers(llm: LLMClient, papers: list[Paper]) -> list[TaggedPaper]:
    """Ask the LLM to suggest a use for each paper (keyed by the PMIDs we supply)."""
    suggestions: dict[str, tuple[str, str]] = {}
    for start in range(0, len(papers), _TAG_BATCH):
        batch = papers[start : start + _TAG_BATCH]
        listing = "\n".join(
            f'- pmid {p.pmid}: "{p.title}" — {p.abstract[:_ABSTRACT_CHARS]}'
            for p in batch
        )
        user = (
            "Suggest a use for each paper below. Return JSON "
            '{"tags":[{"pmid":str,"suggested_use":str,"reason":str}]} using EXACTLY '
            f"the pmids given.\n\n{listing}"
        )
        try:
            data = llm.complete_json(_TAG_SYSTEM, user)
            for tag in data.get("tags", []):
                pmid = str(tag.get("pmid", "")).strip()
                if pmid:
                    suggestions[pmid] = (
                        str(tag.get("suggested_use", "")).strip(),
                        str(tag.get("reason", "")).strip(),
                    )
        except LLMError:
            continue  # a failed batch just leaves those papers untagged

    tagged: list[TaggedPaper] = []
    for paper in papers:
        use, reason = suggestions.get(paper.pmid, ("(untagged)", ""))
        tagged.append(TaggedPaper(paper=paper, suggested_use=use or "(untagged)", reason=reason))
    return tagged


def retrieve(
    pubmed: PubMedClient,
    llm: LLMClient,
    query: str,
    *,
    max_records: int = 400,
    tag: bool = True,
) -> RetrievalResult:
    """Search, fetch full records, dedupe, and (optionally) tag."""
    pmids = pubmed.search_pmids(query, retmax=max_records)
    papers = dedupe(pubmed.fetch_details(pmids))
    if tag and papers:
        tagged = tag_papers(llm, papers)
    else:
        tagged = [TaggedPaper(p, "(untagged)", "") for p in papers]
    return RetrievalResult(query=query, papers=tagged)
