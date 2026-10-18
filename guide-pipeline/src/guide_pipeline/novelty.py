"""Journal novelty check, before a question reaches the shortlist (Samarth, 2026-10-18).

The gates only count recent systematic reviews and PROSPERO registrations. That
let through a question with two closely related primary studies (one from 2026)
and one whose closest narrative review the gates never counted. Novelty is the
most important property of a guide, so every question is now judged the way a
journal editor would before anyone sees it:

  1. Evidence. The closest reviews of any kind (systematic, scoping, narrative)
     and the closest recent primary studies, found in PubMed by the question's
     own search and re-ranked by title similarity, with their abstracts. The
     PROSPERO check from the gates is added.
  2. Judgement. The decider model (Opus 5.5, maximum effort) compares the
     question with each paper, names the closest, and answers three things: is
     it new to an editor, what would it add beyond the closest papers, and is it
     worth answering whatever the result (a review whose likely answer changes
     nothing is a dead review).
  3. Outcome. "not novel" or "dead" drops the question and the next best is
     checked. "uncertain" stays on the shortlist, marked, for a person to judge.

Abstracts only, so it never pauses for full texts. The final check after the
pick still reads the closest reviews in full. Every PMID and title shown comes
from PubMed; the model only labels and judges what it is given.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from .discovery import FILTER_REVIEWS
from .plain import tidy
from .prospero import match_key, similarity
from .sources.pubmed import Paper

NOVEL, NOT_NOVEL, UNCERTAIN, DEAD = "novel", "not novel", "uncertain", "dead"
FILTER_STUDIES = ('NOT (review[pt] OR systematic[sb] OR "meta-analysis"[pt] OR editorial[pt] '
                  'OR letter[pt] OR comment[pt] OR news[pt])')
_ABSTRACT_CHARS = 1800

_S = {"type": "string"}
NOVELTY_SCHEMA = {
    "type": "object",
    "properties": {
        "papers": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": _S,
                "overlap": {"type": "string", "enum": ["same question", "large", "partial",
                                                       "background only"]},
                "why": _S,
            },
            "required": ["id", "overlap", "why"], "additionalProperties": False}},
        "closest_id": _S,
        "verdict": {"type": "string", "enum": [NOVEL, NOT_NOVEL, UNCERTAIN, DEAD]},
        "editor_view": _S,
        "adds": _S,
        "worth_answering": _S,
        "suggested_change": _S,
    },
    "required": ["papers", "closest_id", "verdict", "editor_view", "adds",
                 "worth_answering", "suggested_change"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a strict journal editor deciding whether a proposed review would be seen as new "
    "and worth publishing. Novelty is the single most important thing: a student will spend "
    "months on this, and a review that repeats existing work, or that will not change anything "
    "whatever it finds, is wasted. Judge only from the papers given. Do not invent papers, "
    "PMIDs or findings.\n\n"
    "For each paper, label its overlap with the proposed review: 'same question' (it already "
    "answers it, in this population with this comparison and outcome), 'large' (most of it), "
    "'partial' (part of the question, or the same question in a different population or "
    "setting) or 'background only'. Recent primary studies count too: if one or two recent "
    "studies already answer the question directly, or the field is so small that a review "
    "would mostly restate them, an editor would not see a review as adding much.\n\n"
    "Then give a verdict:\n"
    "- 'novel': no review answers it, the closest papers leave a clear part open, and a "
    "review would add something specific.\n"
    "- 'not novel': a review already answers it or most of it, or recent primary studies "
    "already settle it.\n"
    "- 'dead': it may be new, but the review is unlikely to produce a useful answer, for "
    "example because the data it needs are rarely reported, or because one likely result "
    "(such as 'rates are low') would change no practice and leave nothing to discuss.\n"
    "- 'uncertain': the abstracts are not enough to tell. Say exactly what a person must check.\n"
    "Be sceptical. When in doubt between novel and uncertain, choose uncertain."
)


@dataclass
class Evidence:
    id: str  # R1.. for reviews, S1.. for primary studies (our labels for the model)
    pmid: str
    title: str
    journal: str
    year: Optional[int]
    kind: str  # "review" | "primary study"
    publication_types: tuple[str, ...] = ()
    overlap: str = ""
    why: str = ""

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


@dataclass
class NoveltyCheck:
    title: str
    verdict: str
    editor_view: str
    adds: str
    worth_answering: str
    suggested_change: str
    closest_pmid: str
    papers: list[Evidence] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict in (NOVEL, UNCERTAIN)

    def ranked(self) -> list[Evidence]:
        """Papers by overlap, closest first, the named closest at the top."""
        order = {"same question": 0, "large": 1, "partial": 2, "background only": 3, "": 4}
        return sorted(self.papers, key=lambda e: (e.pmid != self.closest_pmid,
                                                  order.get(e.overlap, 4)))

    def as_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _closest(pubmed: Any, title: str, query: str, *, kind: str, n: int,
             since: Optional[int], pool: int = 40) -> list[Paper]:
    filt = FILTER_REVIEWS if kind == "review" else FILTER_STUDIES
    joiner = " AND " if kind == "review" else " "
    pmids = pubmed.search_pmids(f"({query}){joiner}{filt}", retmax=pool, sort="relevance",
                                min_year=since)
    papers = pubmed.fetch_details(pmids)
    key = match_key(title)
    rank = {pmid: i for i, pmid in enumerate(pmids)}
    scored = sorted(papers, key=lambda p: (-round(similarity(key, match_key(p.title)), 2),
                                           rank.get(p.pmid, 99)))
    return scored[:n]


def gather(pubmed: Any, assessment: Any, *, th: Any, today: date) -> list[tuple[Evidence, str]]:
    """(evidence, abstract) for the closest reviews and recent primary studies."""
    c = assessment.candidate
    out: list[tuple[Evidence, str]] = []
    seen: set[str] = set()
    for kind, label, n, since in (
            ("review", "R", th.novelty_reviews, today.year - th.review_years + 1),
            ("primary study", "S", th.novelty_primary, today.year - th.novelty_primary_years + 1)):
        i = 0
        for p in _closest(pubmed, c.title, c.pubmed_query, kind=kind, n=n, since=since):
            if p.pmid in seen:
                continue
            seen.add(p.pmid)
            i += 1
            out.append((Evidence(f"{label}{i}", p.pmid, p.title, p.journal,
                                 p.first_published_year or p.year, kind,
                                 tuple(p.publication_types)), p.abstract or ""))
    return out


def _prompt(assessment: Any, evidence: list[tuple[Evidence, str]], *, publication_type: str,
            context: str) -> str:
    c, k = assessment.candidate, assessment.counts
    pr = assessment.prospero
    prospero = "no check"
    if pr is not None:
        prospero = pr.verdict + "".join(
            f"\n  {m.registration_id}: {m.title}" for m in pr.matches[:3])
    lines = [f'Proposed {publication_type}: "{c.title}"', f"Why it was proposed: {c.rationale}",
             f"Its PubMed search: {c.pubmed_query}",
             f"Counts: {k.records_to_screen} records to screen, about {k.eligible_studies} "
             f"primary studies, {k.recent_reviews} systematic reviews in recent years.",
             f"PROSPERO: {prospero}", f"The team: {context}", "",
             "The closest papers in PubMed:"]
    for e, abstract in evidence:
        lines.append(f"\n[{e.id}] {e.kind}, {e.journal} {e.year or ''}, "
                     f"{', '.join(e.publication_types)}\nTitle: {e.title}\n"
                     f"Abstract: {(abstract or '(no abstract)')[:_ABSTRACT_CHARS]}")
    if not evidence:
        lines.append("(none found)")
    return "\n".join(lines)


def check(llm: Any, pubmed: Any, assessment: Any, *, th: Any, publication_type: str,
          context: str, today: Optional[date] = None) -> NoveltyCheck:
    today = today or datetime.now(timezone.utc).date()
    c = assessment.candidate
    evidence = gather(pubmed, assessment, th=th, today=today)
    papers = [e for e, _ in evidence]
    try:
        d = llm.complete_json(_SYSTEM, _prompt(assessment, evidence,
                                               publication_type=publication_type,
                                               context=context), schema=NOVELTY_SCHEMA)
    except Exception as exc:  # noqa: BLE001  an unjudged question is "uncertain", never "novel"
        return NoveltyCheck(c.title, UNCERTAIN, "The novelty check could not run.", "", "",
                            "", "", papers, error=str(exc))
    by_id = {e.id: e for e in papers}
    for item in d.get("papers", []):
        e = by_id.get(str(item.get("id", "")).strip())
        if e is not None:
            e.overlap, e.why = str(item.get("overlap", "")), tidy(str(item.get("why", "")))
    closest = by_id.get(str(d.get("closest_id", "")).strip())
    verdict = str(d.get("verdict", UNCERTAIN))
    if verdict not in (NOVEL, NOT_NOVEL, UNCERTAIN, DEAD):
        verdict = UNCERTAIN
    if verdict == NOVEL and any(e.overlap == "same question" for e in papers):
        verdict = UNCERTAIN  # the model's own labels contradict "novel": a person decides
    return NoveltyCheck(
        c.title, verdict, _named(tidy(str(d.get("editor_view", ""))), papers),
        _named(tidy(str(d.get("adds", ""))), papers),
        _named(tidy(str(d.get("worth_answering", ""))), papers),
        _named(tidy(str(d.get("suggested_change", ""))), papers),
        closest.pmid if closest else "", papers)


def _named(text: str, papers: list[Evidence]) -> str:
    """Our R1 and S1 labels mean nothing to a reader: name the paper by PMID."""
    import re

    by_id = {e.id: e for e in papers}

    def name(m: re.Match) -> str:
        e = by_id.get(m.group(1))
        return f"PMID {e.pmid}" if e else m.group(0)

    return re.sub(r"\[?\b([RS]\d{1,2})\b\]?", name, text)


def screen(scored: list[Any], *, llm: Any, pubmed: Any, th: Any, publication_type: str,
           context: str, want: int, say: Callable[[str], None] = lambda _m: None
           ) -> tuple[list[Any], list[NoveltyCheck]]:
    """The first `want` questions (best score first) that pass, and every check made."""
    kept, checks = [], []
    for s in scored[:th.novelty_max_checks]:
        title = s.assessment.candidate.title
        say(f"  novelty check: {title}")
        nc = check(llm, pubmed, s.assessment, th=th, publication_type=publication_type,
                   context=context)
        checks.append(nc)
        say(f"    {nc.verdict}" + (f": {nc.editor_view[:160]}" if nc.editor_view else ""))
        if nc.passed:
            kept.append(s)
            if len(kept) == want:
                break
    return kept, checks
