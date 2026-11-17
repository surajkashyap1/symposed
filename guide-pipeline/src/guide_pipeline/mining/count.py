"""Step 5 of the update pipeline: eligible new studies for each review's update.

For each review that passed step 3 with a usable full text:
  1. its own search strategy (MEDLINE or PubMed where it gives several) is
     translated into PubMed syntax by the reader model, kept as close to the
     original as PubMed allows. Every MeSH heading is checked in PubMed's MeSH
     database. With no strategy in the text, a search is built from the
     criteria, and the report says so;
  2. the search is run for records added to PubMed after the original search
     ended (entry date, the usual cut point for an update);
  3. every hit gets a quick decision from its title and abstract against the
     review's own criteria (Haiku 5.5, one call per paper): likely eligible,
     unclear or likely ineligible, each with a reason.
     Possibly eligible = likely eligible + unclear.

Screening is the costly part, so the run first estimates it and pauses when the
estimate is over `RUN_BUDGET_USD`. A search with more than `MAX_HITS` records is
flagged as too broad and not screened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from ..candidates import SearchRun
from ..guide_content import _verify_mesh
from ..llm import JsonCall, LLMClient, LLMError, run_many
from ..screening import LIKELY_ELIGIBLE, UNCLEAR, ScreenedPaper, ScreeningResult, screen_quick
from ..sources.pubmed import Paper
from .extract import Extraction

# Rough cost of one quick screening call (Haiku 5.5, title and abstract). Used
# only for the budget pause, never reported as cost.
COST_PER_PAPER_USD = 0.001

_STR = {"type": "string"}
TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "pubmed_query": _STR,
        "changes": {"type": "array", "items": _STR},
        "built_from_criteria": {"type": "boolean"},
    },
    "required": ["pubmed_query", "changes", "built_from_criteria"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You translate a systematic review's published search strategy into one PubMed "
    "query, so the same search can be run again to update the review. Stay as close to "
    "the original as PubMed allows: the same concepts, the same terms and synonyms, the "
    "same AND, OR and NOT structure. Ovid subject headings (exp X/) become \"X\"[Mesh] "
    "(and X/ without exp becomes \"X\"[Mesh:NoExp]); free text fields (.tw., .ti,ab.) "
    "become [tiab]; truncation keeps its *; adjacency operators become a phrase or AND. "
    "Leave out database limits and any date limit (the date is added separately), but "
    "keep limits the review applied to its eligibility, such as humans or a language. "
    "List every change you had to make in plain words. If no strategy is given, build a "
    "sensitive PubMed search from the review's criteria (population and intervention "
    "concepts, each with synonyms), set built_from_criteria to true, and say so in the "
    "changes. Never add a MeSH heading you are not sure exists. You return ONLY JSON."
)


@dataclass
class UpdateSearch:
    pubmed_query: str
    changes: list[str]
    built_from_criteria: bool
    unverified_mesh: list[str] = field(default_factory=list)
    error: str = ""


def translate_call(review: Paper, ex: Extraction, feedback: str = "") -> JsonCall:
    s = ex.medline_strategy
    parts = [f"REVIEW: {review.title}", f"CRITERIA:\n{ex.criteria.as_text()}"]
    parts.append(f"ORIGINAL STRATEGY ({s.database}):\n{s.text}" if s
                 else "ORIGINAL STRATEGY: not given in the full text.")
    if feedback:
        parts.append(f"YOUR LAST QUERY FAILED IN PUBMED: {feedback}\nFix it.")
    return JsonCall(_SYSTEM, "\n\n".join(parts), TRANSLATE_SCHEMA, cache_system=True)


def _read(data: dict) -> UpdateSearch:
    return UpdateSearch(str(data.get("pubmed_query", "")).strip(),
                        [str(c) for c in data.get("changes", [])],
                        bool(data.get("built_from_criteria")))


def translate_all(llm: LLMClient, pubmed: Any, items: list[tuple[Paper, Extraction]]
                  ) -> list[UpdateSearch]:
    """One translation per review; a query PubMed rejects or finds nothing for is
    sent back once with the problem."""
    first = run_many(llm, [translate_call(r, ex) for r, ex in items])
    out: list[UpdateSearch] = []
    for (review, ex), data in zip(items, first):
        if isinstance(data, LLMError):
            out.append(UpdateSearch("", [], False, error=str(data)))
            continue
        s = _read(data)
        problem = _check(pubmed, s.pubmed_query)
        if problem:
            call = translate_call(review, ex, problem)
            try:
                s = _read(llm.complete_json(call.system, call.user, schema=call.schema,
                                            cache_system=True))
                s.error = _check(pubmed, s.pubmed_query)
            except LLMError as exc:
                s.error = f"{problem}; the retry failed ({exc})"
        if not s.error and s.pubmed_query:
            s.unverified_mesh = _verify_mesh(pubmed, s.pubmed_query)
        out.append(s)
    return out


def _check(pubmed: Any, query: str) -> str:
    if not query:
        return "the query was empty"
    try:
        n = pubmed.count(query)
    except httpx.HTTPError as exc:
        return f"PubMed rejected it ({exc})"
    return "" if n > 0 else "PubMed returned no records at all for it"


@dataclass
class UpdateCount:
    """Step 5's result for one review."""

    pmid: str
    search: UpdateSearch
    since: Optional[date]          # records added to PubMed from this date
    hits: int = 0
    too_broad: bool = False
    screening: Optional[ScreeningResult] = None
    searches: list[SearchRun] = field(default_factory=list)

    @property
    def possibly_eligible(self) -> list[ScreenedPaper]:
        if self.screening is None:
            return []
        return [s for s in self.screening.papers if s.status in (LIKELY_ELIGIBLE, UNCLEAR)]

    def counts(self) -> dict[str, int]:
        c = self.screening.counts if self.screening else {}
        return {"likely_eligible": c.get(LIKELY_ELIGIBLE, 0), "unclear": c.get(UNCLEAR, 0),
                "possibly_eligible": len(self.possibly_eligible)}

    def as_dict(self) -> dict:
        return {"pmid": self.pmid, "pubmed_query": self.search.pubmed_query,
                "changes": self.search.changes,
                "built_from_criteria": self.search.built_from_criteria,
                "unverified_mesh": self.search.unverified_mesh, "error": self.search.error,
                "since": self.since.isoformat() if self.since else None, "hits": self.hits,
                "too_broad": self.too_broad, **self.counts(),
                "searches": [s.__dict__ for s in self.searches],
                "screening": self.screening.as_dict() if self.screening else None}


class OverBudget(Exception):
    """Screening would cost more than RUN_BUDGET_USD: the run stops before it."""

    def __init__(self, papers: int, estimate: float, budget: float):
        self.papers, self.estimate, self.budget = papers, estimate, budget
        super().__init__(f"screening {papers:,} papers would cost about ${estimate:.2f}, over "
                         f"the ${budget:.2f} budget")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_new(pubmed: Any, items: list[tuple[Paper, Extraction, UpdateSearch]], *,
             max_hits: int, today: Optional[date] = None) -> list[tuple[UpdateCount, list[str]]]:
    """Run each search for records added after the review's search ended."""
    today = today or datetime.now(timezone.utc).date()
    out = []
    for review, ex, s in items:
        since = ex.search_end + timedelta(days=1) if ex.search_end else None
        uc = UpdateCount(review.pmid, s, since)
        if not s.pubmed_query or s.error or since is None:
            out.append((uc, []))
            continue
        n, ids = pubmed.search_dated(s.pubmed_query, datetype="edat",
                                     mindate=since.strftime("%Y/%m/%d"),
                                     maxdate=today.strftime("%Y/%m/%d"), retmax=max_hits)
        uc.hits = n
        uc.searches.append(SearchRun("PubMed", f"{s.pubmed_query} (added {since} to {today})",
                                     n, _now()))
        uc.too_broad = n > max_hits
        out.append((uc, [] if uc.too_broad else ids))
    return out


def screen_new(screen_llm: LLMClient, pubmed: Any,
               found: list[tuple[UpdateCount, list[str]]], extractions: dict[str, Extraction],
               *, budget_usd: float, concurrency: int = 8) -> list[UpdateCount]:
    """Screen every new record for every review in one go, within the budget."""
    total = sum(len(ids) for _, ids in found)
    estimate = total * COST_PER_PAPER_USD
    if estimate > budget_usd:
        raise OverBudget(total, estimate, budget_usd)
    jobs, slots = [], []
    for uc, ids in found:
        if ids:
            papers = pubmed.fetch_details(ids)
            jobs.append((extractions[uc.pmid].criteria, papers))
            slots.append(uc)
    for uc, result in zip(slots, screen_quick(screen_llm, jobs, concurrency=concurrency)):
        uc.screening = result
    return [uc for uc, _ in found]
