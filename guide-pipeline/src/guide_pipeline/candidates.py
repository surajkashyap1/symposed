"""Step 3 — candidate review titles and feasibility gates.

The LLM proposes a batch of candidate review questions, each filling one of the
build spec's 14 gap axes (superseded review, indirect comparison, ...). It supplies
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
    batch: int = 1  # which generation batch produced this candidate


@dataclass(frozen=True)
class ScreenResult:
    assessments: list[CandidateAssessment]  # every candidate from every batch
    survivors: list[CandidateAssessment]  # passed gates, ranked best-first
    top: Optional[CandidateAssessment]
    batches: int = 1  # how many batches were generated


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
        "pubmed_query must find PRIMARY studies (not reviews) answering that question. "
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
        "pubmed_query must find PRIMARY studies (not reviews) answering that question. "
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
    batch: int = 1,
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
        batch=batch,
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
    """End to end: generate, count + gate, rank — batch by batch (spec §1.2).

    Every candidate in a batch is evaluated (counts are cheap). If none passes,
    a new batch is generated with every rejected title passed back as negative
    context; once any candidate passes, no further batches are generated.
    """
    assessments: list[CandidateAssessment] = []
    batches = 0
    while batches < thresholds.max_candidate_batches:
        batches += 1
        rejected = tuple(a.candidate.title for a in assessments if not a.gate.passed)
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
                c,
                thresholds,
                current_year=current_year,
                batch=batches,
            )
            for c in candidates
        ]
        assessments.extend(batch)
        if any(a.gate.passed for a in batch):
            break

    survivors = rank_survivors(assessments)
    return ScreenResult(
        assessments=assessments,
        survivors=survivors,
        top=survivors[0] if survivors else None,
        batches=batches,
    )
