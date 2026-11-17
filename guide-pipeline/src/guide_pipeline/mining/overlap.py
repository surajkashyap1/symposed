"""Overlap judgement: would a proposed review repeat work already done?

Used in step 3 of the update pipeline (docs/spec-update-pipeline.md): has a
review already been updated, or is an update registered on PROSPERO or OSF?
The test (Samarth, 2026-10-25) is duplicated work, not an identical question:
a proposed review that is the same, narrower or wider and containing the
record repeats its work. An update is never a duplicate of the review it
updates, only of a later record that already does that work.

Two stages per candidate:

1. Retrieval. The 30 records (`OVERLAP_RETRIEVAL_K`) most similar to the
   candidate across published reviews and both registry mirrors. The pool is
   built by full text search (each mirror's FTS index, for the question and
   each reformulation) plus semantic search (the stored vectors in
   `embed.VectorIndex`), and published reviews the caller found in PubMed.
   Every pooled record is then scored by embedding similarity to the question
   or any reformulation, and the best k go to the judge.
2. Judgement. The decider model (Opus 5.5, high effort) compares the
   proposed review with each record and returns, per record, an overlap level
   (duplicate, substantial overlap, partial overlap, none), a confidence (high,
   medium, low) and its reasoning on population, intervention, comparator,
   outcomes and study designs. Titles can be worded very differently, so it
   judges meaning, not wording.

The decision (`decide`): a duplicate judged with high or medium confidence
rejects the proposed review (in step 3, the review is already updated or an
update is registered) before any full text is asked for (Samarth, 2026-10-25:
medium as well as high). A duplicate with low confidence, and any substantial
overlap, keeps it but flags it prominently. Partial overlap is
noted. A record the judge did not return leaves it "not fully verified"
rather than clear.

Rule 1: every record's title, identifier, date and text come from PubMed or a
mirror. The model only compares what it is shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol

from ..llm import JsonCall, LLMClient, LLMError, run_many
from ..sources.pubmed import Paper
from .embed import Embedder, VectorIndex
from .models import PICO_FIELDS, Question

PUBLISHED, PROSPERO, OSF = "published review", "PROSPERO", "OSF"
DUPLICATE, SUBSTANTIAL, PARTIAL, NONE = (
    "duplicate", "substantial overlap", "partial overlap", "none")
LEVELS = (DUPLICATE, SUBSTANTIAL, PARTIAL, NONE)
HIGH, MEDIUM, LOW = "high", "medium", "low"
CONFIDENCES = (HIGH, MEDIUM, LOW)

REJECTED = "rejected, duplicate"
FLAGGED = "kept, overlap flagged"
NOTED = "kept, partial overlap noted"
CLEAR = "kept, no overlap found"
UNVERIFIED = "kept, not fully verified"

_BASIS = {PUBLISHED: "title and abstract (PubMed)", PROSPERO: "title only (PROSPERO export)",
          OSF: "title and description (OSF)"}
_TEXT_CHARS = 2500  # of each record's abstract or description shown to the judge


@dataclass(frozen=True)
class OverlapRecord:
    source: str  # PUBLISHED | PROSPERO | OSF
    id: str      # PMID, CRD number or OSF id
    title: str
    text: str = ""  # abstract or description; empty for PROSPERO (titles only)
    when: str = ""  # publication year or registration date, as the source gives it
    url: str = ""
    basis_note: str = ""  # what was read, when not the source's usual record

    @property
    def basis(self) -> str:
        return self.basis_note or _BASIS.get(self.source, self.source)

    @property
    def embed_text(self) -> str:
        return f"{self.title}. {self.text[:1000]}" if self.text else self.title

    @classmethod
    def from_paper(cls, p: Paper) -> "OverlapRecord":
        year = p.first_published_year or p.year
        return cls(PUBLISHED, p.pmid, p.title, p.abstract or "", str(year or ""),
                   f"https://pubmed.ncbi.nlm.nih.gov/{p.pmid}/")

    def as_dict(self) -> dict:
        return {"source": self.source, "id": self.id, "title": self.title, "when": self.when,
                "url": self.url, "basis": self.basis}


class Registry(Protocol):
    """A registry mirror as the overlap check sees it."""

    source: str

    def lexical(self, text: str, limit: int) -> list[OverlapRecord]: ...

    def get(self, ids: list[str]) -> list[OverlapRecord]: ...


def _outside(d: Optional[date], before: Optional[date], after: Optional[date]) -> bool:
    """True when a registration date falls outside the window (unknown dates fail
    a `before` bound, which backtests rely on, but pass an `after` bound)."""
    if before and (d is None or d >= before):
        return True
    return bool(after and d is not None and d < after)


class ProsperoRegistry:
    source = PROSPERO

    def __init__(self, mirror: Any, *, registered_before: Optional[date] = None,
                 registered_after: Optional[date] = None):
        self.mirror, self.before, self.after = mirror, registered_before, registered_after

    def _record(self, m: Any) -> Optional[OverlapRecord]:
        if _outside(m.registration_date, self.before, self.after):
            return None
        return OverlapRecord(PROSPERO, m.registration_id, m.title, "",
                             m.registration_date.isoformat() if m.registration_date else "", m.url)

    def lexical(self, text: str, limit: int) -> list[OverlapRecord]:
        return [r for m in self.mirror.search(text, limit=limit) if (r := self._record(m))]

    def get(self, ids: list[str]) -> list[OverlapRecord]:
        return [r for m in self.mirror.get(ids) if (r := self._record(m))]


class OsfRegistry:
    source = OSF

    def __init__(self, mirror: Any, *, registered_before: Optional[date] = None,
                 registered_after: Optional[date] = None):
        self.mirror, self.before, self.after = mirror, registered_before, registered_after

    def _record(self, m: Any) -> Optional[OverlapRecord]:
        if _outside(m.date_registered, self.before, self.after):
            return None
        return OverlapRecord(OSF, m.id, m.title, m.description,
                             m.date_registered.isoformat() if m.date_registered else "", m.link)

    def lexical(self, text: str, limit: int) -> list[OverlapRecord]:
        return [r for m in self.mirror.search(text, limit=limit, registered_before=self.before)
                if (r := self._record(m))]

    def get(self, ids: list[str]) -> list[OverlapRecord]:
        return [r for m in self.mirror.get(ids) if (r := self._record(m))]


@dataclass(frozen=True)
class Retrieved:
    record: OverlapRecord
    similarity: float


def retrieve(question: Question, reformulations: list[str], *, published: list[OverlapRecord],
             registries: list[Registry], embedder: Embedder,
             index: Optional[VectorIndex] = None, k: int = 30,
             per_query: int = 50) -> list[Retrieved]:
    """The k records most similar to the candidate, across every source."""
    queries = [question.search_text, *[r for r in reformulations if r.strip()]]
    qvecs = embedder.embed(queries)
    pool: dict[tuple[str, str], OverlapRecord] = {(r.source, r.id): r for r in published}
    for reg in registries:
        for q in queries:
            for r in reg.lexical(q, per_query):
                pool.setdefault((r.source, r.id), r)
        if index is not None:
            ids = [i for i, _ in index.search(reg.source, qvecs, k=per_query)]
            for r in reg.get(ids):
                pool.setdefault((r.source, r.id), r)
    if not pool:
        return []
    records = sorted(pool.values(), key=lambda r: (r.source, r.id))
    rvecs = embedder.embed([r.embed_text for r in records])
    sims = (rvecs @ qvecs.T).max(axis=1)
    scored = [Retrieved(r, round(float(s), 4)) for r, s in zip(records, sims)]
    # Deterministic order (the judge's prompt is cached): similarity, then id.
    scored.sort(key=lambda x: (-x.similarity, x.record.source, x.record.id))
    return scored[:k]


# -- judgement ---------------------------------------------------------------------
@dataclass(frozen=True)
class Judgement:
    record: OverlapRecord
    similarity: float
    level: Optional[str]       # None: the judge did not return this record
    confidence: Optional[str]
    reasoning: dict = field(default_factory=dict)  # PICO elements + summary

    @property
    def judged(self) -> bool:
        return self.level is not None

    def as_dict(self) -> dict:
        return {**self.record.as_dict(), "similarity": self.similarity,
                "overlap": self.level or "not judged", "confidence": self.confidence,
                "reasoning": self.reasoning}


_ELEMENT = {"type": "string"}
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "judgements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "record": {"type": "string"},
                    "overlap": {"type": "string", "enum": list(LEVELS)},
                    "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                    **{f: _ELEMENT for f in PICO_FIELDS},
                    "summary": _ELEMENT,
                },
                "required": ["record", "overlap", "confidence", *PICO_FIELDS, "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["judgements"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = (
    "You are a senior systematic reviewer and journal editor. You decide whether a "
    "proposed systematic review would repeat work that has already been done or "
    "registered. Your job is adversarial: try to show the work is already done.\n\n"
    "The test is not whether the record asks the identical question. It is whether "
    "doing the proposed review would repeat work already in the record. That is the "
    "case when the scopes are the same, when the proposed review is wider and contains "
    "the record's question, and when the proposed review is narrower and falls inside "
    "the record's scope. A narrower review repeats the wider one's work even when it "
    "frames the comparison differently: a review of one drug, one route or one dose "
    "against placebo falls inside a record that already reviews that drug, those "
    "routes or those doses in the same population, because the same trials and the "
    "same outcomes are covered (a review of atorvastatin for preventing stroke inside a "
    "review of statins and their doses for preventing stroke). It is new work only "
    "when it asks about a clinically distinct population, intervention or outcome that "
    "the record does not cover. Rewording, synonyms (\"critically ill children\" and "
    "\"paediatric intensive care\") and changes that make no clinical difference "
    "(\"infants\" instead of \"neonates\" for a condition that only occurs in the "
    "first weeks of life) do not make the work new. Compare five elements: population, "
    "intervention or exposure, comparator, outcomes and study designs.\n\n"
    "The one exception is an update. When the proposed review is an update of an "
    "existing review, it is not a duplicate of that review. It is a duplicate of a "
    "record that already updates it, or that covers the same work with a more recent "
    "search, because an update would then repeat that record's work.\n\n"
    "Overlap levels:\n"
    f'- "{DUPLICATE}": the proposed review would repeat the record\'s work: same scope, '
    "inside it, or containing it, with no element that makes it genuinely new.\n"
    f'- "{SUBSTANTIAL}": it would repeat a large part of the record\'s work, but one '
    "element genuinely differs, so some of the work would be new.\n"
    f'- "{PARTIAL}": some elements are shared but most of the work would be new.\n'
    f'- "{NONE}": different work.\n\n'
    "Confidence: high when the record states enough to compare every element that "
    "matters; medium when an element has to be inferred; low when the record is too "
    "brief (for example a title only) to be sure. A title alone can still give high "
    "confidence when it plainly states the same work.\n\n"
    "Use only the text you are given. Do not use outside knowledge about these records, "
    "their authors or the literature, and do not assume a record says something it does "
    "not. For each element write one short sentence comparing the two. The summary says "
    "in one or two sentences why you chose the level. Return a judgement for every "
    "record, using its label. You return ONLY JSON."
)


def _prompt(question: Question, retrieved: list[Retrieved]) -> str:
    if question.updates:
        lines = ["PROPOSED REVIEW: an update of this existing systematic review",
                 f"Existing review: {question.updates}"]
    else:
        lines = [f"PROPOSED REVIEW: {question.title}"]
    if any(getattr(question.pico, f) for f in PICO_FIELDS):
        lines.append(question.pico.as_text())
    if question.description:
        lines.append(f"Abstract of the existing review: {question.description[:_TEXT_CHARS]}"
                     if question.updates else f"Description: {question.description}")
    lines += ["", "RECORDS:"]
    for i, r in enumerate(retrieved, 1):
        rec = r.record
        text = rec.text[:_TEXT_CHARS] if rec.text else "(no text beyond the title)"
        lines += [f"[R{i}] {rec.source} {rec.id}, {rec.when or 'date not given'} "
                  f"({rec.basis})", f"Title: {rec.title}", f"Text: {text}", ""]
    return "\n".join(lines)


def judge_call(question: Question, retrieved: list[Retrieved]) -> JsonCall:
    return JsonCall(JUDGE_SYSTEM, _prompt(question, retrieved), JUDGE_SCHEMA, cache_system=True)


def read_judgements(data: Any, retrieved: list[Retrieved]) -> list[Judgement]:
    """Pair the reply with the records; a record left out stays not judged."""
    got: dict[int, dict] = {}
    items = data.get("judgements", []) if isinstance(data, dict) else []
    for item in items:
        label = str(item.get("record", "")).strip().strip("[]").upper()
        if label.startswith("R") and label[1:].isdigit():
            n = int(label[1:])
            if (1 <= n <= len(retrieved) and n not in got
                    and item.get("overlap") in LEVELS and item.get("confidence") in CONFIDENCES):
                got[n] = item
    out = []
    for i, r in enumerate(retrieved, 1):
        item = got.get(i)
        if item is None:
            out.append(Judgement(r.record, r.similarity, None, None, {}))
            continue
        reasoning = {f: str(item.get(f, "")).strip() for f in (*PICO_FIELDS, "summary")}
        out.append(Judgement(r.record, r.similarity, item["overlap"], item["confidence"],
                             reasoning))
    return out


def judge_many(llm: LLMClient, items: list[tuple[Question, list[Retrieved]]]
               ) -> list[list[Judgement] | LLMError]:
    """Judge several candidates at once (the Batch API, where the client has it)."""
    todo = [(i, q, r) for i, (q, r) in enumerate(items) if r]
    results = run_many(llm, [judge_call(q, r) for _, q, r in todo])
    out: list[list[Judgement] | LLMError] = [[] for _ in items]
    for (i, _q, r), res in zip(todo, results):
        out[i] = res if isinstance(res, LLMError) else read_judgements(res, r)
    return out


# -- decision ----------------------------------------------------------------------
@dataclass(frozen=True)
class OverlapVerdict:
    question: Question
    status: str
    reason: str
    judgements: list[Judgement]
    model: str = ""
    judged_on: str = ""
    error: str = ""

    @property
    def rejected(self) -> bool:
        return self.status == REJECTED

    @property
    def closest(self) -> list[Judgement]:
        """Judged records, most overlapping first."""
        rank = {lvl: i for i, lvl in enumerate(LEVELS)}
        conf = {c: i for i, c in enumerate(CONFIDENCES)}
        return sorted((j for j in self.judgements if j.judged),
                      key=lambda j: (rank[j.level], conf[j.confidence], -j.similarity))

    def as_dict(self) -> dict:
        return {"question": self.question.as_dict(), "status": self.status,
                "reason": self.reason, "model": self.model, "judged_on": self.judged_on,
                "error": self.error, "judgements": [j.as_dict() for j in self.closest]
                + [j.as_dict() for j in self.judgements if not j.judged]}


def _cite(j: Judgement) -> str:
    return (f"{j.record.source} {j.record.id} ({j.record.url}), judged {j.level} with "
            f"{j.confidence} confidence from its {j.record.basis}: "
            f"{j.reasoning.get('summary', '')}")


REJECT_CONFIDENCES = (HIGH, MEDIUM)


def rejects(j: Judgement) -> bool:
    """A duplicate judged with enough confidence to reject without a person."""
    return j.level == DUPLICATE and j.confidence in REJECT_CONFIDENCES


def decide(question: Question, judgements: list[Judgement] | LLMError, *, model: str = "",
           judged_on: str = "") -> OverlapVerdict:
    if isinstance(judgements, LLMError):
        return OverlapVerdict(question, UNVERIFIED,
                              "The overlap judge failed, so this candidate is not verified. "
                              "Check it by hand.", [], model, judged_on, str(judgements))
    judged = [j for j in judgements if j.judged]
    missing = len(judgements) - len(judged)
    dups = [j for j in judged if rejects(j)]
    flags = [j for j in judged if j.level in (DUPLICATE, SUBSTANTIAL)]
    partial = [j for j in judged if j.level == PARTIAL]
    if dups:
        status, reason = REJECTED, "Duplicate of " + _cite(dups[0])
    elif missing:
        status = UNVERIFIED
        reason = (f"{missing} of {len(judgements)} records were not judged, so this candidate "
                  "is not fully verified.")
        if flags:
            reason += " Closest overlap: " + _cite(flags[0])
    elif flags:
        status, reason = FLAGGED, "Overlap flagged: " + _cite(flags[0])
    elif partial:
        status, reason = NOTED, "Partial overlap: " + _cite(partial[0])
    elif judgements:
        status, reason = CLEAR, f"None of the {len(judgements)} closest records overlap."
    else:
        status, reason = CLEAR, "No similar record was found."
    return OverlapVerdict(question, status, reason, list(judgements), model, judged_on)
