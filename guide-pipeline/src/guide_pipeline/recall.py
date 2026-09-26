"""Acceptance tests for screening (spec update): recall, and consistency.

Recall: take a published systematic review whose included studies are known,
screen those studies against the review's own criteria, and measure how many
come out "likely eligible" or "unclear" rather than "likely ineligible". Missing
a study that should be flagged is the failure that matters. Papers are screened
independently, so screening only the included studies gives the same recall as
screening the whole literature set; `others` adds non-included papers from the
review's search when a rough over-inclusion count is wanted too.

Consistency: screen the same papers twice with the same criteria; a status that
flips between eligible and ineligible means effort or prompting needs work.

Each run is appended to `recall_fixtures/history.jsonl` so the numbers can be
tracked across runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .llm import LLMClient
from .screening import (
    LIKELY_ELIGIBLE,
    LIKELY_INELIGIBLE,
    STATUSES,
    UNCLEAR,
    Criteria,
    ScreenedPaper,
    screen_papers,
)
from .sources.europepmc import EuropePmcClient
from .sources.pubmed import PubMedClient

FLAGGED = (LIKELY_ELIGIBLE, UNCLEAR)


@dataclass(frozen=True)
class Fixture:
    name: str
    question: str
    criteria: Criteria
    included_pmids: tuple[str, ...]
    search_query: str = ""
    raw: dict = field(default_factory=dict, compare=False)

    @classmethod
    def load(cls, path: str | Path) -> "Fixture":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            name=d["name"],
            question=d["question"],
            criteria=Criteria.from_dict(d["criteria"]),
            included_pmids=tuple(str(p) for p in d["included_pmids"]),
            search_query=d.get("search_query", ""),
            raw=d,
        )


@dataclass
class RecallResult:
    fixture: str
    included: list[ScreenedPaper]
    not_retrieved: list[str]  # included PMIDs PubMed returned no record for
    others: list[ScreenedPaper] = field(default_factory=list)

    @property
    def flagged(self) -> list[ScreenedPaper]:
        return [s for s in self.included if s.status in FLAGGED]

    @property
    def missed(self) -> list[ScreenedPaper]:
        return [s for s in self.included if s.status == LIKELY_INELIGIBLE]

    @property
    def recall(self) -> float:
        return len(self.flagged) / len(self.included) if self.included else 0.0

    def counts(self, papers: list[ScreenedPaper]) -> dict[str, int]:
        return {st: sum(1 for s in papers if s.status == st) for st in STATUSES}


def run_recall(
    fixture: Fixture,
    pubmed: PubMedClient,
    extract_llm: LLMClient,
    screen_llm: LLMClient,
    *,
    europepmc: Optional[EuropePmcClient] = None,
    others: int = 0,
    concurrency: int = 4,
    fulltext_max_chars: int = 60_000,
) -> RecallResult:
    papers = pubmed.fetch_details(list(fixture.included_pmids))
    got = {p.pmid for p in papers}
    not_retrieved = [p for p in fixture.included_pmids if p not in got]
    extra = []
    if others and fixture.search_query:
        pmids = [p for p in pubmed.search_pmids(fixture.search_query, retmax=others * 3)
                 if p not in set(fixture.included_pmids)][:others]
        extra = pubmed.fetch_details(pmids)
    result = screen_papers(
        extract_llm, screen_llm, fixture.criteria, papers + extra,
        europepmc=europepmc, concurrency=concurrency, fulltext_max_chars=fulltext_max_chars,
    )
    included_ids = set(fixture.included_pmids)
    return RecallResult(
        fixture=fixture.name,
        included=[s for s in result.papers if s.paper.pmid in included_ids],
        not_retrieved=not_retrieved,
        others=[s for s in result.papers if s.paper.pmid not in included_ids],
    )


@dataclass
class ConsistencyResult:
    fixture: str
    pairs: list[tuple[ScreenedPaper, ScreenedPaper]]

    @property
    def changed(self) -> list[tuple[ScreenedPaper, ScreenedPaper]]:
        return [(a, b) for a, b in self.pairs if a.status != b.status]

    @property
    def flipped(self) -> list[tuple[ScreenedPaper, ScreenedPaper]]:
        """Eligible on one run, ineligible on the other: the failure that matters."""
        extremes = {LIKELY_ELIGIBLE, LIKELY_INELIGIBLE}
        return [(a, b) for a, b in self.changed if {a.status, b.status} == extremes]


def run_consistency(
    fixture: Fixture,
    pubmed: PubMedClient,
    extract_llm: LLMClient,
    screen_llm: LLMClient,
    *,
    papers: int = 5,
    europepmc: Optional[EuropePmcClient] = None,
    concurrency: int = 4,
) -> ConsistencyResult:
    """Screen the first `papers` included studies twice with identical input."""
    records = pubmed.fetch_details(list(fixture.included_pmids[:papers]))
    runs = [
        screen_papers(extract_llm, screen_llm, fixture.criteria, records,
                      europepmc=europepmc, concurrency=concurrency).papers
        for _ in range(2)
    ]
    return ConsistencyResult(fixture.name, list(zip(runs[0], runs[1])))


def append_history(path: str | Path, entry: dict) -> None:
    entry = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
