import json

import httpx
import pytest

from guide_pipeline.fulltext import extract_screening_text
from guide_pipeline.http import CachedHttpClient
from guide_pipeline.llm import LLMError
from guide_pipeline.screening import (
    ABSTRACT_BASIS,
    ATTRIBUTES_SCHEMA,
    CRITERIA_SCHEMA,
    LIKELY_ELIGIBLE,
    LIKELY_INELIGIBLE,
    NOT_ASSESSED,
    SCREEN_SCHEMA,
    UNCLEAR,
    Criteria,
    check_heterogeneity,
    screen_paper,
    screen_papers,
    write_criteria,
)
from guide_pipeline.sources.europepmc import EuropePmcClient
from guide_pipeline.sources.pubmed import Paper

CRIT = Criteria(
    population="Critically ill adults in intensive care",
    intervention_or_exposure="Vitamin D supplementation",
    comparator="Placebo or usual care",
    outcomes="All-cause mortality",
    study_designs="Randomised controlled trials",
    exclusion=("Paediatric populations",),
)


def paper(pmid="1", title="Vitamin D in ICU", abstract="An RCT in adults.", year=2021):
    return Paper(pmid, title, abstract, ("Smith J",), "J Test", year, f"10.1/{pmid}")


ATTRS = {"design": "RCT", "population": "ICU adults", "sample_size": "120 patients",
         "intervention": "vitamin D3", "comparator": "placebo",
         "primary_outcome": "28-day mortality", "outcomes": ["mortality"],
         "country": "Austria"}


class RoutedLLM:
    """Answers extraction / screening / grouping calls by schema."""

    def __init__(self, status=LIKELY_ELIGIBLE, fail_screen=False, groups=None):
        self.status, self.fail_screen, self.groups = status, fail_screen, groups or []
        self.calls = []

    def complete_json(self, system, user, schema=None, cache_system=False):
        self.calls.append({"system": system, "user": user, "schema": schema,
                           "cache_system": cache_system})
        if schema is ATTRIBUTES_SCHEMA:
            return dict(ATTRS)
        if schema is SCREEN_SCHEMA:
            if self.fail_screen:
                raise LLMError("boom")
            return {"status": self.status, "reason": "Matches population and intervention."}
        if schema is CRITERIA_SCHEMA:
            return {"population": "p", "intervention_or_exposure": "i", "comparator": "c",
                    "outcomes": "o", "study_designs": "RCT", "setting": "",
                    "other_inclusion": [], "exclusion": ["children"]}
        return {"groups": self.groups}


def test_criteria_are_written_by_the_model_into_a_structure():
    llm = RoutedLLM()
    c = write_criteria(llm, "Vitamin D in ICU", publication_type="systematic review")
    assert c.exclusion == ("children",) and "Exclude: children" in c.as_text()
    assert "systematic review" in llm.calls[0]["user"]


def test_screen_paper_gives_status_reason_and_basis():
    llm = RoutedLLM(status=LIKELY_ELIGIBLE)
    s = screen_paper(llm, llm, CRIT, paper())
    assert (s.status, s.evidence_basis) == (LIKELY_ELIGIBLE, ABSTRACT_BASIS)
    assert s.reason == "Matches population and intervention."
    assert s.attributes["year"] == 2021  # from the PubMed record, not the model
    screen_call = llm.calls[1]
    assert "Randomised controlled trials" in screen_call["system"]  # criteria in system
    assert screen_call["cache_system"] is True  # criteria cached across papers
    assert "only the abstract" in screen_call["user"]
    assert "120 patients" in screen_call["user"]  # attributes feed the screen


def test_failed_assessment_keeps_the_paper_as_unclear():
    s = screen_paper(RoutedLLM(), RoutedLLM(fail_screen=True), CRIT, paper())
    assert s.status == UNCLEAR and s.evidence_basis == NOT_ASSESSED
    assert "screen this paper yourself" in s.reason


def test_no_boolean_decision_field_in_any_schema():
    def walk(schema):
        if isinstance(schema, dict):
            assert schema.get("type") != "boolean"
            for v in schema.values():
                walk(v)
        elif isinstance(schema, list):
            for v in schema:
                walk(v)

    for schema in (SCREEN_SCHEMA, ATTRIBUTES_SCHEMA, CRITERIA_SCHEMA):
        walk(schema)
    assert SCREEN_SCHEMA["properties"]["status"]["enum"] == [
        LIKELY_ELIGIBLE, UNCLEAR, LIKELY_INELIGIBLE
    ]


def test_heterogeneity_groups_stated_primary_outcomes_and_flags():
    llm = RoutedLLM()
    screened = [screen_paper(llm, llm, CRIT, paper(str(i))) for i in range(3)]
    grouping = RoutedLLM(groups=[{"outcome": "mortality", "pmids": ["0", "1", "999"]},
                                 {"outcome": "length of stay", "pmids": ["2"]}])
    h = check_heterogeneity(grouping, screened, threshold=1)
    assert h.outcome_groups == {"mortality": ["0", "1"], "length of stay": ["2"]}  # 999 dropped
    assert h.distinct_outcomes == 2 and h.flagged
    assert not check_heterogeneity(grouping, screened, threshold=5).flagged


def test_heterogeneity_ignores_ineligible_papers():
    llm = RoutedLLM(status=LIKELY_INELIGIBLE)
    screened = [screen_paper(llm, llm, CRIT, paper())]
    grouping = RoutedLLM()
    h = check_heterogeneity(grouping, screened, threshold=5)
    assert h.distinct_outcomes == 0 and grouping.calls == []


# -- full text -----------------------------------------------------------------------
JATS = """<article><front><article-meta><title-group><article-title>Vit D trial</article-title>
</title-group><abstract><p>Short abstract.</p></abstract></article-meta></front>
<body><sec><title>Introduction</title><p>Background text.</p></sec>
<sec><title>Methods</title><p>We randomised 120 ICU adults.</p></sec>
<sec><title>Results</title><p>Mortality fell.</p></sec>
<sec sec-type="ref-list"><title>References</title><p>Ref 1.</p></sec>
<sec><title>Funding</title><p>Grant.</p></sec></body></article>"""


def test_full_text_keeps_methods_and_results_only():
    ft = extract_screening_text(JATS)
    assert "randomised 120 ICU adults" in ft.text and "Mortality fell" in ft.text
    assert "Background text" not in ft.text and "Ref 1" not in ft.text and "Grant" not in ft.text
    assert "Short abstract" in ft.text
    assert ft.basis == "full text (methods and results)"


def test_full_text_truncation_is_declared_and_bad_xml_is_none():
    ft = extract_screening_text(JATS, max_chars=40)
    assert ft.truncated and ft.basis.endswith("truncated)")
    assert extract_screening_text("not xml") is None
    assert extract_screening_text("<article><front/></article>") is None  # no body


def europepmc_with(handler, tmp_path):
    return EuropePmcClient(http=CachedHttpClient(
        cache_dir=tmp_path / ".cache",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    ))


def epmc_handler(oa=("1",), fulltext_status=200):
    def handler(request):
        if request.url.path.endswith("/fullTextXML"):
            return httpx.Response(fulltext_status, text=JATS)
        rows = [{"pmid": p, "pmcid": f"PMC{p}", "isOpenAccess": "Y"} for p in oa]
        rows.append({"pmid": "9", "pmcid": "PMC9", "isOpenAccess": "N"})  # not OA
        return httpx.Response(200, json={"hitCount": len(rows), "resultList": {"result": rows}})

    return handler


def test_open_access_lookup_keeps_only_open_access(tmp_path):
    ep = europepmc_with(epmc_handler(oa=("1", "2")), tmp_path)
    assert ep.open_access_pmcids(["1", "2", "9"]) == {"1": "PMC1", "2": "PMC2"}


def test_screen_papers_uses_full_text_where_open_access(tmp_path):
    llm = RoutedLLM(status=UNCLEAR)
    ep = europepmc_with(epmc_handler(oa=("1",)), tmp_path)
    result = screen_papers(llm, llm, CRIT, [paper("1"), paper("2")], europepmc=ep,
                           grouping_llm=RoutedLLM(groups=[]), concurrency=2)
    first, second = result.papers
    assert first.evidence_basis.startswith("full text") and first.open_access_pmcid == "PMC1"
    assert second.evidence_basis == ABSTRACT_BASIS and second.open_access_pmcid is None
    assert result.full_text_screened == 1
    assert result.counts == {LIKELY_ELIGIBLE: 0, UNCLEAR: 2, LIKELY_INELIGIBLE: 0}
    # only the unclear paper WITHOUT open access goes on the own-access list
    assert [s.paper.pmid for s in result.unclear_without_open_access()] == ["2"]
    d = result.as_dict()
    assert d["retrieve_via_own_access"][0]["doi"] == "10.1/2"
    json.dumps(d)  # serialisable for results.json


def test_screen_papers_falls_back_to_abstract_when_full_text_fails(tmp_path):
    llm = RoutedLLM()
    ep = europepmc_with(epmc_handler(oa=("1",), fulltext_status=404), tmp_path)
    result = screen_papers(llm, llm, CRIT, [paper("1")], europepmc=ep)
    assert result.papers[0].evidence_basis == ABSTRACT_BASIS
    assert result.papers[0].open_access_pmcid == "PMC1"


def test_criteria_prompt_keeps_scope_and_binary_eligibility():
    llm = RoutedLLM()
    write_criteria(llm, "Vitamin D supplementation in ICU", publication_type="systematic review")
    prompt = llm.calls[0]["user"]
    assert "Stay faithful to the question's scope" in prompt
    assert "keeping papers for reference" in prompt


def test_screening_prompt_treats_marginal_mismatches_as_unclear():
    from guide_pipeline.screening import _screen_system

    system = _screen_system(CRIT)
    assert "Partial or marginal mismatches are NOT clear failures" in system
    assert "outcome reported but not as the primary outcome" in system


def test_screen_papers_keeps_papers_whose_extraction_failed():
    class FailOne(RoutedLLM):
        def complete_json(self, system, user, schema=None, cache_system=False):
            if schema is ATTRIBUTES_SCHEMA and "Broken" in user:
                raise LLMError("expired")
            return super().complete_json(system, user, schema, cache_system)

    llm = FailOne(status=LIKELY_ELIGIBLE)
    result = screen_papers(llm, llm, CRIT, [paper("1"), paper("2", title="Broken"), paper("3")],
                           concurrency=1)
    assert [s.paper.pmid for s in result.papers] == ["1", "2", "3"]  # order kept
    assert [s.status for s in result.papers] == [LIKELY_ELIGIBLE, UNCLEAR, LIKELY_ELIGIBLE]
    assert result.papers[1].evidence_basis == NOT_ASSESSED


def test_screen_sees_online_and_issue_years():
    llm = RoutedLLM()
    p = Paper("7", "T", "abs", (), "J", 2023, None, epub_year=2020)
    s = screen_paper(llm, llm, CRIT, p)
    assert s.attributes["year"] == "first published online 2020; journal issue 2023"
    assert "first published online 2020" in llm.calls[1]["user"]
