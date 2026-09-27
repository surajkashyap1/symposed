"""Stage 5 v2 — attribute extraction and full-recall screening (spec update).

For every retrieved paper the pipeline gives a graded, reasoned estimate of
eligibility against the review's own criteria:

  status          "likely eligible" | "likely ineligible" | "unclear, check full text"
  reason          why, naming the criterion
  evidence basis  what was read: the abstract, or open-access full text

This is never a decision and never a silent flag (rule 2): the status is always
shown with its reason and basis, as an estimate the user must verify. The aim is
recall — a paper is marked "likely ineligible" only when the text clearly shows
a criterion is not met; anything that cannot be confirmed is "unclear".

The model only reads text the APIs returned and reports what it says (rule 1):
attributes not stated are recorded as "not stated", and the year comes from the
PubMed record, not the model. Papers are screened independently, so one paper's
result never depends on which others were retrieved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import httpx

from .fulltext import extract_screening_text
from .llm import JsonCall, LLMClient, LLMError, run_many
from .sources.europepmc import EuropePmcClient
from .sources.pubmed import Paper

LIKELY_ELIGIBLE = "likely eligible"
LIKELY_INELIGIBLE = "likely ineligible"
UNCLEAR = "unclear, check full text"
STATUSES = (LIKELY_ELIGIBLE, UNCLEAR, LIKELY_INELIGIBLE)  # display order
ABSTRACT_BASIS = "abstract only"
NOT_ASSESSED = "not assessed"
NOT_STATED = "not stated"


# -- criteria -------------------------------------------------------------------
@dataclass(frozen=True)
class Criteria:
    """The review's own inclusion and exclusion criteria (PICO + design)."""

    population: str
    intervention_or_exposure: str
    comparator: str
    outcomes: str
    study_designs: str
    setting: str = ""
    other_inclusion: tuple[str, ...] = ()
    exclusion: tuple[str, ...] = ()

    def as_text(self) -> str:
        lines = [
            f"Population: {self.population}",
            f"Intervention or exposure: {self.intervention_or_exposure}",
            f"Comparator: {self.comparator}",
            f"Outcomes: {self.outcomes}",
            f"Study designs: {self.study_designs}",
        ]
        if self.setting:
            lines.append(f"Setting: {self.setting}")
        lines += [f"Also required: {c}" for c in self.other_inclusion]
        lines += [f"Exclude: {c}" for c in self.exclusion]
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> "Criteria":
        return cls(
            population=str(d.get("population", "")),
            intervention_or_exposure=str(d.get("intervention_or_exposure", "")),
            comparator=str(d.get("comparator", "")),
            outcomes=str(d.get("outcomes", "")),
            study_designs=str(d.get("study_designs", "")),
            setting=str(d.get("setting", "")),
            other_inclusion=tuple(str(x) for x in d.get("other_inclusion", []) or []),
            exclusion=tuple(str(x) for x in d.get("exclusion", []) or []),
        )


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
CRITERIA_SCHEMA = {
    "type": "object",
    "properties": {
        "population": _STR,
        "intervention_or_exposure": _STR,
        "comparator": _STR,
        "outcomes": _STR,
        "study_designs": _STR,
        "setting": _STR,
        "other_inclusion": _STR_LIST,
        "exclusion": _STR_LIST,
    },
    "required": ["population", "intervention_or_exposure", "comparator", "outcomes",
                 "study_designs", "setting", "other_inclusion", "exclusion"],
    "additionalProperties": False,
}

_CRITERIA_SYSTEM = (
    "You are an experienced systematic reviewer. You write inclusion and exclusion "
    "criteria that two independent screeners could apply consistently at title and "
    "abstract stage. You return ONLY JSON."
)


def write_criteria(llm: LLMClient, title: str, *, publication_type: str) -> Criteria:
    """Draft the review's eligibility criteria from its question (design work)."""
    user = (
        f'Review question: "{title}"\nReview type: {publication_type}\n\n'
        "Write the eligibility criteria for this review: population, intervention or "
        "exposure, comparator, outcomes, eligible study designs, setting (or an empty "
        "string if any setting), any other inclusion requirements, and explicit "
        "exclusions. Each must be specific and checkable from a title and abstract. "
        "Stay faithful to the question's scope: do not broaden the population, the "
        "intervention or exposure, or the designs beyond what the question asks (a "
        "question about an intervention does not admit studies of a biomarker or "
        "status as an exposure). A study is either eligible for inclusion or not: do "
        "not add clauses about keeping papers for reference or citation checking; "
        "reviews are excluded unless the review type itself synthesises reviews. "
        "Do not cite or name specific studies."
    )
    return Criteria.from_dict(llm.complete_json(_CRITERIA_SYSTEM, user, schema=CRITERIA_SCHEMA))


# -- attribute extraction ---------------------------------------------------------
ATTRIBUTE_FIELDS = ("design", "population", "sample_size", "intervention",
                    "comparator", "primary_outcome", "outcomes", "country")
ATTRIBUTES_SCHEMA = {
    "type": "object",
    "properties": {
        **{f: _STR for f in ATTRIBUTE_FIELDS if f != "outcomes"},
        "outcomes": _STR_LIST,
    },
    "required": list(ATTRIBUTE_FIELDS),
    "additionalProperties": False,
}

_EXTRACT_SYSTEM = (
    "You extract facts stated in a research paper's text. You report only what the "
    f'text explicitly says; for anything not stated write "{NOT_STATED}". You never '
    "infer, estimate or fill in from background knowledge. You return ONLY JSON."
)


def _extraction_call(text: str) -> JsonCall:
    user = (
        "Extract from this text: study design, population, sample size (the number "
        "stated, with its unit), intervention, comparator, primary outcome, all "
        "outcomes (list), and country or countries.\n\n"
        f"{text}"
    )
    return JsonCall(_EXTRACT_SYSTEM, user, ATTRIBUTES_SCHEMA)


def _attributes(data: dict, paper: Paper) -> dict:
    attrs = {f: data.get(f, NOT_STATED) for f in ATTRIBUTE_FIELDS}
    if not isinstance(attrs["outcomes"], list):
        attrs["outcomes"] = []
    attrs["year"] = paper.year  # from the PubMed record, never the model
    return attrs


def extract_attributes(llm: LLMClient, paper: Paper, text: str) -> dict:
    """Stated study attributes, feeding the screening step."""
    call = _extraction_call(text)
    return _attributes(llm.complete_json(call.system, call.user, schema=call.schema), paper)


# -- screening --------------------------------------------------------------------
SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "reason": _STR,
    },
    "required": ["status", "reason"],
    "additionalProperties": False,
}


def _screen_system(criteria: Criteria) -> str:
    # Stable per review, so providers can cache it across every paper.
    return (
        "You screen studies for a systematic review at title and abstract stage, "
        "aiming for complete recall: missing an eligible study is far worse than "
        "keeping one that is later excluded. You give an estimate for a human to "
        "check, never a final decision.\n\n"
        "Choose exactly one status:\n"
        f'- "{LIKELY_ELIGIBLE}": the text shows every criterion is met, or met as far '
        "as this text can show.\n"
        f'- "{UNCLEAR}": at least one criterion cannot be confirmed from this text, '
        "and none is clearly failed.\n"
        f'- "{LIKELY_INELIGIBLE}": the text clearly shows the study falls outside the '
        "review: its population, intervention or exposure, comparator or design is a "
        "different one, or an exclusion plainly applies.\n"
        "Partial or marginal mismatches are NOT clear failures: part of the sample "
        "outside the population (e.g. an age boundary), the outcome reported but not "
        "as the primary outcome, a slightly different timing or follow-up, a mixed "
        f'population with a relevant subgroup. Choose "{UNCLEAR}" for these and name '
        "the issue, so a human can judge it. This holds even when a criterion is "
        "worded strictly (e.g. requires the outcome to be primary): reviewers often "
        "include such studies after reading the full text.\n"
        "Something the text does not mention is not the same as something the study "
        "did not do: if a required element (such as an outcome) is simply not "
        f'mentioned, especially in an abstract, choose "{UNCLEAR}".\n'
        "Never assume a detail the text does not state. The reason is one or two "
        "sentences naming the specific criteria that decided the status. You return "
        "ONLY JSON.\n\n"
        f"THE REVIEW'S CRITERIA:\n{criteria.as_text()}"
    )


@dataclass
class ScreenedPaper:
    paper: Paper
    attributes: dict
    status: str
    reason: str
    evidence_basis: str
    open_access_pmcid: Optional[str] = None

    def as_dict(self) -> dict:
        p = self.paper
        return {
            "pmid": p.pmid,
            "doi": p.doi,
            "title": p.title,
            "year": p.year,
            "journal": p.journal,
            "authors": list(p.authors),
            "attributes": self.attributes,
            "status": self.status,
            "reason": self.reason,
            "evidence_basis": self.evidence_basis,
            "open_access_pmcid": self.open_access_pmcid,
        }


def _abstract_text(paper: Paper) -> str:
    return f"TITLE: {paper.title}\n\nABSTRACT: {paper.abstract or '(no abstract available)'}"


def _screening_call(criteria: Criteria, attrs: dict, text: str, basis: str) -> JsonCall:
    attr_lines = "\n".join(
        f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in attrs.items()
    )
    caution = (
        "You are reading only the abstract: details reported only in the full "
        "text must not be inferred.\n\n"
        if basis == ABSTRACT_BASIS
        else ""
    )
    user = f"{caution}EXTRACTED ATTRIBUTES:\n{attr_lines}\n\nTEXT ({basis}):\n{text}"
    return JsonCall(_screen_system(criteria), user, SCREEN_SCHEMA, cache_system=True)


def _screened(paper: Paper, attrs: dict, data: dict, basis: str,
              pmcid: Optional[str]) -> ScreenedPaper:
    status = data.get("status")
    if status not in STATUSES:
        raise LLMError(f"unknown status {status!r}")
    return ScreenedPaper(paper, attrs, status, str(data.get("reason", "")).strip(), basis, pmcid)


def _not_assessed(paper: Paper, exc: Exception, pmcid: Optional[str]) -> ScreenedPaper:
    # Recall first: a paper the model could not assess stays in, for a human.
    return ScreenedPaper(
        paper, {"year": paper.year}, UNCLEAR,
        f"Automated assessment failed ({exc}); screen this paper yourself.",
        NOT_ASSESSED, pmcid,
    )


def screen_paper(
    extract_llm: LLMClient,
    screen_llm: LLMClient,
    criteria: Criteria,
    paper: Paper,
    *,
    text: Optional[str] = None,
    basis: str = ABSTRACT_BASIS,
    pmcid: Optional[str] = None,
) -> ScreenedPaper:
    """Extract attributes, then screen one paper. Never drops a paper."""
    text = text or _abstract_text(paper)
    try:
        attrs = extract_attributes(extract_llm, paper, text)
        call = _screening_call(criteria, attrs, text, basis)
        data = screen_llm.complete_json(call.system, call.user, schema=call.schema,
                                        cache_system=call.cache_system)
        return _screened(paper, attrs, data, basis, pmcid)
    except LLMError as exc:
        return _not_assessed(paper, exc, pmcid)


def _full_text_for(
    europepmc: Optional[EuropePmcClient], pmcid: Optional[str], max_chars: int
) -> tuple[Optional[str], str]:
    if europepmc is None or pmcid is None:
        return None, ABSTRACT_BASIS
    try:
        ft = extract_screening_text(europepmc.full_text_xml(pmcid), max_chars=max_chars)
    except httpx.HTTPError:
        return None, ABSTRACT_BASIS
    if ft is None:
        return None, ABSTRACT_BASIS
    return ft.text, ft.basis


# -- heterogeneity (the spec's sixth gate; needs abstracts, so it runs here) ------
@dataclass(frozen=True)
class HeterogeneityCheck:
    outcome_groups: dict[str, list[str]]  # distinct primary outcome -> pmids
    threshold: int

    @property
    def distinct_outcomes(self) -> int:
        return len(self.outcome_groups)

    @property
    def flagged(self) -> bool:
        return self.distinct_outcomes > self.threshold

    def as_dict(self) -> dict:
        return {
            "distinct_primary_outcomes": self.distinct_outcomes,
            "threshold": self.threshold,
            "outcome": "flag" if self.flagged else "pass",
            "groups": self.outcome_groups,
        }


GROUPS_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"outcome": _STR, "pmids": _STR_LIST},
                "required": ["outcome", "pmids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}


def check_heterogeneity(
    llm: LLMClient, screened: list[ScreenedPaper], *, threshold: int
) -> HeterogeneityCheck:
    """Group the stated primary outcomes of plausibly eligible papers; count them."""
    stated = {
        s.paper.pmid: s.attributes.get("primary_outcome", NOT_STATED)
        for s in screened
        if s.status in (LIKELY_ELIGIBLE, UNCLEAR)
        and s.attributes.get("primary_outcome", NOT_STATED) != NOT_STATED
    }
    if not stated:
        return HeterogeneityCheck({}, threshold)
    listing = "\n".join(f"- pmid {pmid}: {o}" for pmid, o in stated.items())
    user = (
        "Group these primary outcomes so that the same outcome measured or worded "
        "differently falls in one group (e.g. '28-day mortality' and 'all-cause "
        "death at 28 days'). Name each group and list its pmids, using only the pmids "
        f"given.\n\n{listing}"
    )
    data = llm.complete_json(
        "You group outcome descriptions. You return ONLY JSON.", user, schema=GROUPS_SCHEMA
    )
    groups: dict[str, list[str]] = {}
    for g in data.get("groups", []):
        pmids = [p for p in g.get("pmids", []) if p in stated]
        if pmids:
            groups.setdefault(str(g.get("outcome", "")).strip(), []).extend(pmids)
    return HeterogeneityCheck(groups, threshold)


# -- orchestration -----------------------------------------------------------------
@dataclass
class ScreeningResult:
    criteria: Criteria
    papers: list[ScreenedPaper]
    heterogeneity: Optional[HeterogeneityCheck] = None
    full_text_screened: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    def by_status(self, status: str) -> list[ScreenedPaper]:
        return [s for s in self.papers if s.status == status]

    def unclear_without_open_access(self) -> list[ScreenedPaper]:
        """Papers the user must fetch through their own access to decide."""
        return [s for s in self.papers if s.status == UNCLEAR and not s.open_access_pmcid]

    def as_dict(self) -> dict:
        return {
            "criteria": asdict(self.criteria),
            "counts": self.counts,
            "full_text_screened": self.full_text_screened,
            "heterogeneity": self.heterogeneity.as_dict() if self.heterogeneity else None,
            "papers": [s.as_dict() for s in self.papers],
            "retrieve_via_own_access": [
                {"pmid": s.paper.pmid, "doi": s.paper.doi, "title": s.paper.title}
                for s in self.unclear_without_open_access()
            ],
        }


def screen_papers(
    extract_llm: LLMClient,
    screen_llm: LLMClient,
    criteria: Criteria,
    papers: list[Paper],
    *,
    europepmc: Optional[EuropePmcClient] = None,
    grouping_llm: Optional[LLMClient] = None,
    heterogeneity_threshold: int = 5,
    fulltext_max_chars: int = 60_000,
    concurrency: int = 4,
) -> ScreeningResult:
    """Screen every paper (full text where open access), then check heterogeneity."""
    pmcids: dict[str, str] = {}
    if europepmc is not None and papers:
        try:
            pmcids = europepmc.open_access_pmcids([p.pmid for p in papers])
        except httpx.HTTPError:
            pmcids = {}

    # Gather each paper's text first (open-access full text where available).
    inputs = []
    for paper in papers:
        pmcid = pmcids.get(paper.pmid)
        text, basis = _full_text_for(europepmc, pmcid, fulltext_max_chars)
        inputs.append((paper, text or _abstract_text(paper), basis, pmcid))

    # Round 1: attributes for every paper; round 2: screening for every paper.
    # Each round is one batch on clients that batch, else parallel calls.
    extracted = run_many(extract_llm, [_extraction_call(t) for _, t, _, _ in inputs],
                         concurrency=concurrency)
    attrs_by_index: dict[int, dict] = {}
    failures: dict[int, Exception] = {}
    for i, ((paper, _, _, _), data) in enumerate(zip(inputs, extracted)):
        if isinstance(data, LLMError):
            failures[i] = data
        else:
            attrs_by_index[i] = _attributes(data, paper)
    order = sorted(attrs_by_index)
    screened_data = run_many(
        screen_llm,
        [_screening_call(criteria, attrs_by_index[i], inputs[i][1], inputs[i][2]) for i in order],
        concurrency=concurrency,
    )
    results: dict[int, ScreenedPaper] = {}
    for i, data in zip(order, screened_data):
        paper, _, basis, pmcid = inputs[i]
        try:
            if isinstance(data, LLMError):
                raise data
            results[i] = _screened(paper, attrs_by_index[i], data, basis, pmcid)
        except LLMError as exc:
            results[i] = _not_assessed(paper, exc, pmcid)
    for i, exc in failures.items():
        results[i] = _not_assessed(inputs[i][0], exc, inputs[i][3])
    screened = [results[i] for i in range(len(inputs))]  # keeps input order

    heterogeneity = None
    if grouping_llm is not None:
        try:
            heterogeneity = check_heterogeneity(
                grouping_llm, screened, threshold=heterogeneity_threshold
            )
        except LLMError:
            heterogeneity = None
    return ScreeningResult(
        criteria=criteria,
        papers=screened,
        heterogeneity=heterogeneity,
        full_text_screened=sum(1 for s in screened if s.evidence_basis.startswith("full text")),
        counts={st: sum(1 for s in screened if s.status == st) for st in STATUSES},
    )
