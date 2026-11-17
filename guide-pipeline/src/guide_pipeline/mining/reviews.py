"""Steps 2 and 3 of the update pipeline: topic terms, then reviews due an update.

Step 2. The topic from the proforma may hold one term or several, and the user
may also give a title idea of their own ("existingTitle"), searched as one more
term. Each term is searched on its own, as the user wrote it: PubMed maps a plain
term to its MeSH heading itself, so no search strategy is built (Samarth,
2026-10-25).

Step 3. At least `REVIEW_COUNT` (50) systematic reviews, most relevant first,
with two filters:
  1. published more than `REVIEW_MIN_AGE_YEARS` (3) years ago, by publication
     date (the search date is not used here);
  2. not already updated: no later systematic review repeats its work, and no
     update is registered on PROSPERO or OSF. Two PubMed checks on the review's
     title words, one with PubMed's systematic review filter and one with no
     filter (plus PubMed's similar articles), read as titles only and ranked by
     shared title terms; the closest 10 of each go to the overlap judge, with
     any registrations from the local mirrors.

Rule 1: every PMID, title, date and count comes from PubMed, Europe PMC or a
mirror. The model only judges the records it is shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from ..candidates import SearchRun
from ..llm import JsonCall, LLMClient, LLMError, run_many
from ..sources.pubmed import Paper
from .models import Question
from ..prospero.records import match_key, similarity
from .overlap import CLEAR, REJECTED, UNVERIFIED, OverlapVerdict

FILTER_SR = "systematic[sb]"
# Registered protocols are not reviews to update, and PubMed's systematic subset
# also holds guidelines and consensus statements (seen live: 7 of the first 50
# for "Cardiology"), which are not systematic reviews either.
NOT_PROTOCOL = ('NOT (protocol[ti] OR guideline[pt] OR "practice guideline"[pt] OR '
                '"consensus development conference"[pt] OR "consensus statement"[pt])')
_SPLIT = re.compile(r"[,;\n|]+")


def topic_terms(topic: str, existing_title: str = "") -> list[str]:
    """The proforma topic as separate search terms, in the order written, then the
    user's own title idea when they gave one (Samarth, 2026-10-25)."""
    terms = [t.strip() for t in _SPLIT.split(topic or "") if t.strip()]
    if (existing_title or "").strip():
        terms.append(existing_title.strip())
    seen: set[str] = set()
    return [t for t in terms if not (t.lower() in seen or seen.add(t.lower()))]


def looks_like_prose(topic: str) -> bool:
    """A topic written as sentences, not a list of terms (seen live 2026-10-30: a
    paragraph whose commas split it into phrases PubMed finds nothing for)."""
    return any(len(seg.split()) > 5 for seg in _SPLIT.split(topic or ""))


TERMS_SCHEMA = {
    "type": "object",
    "properties": {"terms": {"type": "array", "items": {"type": "string"}}},
    "required": ["terms"],
    "additionalProperties": False,
}
TERMS_SYSTEM = (
    "You turn a student's description of their research interests into short PubMed "
    "search terms. Return 3 to 8 terms, each 1 to 4 words, naming the topics they "
    "mention: conditions, treatments, services, populations or exposures. Use only "
    "topics they mention, add nothing new, and leave out framing and filler words. "
    "Return ONLY JSON: {\"terms\": [...]}."
)


def extract_topic_terms(llm: LLMClient, topic: str, existing_title: str = "") -> list[str]:
    """Search terms from a prose topic, then the user's own title idea if any."""
    data = llm.complete_json(TERMS_SYSTEM, f"Research interests:\n{topic}", schema=TERMS_SCHEMA)
    terms = [str(t).strip() for t in data.get("terms", []) if str(t).strip()][:8]
    return topic_terms("; ".join(terms), existing_title)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _minus_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 February
        return d.replace(year=d.year - years, day=28)


def citation(p: Paper) -> str:
    first = p.authors[0] if p.authors else "Anonymous"
    etal = " et al." if len(p.authors) > 1 else ""
    year = p.first_published_year or p.year or "n.d."
    return f"{first}{etal} ({year}). {p.title} {p.journal}. PMID {p.pmid}."


@dataclass
class Found:
    """Step 3's first filter: the reviews considered, with every search run."""

    terms: list[str]
    reviews: list[Paper]
    cutoff: date
    searches: list[SearchRun] = field(default_factory=list)
    found_by: dict[str, str] = field(default_factory=dict)  # pmid -> term


def find_reviews(pubmed: Any, terms: list[str], *, count: int, min_age_years: int,
                 today: Optional[date] = None) -> Found:
    """The `count` most relevant systematic reviews published before the cutoff.

    Each term is searched separately; the lists are merged by taking each
    term's next best review in turn, so every term is represented.
    """
    today = today or datetime.now(timezone.utc).date()
    cutoff = _minus_years(today, min_age_years)
    found = Found(terms, [], cutoff)
    lists: list[list[str]] = []
    for term in terms:
        q = f"({term}) AND {FILTER_SR} {NOT_PROTOCOL}"
        n, ids = pubmed.search_dated(q, datetype="pdat", maxdate=cutoff.strftime("%Y/%m/%d"),
                                     retmax=count, sort="relevance")
        found.searches.append(SearchRun("PubMed", f"{q} (published to {cutoff})", n, _now()))
        lists.append(ids)
    order: list[str] = []
    for rank in range(count):
        for term, ids in zip(terms, lists):
            if rank < len(ids) and ids[rank] not in found.found_by:
                found.found_by[ids[rank]] = term
                order.append(ids[rank])
    order = order[:count]
    papers = {p.pmid: p for p in pubmed.fetch_details(order)}
    found.reviews = [papers[i] for i in order if i in papers]
    return found


def sample_all_reviews(pubmed: Any, *, count: int, min_age_years: int, since_year: int,
                       seed: str, today: Optional[date] = None) -> Found:
    """A request with no topic (Samarth, 2026-10-27): `count` systematic reviews drawn
    at random from all of PubMed, published from `since_year` to the cutoff.

    Each month's reviews are counted, months are drawn in proportion to their
    count, and a random record is read from the drawn month, so every review in
    the window is equally likely. The draw is the same every time for the same
    `seed` (the run folder), so a resumed run checks the same reviews.
    """
    import random

    today = today or datetime.now(timezone.utc).date()
    cutoff = _minus_years(today, min_age_years)
    q = f"{FILTER_SR} {NOT_PROTOCOL}"
    found = Found([], [], cutoff)
    months: list[tuple[str, str, int]] = []
    y, m = since_year, 1
    while date(y, m, 1) <= cutoff:
        lo = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        hi = min(nxt - timedelta(days=1), cutoff)
        n, _ = pubmed.search_dated(q, datetype="pdat", mindate=lo.strftime("%Y/%m/%d"),
                                   maxdate=hi.strftime("%Y/%m/%d"), retmax=0)
        if n:
            months.append((lo.strftime("%Y/%m/%d"), hi.strftime("%Y/%m/%d"), n))
        y, m = nxt.year, nxt.month
    total = sum(n for *_, n in months)
    found.searches.append(SearchRun(
        "PubMed", f"{q} (published {since_year}/01/01 to {cutoff}, a random sample of "
        f"{count} drawn month by month)", total, _now()))
    rng = random.Random(seed)
    picked: list[str] = []
    tries = 0
    while months and len(picked) < count and tries < count * 5:
        tries += 1
        lo, hi, n = rng.choices(months, weights=[w for *_, w in months])[0]
        # PubMed lists at most the first 10,000 records of a search.
        _, ids = pubmed.search_dated(q, datetype="pdat", mindate=lo, maxdate=hi, retmax=1,
                                     retstart=rng.randrange(min(n, 9_999)), sort="pub_date")
        if ids and ids[0] not in found.found_by:
            found.found_by[ids[0]] = "the whole literature (no topic given)"
            picked.append(ids[0])
    papers = {p.pmid: p for p in pubmed.fetch_details(picked)}
    found.reviews = [papers[i] for i in picked if i in papers]
    return found


def sample_reviews(found: Found, *, min_age_years: int, size: int, seed: str,
                   today: Optional[date] = None) -> list[Paper]:
    """An optional narrowing of step 3: reviews certainly older than `min_age_years`
    (by publication year, since PubMed records here carry only the year), then a
    random sample of at most `size`, the same every time for the same `seed`."""
    import random

    today = today or datetime.now(timezone.utc).date()
    reviews = found.reviews
    if min_age_years:
        last_year = _minus_years(today, min_age_years).year - 1
        reviews = [p for p in reviews if (p.first_published_year or p.year or 9999) <= last_year]
    if size and len(reviews) > size:
        picked = set(random.Random(seed).sample(range(len(reviews)), size))
        reviews = [p for i, p in enumerate(reviews) if i in picked]
    return reviews




def title_search(review: Paper, *, words: int = 6, sr_filter: bool = True) -> str:
    """A PubMed search for later papers sharing the review's main title words,
    with PubMed's built-in systematic review filter or without any filter."""
    key = [w for w in match_key(review.title).split() if len(w) > 2][:words]
    terms = " AND ".join(f"{w}[tiab]" for w in key)
    if not terms:
        return ""
    return f"({terms}) AND {FILTER_SR}" if sr_filter else f"({terms})"


LATER_SEARCHED = 20   # later reviews read per search, most relevant first
LATER_SHOWN = 5       # of those, the closest by title go to the judge with abstracts
REGISTERED_SHOWN = 3  # closest PROSPERO and OSF registrations since the review, titles only
ABSTRACT_CHARS = 1500


def later_reviews(pubmed: Any, review: Paper, *, searched: int = LATER_SEARCHED,
                  shown: int = LATER_SHOWN) -> list[Paper]:
    """The later systematic reviews closest to this one, with their abstracts.

    One search (Samarth, 2026-10-27): the review's main title words with PubMed's
    systematic review filter, limited to papers published in or after the
    review's year. The `shown` closest by title are read in full (title and
    abstract), online and never saved.
    """
    year = review.first_published_year or review.year or 1900
    q = title_search(review, sr_filter=True)
    if not q:
        return []
    _, ids = pubmed.search_dated(q, datetype="pdat", mindate=f"{year}/01/01",
                                 retmax=searched, sort="relevance", store=False)
    ids = [i for i in dict.fromkeys(ids) if i.isdigit() and i != review.pmid]
    if not ids:
        return []
    key = match_key(review.title)
    summaries = [s for s in pubmed.summaries(ids, store=False) if (s["year"] or 0) >= year]
    summaries.sort(key=lambda s: (-similarity(key, match_key(s["title"])), s["pmid"]))
    closest = [s["pmid"] for s in summaries[:shown]]
    papers = {p.pmid: p for p in pubmed.fetch_details(closest, store=False)}
    return [papers[i] for i in closest if i in papers]


def registered_since(review: Paper, prospero: Any = None, osf: Any = None, *,
                     shown: int = REGISTERED_SHOWN) -> list[tuple[str, str, str]]:
    """(label, title, url) of the closest PROSPERO and OSF registrations made in or
    after the review's year, from the local mirrors only."""
    year = review.first_published_year or review.year or 1900
    out: list[tuple[str, str, str]] = []
    if prospero is not None:
        for m in prospero.search(review.title, limit=shown * 3):
            if m.registration_date and m.registration_date.year >= year:
                out.append((f"PROSPERO {m.registration_id}", m.title, m.url))
        out = out[:shown]
    if osf is not None:
        # The OSF copy ranks by shared words: re-rank by title similarity, as PROSPERO does.
        key = match_key(review.title)
        hits = [m for m in osf.search(review.title, limit=shown * 10)
                if m.date_registered and m.date_registered.year >= year]
        hits.sort(key=lambda m: -similarity(key, match_key(m.title)))
        out += [(f"OSF {m.id}", m.title, m.link) for m in hits[:shown]]
    return out


UPDATE_CHECK_SCHEMA = {
    "type": "object",
    "properties": {"already_updated": {"type": "boolean"}, "updated_by": {"type": "string"}},
    "required": ["already_updated", "updated_by"],
    "additionalProperties": False,
}

UPDATE_CHECK_SYSTEM = (
    "You decide whether a published systematic review has already been updated or "
    "repeated by a later record. A later record repeats it when an update of the review "
    "would repeat work already done: the later review or registered protocol answers the "
    "same question, a narrower question inside it, or a wider question that contains it. "
    "A registered protocol counts even though its review is still in progress. "
    "A record on a different population, intervention, comparator or outcome that the "
    "original does not cover does not repeat it. Reply ONLY with JSON: already_updated "
    "(true or false) and updated_by (the label of the record that repeats it, or an empty "
    "string). Give no explanation."
)


def _update_check_user(review: Paper, later: list[Paper],
                       registered: list[tuple[str, str, str]]) -> str:
    def short(text: str) -> str:
        text = text or "(no abstract)"
        return text if len(text) <= ABSTRACT_CHARS else text[:ABSTRACT_CHARS] + " ..."
    lines = [f"REVIEW (PMID {review.pmid}, {review.first_published_year or review.year}): "
             f"{review.title}", f"Abstract: {short(review.abstract)}", "", "LATER RECORDS:"]
    for p in later:
        lines += [f"[PMID {p.pmid}] {p.first_published_year or p.year}: {p.title}",
                  f"Abstract: {short(p.abstract)}", ""]
    for label, title, _ in registered:
        lines += [f"[{label}] registered protocol: {title}", ""]
    if not later and not registered:
        lines.append("(none found)")
    return "\n".join(lines)


def update_question(review: Paper) -> Question:
    return Question(f"update-{review.pmid}", f"An update of: {review.title}",
                    description=review.abstract or "", updates=citation(review))


@dataclass
class AlreadyCheck:
    """Step 3's second filter, for one review."""

    review: Paper
    verdict: OverlapVerdict
    later_found: int  # later reviews pooled before the closest were chosen

    @property
    def passes(self) -> bool:
        return not self.verdict.rejected


def check_already_updated(reviews: list[Paper], *, llm: LLMClient, pubmed: Any,
                          europepmc: Any = None, prospero: Any = None, osf: Any = None,
                          embedder: Any = None, index: Any = None, k: int = 30,
                          later_limit: int = LATER_SHOWN, judged_on: str = "",
                          store: Any = None, say=lambda _m: None) -> list[AlreadyCheck]:
    """Has each review already been updated or repeated? (Samarth, 2026-10-27)

    One SR filtered PubMed search per review, the closest later reviews read with
    their abstracts, plus the closest registrations from the local PROSPERO and OSF
    copies when they are in use. The judge (task update_check) gives a decision
    only, with no rationale. `europepmc`, `embedder`, `index` and `k` are unused.

    A review already judged in an earlier run keeps that verdict, read from `store`
    (Samarth, 2026-10-27: judgements already paid for are never redone). Only a
    review never judged, or whose check failed, goes to the judge."""
    done: dict[str, AlreadyCheck] = {}
    for r in reviews:
        prev = saved_verdict(store, r) if store is not None else None
        if prev is not None:
            done[r.pmid] = AlreadyCheck(r, prev, 0)
    todo = [r for r in reviews if r.pmid not in done]
    if done:
        say(f"  {len(done)} already judged in an earlier run: verdicts reused")
    calls, pools = [], []
    for i, r in enumerate(todo, 1):
        say(f"  later reviews for {i}/{len(todo)}: PMID {r.pmid}")
        later = later_reviews(pubmed, r, shown=later_limit)
        registered = registered_since(r, prospero, osf)
        calls.append(JsonCall(UPDATE_CHECK_SYSTEM, _update_check_user(r, later, registered),
                              UPDATE_CHECK_SCHEMA, cache_system=True))
        pools.append((later, registered))
    say(f"  judging {len(calls)} reviews...")
    model = getattr(llm, "model", "")
    out = []
    for r, (later, registered), res in zip(todo, pools, run_many(llm, calls) if calls else []):
        q = update_question(r)
        if isinstance(res, LLMError):
            v = OverlapVerdict(q, UNVERIFIED, "The update check failed. Check it by hand.",
                               [], model, judged_on, str(res))
        elif res.get("already_updated"):
            named = str(res.get("updated_by", "")).strip().strip("[]")
            hit = next((f"PMID {p.pmid} ({p.first_published_year or p.year}): {p.title}"
                        for p in later if named in (p.pmid, f"PMID {p.pmid}")), None)
            hit = hit or next((f"{label}: {title}" for label, title, _ in registered
                               if named == label), None)
            v = OverlapVerdict(q, REJECTED, "Already updated or repeated by "
                               + (hit or f"a record the judge named as {named or 'none'}"),
                               [], model, judged_on)
        else:
            v = OverlapVerdict(q, CLEAR, f"Not repeated by any of the {len(later)} closest "
                               f"later reviews or {len(registered)} registrations checked",
                               [], model, judged_on)
        out.append(AlreadyCheck(r, v, len(later)))
    fresh = {c.review.pmid: c for c in out}
    return [done.get(r.pmid) or fresh[r.pmid] for r in reviews]


def saved_verdict(store: Any, review: Paper) -> Optional[OverlapVerdict]:
    """The latest verdict an earlier run saved for this review, unless that check
    failed or was incomplete (those are judged again)."""
    rows = store.overlap_verdicts(update_question(review).key)
    if not rows or rows[-1]["status"] == UNVERIFIED:
        return None
    last = rows[-1]
    return OverlapVerdict(update_question(review), last["status"], last["reason"], [],
                          last["model"] or "", last["judged_at"])
