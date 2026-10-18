"""Two alternative questions, delivered with every guide (guide v2, step 4).

Each guide is written for the top question, with a shortlist page offering two
alternatives the user can switch to within 30 days for £5. The alternatives are
the next best scored questions that passed the gates (and, in review led mode,
did not fail a final check). They get a quick title level check only: the gates
and the PROSPERO check already run for every candidate. A swap re-runs those
checks before the full guide is written (`swap` command), because the date on
the shortlist will be weeks old by then.

Everything shown is factual (PubMed counts and the PROSPERO check from this
run) except the PICO, which is drafted by the same criteria writer as the main
question.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .plain import tidy
from .screening import Criteria, write_criteria

SWAP_PRICE = "£5"
HOLD_DAYS = 30


@dataclass
class Alternative:
    number: int
    title: str
    axis: str
    rationale: str
    why_novel: str
    eligible_estimate: int
    records_to_screen: int
    search_query: str
    search_count: int
    prospero_checked_on: str
    prospero_verdict: str
    trials_query: str = ""
    pico: list[list[str]] = field(default_factory=list)
    brief: str = ""  # shortlist only: what the project is, in plain words
    scope: list[list[str]] = field(default_factory=list)  # what is in and out
    novelty: dict = field(default_factory=dict)  # shortlist only: novelty.NoveltyCheck.as_dict()

    def as_dict(self) -> dict:
        return asdict(self)


def pick(initial: list[Any], *, winner_title: str, exclude: set[str], n: int = 2) -> list[Any]:
    """The next best scored questions after the winner (assessments, best first)."""
    out = []
    for s in initial:
        title = s.assessment.candidate.title
        if title == winner_title or title in exclude:
            continue
        out.append(s.assessment)
        if len(out) == n:
            break
    return out


def why_novel(a: Any, *, review_years: int) -> str:
    """Plain, factual: what the novelty checks found on the day."""
    k, p = a.counts, a.prospero
    date = p.checked_on.strftime("%d/%m/%Y") if p else "the date of this guide"
    reviews = ("no recent systematic review" if k.recent_reviews == 0 else
               f"{k.recent_reviews} recent systematic review"
               f"{'s' if k.recent_reviews != 1 else ''} on the wider topic, none matching "
               "this exact question")
    if p is None or not p.matches:
        reg = "no similar registered protocol on PROSPERO"
    elif p.verdict == "clear":
        reg = "no close match on PROSPERO"
    else:
        top = p.matches[0]
        reg = (f"a related PROSPERO registration ({top.registration_id}) that we judged "
               "different but you should read")
    return (f"On {date} we found {reviews} in PubMed (last {review_years} years) and {reg}.")


def scope_rows(crit: Optional[Criteria], a: Any, *, publication_type: str) -> list[list[str]]:
    """What the review would cover beyond its PICO: type, setting, size, in and out."""
    k = a.counts
    rows = [["Type of review", publication_type[:1].upper() + publication_type[1:]]]
    if crit and crit.setting:
        rows.append(["Setting", tidy(crit.setting)])
    rows.append(["Size", f"About {k.eligible_studies} studies likely to fit, from about "
                          f"{k.records_to_screen} search results to screen"])
    if crit and crit.other_inclusion:
        rows.append(["Also included", tidy(". ".join(crit.other_inclusion))])
    if crit and crit.exclusion:
        rows.append(["Left out", tidy(". ".join(crit.exclusion))])
    return rows


def build(assessments: list[Any], *, criteria_llm: Any, publication_type: str,
          review_years: int) -> list[Alternative]:
    out = []
    for i, a in enumerate(assessments, 1):
        c = a.candidate
        try:
            crit: Optional[Criteria] = write_criteria(criteria_llm, c.title,
                                                      publication_type=publication_type)
        except Exception:  # noqa: BLE001  a missing PICO never blocks the guide
            crit = None
        pico = ([[k, tidy(v)] for k, v in (
            ("Population", crit.population),
            ("Intervention or exposure", crit.intervention_or_exposure),
            ("Comparator", crit.comparator), ("Outcomes", crit.outcomes),
            ("Study designs", crit.study_designs)) if v] if crit else [])
        out.append(Alternative(
            number=i, title=c.title, axis=c.axis, rationale=tidy(c.rationale),
            why_novel=why_novel(a, review_years=review_years),
            eligible_estimate=a.counts.eligible_studies,
            records_to_screen=a.counts.records_to_screen,
            search_query=c.pubmed_query, search_count=a.counts.records_to_screen,
            prospero_checked_on=(a.prospero.checked_on.strftime("%d/%m/%Y")
                                 if a.prospero else ""),
            prospero_verdict=a.prospero.verdict if a.prospero else "",
            trials_query=c.trials_query, pico=pico,
            scope=scope_rows(crit, a, publication_type=publication_type)))
    return out
