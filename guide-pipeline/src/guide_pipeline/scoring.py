"""Stage 4b objective ranking, Stage 5 re-scoring, and Stage 5b tie break (spec §4).

Every candidate that cleared the gates gets six component scores in [0, 1], all
computed from API counts and the proforma, never model judgement:

  workable     eligible studies inside the workable band (default 12-40)
  recency      share of those studies published in the last 5 years
  rationale    a self-evident reason (the spec's high-yield axes) or a stated one
  alignment    how much of the user's topic or specialties the question covers
  feasibility  records to screen against the team's screening cap
  distance     1 - similarity to the nearest registered or published protocol

The total is the weighted mean (weights are settings). If the leader beats the
next by more than the margin it proceeds alone; otherwise up to `max_tied`
candidates proceed to deep retrieval, are re-scored on what retrieval found, and
only if still tied does the model choose (5b). The tie break selects a question,
never papers; it can never pick a candidate that failed a gate; its choice and
full rationale are stored, and a reviewer can override it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .candidates import HIGH_YIELD_AXES, CandidateAssessment, RequestPreferences
from .gates import records_cap
from .llm import LLMClient, LLMError
from .prospero import match_key
from .settings import Thresholds


@dataclass(frozen=True)
class ScoreWeights:
    workable: float = 1.0
    recency: float = 1.0
    rationale: float = 1.0
    alignment: float = 1.0
    feasibility: float = 1.0
    distance: float = 1.0

    @classmethod
    def from_env(cls) -> "ScoreWeights":
        """SCORE_WEIGHT_<COMPONENT> overrides, e.g. SCORE_WEIGHT_DISTANCE=2."""
        return cls(**{
            k: float(os.environ.get(f"SCORE_WEIGHT_{k.upper()}", v))
            for k, v in cls().__dict__.items()
        })


@dataclass(frozen=True)
class CandidateScore:
    assessment: CandidateAssessment
    components: dict[str, float]
    total: float
    eligible_basis: str = "triage count"  # or "screened (eligible + unclear)"

    def as_dict(self) -> dict:
        return {
            "title": self.assessment.candidate.title,
            "axis": self.assessment.candidate.axis,
            "total": self.total,
            "components": self.components,
            "eligible_basis": self.eligible_basis,
        }


def _workable(n: int, low: int, high: int, cap: int) -> float:
    if low <= n <= high:
        return 1.0
    if n < low:
        return round(max(0.0, n / low), 3)
    return round(max(0.0, 1 - (n - high) / max(1, cap - high)), 3)


def _alignment(title: str, preferences: RequestPreferences, topic: str) -> float:
    wanted = set(match_key(topic or " ".join(preferences.specialties)).split())
    if not wanted:
        return 1.0  # no stated preference to align with
    have = set(match_key(title).split())
    return round(len(wanted & have) / len(wanted), 3)


def score_candidate(
    a: CandidateAssessment,
    *,
    recent_share: float,
    preferences: RequestPreferences,
    topic: str,
    thresholds: Thresholds,
    weights: ScoreWeights,
    eligible: Optional[int] = None,
    eligible_basis: str = "triage count",
) -> CandidateScore:
    th = thresholds
    cap = records_cap(th, collaborators=preferences.collaborators)
    n = a.counts.eligible_studies if eligible is None else eligible
    registered = [a.prospero.matches[0].score] if a.prospero and a.prospero.matches else []
    published = [p[2] for p in a.counts.protocol_matches]
    nearest = max(registered + published + [0.0])
    rationale = (
        1.0 if a.candidate.axis in HIGH_YIELD_AXES
        else 0.5 if a.candidate.rationale.strip() else 0.0
    )
    components = {
        "workable": _workable(n, th.workable_min_studies, th.workable_max_studies, cap),
        "recency": round(min(1.0, max(0.0, recent_share)), 3),
        "rationale": rationale,
        "alignment": _alignment(a.candidate.title, preferences, topic),
        "feasibility": round(max(0.0, 1 - a.counts.records_to_screen / cap), 3),
        "distance": round(max(0.0, 1 - nearest), 3),
    }
    w = weights.__dict__
    total = sum(components[k] * w[k] for k in components) / (sum(w.values()) or 1.0)
    return CandidateScore(a, components, round(total, 4), eligible_basis)


def rank(scores: list[CandidateScore]) -> list[CandidateScore]:
    return sorted(scores, key=lambda s: s.total, reverse=True)


def tied_leaders(ranked: list[CandidateScore], *, margin: float, max_tied: int) -> list[CandidateScore]:
    """The leader alone if it wins clearly, else everyone within the margin (capped)."""
    if not ranked:
        return []
    top = ranked[0].total
    within = [s for s in ranked if top - s.total <= margin]
    return within[: max(1, max_tied)]


# -- Stage 5b ----------------------------------------------------------------------
TIE_BREAK_CRITERIA = (
    "Clinical usefulness: would answering it change what a clinician does, or inform "
    "a guideline or a real decision? Prefer a broader, clinically consequential "
    "question over one refining a marginal outcome in a narrow population, when "
    "feasibility is equal.",
    "Novelty as a journal would see it: can the contribution be stated in one "
    "sentence an editor would accept as new?",
    "Breadth of relevance: how many clinicians and patients does it touch?",
    "Question clarity: a single clean answerable question beats a compound or "
    "vaguely bounded one.",
    "Fit with the user's stated interests and capabilities.",
)
TIE_SCHEMA = {
    "type": "object",
    "properties": {
        "choice": {"type": "integer"},
        "rationale": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"criterion": {"type": "string"}, "assessment": {"type": "string"}},
                "required": ["criterion", "assessment"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["choice", "rationale", "summary"],
    "additionalProperties": False,
}


@dataclass
class TieBreak:
    candidates: list[str]  # tied titles, in the order shown to the model
    choice: int  # index into candidates
    rationale: list[dict]
    summary: str
    reviewer_override: Optional[int] = None  # set at human verification (Stage 6)
    override_reason: str = ""

    @property
    def final_choice(self) -> int:
        return self.choice if self.reviewer_override is None else self.reviewer_override

    def as_dict(self) -> dict:
        return {
            "candidates": self.candidates,
            "model_choice": self.choice,
            "rationale": self.rationale,
            "summary": self.summary,
            "reviewer_override": self.reviewer_override,
            "override_reason": self.override_reason,
            "final_choice": self.final_choice,
        }


def break_tie(
    llm: LLMClient,
    tied: list[tuple[CandidateScore, str]],
    *,
    preferences: RequestPreferences,
) -> TieBreak:
    """Model judgement between tied candidates that all passed the gates (5b).

    `tied` pairs each candidate's score with a plain summary of what deep
    retrieval found for it (counts and statuses only — nothing invented).
    """
    for s, _ in tied:
        if not s.assessment.verdict.passed:
            raise ValueError("a candidate that failed a gate can never be tie-broken in")
    blocks = []
    for i, (s, found) in enumerate(tied):
        c = s.assessment.candidate
        blocks.append(
            f"[{i}] {c.title}\n    axis: {c.axis}\n    rationale: {c.rationale}\n"
            f"    objective score: {s.total} {s.components}\n    retrieval found: {found}"
        )
    criteria = "\n".join(f"{n}. {t}" for n, t in enumerate(TIE_BREAK_CRITERIA, 1))
    user = (
        "These review questions all passed every gate and objective scoring cannot "
        "separate them. Choose the ONE to offer, judging these criteria in priority "
        f"order:\n{criteria}\n\n{preferences.context}\n\nCANDIDATES:\n"
        + "\n\n".join(blocks)
        + "\n\nReturn the chosen index, an assessment for each criterion, and a "
        "one-paragraph summary. You choose a question, never papers."
    )
    data = llm.complete_json(
        "You are a senior systematic reviewer and journal editor. You return ONLY JSON.",
        user,
        schema=TIE_SCHEMA,
    )
    choice = data.get("choice")
    if not isinstance(choice, int) or not 0 <= choice < len(tied):
        raise LLMError(f"tie break chose an invalid index: {choice!r}")
    return TieBreak(
        candidates=[s.assessment.candidate.title for s, _ in tied],
        choice=choice,
        rationale=list(data.get("rationale", [])),
        summary=str(data.get("summary", "")),
    )


@dataclass
class Selection:
    """Stages 4b-5b outcome, for the results file and the metrics."""

    initial: list[CandidateScore]
    tied: list[CandidateScore]
    rescored: list[CandidateScore] = field(default_factory=list)
    tie_break: Optional[TieBreak] = None
    winner: Optional[CandidateScore] = None

    def as_dict(self) -> dict:
        return {
            "initial_ranking": [s.as_dict() for s in self.initial],
            "tied": [s.assessment.candidate.title for s in self.tied],
            "rescored": [s.as_dict() for s in self.rescored],
            "tie_break": self.tie_break.as_dict() if self.tie_break else None,
            "winner": self.winner.assessment.candidate.title if self.winner else None,
            "unchosen": [s.assessment.candidate.title for s in self.initial
                         if self.winner is None
                         or s.assessment.candidate.title != self.winner.assessment.candidate.title],
        }


def rescore(score: CandidateScore, *, screened_eligible: int, **kw) -> CandidateScore:
    """Re-score with the eligible count deep retrieval actually found."""
    return score_candidate(score.assessment, eligible=screened_eligible,
                           eligible_basis="screened (eligible + unclear)", **kw)


