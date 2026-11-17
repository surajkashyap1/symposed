"""Step 4 of the update pipeline: what an update needs from the review's full text.

Samarth supplies the full text of every review that passed step 3 (no automatic
download). From each one the reader model (Sonnet 5.5, low effort) pulls out:
the date the search ended, the search strategy for each database exactly as
printed, the inclusion and exclusion criteria, how many studies were included,
and the list of included studies (for the recall test in step 7).

Rule 1 holds through quotes: the search date and the included count must each
come with the sentence they were read from, and code checks that the sentence
and every strategy really appear in the full text. Anything not found is
marked unverified, never silently trusted. A review whose strategy is not in
the text (often it sits in an online supplement) is marked so, and step 5
then builds a search from the criteria and says it did.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional

from ..llm import JsonCall, LLMClient, LLMError, run_many
from ..screening import CRITERIA_SCHEMA, Criteria
from ..sources.pubmed import Paper

_STR = {"type": "string"}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "search_end_as_written": _STR,
        "search_end_iso": _STR,
        "search_end_quote": _STR,
        "databases": {"type": "array", "items": _STR},
        "strategies": {"type": "array", "items": {
            "type": "object",
            "properties": {"database": _STR, "strategy": _STR},
            "required": ["database", "strategy"], "additionalProperties": False}},
        "criteria": CRITERIA_SCHEMA,
        "included_count": {"type": "integer"},
        "included_count_quote": _STR,
        "included_studies": {"type": "array", "items": {
            "type": "object",
            "properties": {"first_author": _STR, "year": _STR, "title": _STR},
            "required": ["first_author", "year", "title"], "additionalProperties": False}},
    },
    "required": ["search_end_as_written", "search_end_iso", "search_end_quote", "databases",
                 "strategies", "criteria", "included_count", "included_count_quote",
                 "included_studies"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You read a published systematic review and copy out exactly what an update of it "
    "needs. You never add anything the text does not say. You return ONLY JSON.\n\n"
    "- search_end_as_written: the date the literature search was last run, as the text "
    "words it (\"up to 14 March 2019\", \"inception to June 2018\"). Empty if not stated.\n"
    "- search_end_iso: that date as YYYY-MM-DD, or YYYY-MM when no day is given. Empty "
    "if not stated.\n"
    "- search_end_quote: the sentence it comes from, copied exactly.\n"
    "- databases: every database searched.\n"
    "- strategies: each full search strategy printed in the text, copied exactly, line "
    "for line, with the database it is for. Empty if the text gives no strategy (for "
    "example \"see supplementary appendix\").\n"
    "- criteria: the review's inclusion and exclusion criteria, in its own terms. Do not "
    "broaden or narrow them.\n"
    "- included_count: the number of studies included in the review, or -1 if not "
    "stated. included_count_quote: the sentence it comes from, copied exactly.\n"
    "- included_studies: every study the review included, from its tables or reference "
    "list: first author's surname, year, and title when the text gives it (else empty)."
)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def found_in(quote: str, text: str) -> bool:
    """True when the quote appears in the text, ignoring spacing and punctuation."""
    q = _norm(quote)
    return bool(q) and q in _norm(text)


def _iso(value: str) -> Optional[date]:
    m = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", value.strip())
    if not m:
        return None
    try:
        y, mo = int(m.group(1)), int(m.group(2))
        if m.group(3):
            return date(y, mo, int(m.group(3)))
        # Month only: the last day of that month, so nothing searched is counted twice.
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1)
    except ValueError:
        return None


@dataclass
class Strategy:
    database: str
    text: str
    verbatim: bool  # found word for word in the full text


@dataclass
class Extraction:
    """What step 4 read from one review, with how far each part is verified."""

    pmid: str
    basis: str                       # where the text came from
    search_end: Optional[date]
    search_end_as_written: str
    search_end_verified: bool
    search_end_estimated: bool       # no date in the text: the publication date is used
    databases: list[str]
    strategies: list[Strategy]
    criteria: Criteria
    included_count: Optional[int]
    included_count_verified: bool
    included_studies: list[dict]
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def medline_strategy(self) -> Optional[Strategy]:
        """The strategy for MEDLINE or PubMed, else the first one given."""
        for s in self.strategies:
            if re.search(r"medline|pubmed", s.database, re.I):
                return s
        return self.strategies[0] if self.strategies else None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["search_end"] = self.search_end.isoformat() if self.search_end else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Extraction":
        d = dict(d)
        d["search_end"] = date.fromisoformat(d["search_end"]) if d.get("search_end") else None
        d["strategies"] = [Strategy(**s) for s in d.get("strategies", [])]
        d["criteria"] = Criteria.from_dict(d.get("criteria", {}))
        return cls(**d)


# A printed strategy line: "12 exp Heart Failure/", "3 (HEART adj4 INFARCT$5).tw.",
# "#4 ... [tiab]", "15 or/1-14". Seen live (2026-10-25): the model missed a full Ovid
# strategy printed in a supplement appended to the PDF, so code finds them too.
_LINE = re.compile(r"^\s*#?\d{1,3}[.)]?\s+\S")
_SYNTAX = re.compile(r"\bexp\b|/\s*$|\.(tw|ti|ab|ti,ab|mp|pt|sh|jn|kw)\b|\badj\d|\bor/\d|"
                     r"\band/\d|\[(tiab|mh|mesh|pt|ti|tw)\]|\bMH\b|\bTI\b|\$\d?", re.IGNORECASE)
_DATABASE = re.compile(r"medline|pubmed|embase|cinahl|cochrane|central|web of science|"
                       r"psycinfo|scopus|ajol", re.IGNORECASE)


def find_strategy_blocks(text: str, *, min_lines: int = 5) -> list[tuple[str, str]]:
    """(database, block) for every printed line by line search strategy: at least
    `min_lines` consecutive numbered lines, most in database syntax. The database
    is read from the lines just above the block, else "not stated"."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if not _LINE.match(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and (_LINE.match(lines[j]) or not lines[j].strip()):
            j += 1
        block = [ln for ln in lines[i:j] if ln.strip()]
        if len(block) >= min_lines and sum(bool(_SYNTAX.search(ln)) for ln in block) >= len(block) // 2:
            above = " ".join(lines[max(0, i - 3):i])
            db = _DATABASE.findall(above)
            out.append((db[-1] if db else "not stated", "\n".join(ln.strip() for ln in block)))
        i = max(j, i + 1)
    return out


def _call(review: Paper, text: str) -> JsonCall:
    user = f"REVIEW: {review.title} (PMID {review.pmid})\n\nFULL TEXT:\n{text}"
    blocks = find_strategy_blocks(text)
    if blocks:
        user += ("\n\nNOTE: the text above contains these printed search strategies (often in a "
                 "supplement at the end). Copy each one into strategies:\n\n"
                 + "\n\n".join(f"[{db}]\n{b}" for db, b in blocks))
    return JsonCall(_SYSTEM, user, EXTRACT_SCHEMA, cache_system=True)


def _published(review: Paper) -> Optional[date]:
    year = review.first_published_year or review.year
    return date(year, 1, 1) if year else None


def read_extraction(review: Paper, text: str, basis: str, data: dict) -> Extraction:
    warnings: list[str] = []
    end = _iso(str(data.get("search_end_iso", "")))
    quote = str(data.get("search_end_quote", ""))
    end_ok = end is not None and found_in(quote, text)
    estimated = False
    if end is None:
        end, estimated = _published(review), True
        warnings.append("The full text gives no search end date: the publication date is "
                        "used instead, marked estimated.")
    elif not end_ok:
        warnings.append("The search end date's quote was not found in the full text: "
                        "check the date.")
    strategies = [Strategy(str(s.get("database", "")), str(s.get("strategy", "")),
                           found_in(str(s.get("strategy", "")), text))
                  for s in data.get("strategies", []) if str(s.get("strategy", "")).strip()]
    for db, block in find_strategy_blocks(text):
        # A printed strategy the model left out is added straight from the text.
        if not any(found_in(block[:200], s.text) for s in strategies):
            strategies.append(Strategy(db, block, True))
    for s in strategies:
        if not s.verbatim:
            warnings.append(f"The {s.database or 'search'} strategy was not found word for "
                            "word in the full text: check it against the review.")
    if not strategies:
        warnings.append("The full text has no search strategy (it may be in a supplement): "
                        "the search for new studies is built from the criteria.")
    n = data.get("included_count")
    n = n if isinstance(n, int) and n >= 0 else None
    n_ok = n is not None and found_in(str(data.get("included_count_quote", "")), text)
    if n is not None and not n_ok:
        warnings.append("The included study count's quote was not found in the full text.")
    studies = [{"first_author": str(s.get("first_author", "")).strip(),
                "year": str(s.get("year", "")).strip(), "title": str(s.get("title", "")).strip()}
               for s in data.get("included_studies", []) if s.get("first_author")]
    return Extraction(review.pmid, basis, end, str(data.get("search_end_as_written", "")),
                      end_ok, estimated, [str(x) for x in data.get("databases", [])], strategies,
                      Criteria.from_dict(data.get("criteria") or {}), n, n_ok, studies, warnings)


def extract_all(llm: LLMClient, items: list[tuple[Paper, str, str]]) -> list[Extraction]:
    """Read every (review, full text, basis) at once (one batch where possible)."""
    results = run_many(llm, [_call(r, t) for r, t, _ in items])
    out = []
    for (review, text, basis), data in zip(items, results):
        if isinstance(data, LLMError):
            out.append(Extraction(review.pmid, basis, _published(review), "", False, True, [],
                                  [], Criteria("", "", "", "", ""), None, False, [],
                                  [f"Could not read the full text: {data}"], str(data)))
        else:
            out.append(read_extraction(review, text, basis, data))
    return out
