"""Step 3 — candidate review titles and feasibility gates.

The LLM proposes several candidate review questions that vary the topic along
different axes (population, intervention, outcome, setting, ...). It supplies
*only* the question, the axis, and a PubMed query for the primary studies that
would answer it — never any counts, PMIDs or claims about how much exists
(CLAUDE.md rule 1). This module then does the counting itself and applies the
feasibility gates, whose thresholds all come from `Thresholds` settings.

Gates that our three data sources can decide are applied automatically. Whether a
protocol is already registered (PROSPERO) stays a manual human check — surfaced
as a note, never auto-decided — because a human reviews every output and checks
PROSPERO before anything reaches a customer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from .landscape import FILTER_SYSTEMATIC_REVIEW, Landscape
from .llm import LLMClient, LLMError
from .settings import Thresholds
from .sources.clinicaltrials import ACTIVE_STATUSES, ClinicalTrialsClient
from .sources.pubmed import PubMedClient

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

# The axes along which a review question can be varied — passed to the model so
# its candidates spread across distinct angles rather than restating one idea.
AXES = (
    "population",
    "intervention",
    "comparator",
    "outcome",
    "study design",
    "care setting",
    "age group",
    "disease severity",
    "geography / health system",
    "time period",
    "sex / gender",
    "comorbidity",
    "dose / intensity",
    "mode of delivery",
)

_SYSTEM_PROMPT = (
    "You help clinicians scope a first systematic review or audit. "
    "You return ONLY valid JSON. You NEVER state how many papers exist, and you "
    "NEVER invent PMIDs, DOIs or citations — a separate program counts the "
    "literature. Each PubMed query you write must target PRIMARY studies that "
    "would answer the question, not existing reviews."
)


@dataclass(frozen=True)
class Candidate:
    title: str
    axis: str
    pubmed_query: str
    trials_query: str = ""  # plain keywords for ClinicalTrials.gov (no field tags)
    rationale: str = ""


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: list[str]  # rejection reasons; empty when passed


@dataclass(frozen=True)
class CandidateAssessment:
    candidate: Candidate
    eligible_studies: int
    recent_reviews: int
    active_trials: Optional[int]  # None when the trials check could not be run
    gate: GateResult
    manual_checks: list[str]


@dataclass(frozen=True)
class ScreenResult:
    assessments: list[CandidateAssessment]
    survivors: list[CandidateAssessment]  # passed gates, ranked best-first
    top: Optional[CandidateAssessment]


def generate_candidates(
    llm: LLMClient,
    topic: str,
    *,
    landscape: Optional[Landscape] = None,
    min_n: int = 8,
    max_n: int = 12,
) -> list[Candidate]:
    """Ask the LLM for candidate review questions across distinct axes."""
    context = ""
    if landscape is not None:
        mesh = ", ".join(t.name for t in landscape.mesh_terms) or "none matched"
        context = (
            f"\nContext (already measured, do not restate as numbers): the topic maps "
            f"to MeSH terms [{mesh}] and has an established but not exhausted literature."
        )
    user = (
        f'Topic: "{topic}".{context}\n\n'
        f"Propose between {min_n} and {max_n} candidate review titles. Each must be a "
        f"specific, answerable review question that varies the topic along a DISTINCT "
        f"axis from this list: {', '.join(AXES)}.\n\n"
        'Return JSON of the form {"candidates": [{"title": str, "axis": str, '
        '"pubmed_query": str, "trials_query": str, "rationale": str}]}. The '
        "pubmed_query must find PRIMARY studies (not reviews) answering that question. "
        "The trials_query is plain keywords for ClinicalTrials.gov — NO field tags, "
        "quotes or boolean operators."
    )
    data = llm.complete_json(_SYSTEM_PROMPT, user)
    raw = data.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise LLMError("LLM returned no candidates")

    candidates: list[Candidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        query = str(item.get("pubmed_query", "")).strip()
        if not title or not query:
            continue  # unusable without a title and a query to count
        trials_query = str(item.get("trials_query", "")).strip() or plain_terms(query)
        candidates.append(
            Candidate(
                title=title,
                axis=str(item.get("axis", "")).strip(),
                pubmed_query=query,
                trials_query=trials_query,
                rationale=str(item.get("rationale", "")).strip(),
            )
        )
    if not candidates:
        raise LLMError("LLM candidates were all malformed")
    return candidates


def apply_gates(
    eligible_studies: int, recent_reviews: int, thresholds: Thresholds
) -> GateResult:
    """Automatic feasibility gates (all thresholds are settings)."""
    reasons: list[str] = []
    if eligible_studies < thresholds.min_eligible_studies:
        reasons.append(
            f"only {eligible_studies} eligible studies "
            f"(< {thresholds.min_eligible_studies})"
        )
    if eligible_studies > thresholds.max_records_to_screen:
        reasons.append(
            f"{eligible_studies} records to screen "
            f"(> {thresholds.max_records_to_screen})"
        )
    if recent_reviews > 0:
        reasons.append(
            f"{recent_reviews} systematic review(s) in the last "
            f"{thresholds.recent_review_years} years"
        )
    return GateResult(passed=not reasons, reasons=reasons)


def assess_candidate(
    pubmed: PubMedClient,
    clinicaltrials: ClinicalTrialsClient,
    candidate: Candidate,
    thresholds: Thresholds,
    *,
    current_year: Optional[int] = None,
) -> CandidateAssessment:
    """Count the literature for one candidate and apply the gates."""
    current_year = current_year or datetime.now(timezone.utc).year
    eligible = pubmed.count(candidate.pubmed_query)
    recent_reviews = pubmed.count(
        f"({candidate.pubmed_query}) AND {FILTER_SYSTEMATIC_REVIEW}",
        min_year=current_year - thresholds.recent_review_years + 1,
    )
    # Advisory only (not a gate): a plain-keyword query, and never fatal — one
    # source failing on one candidate must not abort the whole screen.
    active_trials: Optional[int]
    try:
        active_trials = clinicaltrials.count(
            candidate.trials_query or plain_terms(candidate.pubmed_query),
            statuses=ACTIVE_STATUSES,
        )
    except httpx.HTTPError:
        active_trials = None

    gate = apply_gates(eligible, recent_reviews, thresholds)

    manual_checks = ["Check PROSPERO for a registered or ongoing protocol"]
    if active_trials is None:
        manual_checks.append("Trial check failed — verify ClinicalTrials.gov manually")
    elif active_trials > 0:
        manual_checks.append(
            f"{active_trials} trial(s) still running — confirm none report within "
            f"{thresholds.active_trial_completion_months} months"
        )
    return CandidateAssessment(
        candidate=candidate,
        eligible_studies=eligible,
        recent_reviews=recent_reviews,
        active_trials=active_trials,
        gate=gate,
        manual_checks=manual_checks,
    )


def rank_survivors(
    assessments: list[CandidateAssessment],
) -> list[CandidateAssessment]:
    """Passed candidates, most evidence first (still under the screening cap)."""
    survivors = [a for a in assessments if a.gate.passed]
    return sorted(survivors, key=lambda a: a.eligible_studies, reverse=True)


def screen_candidates(
    llm: LLMClient,
    pubmed: PubMedClient,
    clinicaltrials: ClinicalTrialsClient,
    topic: str,
    thresholds: Thresholds,
    *,
    landscape: Optional[Landscape] = None,
    current_year: Optional[int] = None,
) -> ScreenResult:
    """End to end: generate candidates, count + gate each, rank the survivors."""
    candidates = generate_candidates(
        llm,
        topic,
        landscape=landscape,
        min_n=thresholds.candidate_titles_min,
        max_n=thresholds.candidate_titles_max,
    )
    assessments = [
        assess_candidate(
            pubmed, clinicaltrials, c, thresholds, current_year=current_year
        )
        for c in candidates
    ]
    survivors = rank_survivors(assessments)
    return ScreenResult(
        assessments=assessments,
        survivors=survivors,
        top=survivors[0] if survivors else None,
    )
