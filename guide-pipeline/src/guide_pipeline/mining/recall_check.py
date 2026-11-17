"""Step 7 of the update pipeline: does the guide's search find the original's studies?

The search the guide will recommend is the review's own strategy as translated
in step 5. Before the guide is written it is backtested on the studies the
original review included:

  1. each included study (read from the full text in step 4) is matched to its
     PubMed record by title words and year. Studies that cannot be matched are
     listed and left out of the denominator;
  2. search recall: how many of the matched studies the search finds
     (target `SEARCH_RECALL_MIN`, 90%);
  3. screening recall: how many of those found are kept (likely eligible or
     unclear) when screened against the review's criteria
     (target `SCREEN_RECALL_MIN`, 95%).

When search recall falls short, the reader model is shown the studies it
missed and revises the search, up to `MAX_SEARCH_REVISIONS` times, with the
reason for each miss recorded. The final search is what the guide uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..llm import JsonCall, LLMClient, LLMError
from ..prospero.records import match_key, similarity
from ..screening import LIKELY_ELIGIBLE, UNCLEAR, Criteria, screen_quick
from ..sources.pubmed import Paper

MATCH_MIN = 0.6  # title similarity needed to accept a PubMed record as the study


def _words(title: str) -> list[str]:
    return [w for w in match_key(title).split() if len(w) > 3][:10]


def resolve_included(pubmed: Any, studies: list[dict]) -> tuple[list[tuple[dict, str]], list[dict]]:
    """Match each included study to a PMID. Returns (matched, unmatched)."""
    matched, unmatched = [], []
    for st in studies:
        title, year = st.get("title", ""), st.get("year", "")
        words = _words(title)
        if not words or not re.fullmatch(r"\d{4}", year or ""):
            unmatched.append(st)
            continue
        y = int(year)
        q = " AND ".join(f"{w}[ti]" for w in words)
        _, ids = pubmed.search_dated(q, datetype="pdat", mindate=f"{y - 1}/01/01",
                                     maxdate=f"{y + 1}/12/31", retmax=5)
        best, score = None, 0.0
        for pmid, found in pubmed.titles(ids) if ids else []:
            s = similarity(match_key(title), match_key(found))
            if s > score:
                best, score = pmid, s
        if best and score >= MATCH_MIN:
            matched.append((st, best))
        else:
            unmatched.append(st)
    return matched, unmatched


_STR = {"type": "string"}
REVISE_SCHEMA = {
    "type": "object",
    "properties": {
        "pubmed_query": _STR,
        "diagnoses": {"type": "array", "items": {
            "type": "object", "properties": {"pmid": _STR, "reason": _STR},
            "required": ["pmid", "reason"], "additionalProperties": False}},
        "changes": {"type": "array", "items": _STR},
    },
    "required": ["pubmed_query", "diagnoses", "changes"],
    "additionalProperties": False,
}

_REVISE_SYSTEM = (
    "You improve a PubMed search strategy for updating a systematic review. The search "
    "missed some studies the original review included. For each missed study, say which "
    "concept of the search it fails (for example a synonym or MeSH heading the search "
    "lacks). Then revise the query so it would find them, changing as little as possible "
    "and keeping the original review's concepts and structure. Add only terms that a "
    "systematic searcher would accept for every study, not terms that pick out one paper. "
    "Never add a MeSH heading you are not sure exists. You return ONLY JSON."
)


def _revise_call(query: str, criteria: Criteria, missed: list[Paper]) -> JsonCall:
    lines = [f"CURRENT QUERY:\n{query}", f"REVIEW CRITERIA:\n{criteria.as_text()}",
             "MISSED STUDIES:"]
    for p in missed:
        lines.append(f"PMID {p.pmid}: {p.title}\n{(p.abstract or '')[:1500]}")
    return JsonCall(_REVISE_SYSTEM, "\n\n".join(lines), REVISE_SCHEMA)


@dataclass
class Attempt:
    query: str
    found: list[str]          # matched included studies the search retrieves
    missed: list[str]
    search_recall: Optional[float]
    diagnoses: list[dict] = field(default_factory=list)  # why each miss happened
    changes: list[str] = field(default_factory=list)     # what the next revision changed


@dataclass
class RecallResult:
    pmid: str
    matched: list[tuple[dict, str]]
    unmatched: list[dict]
    attempts: list[Attempt]
    screened_kept: list[str] = field(default_factory=list)
    screened_dropped: list[dict] = field(default_factory=list)  # pmid, title, reason
    screen_recall: Optional[float] = None
    search_target: float = 0.9
    screen_target: float = 0.95

    @property
    def final(self) -> Attempt:
        return self.attempts[-1]

    @property
    def passed(self) -> bool:
        sr, sc = self.final.search_recall, self.screen_recall
        return (sr is not None and sr >= self.search_target
                and sc is not None and sc >= self.screen_target)

    def as_dict(self) -> dict:
        return {
            "pmid": self.pmid, "passed": self.passed,
            "search_recall": self.final.search_recall, "screen_recall": self.screen_recall,
            "targets": {"search": self.search_target, "screen": self.screen_target},
            "final_query": self.final.query,
            "matched": [{"study": s, "pmid": p} for s, p in self.matched],
            "unmatched": self.unmatched,
            "attempts": [a.__dict__ for a in self.attempts],
            "screened_dropped": self.screened_dropped,
        }


def _attempt(pubmed: Any, query: str, known: list[str]) -> Attempt:
    if not known:
        return Attempt(query, [], [], None)
    found: set[str] = set()
    for start in range(0, len(known), 200):
        uids = " OR ".join(f"{p}[uid]" for p in known[start:start + 200])
        _, ids = pubmed.search_dated(f"({query}) AND ({uids})", retmax=200)
        found |= set(ids)
    hit = [p for p in known if p in found]
    return Attempt(query, hit, [p for p in known if p not in found], len(hit) / len(known))


def run_recall_test(pubmed: Any, *, pmid: str, query: str, criteria: Criteria,
                    studies: list[dict], revise_llm: LLMClient,
                    screen_llm: LLMClient, search_target: float, screen_target: float,
                    max_revisions: int) -> RecallResult:
    matched, unmatched = resolve_included(pubmed, studies)
    known = list(dict.fromkeys(p for _, p in matched))
    attempts = [_attempt(pubmed, query, known)]
    while (attempts[-1].search_recall is not None
           and attempts[-1].search_recall < search_target
           and len(attempts) <= max_revisions):
        last = attempts[-1]
        missed = pubmed.fetch_details(last.missed)
        try:
            call = _revise_call(last.query, criteria, missed)
            data = revise_llm.complete_json(call.system, call.user, schema=call.schema)
        except LLMError:
            break
        new = str(data.get("pubmed_query", "")).strip()
        last.diagnoses = [dict(d) for d in data.get("diagnoses", [])]
        last.changes = [str(c) for c in data.get("changes", [])]
        if not new or new == last.query:
            break
        try:
            attempts.append(_attempt(pubmed, new, known))
        except Exception:  # noqa: BLE001  a revision PubMed rejects ends the loop
            break
        if attempts[-1].search_recall is not None and last.search_recall is not None \
                and attempts[-1].search_recall < last.search_recall:
            attempts.pop()  # never keep a revision that finds fewer
            break
    result = RecallResult(pmid, matched, unmatched, attempts, search_target=search_target,
                          screen_target=screen_target)
    found = attempts[-1].found
    if found:
        (screened,) = screen_quick(screen_llm, [(criteria, pubmed.fetch_details(found))])
        kept = [s for s in screened.papers if s.status in (LIKELY_ELIGIBLE, UNCLEAR)]
        result.screened_kept = [s.paper.pmid for s in kept]
        result.screened_dropped = [{"pmid": s.paper.pmid, "title": s.paper.title,
                                    "reason": s.reason}
                                   for s in screened.papers if s not in kept]
        result.screen_recall = len(kept) / len(screened.papers) if screened.papers else None
    return result
