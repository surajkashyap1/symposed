import httpx
import pytest

from guide_pipeline.candidates import (
    Candidate,
    apply_gates,
    assess_candidate,
    generate_candidates,
    plain_terms,
    rank_survivors,
    screen_candidates,
)
from guide_pipeline.http import CachedHttpClient
from guide_pipeline.llm import LLMError
from guide_pipeline.settings import Thresholds
from guide_pipeline.sources.clinicaltrials import ClinicalTrialsClient
from guide_pipeline.sources.pubmed import PubMedClient


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        return self.payload


# -- generation --------------------------------------------------------------
def test_generate_candidates_parses_and_filters():
    llm = FakeLLM(
        {
            "candidates": [
                {"title": "A", "axis": "population", "pubmed_query": "q1"},
                {"title": "", "axis": "outcome", "pubmed_query": "q2"},  # no title
                {"title": "C", "axis": "outcome", "pubmed_query": ""},  # no query
                {"title": "D", "axis": "setting", "pubmed_query": "q4", "rationale": "r"},
            ]
        }
    )
    out = generate_candidates(llm, "sepsis", min_n=2, max_n=4)
    assert [c.title for c in out] == ["A", "D"]
    assert out[1].rationale == "r"


def test_generate_candidates_raises_when_empty():
    with pytest.raises(LLMError):
        generate_candidates(FakeLLM({"candidates": []}), "sepsis")
    with pytest.raises(LLMError):
        generate_candidates(FakeLLM({"candidates": [{"title": "x"}]}), "sepsis")  # no query


def test_plain_terms_strips_pubmed_syntax():
    q = '("vitamin D"[MeSH Terms] OR vitamin[tiab]) AND sepsis[tiab] NOT review[pt]'
    assert plain_terms(q) == "vitamin D vitamin sepsis review"


def test_generate_candidates_trials_query_fallback():
    llm = FakeLLM(
        {
            "candidates": [
                {"title": "A", "axis": "x", "pubmed_query": "sepsis[tiab] AND fluids"},
                {
                    "title": "B",
                    "axis": "y",
                    "pubmed_query": "q",
                    "trials_query": "given plainly",
                },
            ]
        }
    )
    out = generate_candidates(llm, "sepsis", min_n=1, max_n=4)
    assert out[0].trials_query == "sepsis fluids"  # derived from pubmed_query
    assert out[1].trials_query == "given plainly"  # used as given


# -- gates -------------------------------------------------------------------
TH = Thresholds(min_eligible_studies=8, max_records_to_screen=400, recent_review_years=4)


def test_gate_rejects_too_few():
    r = apply_gates(3, 0, TH)
    assert not r.passed and "only 3 eligible" in r.reasons[0]


def test_gate_rejects_too_many():
    r = apply_gates(5000, 0, TH)
    assert not r.passed and "to screen" in r.reasons[0]


def test_gate_rejects_recent_review():
    r = apply_gates(50, 2, TH)
    assert not r.passed and "systematic review" in r.reasons[0]


def test_gate_passes_in_band():
    assert apply_gates(50, 0, TH).passed


# -- assessment (with mocked APIs) -------------------------------------------
def make_sources(handler, tmp_path):
    def http():
        return CachedHttpClient(
            cache_dir=tmp_path / str(id(object())),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )

    return PubMedClient(http=http()), ClinicalTrialsClient(http=http())


def routed_handler(eligible, recent, active):
    def handler(request):
        if "clinicaltrials" in request.url.host:
            params = dict(request.url.params)
            n = active if "filter.overallStatus" in params else 999
            return httpx.Response(200, json={"totalCount": n})
        term = dict(request.url.params).get("term", "")
        count = recent if "systematic[sb]" in term else eligible
        return httpx.Response(200, json={"esearchresult": {"count": str(count)}})

    return handler


def test_assess_candidate_passes_and_flags_prospero(tmp_path):
    pubmed, ct = make_sources(routed_handler(eligible=50, recent=0, active=2), tmp_path)
    cand = Candidate("Title", "population", "sepsis fluids")
    a = assess_candidate(pubmed, ct, cand, TH, current_year=2026)
    assert a.gate.passed
    assert a.eligible_studies == 50 and a.recent_reviews == 0 and a.active_trials == 2
    assert any("PROSPERO" in m for m in a.manual_checks)
    assert any("still running" in m for m in a.manual_checks)  # active>0 note


def test_assess_candidate_rejected_by_recent_review(tmp_path):
    pubmed, ct = make_sources(routed_handler(eligible=50, recent=1, active=0), tmp_path)
    a = assess_candidate(pubmed, ct, Candidate("T", "x", "q"), TH, current_year=2026)
    assert not a.gate.passed
    assert a.active_trials == 0
    assert not any("still running" in m for m in a.manual_checks)


def test_assess_candidate_trial_failure_is_nonfatal(tmp_path):
    # ClinicalTrials.gov returns 400 (e.g. bad query) — must not abort the screen.
    def handler(request):
        if "clinicaltrials" in request.url.host:
            return httpx.Response(400, text="bad request")
        term = dict(request.url.params).get("term", "")
        count = 0 if "systematic[sb]" in term else 50
        return httpx.Response(200, json={"esearchresult": {"count": str(count)}})

    pubmed, ct = make_sources(handler, tmp_path)
    a = assess_candidate(pubmed, ct, Candidate("T", "x", "q"), TH, current_year=2026)
    assert a.gate.passed  # PubMed-based gates still decided
    assert a.active_trials is None
    assert any("Trial check failed" in m for m in a.manual_checks)


# -- ranking + end-to-end ----------------------------------------------------
def test_rank_survivors_orders_by_evidence(tmp_path):
    def a(elig, passed):
        from guide_pipeline.candidates import CandidateAssessment, GateResult

        return CandidateAssessment(
            candidate=Candidate("t", "a", "q"),
            eligible_studies=elig,
            recent_reviews=0,
            active_trials=0,
            gate=GateResult(passed, [] if passed else ["x"]),
            manual_checks=[],
        )

    ranked = rank_survivors([a(20, True), a(90, True), a(999, False), a(50, True)])
    assert [x.eligible_studies for x in ranked] == [90, 50, 20]


def test_screen_candidates_end_to_end(tmp_path):
    llm = FakeLLM(
        {
            "candidates": [
                {"title": "Good", "axis": "population", "pubmed_query": "good"},
                {"title": "Also", "axis": "outcome", "pubmed_query": "also"},
            ]
        }
    )
    pubmed, ct = make_sources(routed_handler(eligible=50, recent=0, active=0), tmp_path)
    result = screen_candidates(llm, pubmed, ct, "sepsis", TH, current_year=2026)
    assert len(result.assessments) == 2
    assert result.top is not None and result.top.gate.passed
