"""Stage 5 — deep retrieval for the chosen question.

Pull the actual records (with abstracts) from PubMed and remove duplicates. Every
record is fetched, never invented (rule 1). Assessing each paper against the
review's criteria is the next step, in `screening.py` — it replaced the old
suggested-use tagging (spec update).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .sources.pubmed import Paper, PubMedClient

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    papers: list[Paper]  # deduplicated
    identified: int = 0  # PubMed's total for the query (may exceed what was fetched)
    fetched: int = 0  # records fetched before duplicates were removed

    def as_dict(self) -> dict:
        return {"query": self.query, "count": len(self.papers),
                "identified": self.identified, "fetched": self.fetched}


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


def retrieve(pubmed: PubMedClient, query: str, *, max_records: int = 400) -> RetrievalResult:
    """Search, fetch full records, dedupe (counts kept for the PRISMA diagram)."""
    identified = pubmed.count(query)
    pmids = pubmed.search_pmids(query, retmax=max_records)
    fetched = pubmed.fetch_details(pmids)
    return RetrievalResult(query=query, papers=dedupe(fetched), identified=identified,
                           fetched=len(fetched))
