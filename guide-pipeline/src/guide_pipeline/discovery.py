"""Review led discovery: find questions in the gaps existing reviews leave.

Guide v2, step 3 (Suraj, 2026-10-17). Candidate questions come from reading the
closest existing reviews, not from the 14 axes alone:

  1. Topics. A concrete stated topic is used as it is, unless it has so many
     reviews that it is really a field. Otherwise the decider model proposes
     narrow topics one or two levels inside the specialty ("atrial
     fibrillation", not "cardiology"). Every topic gets real PubMed counts of
     reviews and primary studies over the last N years, and the topic with the
     fewest reviews (but enough primary studies) is tried first.
  2. Neighbouring reviews. The most relevant systematic and literature reviews
     on the topic from the last N years, at most `max_fulltexts` of them.
  3. Full texts. Open access reviews are fetched from Europe PMC, or as an open
     access PDF found through OpenAlex. The rest are requested from a person: the run stops with `AwaitingFullTexts`, listing
     each review and the file name to save it under. Running again resumes.
  4. Reading. The reader model reads each review: what it achieves, its
     limitations, the questions it opens and the gaps it names.
  5. Questions. The decider model turns those gaps into candidate questions,
     which go through the usual gates. If none survive because they are not
     new, the 14 axes are used as a lens to rework them. If the topic shows no
     real gap, the next topic is tried.

After scoring, `final_check` reads the 2 or 3 reviews closest to the chosen
title (another round of full texts) and asks the decider whether the question
is new, publishable as a review and realistic for this user.

Rule 1 holds throughout: every PMID, title and count comes from PubMed. The
model only reads what it is given and writes questions and judgements.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .candidates import (
    AXES,
    FILTER_PRIMARY,
    FOUND,
    FOUND_OTHER_TYPE,
    NEEDS_CONTACT,
    Candidate,
    CandidateAssessment,
    RequestPreferences,
    ScreenResult,
    _contact_reason,
    assess_candidate,
    generate_candidates,
    normalise_title,
    rank_survivors,
)
from .fulltext import LOCAL_SUFFIXES, extract_review_text, read_local_text
from .gates import DOWNGRADE
from .llm import LLMClient, LLMError
from .plain import tidy
from .prospero import match_key, similarity
from .settings import Thresholds
from .sources.pubmed import Paper, PubMedClient

FILTER_REVIEWS = '(systematic[sb] OR review[pt] OR "scoping review"[pt])'
GAP_AXIS = "Gap in existing reviews"
SHORTLIST = 3  # a main question plus two alternatives
SKIP_SUFFIX = ".skip"  # an empty <PMID>.skip file: "we could not get this one"
FETCHED_SUFFIX = ".oa.pdf"  # an open access PDF the run downloaded itself
MIN_READABLE_CHARS = 1000  # less text than this: a scanned PDF or an empty file


# -- pausing for full texts --------------------------------------------------------
@dataclass(frozen=True)
class ReviewRef:
    pmid: str
    title: str
    journal: str
    year: Optional[int]
    doi: str
    publication_types: tuple[str, ...]

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    @classmethod
    def from_paper(cls, p: Paper) -> "ReviewRef":
        return cls(p.pmid, p.title, p.journal, p.first_published_year or p.year,
                   p.doi or "", tuple(p.publication_types))


class AwaitingFullTexts(Exception):
    """The run needs full texts a person has to fetch. Run again once they are in."""

    def __init__(self, stage: str, missing: list[ReviewRef], folder: Path, request_path: Path):
        self.stage, self.missing, self.folder, self.request_path = (
            stage, missing, folder, request_path)
        super().__init__(f"{len(missing)} full text(s) needed for {stage}: see {request_path}")


class FullTextStore:
    """Full texts for one request: supplied files, Europe PMC open access, then an
    open access PDF found through OpenAlex. Anything else is asked of a person.

    A file only counts when text can be read from it: a scanned PDF (pictures of
    the pages) gives none, so the run asks for the text pasted into Word instead
    of quietly reading the abstract while calling it a full text.
    """

    def __init__(self, folder: Path, europepmc: Any = None, *, openalex: Any = None,
                 max_chars: int = 120_000, abstracts_ok: bool = False):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.europepmc = europepmc
        self.openalex = openalex
        self.max_chars = max_chars
        self.abstracts_ok = abstracts_ok  # treat every missing file as "not available"
        self._oa: dict[str, str] = {}
        self._read: dict[tuple[Path, float], str] = {}

    def _read_file(self, path: Path) -> str:
        key = (path, path.stat().st_mtime)
        if key not in self._read:
            try:
                self._read[key] = read_local_text(path).strip()
            except Exception:  # noqa: BLE001  a broken file is an unreadable file
                self._read[key] = ""
        return self._read[key]

    def _readable(self, path: Path) -> bool:
        return len(self._read_file(path)) >= MIN_READABLE_CHARS

    def _files(self, pmid: str) -> list[Path]:
        return [p for suffix in (*LOCAL_SUFFIXES, FETCHED_SUFFIX)
                if (p := self.folder / f"{pmid}{suffix}").exists()]

    def _local(self, pmid: str) -> Optional[Path]:
        """The first readable file for this review, else its .skip file, else None."""
        for p in self._files(pmid):
            if self._readable(p):
                return p
        skip = self.folder / f"{pmid}{SKIP_SUFFIX}"
        return skip if skip.exists() else None

    def unreadable(self, pmid: str) -> list[Path]:
        """Supplied files with no text in them (most often a scanned PDF)."""
        return [p for p in self._files(pmid) if not self._readable(p)]

    def _open_access(self, refs: list[ReviewRef]) -> None:
        todo = [r.pmid for r in refs if r.pmid not in self._oa]
        if not todo or self.europepmc is None:
            return
        try:
            self._oa.update(self.europepmc.open_access_pmcids(todo))
        except Exception:  # noqa: BLE001  open access is a bonus, never fatal
            pass

    def _fetch_open_pdf(self, ref: ReviewRef) -> None:
        """Save the open access PDF OpenAlex lists for this review, if one downloads
        and really is this review (its title words are on the first pages)."""
        if self.openalex is None or not ref.doi:
            return
        try:
            urls = self.openalex.open_access_pdf_urls(ref.doi)
        except Exception:  # noqa: BLE001  open access is a bonus, never fatal
            return
        path = self.folder / f"{ref.pmid}{FETCHED_SUFFIX}"
        for url in urls[:3]:
            try:
                body = self.openalex.download_pdf(url)
            except Exception:  # noqa: BLE001
                body = None
            if not body:
                continue
            path.write_bytes(body)
            if self._readable(path) and _same_paper(ref.title, self._read_file(path)):
                return
            path.unlink()

    def text(self, ref: ReviewRef) -> tuple[Optional[str], str]:
        """(text, basis). Text is None when only the abstract can be used."""
        local = self._local(ref.pmid)
        if local is not None and local.suffix != SKIP_SUFFIX:
            basis = ("full text (open access PDF)" if local.name.endswith(FETCHED_SUFFIX)
                     else f"full text (supplied {local.suffix[1:]})")
            return self._read_file(local)[: self.max_chars], basis
        pmcid = self._oa.get(ref.pmid)
        if pmcid and self.europepmc is not None:
            try:
                ft = extract_review_text(self.europepmc.full_text_xml(pmcid),
                                         max_chars=self.max_chars)
            except Exception:  # noqa: BLE001
                ft = None
            if ft is not None:
                return ft.text, "full text (Europe PMC open access)"
        return None, "abstract only"

    def _missing(self, refs: list[ReviewRef]) -> list[ReviewRef]:
        return [r for r in refs if self._local(r.pmid) is None and r.pmid not in self._oa]

    def require(self, refs: list[ReviewRef], *, stage: str) -> None:
        """Stop the run if any review still needs a person to fetch it."""
        self._open_access(refs)
        for r in self._missing(refs):
            self._fetch_open_pdf(r)
        missing = self._missing(refs)
        if missing and not self.abstracts_ok:
            path = self.write_request(stage, refs, missing)
            raise AwaitingFullTexts(stage, missing, self.folder, path)

    def write_request(self, stage: str, refs: list[ReviewRef], missing: list[ReviewRef]) -> Path:
        path = self.folder / "NEEDED.md"
        lines = [
            f"# Full texts needed ({stage})", "",
            f"Save each review below into `{self.folder}` as `<PMID>.docx`, `.pdf`, `.txt` "
            "or `.md` (pasting the text into a Word document is fine). If you cannot get "
            f"one, create an empty file `<PMID>{SKIP_SUFFIX}` and its abstract will be used.",
            "Then run the same command again: the run picks up where it stopped.", "",
            "| Save as | Review | Journal, year | Links |", "|---|---|---|---|",
        ]
        unreadable = []
        for r in missing:
            doi = f" · [DOI](https://doi.org/{r.doi})" if r.doi else ""
            bad = self.unreadable(r.pmid)
            if bad:
                unreadable.append((r, bad))
            note = f" (no text could be read from {', '.join(f'`{p.name}`' for p in bad)})" if bad else ""
            lines.append(f"| `{r.pmid}.docx`{note} | {r.title} | {r.journal}, {r.year or ''} | "
                         f"[PubMed]({r.url}){doi} |")
        if unreadable:
            lines += ["", "We could not read any text from the files marked above. They are "
                      "most likely scanned PDFs (pictures of the pages). Open the article, "
                      "copy its text into a Word document and save it as `<PMID>.docx` next "
                      "to the old file.", ""]
        have = [r for r in refs if r not in missing]
        if have:
            lines += ["", "Already available (open access or supplied):", ""]
            lines += [f"- {r.pmid}: {r.title}" for r in have]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def _same_paper(title: str, text: str) -> bool:
    """True when most of the title's words appear near the start of the text."""
    words = {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3}
    head = " ".join(re.findall(r"[a-z0-9]+", text[:8000].lower()))
    return not words or sum(w in head for w in words) / len(words) >= 0.6


# -- topics -------------------------------------------------------------------------
@dataclass
class TopicOption:
    name: str
    pubmed_query: str
    why: str = ""
    stated: bool = False  # the user's own topic
    reviews: int = 0  # reviews in the last N years (PubMed)
    primary: int = 0  # primary studies in the last N years (PubMed)
    usable: bool = True
    note: str = ""


_S = {"type": "string"}
TOPICS_SCHEMA = {
    "type": "object",
    "properties": {
        "stated_topic_query": _S,
        "topics": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": _S, "pubmed_query": _S, "why": _S},
            "required": ["name", "pubmed_query", "why"], "additionalProperties": False}},
    },
    "required": ["stated_topic_query", "topics"],
    "additionalProperties": False,
}
_DECIDER = (
    "You are a senior systematic reviewer helping a first-time researcher find a review "
    "question that is genuinely open and genuinely doable. You never state how many "
    "papers exist and never invent PMIDs, titles or citations: a separate program counts "
    "the literature. PubMed queries capture only the concepts; the program adds filters. "
    "You return ONLY JSON."
)


def _clean_name(name: str) -> str:
    """Drop any bracketed label the model adds, e.g. "(axis: emerging indication)"."""
    return re.sub(r"\s*\((?:axis|type|note|review)[^)]*\)", "", name, flags=re.I).strip()


def propose_topics(llm: LLMClient, *, stated: str, specialties: tuple[str, ...], context: str,
                   n: int, avoid: tuple[str, ...] = ()) -> tuple[str, list[TopicOption]]:
    where = ", ".join(specialties) or "any clinical specialty"
    ask = (
        f'The user stated this topic: "{stated}". First write a PubMed concept query for it '
        "exactly as stated (stated_topic_query). Then propose narrower topics inside it. "
        f'Every topic must stay within "{stated}": a narrower population, indication, '
        "outcome, comparison or setting of it, never a different subject."
        if stated.strip() else
        f"The user left the topic open. Their specialties: {where}. Set stated_topic_query "
        "to an empty string and propose topics inside these specialties."
    )
    user = (
        f"{ask}\n\nUser: {context}\n\n"
        f"Propose {n} candidate topics, each one or two levels inside the specialty: for "
        "example 'atrial fibrillation' rather than 'cardiology', 'tibial fractures' rather "
        "than 'orthopaedics', 'epilepsy in children' rather than 'paediatrics'. A topic is a "
        "condition, population, intervention or test area, not a full research question. "
        "Prefer topics where a small team could plausibly find an open review question. "
        "Give each a PubMed concept query (MeSH terms only where certain, plus title and "
        "abstract synonyms) and one sentence on why it suits this user. The name is the "
        "topic alone, with no labels, brackets or notes."
        + (f"\n\nDo not propose these again: {'; '.join(avoid)}" if avoid else "")
    )
    data = llm.complete_json(_DECIDER, user, schema=TOPICS_SCHEMA)
    topics = [TopicOption(_clean_name(str(t["name"])), str(t["pubmed_query"]).strip(),
                          tidy(str(t.get("why", ""))))
              for t in data.get("topics", []) if str(t.get("pubmed_query", "")).strip()]
    return str(data.get("stated_topic_query", "")).strip(), topics[:n]


def count_topic(pubmed: PubMedClient, t: TopicOption, *, since: int) -> TopicOption:
    t.reviews = pubmed.count(f"({t.pubmed_query}) AND {FILTER_REVIEWS}", min_year=since)
    t.primary = pubmed.count(f"({t.pubmed_query}) {FILTER_PRIMARY}", min_year=since)
    return t


def choose_topics(llm: LLMClient, pubmed: PubMedClient, *, stated: str,
                  prefs: RequestPreferences, th: Thresholds, today: date) -> list[TopicOption]:
    """Topics to try, in order. Fewest reviews first, among topics with enough
    primary studies and not so many reviews that it is really a whole field."""
    since = today.year - th.review_years + 1
    stated_query, proposed = propose_topics(
        llm, stated=stated, specialties=prefs.specialties, context=prefs.context,
        n=th.max_topics)
    for t in proposed:
        count_topic(pubmed, t, since=since)
        if t.primary < th.topic_min_primary:
            t.usable, t.note = False, f"only {t.primary} primary studies"
        elif t.reviews > th.topic_max_reviews:
            t.usable, t.note = False, f"{t.reviews} reviews: too broad"
    ranked = sorted((t for t in proposed if t.usable), key=lambda t: (t.reviews, -t.primary))
    if not ranked:
        # Every narrower topic is busier than the ceiling: still try the least
        # reviewed ones with enough primary studies (we only ever read the
        # closest few reviews), rather than giving up on a well studied field.
        busy = [t for t in proposed if t.primary >= th.topic_min_primary]
        for t in busy:
            t.usable, t.note = True, f"{t.reviews} reviews: busy, tried as the least reviewed"
        ranked = sorted(busy, key=lambda t: (t.reviews, -t.primary))
    out: list[TopicOption] = []
    rejected = [t for t in proposed if not t.usable]
    if stated.strip() and stated_query:
        own = count_topic(pubmed, TopicOption(stated.strip(), stated_query, stated=True),
                          since=since)
        if own.reviews <= th.topic_max_reviews and own.primary >= th.topic_min_primary:
            out.append(own)  # a concrete topic: start there
        else:
            own.usable = False
            own.note = (f"{own.reviews} reviews: too broad, so narrower topics inside it "
                        "come first" if own.reviews > th.topic_max_reviews
                        else f"only {own.primary} primary studies")
            rejected.insert(0, own)
    out += ranked
    return out + rejected  # unusable topics are kept for the record


# -- neighbouring reviews -----------------------------------------------------------
def neighbour_reviews(pubmed: PubMedClient, topic: str, query: str, *, n: int, since: int,
                      pool: int = 25) -> list[ReviewRef]:
    """The n reviews closest to the topic since `since`.

    PubMed's Best match alone can surface off-topic reviews when a query has a
    broad OR branch (seen live: a heart failure review for a COPD topic), so a
    larger Best match pool is re-ranked by similarity to the topic's name.
    """
    return closest_reviews(pubmed, topic, query, n=n, since=since, pool=pool)


def closest_reviews(pubmed: PubMedClient, title: str, query: str, *, n: int,
                    since: int, pool: int = 25) -> list[ReviewRef]:
    """The reviews closest to a final title: Best match pool, then title similarity."""
    pmids = pubmed.search_pmids(f"({query}) AND {FILTER_REVIEWS}", retmax=pool,
                                sort="relevance", min_year=since)
    papers = pubmed.fetch_details(pmids)
    key = match_key(title)
    rank = {pmid: i for i, pmid in enumerate(pmids)}
    scored = sorted(papers, key=lambda p: (-round(similarity(key, match_key(p.title)), 2),
                                           rank.get(p.pmid, 99)))
    return [ReviewRef.from_paper(p) for p in scored[:n]]


# -- reading ------------------------------------------------------------------------
@dataclass
class ReviewReading:
    pmid: str
    title: str
    basis: str
    achieves: str = ""
    limitations: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    search_to: str = ""  # how recent its search was, if stated
    error: str = ""


_SL = {"type": "array", "items": _S}
READING_SCHEMA = {
    "type": "object",
    "properties": {"achieves": _S, "limitations": _SL, "open_questions": _SL, "gaps": _SL,
                   "search_to": _S},
    "required": ["achieves", "limitations", "open_questions", "gaps", "search_to"],
    "additionalProperties": False,
}
_READER = (
    "You read one published review for a researcher looking for an open question near "
    "it. Use only the text given. Be concrete: name populations, interventions, outcomes, "
    "designs and settings. You return ONLY JSON."
)


def read_reviews(llm: LLMClient, refs: list[ReviewRef], store: FullTextStore, *,
                 abstracts: dict[str, str], concurrency: int = 4) -> list[ReviewReading]:
    def one(ref: ReviewRef) -> ReviewReading:
        text, basis = store.text(ref)
        if text is None:
            text = f"TITLE: {ref.title}\n\nABSTRACT: {abstracts.get(ref.pmid, '')}"
        user = (
            f"REVIEW ({basis}):\n{text}\n\n"
            "Report: achieves (two or three sentences on what it did and found), "
            "limitations (as the authors state them, plus any you see), open_questions "
            "(questions it raises but does not answer), gaps (evidence gaps it names or "
            "that its scope leaves open, each specific enough to become a review "
            "question), search_to (the date its search ended, or empty)."
        )
        try:
            d = llm.complete_json(_READER, user, schema=READING_SCHEMA)
        except LLMError as exc:
            return ReviewReading(ref.pmid, ref.title, basis, error=str(exc))
        return ReviewReading(ref.pmid, ref.title, basis, tidy(str(d.get("achieves", ""))),
                             [tidy(x) for x in d.get("limitations", [])],
                             [tidy(x) for x in d.get("open_questions", [])],
                             [tidy(x) for x in d.get("gaps", [])],
                             str(d.get("search_to", "")))

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return list(pool.map(one, refs))


def _readings_block(readings: list[ReviewReading]) -> str:
    out = []
    for i, r in enumerate(readings, 1):
        out.append(
            f"[R{i}] {r.title} (PMID {r.pmid}; read: {r.basis}; search to: "
            f"{r.search_to or 'not stated'})\n  Achieves: {r.achieves}\n"
            f"  Limitations: {' | '.join(r.limitations)}\n"
            f"  Open questions: {' | '.join(r.open_questions)}\n"
            f"  Gaps: {' | '.join(r.gaps)}")
    return "\n".join(out)


# -- questions from gaps ----------------------------------------------------------
GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "gap_found": {"type": "boolean"},
        "gap_summary": _S,
        "candidates": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": _S, "pubmed_query": _S, "trials_query": _S,
                           "rationale": _S, "from_reviews": _SL},
            "required": ["title", "pubmed_query", "trials_query", "rationale",
                         "from_reviews"],
            "additionalProperties": False}},
    },
    "required": ["gap_found", "gap_summary", "candidates"],
    "additionalProperties": False,
}


@dataclass
class GapResult:
    gap_found: bool
    summary: str
    candidates: list[Candidate]


_R_REF = re.compile(r"\[?\bR(\d+)\b\]?")


def _named_refs(text: str, readings: list[ReviewReading]) -> str:
    """Our internal R1, R2 labels mean nothing to a user: name the review instead."""
    def name(m: re.Match) -> str:
        i = int(m.group(1))
        return f"a review (PMID {readings[i - 1].pmid})" if 1 <= i <= len(readings) else "a review"
    out = _R_REF.sub(name, text)
    return out[0].upper() + out[1:] if out else out


def _candidate(d: dict, axis: str, readings: list[ReviewReading]) -> Optional[Candidate]:
    title, query = str(d.get("title", "")).strip(), str(d.get("pubmed_query", "")).strip()
    if not title or not query:
        return None
    refs = []
    for tag in d.get("from_reviews", []) or []:
        digits = "".join(ch for ch in str(tag) if ch.isdigit())
        if digits and 1 <= int(digits) <= len(readings):
            refs.append(f"PMID {readings[int(digits) - 1].pmid}")
    rationale = _named_refs(tidy(str(d.get("rationale", ""))), readings)
    if refs:
        rationale += f" (gap found in {', '.join(refs)})"
    return Candidate(title, axis, query, str(d.get("trials_query", "")).strip(), rationale)


def questions_from_gaps(llm: LLMClient, *, topic: TopicOption, readings: list[ReviewReading],
                        prefs: RequestPreferences, avoid: tuple[str, ...], n: int = 6
                        ) -> GapResult:
    user = (
        f"Topic: {topic.name}\nReview type the user wants: {prefs.publication_type}\n"
        f"User: {prefs.context}\n\n"
        f"The closest existing reviews from the last years, as read:\n"
        f"{_readings_block(readings)}\n\n"
        "Decide whether these reviews leave a real, specific gap that a new "
        f"{prefs.publication_type} could fill (gap_found), and summarise it in two or three "
        "plain sentences (gap_summary). If there is one, write up to "
        f"{n} candidate review questions that come naturally out of the gaps, limitations "
        "and open questions above. A good question is one the reviews themselves point "
        "to, not a forced variation. Each must be answerable from published primary "
        "studies by this user's team. Cite the reviews it comes from as R numbers "
        "in from_reviews only: the rationale is read by the user, so describe the reviews "
        "there in words and never write R numbers. For each, give a PubMed concept query and plain keywords for "
        "ClinicalTrials.gov (trials_query)."
        + (f"\n\nDo not repeat these questions: {'; '.join(avoid)}" if avoid else "")
    )
    d = llm.complete_json(_DECIDER, user, schema=GAP_SCHEMA)
    avoid_keys = {normalise_title(t) for t in avoid}
    cands = [c for c in (_candidate(x, GAP_AXIS, readings) for x in d.get("candidates", []))
             if c is not None and normalise_title(c.title) not in avoid_keys]
    return GapResult(bool(d.get("gap_found")) and bool(cands),
                     tidy(str(d.get("gap_summary", ""))), cands[:n])


LENS_SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": _S, "axis": {"type": "string", "enum": list(AXES)},
                       "pubmed_query": _S, "trials_query": _S, "rationale": _S,
                       "from_reviews": _SL},
        "required": ["title", "axis", "pubmed_query", "trials_query", "rationale",
                     "from_reviews"],
        "additionalProperties": False}}},
    "required": ["candidates"],
    "additionalProperties": False,
}


def axis_lens(llm: LLMClient, *, rejected: list[CandidateAssessment],
              readings: list[ReviewReading], prefs: RequestPreferences,
              avoid: tuple[str, ...], n: int = 4) -> list[Candidate]:
    """Rework questions that failed for lack of novelty through the 14 axes."""
    axes = "\n".join(f"- {k}: {v}" for k, v in AXES.items())
    failed = "\n".join(
        f"- {a.candidate.title} (failed: "
        f"{', '.join(g.name for g in a.verdict.gates if g.outcome == 'reject') or 'flagged'})"
        for a in rejected)
    user = (
        f"These questions came from gaps in existing reviews but did not pass our checks:\n"
        f"{failed}\n\nThe reviews they came from:\n{_readings_block(readings)}\n\n"
        f"Using these gap axes as a lens:\n{axes}\n\n"
        f"Write up to {n} reworked questions for a {prefs.publication_type} that keep the "
        "spirit of the gap but take a perspective that is more likely to be new (for "
        "example a subgroup, setting, outcome or comparison the reviews did not cover). "
        "Name the axis used. User: " + prefs.context
        + (f"\n\nDo not repeat: {'; '.join(avoid)}" if avoid else "")
    )
    d = llm.complete_json(_DECIDER, user, schema=LENS_SCHEMA)
    avoid_keys = {normalise_title(t) for t in avoid}
    out = [c for c in (_candidate(x, str(x.get("axis", GAP_AXIS)), readings)
                       for x in d.get("candidates", []))
           if c is not None and normalise_title(c.title) not in avoid_keys]
    return out[:n]


# -- the discovery loop -----------------------------------------------------------------
@dataclass
class TopicTrial:
    topic: TopicOption
    reviews: list[ReviewRef] = field(default_factory=list)
    readings: list[ReviewReading] = field(default_factory=list)
    gap_found: bool = False
    gap_summary: str = ""
    route: str = ""  # gaps | gaps+axes | axes (no reviews) | no gap

    def as_dict(self) -> dict:
        return {"topic": asdict(self.topic), "reviews": [asdict(r) for r in self.reviews],
                "readings": [asdict(r) for r in self.readings], "gap_found": self.gap_found,
                "gap_summary": self.gap_summary, "route": self.route}


@dataclass
class Discovery:
    topics: list[TopicOption]
    trials: list[TopicTrial]
    screen: ScreenResult

    def as_dict(self) -> dict:
        return {"topics": [asdict(t) for t in self.topics],
                "trials": [t.as_dict() for t in self.trials]}


def discover(
    *,
    llms: dict[str, LLMClient],
    pubmed: PubMedClient,
    clinicaltrials: Any,
    mirror: Any,
    store: FullTextStore,
    stated_topic: str,
    prefs: RequestPreferences,
    th: Thresholds,
    landscape: Any = None,
    mirror_max_age_days: int = 10,
    avoid_titles: tuple[str, ...] = (),
    today: Optional[date] = None,
    say: Callable[[str], None] = lambda _m: None,
) -> Discovery:
    """Topics -> neighbouring reviews -> gaps -> gated candidates (ScreenResult)."""
    today = today or datetime.now(timezone.utc).date()
    mirror.ensure_fresh(max_age_days=mirror_max_age_days, today=today)
    since = today.year - th.review_years + 1
    topics = choose_topics(llms["topic_generation"], pubmed, stated=stated_topic,
                           prefs=prefs, th=th, today=today)
    # The stated topic first (when concrete), then narrower topics, fewest reviews first.
    usable = [t for t in topics if t.usable]
    for t in topics:
        say(f"  topic {t.name!r}: {t.reviews} reviews, {t.primary} primary studies"
            f"{' (' + t.note + ')' if t.note else ''}")

    assessments: list[CandidateAssessment] = []
    trials: list[TopicTrial] = []

    def gate(cands: list[Candidate], batch: int) -> list[CandidateAssessment]:
        out = [assess_candidate(pubmed, clinicaltrials, mirror, c, th,
                                mirror_max_age_days=mirror_max_age_days,
                                publication_type=prefs.publication_type,
                                collaborators=prefs.collaborators, today=today, batch=batch)
               for c in cands]
        assessments.extend(out)
        return out

    def tried() -> tuple[str, ...]:
        return tuple(avoid_titles) + tuple(a.candidate.title for a in assessments)

    for i, topic in enumerate(usable, 1):
        trial = TopicTrial(topic)
        trials.append(trial)
        say(f"Topic {i}: {topic.name} ({topic.reviews} reviews in {th.review_years} years)")
        refs = neighbour_reviews(pubmed, topic.name, topic.pubmed_query, n=th.max_fulltexts,
                                 since=since)
        trial.reviews = refs
        if not refs:
            # No recent review at all: the gap is the whole topic. Generate with
            # the axes directly (nothing to read).
            trial.route, trial.gap_found = "axes (no reviews)", True
            trial.gap_summary = f"No review on {topic.name} in the last {th.review_years} years."
            batch = gate(generate_candidates(
                llms["candidate_generation"], topic.name, landscape=landscape,
                min_n=th.candidate_titles_min, max_n=th.candidate_titles_max,
                min_axes=th.candidate_min_axes, max_per_axis=th.candidate_max_per_axis,
                avoid=tried(), preferences=prefs, batch=i), i)
            if any(a.verdict.passed for a in batch):
                break
            continue
        store.require(refs, stage=f"reading the reviews on '{topic.name}'")
        abstracts = {p.pmid: p.abstract for p in pubmed.fetch_details([r.pmid for r in refs])}
        say(f"  reading {len(refs)} review(s)...")
        trial.readings = read_reviews(llms["review_reading"], refs, store, abstracts=abstracts)
        gaps = questions_from_gaps(llms["gap_candidates"], topic=topic,
                                   readings=trial.readings, prefs=prefs, avoid=tried())
        trial.gap_found, trial.gap_summary = gaps.gap_found, gaps.summary
        if not gaps.gap_found:
            trial.route = "no gap"
            say("  no real gap in these reviews: next topic")
            continue
        trial.route = "gaps"
        batch = gate(gaps.candidates, i)
        passed = sum(a.verdict.passed for a in batch)
        if passed >= SHORTLIST:
            break
        # Too few new enough as worded (the guide needs a main question and two
        # alternatives): use the axes as a lens on the same gaps. No new reviews.
        rejected = [a for a in batch if not a.verdict.passed]
        if rejected:
            say(f"  {passed} gap question(s) passed: reworking the rest through the axes")
            trial.route = "gaps+axes"
            lens = axis_lens(llms["axis_lens"], rejected=rejected, readings=trial.readings,
                             prefs=prefs, avoid=tried())
            passed += sum(a.verdict.passed for a in gate(lens, i))
        if 0 < passed < SHORTLIST:
            # Still short of two alternatives: one batch from the axes on the same
            # narrow topic, informed by the gaps (no new reviews to fetch).
            say(f"  {passed} passing: topping up the shortlist from the axes")
            try:
                extra = generate_candidates(
                    llms["candidate_generation"], f"{topic.name}. Known gaps: {gaps.summary}",
                    landscape=landscape, min_n=th.candidate_titles_min,
                    max_n=th.candidate_titles_max, min_axes=th.candidate_min_axes,
                    max_per_axis=th.candidate_max_per_axis, avoid=tried(),
                    preferences=prefs, batch=i)
                gate(extra, i)
            except LLMError as exc:
                say(f"  top up failed: {exc}")
        if passed:
            break

    survivors = rank_survivors(assessments)
    downgraded = sorted((a for a in assessments if a.verdict.outcome == DOWNGRADE),
                        key=lambda a: a.counts.eligible_studies, reverse=True)
    if survivors:
        outcome, top, reason = FOUND, survivors[0], ""
    elif downgraded and prefs.type_flexible:
        outcome, top, reason = FOUND_OTHER_TYPE, downgraded[0], ""
    else:
        outcome, top, reason = NEEDS_CONTACT, None, _contact_reason(prefs, downgraded)
    screen = ScreenResult(assessments=assessments, survivors=survivors, top=top,
                          batches=len(trials), downgraded=downgraded, outcome=outcome,
                          contact_reason=reason)
    return Discovery(topics, trials, screen)


# -- the final check ----------------------------------------------------------------
FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "novel": {"type": "boolean"}, "novel_reason": _S,
        "publishable": {"type": "boolean"}, "publishable_reason": _S,
        "realistic": {"type": "boolean"}, "realistic_reason": _S,
        "suggested_change": _S,
    },
    "required": ["novel", "novel_reason", "publishable", "publishable_reason", "realistic",
                 "realistic_reason", "suggested_change"],
    "additionalProperties": False,
}


@dataclass
class FinalCheck:
    title: str
    reviews: list[ReviewRef]
    readings: list[ReviewReading]
    novel: bool
    publishable: bool
    realistic: bool
    reasons: dict[str, str]
    suggested_change: str = ""

    @property
    def passed(self) -> bool:
        return self.novel and self.publishable and self.realistic

    def as_dict(self) -> dict:
        return {"title": self.title, "passed": self.passed, "novel": self.novel,
                "publishable": self.publishable, "realistic": self.realistic,
                "reasons": self.reasons, "suggested_change": self.suggested_change,
                "reviews": [asdict(r) for r in self.reviews],
                "readings": [asdict(r) for r in self.readings]}


def final_check(*, llms: dict[str, LLMClient], pubmed: PubMedClient, store: FullTextStore,
                assessment: CandidateAssessment, prefs: RequestPreferences, th: Thresholds,
                today: Optional[date] = None, say: Callable[[str], None] = lambda _m: None
                ) -> FinalCheck:
    today = today or datetime.now(timezone.utc).date()
    c = assessment.candidate
    refs = closest_reviews(pubmed, c.title, c.pubmed_query, n=th.final_check_reviews,
                           since=today.year - th.review_years + 1)
    if refs:
        store.require(refs, stage=f"the final check on '{c.title}'")
        abstracts = {p.pmid: p.abstract for p in pubmed.fetch_details([r.pmid for r in refs])}
        readings = read_reviews(llms["review_reading"], refs, store, abstracts=abstracts)
    else:
        readings = []
    k = assessment.counts
    user = (
        f'Proposed {prefs.publication_type}: "{c.title}"\nWhy: {c.rationale}\n'
        f"User: {prefs.context}\n"
        f"PubMed counts: {k.records_to_screen} records to screen, {k.eligible_studies} "
        f"primary studies, {k.recent_reviews} recent systematic reviews on the concepts. "
        f"PROSPERO check: {assessment.prospero.verdict if assessment.prospero else 'n/a'}.\n\n"
        "The closest existing reviews, as read:\n"
        f"{_readings_block(readings) if readings else '(none found)'}\n\n"
        "Judge three things strictly. novel: no review above (or in the counts) already "
        "answers this question in this population with this comparison. publishable: a "
        "journal would accept it as a review (a clear question, enough studies, a reason it "
        "matters now). realistic: this user's team can do it in their time. Give a reason "
        "for each, and if any fails, the smallest change to the question that would fix it."
    )
    d = llms["final_check"].complete_json(_DECIDER, user, schema=FINAL_SCHEMA)
    check = FinalCheck(c.title, refs, readings, bool(d.get("novel")), bool(d.get("publishable")),
                       bool(d.get("realistic")),
                       {k2: tidy(str(d.get(f"{k2}_reason", "")))
                        for k2 in ("novel", "publishable", "realistic")},
                       tidy(str(d.get("suggested_change", ""))))
    say(f"  final check: novel={check.novel} publishable={check.publishable} "
        f"realistic={check.realistic}")
    return check


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
