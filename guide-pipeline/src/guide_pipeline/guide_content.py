"""Content for the full guide (spec §6), assembled before rendering.

Most sections are built by code from what the pipeline measured: the novelty
statement and its date, the question as PICO, feasibility numbers, the papers
table, the risk of bias tool and reporting guideline for the design, the PRISMA
counts, the timeline from the user's hours, and the search appendix.

Three model calls write the parts that need design, and code checks each:
  search strategies (effort medium)  every PubMed strategy is run for a real
                                     count; every MeSH term is looked up
  protocol (medium)                  rationale, criteria reasoning, aims,
                                     analysis, differences from similar work;
                                     may cite only numbered records supplied,
                                     and invalid citation numbers are removed
  PROSPERO entry (low)               reformatting of the protocol

Verbatim texts come from the spec (§6.1, 6.2, 6.4) and the website copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .gates import LIGHTER_TYPES, SYSTEMATIC
from .llm import LLMClient
from .prospero import match_key, similarity
from .screening import LIKELY_ELIGIBLE, LIKELY_INELIGIBLE, UNCLEAR, Criteria, ScreeningResult
from .sources.pubmed import Paper, PubMedClient

# -- verbatim texts ---------------------------------------------------------------
NOVELTY_STATEMENT = (
    "This title was checked against PROSPERO and the published literature on {date}, "
    "and no registered protocol or published review covering this question was found. "
    "New protocols are registered daily. Check PROSPERO yourself before you begin work."
)
REGISTRATION_URGENCY = (
    "Register this review on PROSPERO as soon as you can. Registration is free, takes "
    "under an hour, and creates a public timestamped record that this question is "
    "yours. Until you register, someone else may register the same question.",
    "Your guide contains a pre drafted registration entry, so most of the form is "
    "already written for you.",
    "When you register, PROSPERO will show you a list of similar registered reviews. "
    "Read that list carefully rather than clicking past it. It is a more recent check "
    "than ours. If anything on it looks close to your question, contact us before you "
    "start work and we will refine the title and angle with you.",
)
DISCLAIMERS = (
    "The papers listed in this guide are suggestions, not a complete or exhaustive "
    "set. They were identified by a preliminary search and have not been screened "
    "against your inclusion and exclusion criteria.",
    "You must run your own search and make your own decisions about which papers to "
    "include. Those decisions are yours as the author, and Symposed cannot be "
    "responsible for the inclusion or exclusion of any paper, or for any error in the "
    "resulting study.",
    "The counts shown in the PRISMA diagram come from our preliminary search on the "
    "date stated above. They will need updating once you have run your own search and "
    "completed formal screening.",
    "This guide does not guarantee publication or acceptance by any journal.",
)
# Website copy (guides-meta.ts), word for word.
ACKNOWLEDGEMENT_WORDING = "Methodological support for this study was provided by Symposed."
AUTHOR_AI_NOTE = (
    "Note for authors: AI assisted tools were used in developing the search strategy "
    "for this guide. Most journals now require any use of AI in the preparation of a "
    "manuscript, including methodology development, to be declared. Please check the "
    "disclosure policy of your target journal before you submit, and declare accordingly."
)
SCREENING_ESTIMATE_NOTE = (
    "The eligibility shown for each paper is an automated estimate with its reason and "
    "what was read, not screening. Screen every paper yourself."
)
COLLABORATION_PROMPT = (
    "Post this project on Symposed to recruit collaborators. Reviews are stronger, and "
    "far more likely to be accepted, when papers are screened independently by more "
    "than one person, and leading a team is evidence you cannot generate working alone."
)

# -- rule-based content -----------------------------------------------------------
HOURS_PER_WEEK = {"Under 3": 2.0, "3 to 5": 4.0, "5 to 10": 7.5, "Over 10": 12.0}


def risk_of_bias_tool(designs: str, axis: str = "") -> str:
    d = f"{designs} {axis}".lower()
    if "diagnostic" in d or "accuracy" in d:
        return "QUADAS-2 (diagnostic accuracy studies)"
    if "prediction model" in d or "prognostic model" in d:
        return "PROBAST (prediction model studies)"
    if "prognostic factor" in d:
        return "QUIPS (prognostic factor studies)"
    randomised = "random" in d
    non_randomised = any(w in d for w in ("cohort", "case-control", "observational",
                                          "non-randomised", "non-randomized", "quasi"))
    if randomised and non_randomised:
        return "RoB 2 for randomised trials and ROBINS-I for non-randomised studies"
    if randomised:
        return "RoB 2 (randomised trials)"
    if "case-control" in d or "cohort" in d or "observational" in d:
        return "Newcastle-Ottawa Scale (cohort and case-control studies)"
    return "ROBINS-I (non-randomised studies of interventions)"


def reporting_guideline(publication_type: str, designs: str = "") -> list[str]:
    if publication_type == SYSTEMATIC:
        out = ["PRISMA 2020", "PRISMA-S for reporting the search"]
        if "prediction model" in designs.lower():
            out.append("TRIPOD-SRMA alongside PRISMA for prediction model reviews")
        out.append("SWiM if you synthesise without meta-analysis")
        return out
    if "scoping" in publication_type:
        return ["PRISMA-ScR (scoping reviews)", "JBI scoping review guidance"]
    return ["SANRA (scale for the assessment of narrative review articles) as a quality "
            "checklist", "Report your search transparently (sources, dates, terms)"]


SCREENING_PLATFORM = (
    "Rayyan (free, rayyan.ai): create a review, import the RIS export of your search, "
    "invite your co-reviewer, switch on blind mode so you screen independently, then "
    "resolve conflicts together. Covidence is an alternative if your institution "
    "subscribes."
)
GREY_LITERATURE = (
    "Search trial registries (ClinicalTrials.gov, WHO ICTRP) for completed and ongoing "
    "trials, including unpublished results.",
    "Search conference proceedings in your specialty for the last 3 to 5 years.",
    "Search preprint servers (medRxiv) and Europe PMC for preprints.",
    "Check the reference lists of included studies and relevant reviews (backward "
    "citation searching) and who cites them (forward citation searching).",
    "Search relevant guideline repositories (NICE, SIGN) for grey literature.",
)
REJECTION_REASONS = {
    SYSTEMATIC: (
        "No registered protocol, or the review deviates from it without explanation.",
        "A search that is not reproducible: missing databases, dates or full strategies.",
        "Screening or extraction done by one person only.",
        "Risk of bias not assessed, or not used when interpreting results.",
        "Pooling studies that are too different, without exploring heterogeneity.",
        "The question has recently been answered by another review.",
        "Conclusions that go beyond what the evidence supports.",
    ),
    "scoping": (
        "An unclear purpose: mapping versus answering an effectiveness question.",
        "No protocol, or a protocol not registered (for example on OSF).",
        "Charting that is descriptive only, without mapping the gaps.",
        "Assessing quality as if it were a systematic review.",
    ),
    "narrative": (
        "No transparent search, so the selection of sources looks arbitrary.",
        "An unbalanced account that ignores conflicting evidence.",
        "No clear angle or contribution beyond existing reviews.",
        "Conclusions stated more strongly than the evidence allows.",
    ),
}


def rejection_reasons(publication_type: str) -> tuple[str, ...]:
    if publication_type == SYSTEMATIC:
        return REJECTION_REASONS[SYSTEMATIC]
    return REJECTION_REASONS["scoping" if "scoping" in publication_type else "narrative"]


def publication_structure(publication_type: str) -> list[tuple[str, list[str]]]:
    if publication_type == SYSTEMATIC:
        return [
            ("Title and abstract", ["Structured abstract (PRISMA for Abstracts)"]),
            ("Introduction", ["Rationale", "Objectives (PICO)"]),
            ("Methods", ["Protocol and registration", "Eligibility criteria",
                         "Information sources and search", "Selection process",
                         "Data collection", "Risk of bias assessment",
                         "Synthesis methods", "Certainty of evidence (GRADE)"]),
            ("Results", ["Study selection (Figure 1: PRISMA flow diagram)",
                         "Study characteristics (Table 1)",
                         "Risk of bias (Figure 2 or Table 2)",
                         "Results of syntheses (forest plots, if pooled)"]),
            ("Discussion", ["Summary of evidence", "Limitations", "Implications"]),
            ("Other", ["Registration number", "Funding", "Competing interests",
                       "Data availability"]),
        ]
    return [
        ("Title and abstract", ["Unstructured or structured abstract per journal"]),
        ("Introduction", ["Why this topic matters", "Aim of the review"]),
        ("Methods", ["Search approach (sources, dates, terms)",
                     "How sources were selected"]),
        ("Main body", ["Themed sections, one per sub-question",
                       "Summary table of key studies (Table 1)"]),
        ("Discussion", ["Synthesis across themes", "Gaps and future research",
                        "Limitations"]),
        ("Conclusion", ["Key messages"]),
    ]


@dataclass(frozen=True)
class Milestone:
    phase: str
    hours: float
    week_ends: int


def timeline(*, records: int, eligible: int, team: int, hours_label: str,
             publication_type: str) -> tuple[list[Milestone], dict[str, Any]]:
    """Milestones from the user's hours. Assumptions are returned for display."""
    per_week = HOURS_PER_WEEK.get(hours_label, 4.0)
    team = max(team, 2)
    sr = publication_type == SYSTEMATIC
    # Minutes per record per person; dual screening means each record twice.
    phases = [
        ("Refine question, register protocol", 6.0 if sr else 3.0),
        ("Run searches in all databases, remove duplicates", 5.0),
        ("Title and abstract screening", records * 1.0 * 2 / team / 60),
        ("Full text screening", eligible * 15.0 * 2 / team / 60),
        ("Data extraction", eligible * 30.0 / team / 60),
    ]
    if sr:
        phases.append(("Risk of bias assessment", eligible * 20.0 * 2 / team / 60))
        phases.append(("Analysis and synthesis", 15.0))
    else:
        phases.append(("Thematic synthesis", 10.0))
    phases.append(("Write up and submit", 25.0))
    out, total = [], 0.0
    for name, h in phases:
        total += h
        out.append(Milestone(name, round(h, 1), max(1, round(total / per_week + 0.49))))
    assumptions = {
        "hours_per_week_each": per_week, "team": team, "records_to_screen": records,
        "eligible_estimate": eligible,
        "rates": "1 minute per title and abstract, 15 per full text, 30 per extraction, "
                 "20 per risk of bias, each by two people where the method needs it",
    }
    return out, assumptions


def extraction_template(publication_type: str, designs: str) -> list[str]:
    fields = ["Study ID (first author, year)", "Country and setting", "Study design",
              "Population and sample size", "Intervention or exposure",
              "Comparator", "Outcomes and time points", "Results for each outcome",
              "Funding and conflicts of interest"]
    if publication_type == SYSTEMATIC:
        fields += ["Effect estimates with 95% CI (or data to compute them)",
                   "Risk of bias judgement per domain"]
    if "prediction model" in designs.lower():
        fields += ["Predictors", "Model development method", "Discrimination (AUC)",
                   "Calibration", "Validation (internal, external)"]
    return fields


# -- model-written sections ---------------------------------------------------------
_S = {"type": "string"}
_SL = {"type": "array", "items": _S}
STRATEGY_SCHEMA = {
    "type": "object",
    "properties": {
        "strategies": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": _S, "pubmed_query": _S, "purpose": _S},
            "required": ["name", "pubmed_query", "purpose"], "additionalProperties": False}},
        "recommended": {"type": "integer"},
        "recommendation_reason": _S,
        "embase_emtree": _S,
        "cochrane_central": _S,
    },
    "required": ["strategies", "recommended", "recommendation_reason", "embase_emtree",
                 "cochrane_central"],
    "additionalProperties": False,
}
PROTOCOL_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": _S,
        "similar_work_differences": {"type": "array", "items": {
            "type": "object", "properties": {"ref": {"type": "integer"}, "difference": _S},
            "required": ["ref", "difference"], "additionalProperties": False}},
        "criteria_reasoning": {"type": "array", "items": {
            "type": "object", "properties": {"criterion": _S, "reasoning": _S},
            "required": ["criterion", "reasoning"], "additionalProperties": False}},
        "aims": _S,
        "objectives": _SL,
        "analysis": _S,
        "skills_needed": _SL,
    },
    "required": ["rationale", "similar_work_differences", "criteria_reasoning", "aims",
                 "objectives", "analysis", "skills_needed"],
    "additionalProperties": False,
}
PROSPERO_FIELDS = ("review_title", "review_question", "searches", "condition_or_domain",
                   "population", "intervention_exposure", "comparator_control",
                   "types_of_study", "main_outcomes", "additional_outcomes",
                   "data_extraction", "risk_of_bias_assessment", "strategy_for_synthesis",
                   "subgroup_analyses")
PROSPERO_SCHEMA = {
    "type": "object", "properties": {f: _S for f in PROSPERO_FIELDS},
    "required": list(PROSPERO_FIELDS), "additionalProperties": False,
}
_DESIGNER = (
    "You are an experienced systematic reviewer writing part of a methods guide for a "
    "first-time reviewer. Be specific and practical. Never invent studies, counts, "
    "citations or MeSH terms: cite only by the [n] numbers given. You return ONLY JSON."
)
_MESH_TAG = re.compile(r'"?([^"()]+?)"?\s*\[(?:mh|mesh|MeSH|MeSH Terms|Mesh)(?::noexp)?\]')
_CITE = re.compile(r"\[(\d+)\]")


@dataclass
class Strategy:
    name: str
    pubmed_query: str
    purpose: str
    count: Optional[int] = None  # from PubMed, never the model
    unverified_mesh: list[str] = field(default_factory=list)


def _verify_mesh(pubmed: PubMedClient, query: str) -> list[str]:
    missing = []
    for term in dict.fromkeys(t.strip() for t in _MESH_TAG.findall(query)):
        found = {m.name.lower() for m in pubmed.mesh_terms(term, max_terms=5)}
        if term.lower() not in found:
            missing.append(term)
    return missing


def search_strategies(llm: LLMClient, pubmed: PubMedClient, *, title: str,
                      criteria: Criteria, base_query: str) -> dict[str, Any]:
    user = (
        f'Review question: "{title}"\n\nCriteria:\n{criteria.as_text()}\n\n'
        f"A working PubMed query already used: {base_query}\n\n"
        "Write 2 or 3 complete PubMed search strategies (for example sensitive, balanced "
        "and precise), each with every term, synonyms combined with OR, and MeSH terms "
        "only where you are certain they exist. Say which one you recommend and why. "
        "Then translate the recommended strategy into Embase (Emtree, Ovid or "
        "Embase.com syntax) and Cochrane CENTRAL syntax."
    )
    data = llm.complete_json(_DESIGNER, user, schema=STRATEGY_SCHEMA)
    strategies = []
    for s in data.get("strategies", [])[:3]:
        st = Strategy(str(s.get("name", "")), str(s.get("pubmed_query", "")),
                      str(s.get("purpose", "")))
        if st.pubmed_query:
            try:
                st.count = pubmed.count(st.pubmed_query)
                st.unverified_mesh = _verify_mesh(pubmed, st.pubmed_query)
            except httpx.HTTPError:  # a malformed query is shown with no count
                st.count = None
            strategies.append(st)
    rec = data.get("recommended", 0)
    return {
        "strategies": strategies,
        "recommended": rec if isinstance(rec, int) and 0 <= rec < len(strategies) else 0,
        "recommendation_reason": str(data.get("recommendation_reason", "")),
        "embase_emtree": str(data.get("embase_emtree", "")),
        "cochrane_central": str(data.get("cochrane_central", "")),
    }


def _clean_citations(text: str, valid: int) -> str:
    """Drop any [n] outside the supplied list (rule 1: no invented citations)."""
    return _CITE.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= valid else "", text)


def protocol_sections(llm: LLMClient, *, title: str, publication_type: str,
                      criteria: Criteria, rationale_hint: str, references: list[str],
                      similar: list[str], context: str) -> dict[str, Any]:
    refs = "\n".join(f"[{i}] {r}" for i, r in enumerate(references, 1))
    sim = "\n".join(f"[{i}] {s}" for i, s in enumerate(similar, 1)) or "(none found)"
    user = (
        f'Review question: "{title}" ({publication_type})\n{context}\n\n'
        f"Why this question was chosen: {rationale_hint}\n\nCriteria:\n{criteria.as_text()}\n\n"
        f"RETRIEVED RECORDS you may cite by number:\n{refs}\n\n"
        f"SIMILAR EXISTING WORK (numbered separately):\n{sim}\n\n"
        "Write: (1) a rationale of 150 to 250 words on why this question matters and why "
        "it is currently unanswered, citing retrieved records as [n]; (2) for each "
        "similar work, how the proposed question differs (ref = its number in the "
        "similar list); (3) the reasoning behind each criterion; (4) the aim and 3 to 5 "
        "objectives; (5) the analysis plan and statistical tests likely needed, for a "
        "user of this statistics level; (6) the skills needed."
    )
    data = llm.complete_json(_DESIGNER, user, schema=PROTOCOL_SCHEMA)
    data["rationale"] = _clean_citations(str(data.get("rationale", "")), len(references))
    data["similar_work_differences"] = [
        d for d in data.get("similar_work_differences", [])
        if isinstance(d.get("ref"), int) and 1 <= d["ref"] <= len(similar)
    ]
    return data


def prospero_entry(llm: LLMClient, *, title: str, criteria: Criteria, protocol: dict,
                   strategy: str, rob_tool: str) -> dict[str, str]:
    user = (
        f'Map this protocol onto the PROSPERO registration fields.\nTitle: "{title}"\n'
        f"Criteria:\n{criteria.as_text()}\nAims: {protocol.get('aims', '')}\n"
        f"Objectives: {protocol.get('objectives', [])}\nAnalysis: {protocol.get('analysis', '')}\n"
        f"Search strategy: {strategy}\nRisk of bias tool: {rob_tool}\n"
        "Reformat only: do not add new design decisions."
    )
    data = llm.complete_json(
        "You fill registration forms from a finished protocol. You return ONLY JSON.",
        user, schema=PROSPERO_SCHEMA)
    return {f: str(data.get(f, "")) for f in PROSPERO_FIELDS}


# -- similar work and journals (from API records only) --------------------------------
def similar_reviews(pubmed: PubMedClient, *, concept_query: str, title: str,
                    limit: int = 5) -> list[dict[str, Any]]:
    """The published reviews on the concepts most similar in wording to the title."""
    pmids = pubmed.search_pmids(f"({concept_query}) AND systematic[sb]", retmax=20)
    key = match_key(title)
    scored = [
        {"pmid": pmid, "title": t, "score": round(similarity(key, match_key(t)), 3),
         "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
        for pmid, t in pubmed.titles(pmids)
    ]
    return sorted(scored, key=lambda d: d["score"], reverse=True)[:limit]


def journal_shortlist(screening: ScreeningResult, limit: int = 5) -> list[tuple[str, int]]:
    """Journals that published the plausibly eligible papers, most frequent first."""
    counts: dict[str, int] = {}
    for s in screening.papers:
        if s.status in (LIKELY_ELIGIBLE, UNCLEAR) and s.paper.journal:
            counts[s.paper.journal] = counts.get(s.paper.journal, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def citation(p: Paper) -> str:
    if not p.authors:
        who = "[No author listed]"
    else:
        who = p.authors[0] + (" et al." if len(p.authors) > 1 else "")
    parts = [f"{who} ({p.year or 'n.d.'}).", p.title.rstrip(".") + ".",
             f"{p.journal}." if p.journal else "",
             f"Europe PMC {p.pmid}." if p.is_preprint else f"PMID {p.pmid}."]
    if p.doi:
        parts.append(f"doi:{p.doi}")
    return " ".join(x for x in parts if x)


def prisma_counts(retrieval_identified: int, fetched: int, deduped: int,
                  screening: ScreeningResult, preprints_identified: int = 0) -> dict[str, int]:
    c = screening.counts
    return {
        "identified": retrieval_identified,
        "preprints_identified": preprints_identified,
        "retrieved": fetched,
        "duplicates_removed": max(0, fetched - deduped),
        "screened": len(screening.papers),
        "excluded_estimate": c.get(LIKELY_INELIGIBLE, 0),
        "full_text_to_assess": c.get(LIKELY_ELIGIBLE, 0) + c.get(UNCLEAR, 0),
    }


def is_systematic(publication_type: str) -> bool:
    return publication_type == SYSTEMATIC


def is_lighter(publication_type: str) -> bool:
    return publication_type in LIGHTER_TYPES or "scoping" in publication_type or \
        "narrative" in publication_type



# -- assembly ---------------------------------------------------------------------
@dataclass
class GuideContent:
    """Everything the guide shows, in section order, as plain data."""

    title: str
    publication_type: str
    generated_on: str
    search_date: str
    novelty_date: str
    pico: list[tuple[str, str]]
    rationale: str
    references: list[str]
    similar: list[dict[str, Any]]
    differences: dict[int, str]
    feasibility: dict[str, Any]
    strategies: dict[str, Any]
    papers: ScreeningResult
    criteria: Criteria
    criteria_reasoning: list[dict[str, str]]
    prospero: Optional[dict[str, str]]
    rob_tool: str
    reporting: list[str]
    aims: str
    objectives: list[str]
    analysis: str
    skills: list[str]
    extraction_fields: list[str]
    prisma: Optional[dict[str, int]]
    structure: list[tuple[str, list[str]]]
    timeline: list[Milestone]
    timeline_assumptions: dict[str, Any]
    journals: list[tuple[str, int]]
    search_appendix: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)  # for the human reviewer

    @property
    def systematic(self) -> bool:
        return is_systematic(self.publication_type)


def assemble(
    *,
    title: str,
    publication_type: str,
    criteria: Criteria,
    assessment: Any,
    retrieval: Any,
    screening: ScreeningResult,
    preferences: Any,
    proforma: dict,
    search_date: str,
    pubmed: PubMedClient,
    llms: dict[str, LLMClient],
    screened_all: bool = True,
) -> GuideContent:
    c = assessment.candidate
    warnings: list[str] = []
    plausible = [s for s in screening.papers if s.status in (LIKELY_ELIGIBLE, UNCLEAR)]
    references = [citation(s.paper) for s in plausible[:25]]

    similar = similar_reviews(pubmed, concept_query=c.pubmed_query, title=title)
    for m in (assessment.prospero.matches[:3] if assessment.prospero else []):
        similar.append({"pmid": None, "title": f"PROSPERO {m.registration_id}: {m.title}",
                        "score": m.score, "url": m.url})
    similar = sorted(similar, key=lambda d: d["score"], reverse=True)[:5]

    strategies = search_strategies(llms["search_strategy"], pubmed, title=title,
                                   criteria=criteria, base_query=retrieval.query)
    for st in strategies["strategies"]:
        if st.unverified_mesh:
            warnings.append(f"Strategy '{st.name}': MeSH term(s) not found in the MeSH "
                            f"database: {', '.join(st.unverified_mesh)}")
        if st.count in (None, 0):
            warnings.append(f"Strategy '{st.name}' returned {st.count} records: check it")

    protocol = protocol_sections(
        llms["protocol_drafting"], title=title, publication_type=publication_type,
        criteria=criteria, rationale_hint=c.rationale, references=references,
        similar=[d["title"] for d in similar], context=preferences.context)
    found = [st for st in strategies["strategies"] if st.count]
    if strategies["strategies"] and not strategies["strategies"][strategies["recommended"]].count and found:
        # Never recommend a strategy PubMed returned nothing for: switch to the
        # most sensitive one that works, and tell the reviewer.
        bad = strategies["strategies"][strategies["recommended"]]
        best = max(found, key=lambda st: st.count)
        strategies["recommended"] = strategies["strategies"].index(best)
        strategies["recommendation_reason"] = (
            f"'{best.name}' is recommended because it returns records in PubMed "
            f"({best.count:,} on {search_date}).")
        warnings.append(f"The model recommended '{bad.name}', which returned "
                        f"{bad.count} records; switched to '{best.name}'.")
    rob = risk_of_bias_tool(criteria.study_designs, c.axis)
    rec = strategies["strategies"][strategies["recommended"]] if strategies["strategies"] else None
    prospero = None
    if is_systematic(publication_type):
        prospero = prospero_entry(llms["prospero_form"], title=title, criteria=criteria,
                                  protocol=protocol,
                                  strategy=rec.pubmed_query if rec else retrieval.query,
                                  rob_tool=rob)

    eligible_estimate = len(plausible)
    if not screened_all:
        warnings.append(f"Screening was capped at {len(screening.papers)} of "
                        f"{len(retrieval.papers)} retrieved papers (test run).")
    # Screening volume: the question's concepts across all publication types
    # (the triage count), not the narrower retrieval query.
    records = max(assessment.counts.records_to_screen, retrieval.identified,
                  len(retrieval.papers))
    team = max(preferences.collaborators, 2)
    tl, assumptions = timeline(records=records, eligible=eligible_estimate, team=team,
                               hours_label=str(proforma.get("hoursPerWeek", "")),
                               publication_type=publication_type)
    appendix = [{"source": r.source, "query": r.query, "count": r.result,
                 "run_at": r.run_at} for r in assessment.searches]
    appendix.append({"source": "PubMed", "query": retrieval.query,
                     "count": retrieval.identified, "run_at": search_date})
    if getattr(retrieval, "preprint_query", ""):
        appendix.append({"source": "Europe PMC (preprints)", "query": retrieval.preprint_query,
                         "count": retrieval.preprints_identified, "run_at": search_date})
    appendix += [{"source": "PubMed", "query": st.pubmed_query, "count": st.count,
                  "run_at": search_date} for st in strategies["strategies"]]

    return GuideContent(
        title=title,
        publication_type=publication_type,
        generated_on=search_date,
        search_date=search_date,
        novelty_date=(assessment.prospero.checked_on.strftime("%d/%m/%Y")
                      if assessment.prospero else search_date),
        pico=[("Population", criteria.population),
              ("Intervention or exposure", criteria.intervention_or_exposure),
              ("Comparator", criteria.comparator),
              ("Outcomes", criteria.outcomes),
              ("Study designs", criteria.study_designs)],
        rationale=protocol["rationale"],
        references=references,
        similar=similar,
        differences={d["ref"]: d["difference"] for d in protocol["similar_work_differences"]},
        feasibility={
            "eligible_triage": assessment.counts.eligible_studies,
            "eligible_screened": eligible_estimate,
            "records_to_screen": records,
            "recommended_team": team,
        },
        strategies=strategies,
        papers=screening,
        criteria=criteria,
        criteria_reasoning=protocol["criteria_reasoning"],
        prospero=prospero,
        rob_tool=rob,
        reporting=reporting_guideline(publication_type, criteria.study_designs),
        aims=protocol["aims"],
        objectives=protocol["objectives"],
        analysis=protocol["analysis"],
        skills=protocol["skills_needed"],
        extraction_fields=extraction_template(publication_type, criteria.study_designs),
        prisma=(prisma_counts(retrieval.identified, retrieval.fetched,
                              len(retrieval.papers), screening,
                              getattr(retrieval, "preprints_identified", 0))
                if is_systematic(publication_type) else None),
        structure=publication_structure(publication_type),
        timeline=tl,
        timeline_assumptions=assumptions,
        journals=journal_shortlist(screening),
        search_appendix=appendix,
        warnings=warnings,
    )
