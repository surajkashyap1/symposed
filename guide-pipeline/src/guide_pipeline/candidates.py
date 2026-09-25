"""Stages 2-4 — candidate review titles, count-only triage, and the gates.

The LLM proposes a batch of candidate review questions, each filling one of the
build spec's 14 gap axes (superseded review, indirect comparison, ...). It supplies
*only* the question, the axis, and a PubMed query for the question's CONCEPTS —
never any counts, PMIDs or claims about how much exists (CLAUDE.md rule 1), and
never publication-type filters: those are applied here, in code, so the three
triage counts (spec Stage 3) all derive from one concept query:

  records to screen  = concepts, all publication types
  eligible studies   = concepts, primary-study designs only
  recent reviews     = concepts, systematic reviews within the recency window

Triage never fetches abstracts. The gates themselves live in `gates.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from .gates import DOWNGRADE, SYSTEMATIC, GateVerdict, TriageCounts, apply_gates
from .landscape import FILTER_SYSTEMATIC_REVIEW, Landscape
from .llm import LLMClient, LLMError
from .prospero import ProsperoCheck, ProsperoMirror, check_title, match_key, similarity
from .settings import Thresholds
from .sources.clinicaltrials import ACTIVE_STATUSES, ClinicalTrialsClient
from .sources.pubmed import PubMedClient

# Design filter for "plausible eligible studies": drop publication types that
# are not primary studies.
FILTER_PRIMARY = (
    'NOT (review[pt] OR systematic[sb] OR "meta-analysis"[pt] OR editorial[pt] '
    'OR letter[pt] OR comment[pt] OR news[pt] OR "case reports"[pt])'
)
# Published review protocols (the spec's "published protocols via PubMed").
FILTER_PROTOCOL = (
    '(protocol[ti] AND (systematic[tiab] OR "scoping review"[tiab] OR meta-analys*[tiab]))'
)
_PROTOCOL_TITLES = 20  # most recent protocol titles fuzzy-matched per candidate

_FIELD_TAG_RE = re.compile(r"\[[^\]]*\]")
_BOOLEAN_RE = re.compile(r"\b(AND|OR|NOT)\b")


def plain_terms(query: str) -> str:
    """Strip PubMed field tags/booleans to bare keywords for ClinicalTrials.gov.

    ClinicalTrials.gov's query.term rejects PubMed syntax like `[MeSH Terms]`, so a
    PubMed query must be reduced to plain keywords before it is used there.
    """
    text = _FIELD_TAG_RE.sub(" ", query)
    text = _BOOLEAN_RE.sub(" ", text)
    text = text.replace('"', " ").replace("(", " ").replace(")", " ")
    return " ".join(text.split())

# The 14 gap-finding axes from the build spec (Stage 2). Each names a *kind of
# gap* in the evidence, not merely a dimension to vary — so candidates are
# questions nobody has answered yet, not restatements of the topic.
AXES: dict[str, str] = {
    "Unexamined subgroup": "A population studied within larger trials but never "
    "analysed separately: elderly, paediatric, pregnant, renal impairment, a "
    "comorbidity cluster.",
    "Unpooled outcome": "An outcome measured in primary studies but never "
    "synthesised: quality of life, length of stay, cost, patient reported "
    "outcomes, readmission.",
    "Superseded review": "An existing review whose search predates a guideline "
    "change, a new agent, a new device, or a large trial published since.",
    "Indirect comparison": "Two interventions compared with placebo but never "
    "head to head.",
    "Methodological gap": "A prior review that excluded a study design, restricted "
    "language, omitted grey literature, or left heterogeneity unresolved.",
    "Setting transfer": "Evidence established in one setting but never synthesised "
    "in another: primary versus secondary care, high versus low resource, "
    "emergency versus elective.",
    "Diagnostic accuracy": "A test in wide clinical use whose accuracy has never "
    "been pooled, or pooled only against a superseded reference standard.",
    "Prognostic factor": "A predictor repeatedly reported across cohorts but never "
    "systematically synthesised.",
    "Timing or dose": "Early versus late, short versus long course, high versus "
    "low dose, duration of therapy.",
    "Delivery model": "The same intervention delivered differently: nurse led, "
    "remote, group, digital, pharmacist led.",
    "Safety and harms": "A specific adverse effect reported inconsistently across "
    "studies of a common intervention.",
    "Emerging technology": "A recent technique or agent with enough primary "
    "studies to pool but no synthesis yet.",
    "Discordance": "Two or more existing reviews reaching conflicting conclusions.",
    "Guideline evidence gap": "A recommendation in a current guideline supported "
    "by weak or narrative evidence, never formally synthesised.",
}

# Spec: highest yield because the rationale is self evident to a reviewer.
# Generation is weighted toward these without excluding the others.
HIGH_YIELD_AXES = (
    "Superseded review",
    "Indirect comparison",
    "Emerging technology",
    "Discordance",
)

_AXIS_LOOKUP = {name.lower(): name for name in AXES}

_SYSTEM_PROMPT = (
    "You help clinicians scope a first systematic review or audit. "
    "You return ONLY valid JSON. You NEVER state how many papers exist, and you "
    "NEVER invent PMIDs, DOIs or citations — a separate program counts the "
    "literature. Each PubMed query you write captures only the question's "
    "concepts; the program adds publication-type filters itself."
)


@dataclass(frozen=True)
class Candidate:
    title: str
    axis: str
    pubmed_query: str
    trials_query: str = ""  # plain keywords for ClinicalTrials.gov (no field tags)
    rationale: str = ""


@dataclass(frozen=True)
class SearchRun:
    """One query sent during triage (spec: record every search run)."""

    source: str
    query: str
    result: int
    run_at: str  # ISO timestamp


@dataclass(frozen=True)
class CandidateAssessment:
    candidate: Candidate
    counts: TriageCounts
    verdict: GateVerdict
    prospero: ProsperoCheck
    searches: list[SearchRun]
    batch: int = 1  # which generation batch produced this candidate


@dataclass(frozen=True)
class ScreenResult:
    assessments: list[CandidateAssessment]  # every candidate from every batch
    survivors: list[CandidateAssessment]  # passed gates, ranked best-first
    top: Optional[CandidateAssessment]
    batches: int = 1  # how many batches were generated
    # too few studies for a systematic review, but may suit a scoping review
    downgraded: list[CandidateAssessment] = field(default_factory=list)


def normalise_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse spaces — for comparing titles."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())


def _match_axis(raw: str) -> Optional[str]:
    """The canonical spec axis name for a model-supplied axis, else None."""
    return _AXIS_LOOKUP.get(" ".join(raw.lower().split()))


def _build_prompt(
    topic: str,
    landscape: Optional[Landscape],
    min_n: int,
    max_n: int,
    min_axes: int,
    max_per_axis: int,
    avoid: tuple[str, ...],
) -> str:
    context = ""
    if landscape is not None:
        mesh = ", ".join(t.name for t in landscape.mesh_terms) or "none matched"
        context = (
            f"\nContext (already measured, do not restate as numbers): the topic maps "
            f"to MeSH terms [{mesh}] and has an established but not exhausted literature."
        )
    axes = "\n".join(f"- {name}: {desc}" for name, desc in AXES.items())
    # Without this the model tends to fill the whole batch from the high-yield
    # axes alone (4 axes x 2), which fails the distinct-axes rule.
    others = min_axes - len(HIGH_YIELD_AXES)
    mix = (
        f" At least {others} of the axes you use must be OUTSIDE that high-yield list."
        if others > 0
        else ""
    )
    avoid_block = ""
    if avoid:
        listed = "\n".join(f"- {t}" for t in avoid)
        avoid_block = (
            "\n\nThese titles were already proposed and rejected. Do NOT propose them "
            f"again or close rewordings of them — cover different ground:\n{listed}"
        )
    return (
        f'Topic: "{topic}".{context}\n\n'
        f"Propose between {min_n} and {max_n} candidate review titles. Each must be a "
        "specific, answerable review question that fills a GAP of one of these kinds "
        f"(its axis):\n{axes}\n\n"
        f"Rules: use at least {min_axes} DIFFERENT axes, and no more than "
        f"{max_per_axis} candidates from any single axis. Weight the batch toward "
        f"{', '.join(HIGH_YIELD_AXES)} — their rationale is self evident to a "
        f"reviewer — without excluding the others.{mix} Every question must be workable "
        "by at least two people (dual independent screening). The axis value must be "
        "one of the axis names above, spelled exactly."
        f"{avoid_block}\n\n"
        'Return JSON of the form {"candidates": [{"title": str, "axis": str, '
        '"pubmed_query": str, "trials_query": str, "rationale": str}]}. The '
        "pubmed_query is PubMed syntax for the question's CONCEPTS only (population or "
        "condition, intervention or exposure, and a comparator or outcome if central) — "
        "combine synonyms with OR, include a MeSH term where you are sure it exists, and "
        "add NO publication-type, study-design or date filters. "
        "The trials_query is plain keywords for ClinicalTrials.gov — NO field tags, "
        "quotes or boolean operators. The rationale says what gap the question fills."
    )


def _parse_candidates(
    data: dict,
    max_per_axis: int,
    avoid_keys: set[str],
    existing: tuple[Candidate, ...] = (),
) -> list[Candidate]:
    """Validate the model's batch: known axes only, a per-axis cap, no avoided titles.

    `existing` are candidates already accepted into this batch: they count
    toward the per-axis cap and their titles are not accepted twice.
    """
    raw = data.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise LLMError("LLM returned no candidates")

    candidates: list[Candidate] = []
    per_axis: dict[str, int] = {}
    avoid_keys = avoid_keys | {normalise_title(c.title) for c in existing}
    for c in existing:
        per_axis[c.axis] = per_axis.get(c.axis, 0) + 1
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        query = str(item.get("pubmed_query", "")).strip()
        if not title or not query:
            continue  # unusable without a title and a query to count
        axis = _match_axis(str(item.get("axis", "")))
        if axis is None:
            continue  # not one of the spec's 14 axes
        if normalise_title(title) in avoid_keys:
            continue  # previously rejected (or a duplicate) — never regenerate it
        avoid_keys.add(normalise_title(title))
        if per_axis.get(axis, 0) >= max_per_axis:
            continue
        per_axis[axis] = per_axis.get(axis, 0) + 1
        trials_query = str(item.get("trials_query", "")).strip() or plain_terms(query)
        candidates.append(
            Candidate(
                title=title,
                axis=axis,
                pubmed_query=query,
                trials_query=trials_query,
                rationale=str(item.get("rationale", "")).strip(),
            )
        )
    if not candidates:
        raise LLMError("LLM candidates were all malformed")
    return candidates


def _top_up_prompt(
    topic: str, have: list[Candidate], unused_axes: list[str], needed: int
) -> str:
    axes = "\n".join(f"- {name}: {AXES[name]}" for name in unused_axes)
    taken = "\n".join(f"- {c.title}" for c in have)
    return (
        f'Topic: "{topic}".\n\n'
        f"These candidate review titles already exist — do NOT repeat them:\n{taken}\n\n"
        f"Propose {needed} MORE candidate review titles, each from a DIFFERENT axis, "
        f"using ONLY these axes:\n{axes}\n\n"
        "Each must be a specific, answerable review question workable by at least two "
        "people. The axis value must be one of the axis names above, spelled exactly.\n\n"
        'Return JSON of the form {"candidates": [{"title": str, "axis": str, '
        '"pubmed_query": str, "trials_query": str, "rationale": str}]}. The '
        "pubmed_query is PubMed syntax for the question's CONCEPTS only (population or "
        "condition, intervention or exposure, and a comparator or outcome if central) — "
        "combine synonyms with OR, include a MeSH term where you are sure it exists, and "
        "add NO publication-type, study-design or date filters. "
        "The trials_query is plain keywords for ClinicalTrials.gov — NO field tags, "
        "quotes or boolean operators. The rationale says what gap the question fills."
    )


def generate_candidates(
    llm: LLMClient,
    topic: str,
    *,
    landscape: Optional[Landscape] = None,
    min_n: int = 8,
    max_n: int = 12,
    min_axes: int = 6,
    max_per_axis: int = 2,
    avoid: tuple[str, ...] | list[str] = (),
    top_ups: int = 2,
) -> list[Candidate]:
    """Ask the LLM for one batch of candidates spread across the spec's axes.

    The batch rules are enforced in code, not trusted to the model: unknown axes
    and avoided titles are dropped and each axis is capped at `max_per_axis`. A
    batch spanning fewer than `min_axes` axes keeps what it has and is topped up
    with candidates from the axes it has not used yet (models tend to cluster on
    the high-yield axes, and a full regeneration repeats the same shape).
    """
    avoid = tuple(avoid)
    avoid_keys = {normalise_title(t) for t in avoid}
    user = _build_prompt(topic, landscape, min_n, max_n, min_axes, max_per_axis, avoid)
    candidates = _parse_candidates(
        llm.complete_json(_SYSTEM_PROMPT, user), max_per_axis, avoid_keys
    )
    for _ in range(top_ups):
        used = {c.axis for c in candidates}
        if len(used) >= min_axes:
            break
        unused = [name for name in AXES if name not in used]
        needed = min_axes - len(used) + 1  # one spare, as some may be dropped
        try:
            extra = _parse_candidates(
                llm.complete_json(
                    _SYSTEM_PROMPT, _top_up_prompt(topic, candidates, unused, needed)
                ),
                max_per_axis,
                avoid_keys,
                existing=tuple(candidates),
            )
        except LLMError:
            continue  # an unusable top-up just uses one of the attempts
        candidates.extend(extra)

    distinct = len({c.axis for c in candidates})
    if distinct < min_axes:
        raise LLMError(
            f"LLM batch spanned only {distinct} distinct axes (need {min_axes})"
        )
    return candidates


def _published_protocols(
    pubmed: PubMedClient, candidate: Candidate, runs: list[SearchRun], stamp: str
) -> list[tuple[str, str, float]]:
    """Published protocols on the question's concepts, scored against the title."""
    query = f"({candidate.pubmed_query}) AND {FILTER_PROTOCOL}"
    n = pubmed.count(query)
    runs.append(SearchRun("PubMed", query, n, stamp))
    if n == 0:
        return []
    key = match_key(candidate.title)
    titles = pubmed.titles(pubmed.search_pmids(query, retmax=_PROTOCOL_TITLES))
    scored = [(pmid, t, round(similarity(key, match_key(t)), 3)) for pmid, t in titles]
    return sorted(scored, key=lambda p: p[2], reverse=True)


def assess_candidate(
    pubmed: PubMedClient,
    clinicaltrials: ClinicalTrialsClient,
    mirror: ProsperoMirror,
    candidate: Candidate,
    thresholds: Thresholds,
    *,
    mirror_max_age_days: int = 10,
    publication_type: str = SYSTEMATIC,
    collaborators: int = 2,
    today: Optional[date] = None,
    batch: int = 1,
) -> CandidateAssessment:
    """Stage 3 count-only triage for one candidate, then the Stage 4 gates."""
    today = today or datetime.now(timezone.utc).date()
    stamp = datetime.now(timezone.utc).isoformat()
    runs: list[SearchRun] = []

    def pm_count(query: str, **kw) -> int:
        n = pubmed.count(query, **kw)
        label = query if not kw else f"{query} [pub year >= {kw['min_year']}]"
        runs.append(SearchRun("PubMed", label, n, stamp))
        return n

    q = candidate.pubmed_query
    records = pm_count(q)
    eligible = pm_count(f"({q}) {FILTER_PRIMARY}")
    recent = pm_count(
        f"({q}) AND {FILTER_SYSTEMATIC_REVIEW}",
        min_year=today.year - thresholds.recent_review_years + 1,
    )
    protocols = _published_protocols(pubmed, candidate, runs, stamp)

    # Never fatal: one registry failing must not abort the whole screen.
    trials_q = candidate.trials_query or plain_terms(q)
    completes_by = today + timedelta(days=round(thresholds.active_trial_completion_months * 30.44))
    soon: Optional[int]
    try:
        soon = clinicaltrials.count(trials_q, statuses=ACTIVE_STATUSES, completes_by=completes_by)
        runs.append(SearchRun(
            "ClinicalTrials.gov",
            f"{trials_q} [active, completing by {completes_by}]", soon, stamp,
        ))
    except httpx.HTTPError:
        soon = None

    prospero = check_title(
        mirror,
        candidate.title,
        max_age_days=mirror_max_age_days,
        reject_threshold=thresholds.prospero_reject_similarity,
        review_threshold=thresholds.prospero_review_similarity,
        today=today,
    )
    counts = TriageCounts(
        records_to_screen=records,
        eligible_studies=eligible,
        recent_reviews=recent,
        trials_reporting_soon=soon,
        protocol_matches=protocols[:3],
    )
    verdict = apply_gates(
        counts, prospero, thresholds,
        publication_type=publication_type, collaborators=collaborators,
    )
    return CandidateAssessment(
        candidate=candidate,
        counts=counts,
        verdict=verdict,
        prospero=prospero,
        searches=runs,
        batch=batch,
    )


def rank_survivors(
    assessments: list[CandidateAssessment],
) -> list[CandidateAssessment]:
    """Passed candidates, most evidence first (Stage 4b scoring replaces this)."""
    survivors = [a for a in assessments if a.verdict.passed]
    return sorted(survivors, key=lambda a: a.counts.eligible_studies, reverse=True)


def screen_candidates(
    llm: LLMClient,
    pubmed: PubMedClient,
    clinicaltrials: ClinicalTrialsClient,
    mirror: ProsperoMirror,
    topic: str,
    thresholds: Thresholds,
    *,
    landscape: Optional[Landscape] = None,
    mirror_max_age_days: int = 10,
    publication_type: str = SYSTEMATIC,
    collaborators: int = 2,
    today: Optional[date] = None,
) -> ScreenResult:
    """End to end: generate, triage + gate, rank — batch by batch (spec §1.2).

    Refuses to start on a stale PROSPERO mirror, before any API is called.
    Every candidate in a batch is evaluated (counts are cheap). If none passes,
    a new batch is generated with every rejected title passed back as negative
    context; once any candidate passes, no further batches are generated.
    """
    mirror.ensure_fresh(max_age_days=mirror_max_age_days, today=today)
    assessments: list[CandidateAssessment] = []
    batches = 0
    while batches < thresholds.max_candidate_batches:
        batches += 1
        rejected = tuple(a.candidate.title for a in assessments if not a.verdict.passed)
        candidates = generate_candidates(
            llm,
            topic,
            landscape=landscape,
            min_n=thresholds.candidate_titles_min,
            max_n=thresholds.candidate_titles_max,
            min_axes=thresholds.candidate_min_axes,
            max_per_axis=thresholds.candidate_max_per_axis,
            avoid=rejected,
        )
        batch = [
            assess_candidate(
                pubmed,
                clinicaltrials,
                mirror,
                c,
                thresholds,
                mirror_max_age_days=mirror_max_age_days,
                publication_type=publication_type,
                collaborators=collaborators,
                today=today,
                batch=batches,
            )
            for c in candidates
        ]
        assessments.extend(batch)
        if any(a.verdict.passed for a in batch):
            break

    survivors = rank_survivors(assessments)
    return ScreenResult(
        assessments=assessments,
        survivors=survivors,
        top=survivors[0] if survivors else None,
        batches=batches,
        downgraded=[a for a in assessments if a.verdict.outcome == DOWNGRADE],
    )
