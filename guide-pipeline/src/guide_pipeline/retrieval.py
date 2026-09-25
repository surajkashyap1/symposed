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

# The fixed suggested-use taxonomy from the build spec (section 6.3), in the order
# the guide groups them. A suggested use is never an include/exclude decision.
USE_CATEGORIES = (
    "Background or rationale",
    "Methods justification",
    "Comparable review for discussion",
    "Potential included study",
    "Excluded but contextually relevant",
)

TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pmid": {"type": "string"},
                    "suggested_use": {"type": "string", "enum": list(USE_CATEGORIES)},
                    "reason": {"type": "string"},
                },
                "required": ["pmid", "suggested_use", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tags"],
    "additionalProperties": False,
}

# One-line meanings sent to the model so it picks consistently.
_USE_MEANINGS = {
    "Background or rationale": "sets the clinical scene or shows why the question matters",
    "Methods justification": "supports a methodological choice (design, tool, outcome measure)",
    "Comparable review for discussion": "an existing review to compare against in the discussion",
    "Potential included study": "a primary study that might meet the review's eligibility criteria",
    "Excluded but contextually relevant": "unlikely to meet eligibility but useful context",
}

_TAG_SYSTEM = (
    "You help a clinician triage papers for a review. You return ONLY valid JSON. "
    "For each paper you SUGGEST how it might be used by choosing exactly one "
    "category from the list you are given. You do NOT decide inclusion or "
    "exclusion — the user decides that."
)


def _normalize_use(raw: str) -> str:
    """Map a model-supplied use to the fixed taxonomy; anything else is ''."""
    r = raw.strip().lower()
    for category in USE_CATEGORIES:
        if r == category.lower():
            return category
    return ""  # off-taxonomy -> untagged, so a human sees it rather than a guess


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
        meanings = "\n".join(f"- {c}: {m}" for c, m in _USE_MEANINGS.items())
        user = (
            "Suggest a use for each paper below. For suggested_use choose EXACTLY one "
            f"of these (name spelled exactly):\n{meanings}\n\nReturn JSON "
            '{"tags":[{"pmid":str,"suggested_use":str,"reason":str}]} using EXACTLY '
            f"the pmids given. The reason says why the paper was flagged.\n\n{listing}"
        )
        try:
            data = llm.complete_json(_TAG_SYSTEM, user, schema=TAGS_SCHEMA)
            for tag in data.get("tags", []):
                pmid = str(tag.get("pmid", "")).strip()
                if pmid:
                    suggestions[pmid] = (
                        _normalize_use(str(tag.get("suggested_use", ""))),
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
