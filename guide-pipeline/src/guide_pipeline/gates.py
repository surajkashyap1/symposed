"""Stage 4 — the gates (spec section 4). Hard rules in code, not model judgement.

Every gate records its outcome together with the numeric value it tested and
the threshold it used, so the verification screen and the database can show
exactly why a candidate passed or failed. All thresholds are settings.

Outcomes, strongest first: REJECT > DOWNGRADE > FLAG > PASS. A candidate
survives on PASS or FLAG (flags go to the human reviewer). DOWNGRADE means "not
enough for a systematic review, but may suit a scoping or narrative review".

The spec's heterogeneity gate needs abstracts, which triage never fetches, so it
runs after deep retrieval, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .prospero import ProsperoCheck
from .settings import Thresholds

PASS, FLAG, DOWNGRADE, REJECT = "pass", "flag", "downgrade", "reject"
_SEVERITY = {PASS: 0, FLAG: 1, DOWNGRADE: 2, REJECT: 3}

SYSTEMATIC = "systematic review"
LIGHTER_TYPES = ("scoping review", "narrative review", "literature review")


@dataclass(frozen=True)
class TriageCounts:
    """Stage 3 outputs: integers only (plus titles of any published protocols)."""

    records_to_screen: int  # the question's concepts, all publication types
    eligible_studies: int  # ...restricted to primary-study designs
    recent_reviews: int  # ...systematic reviews within the recency window
    trials_reporting_soon: Optional[int]  # None when the registry check failed
    # (pmid, title, similarity) of published protocols close to the title
    protocol_matches: list[tuple[str, str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class GateResult:
    name: str
    outcome: str
    value: Optional[float]
    threshold: Optional[float]
    detail: str


@dataclass(frozen=True)
class GateVerdict:
    outcome: str
    gates: list[GateResult]

    @property
    def passed(self) -> bool:
        return self.outcome in (PASS, FLAG)

    @property
    def reasons(self) -> list[str]:
        return [g.detail for g in self.gates if g.outcome != PASS]


def records_cap(thresholds: Thresholds, *, collaborators: int = 2) -> int:
    """Screening cap scaled to team size (dual screening needs at least two)."""
    return thresholds.max_records_to_screen * max(collaborators, 2) // 2


def _too_few(n: int, th: Thresholds, publication_type: str) -> GateResult:
    if publication_type in LIGHTER_TYPES:
        minimum = th.scoping_min_studies
        if n < minimum:
            return GateResult("too_few_studies", REJECT, n, minimum,
                              f"only {n} eligible studies (< {minimum})")
        return GateResult("too_few_studies", PASS, n, minimum, "")
    if n >= th.min_eligible_studies:
        return GateResult("too_few_studies", PASS, n, th.min_eligible_studies, "")
    if n >= th.scoping_min_studies:
        return GateResult(
            "too_few_studies", DOWNGRADE, n, th.min_eligible_studies,
            f"only {n} eligible studies (< {th.min_eligible_studies}) — too few to "
            "pool; consider a scoping or narrative review",
        )
    return GateResult("too_few_studies", REJECT, n, th.scoping_min_studies,
                      f"only {n} eligible studies (< {th.scoping_min_studies})")


def _registered(
    prospero: ProsperoCheck, published: list[tuple[str, str, float]], th: Thresholds
) -> GateResult:
    best_prospero = prospero.matches[0] if prospero.matches else None
    best_published = max(published, key=lambda p: p[2], default=None)
    scores = [m.score for m in [best_prospero] if m] + [p[2] for p in [best_published] if p]
    value = max(scores, default=0.0)
    # Name only the matches close enough to matter.
    notes = []
    if best_prospero and best_prospero.score >= th.prospero_review_similarity:
        notes.append(f"PROSPERO {best_prospero.registration_id} ({best_prospero.score:.2f})")
    if best_published and best_published[2] >= th.prospero_review_similarity:
        notes.append(f"published protocol PMID {best_published[0]} ({best_published[2]:.2f})")
    where = "; ".join(notes)
    if value >= th.prospero_reject_similarity:
        return GateResult("registered_protocol", REJECT, value, th.prospero_reject_similarity,
                          f"a registered or published protocol matches: {where}")
    if value >= th.prospero_review_similarity:
        return GateResult("registered_protocol", FLAG, value, th.prospero_review_similarity,
                          f"similar protocol(s) for human review: {where}")
    return GateResult("registered_protocol", PASS, value, th.prospero_review_similarity, "")


def apply_gates(
    counts: TriageCounts,
    prospero: ProsperoCheck,
    thresholds: Thresholds,
    *,
    publication_type: str = SYSTEMATIC,
    collaborators: int = 2,
) -> GateVerdict:
    th = thresholds
    cap = records_cap(th, collaborators=collaborators)
    gates = [_too_few(counts.eligible_studies, th, publication_type)]

    n = counts.records_to_screen
    gates.append(
        GateResult("too_many_records", REJECT, n, cap,
                   f"{n} records to screen (> {cap} for {max(collaborators, 2)} people)")
        if n > cap
        else GateResult("too_many_records", PASS, n, cap, "")
    )

    n = counts.recent_reviews
    gates.append(
        GateResult("already_reviewed", REJECT, n, 0,
                   f"{n} systematic review(s) on this question in the last "
                   f"{th.recent_review_years} years")
        if n > 0
        else GateResult("already_reviewed", PASS, n, 0, "")
    )

    gates.append(_registered(prospero, counts.protocol_matches, th))

    n = counts.trials_reporting_soon
    months = th.active_trial_completion_months
    if n is None:
        gates.append(GateResult("trials_reporting_soon", FLAG, None, 0,
                                "ongoing trials could not be checked — verify on "
                                "ClinicalTrials.gov"))
    elif n > 0:
        gates.append(GateResult("trials_reporting_soon", FLAG, n, 0,
                                f"{n} ongoing trial(s) due to complete within {months} "
                                "months could change the evidence"))
    else:
        gates.append(GateResult("trials_reporting_soon", PASS, n, 0, ""))

    outcome = max((g.outcome for g in gates), key=_SEVERITY.__getitem__)
    return GateVerdict(outcome=outcome, gates=gates)
