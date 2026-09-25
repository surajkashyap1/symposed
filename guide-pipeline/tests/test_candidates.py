import httpx
import pytest

from guide_pipeline.candidates import (
    AXES,
    HIGH_YIELD_AXES,
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
# Six distinct spec axes — the minimum a batch must cover.
SIX = [
    "Unexamined subgroup",
    "Unpooled outcome",
    "Superseded review",
    "Indirect comparison",
    "Emerging technology",
    "Discordance",
]


def cand(title, axis, query="q"):
    return {"title": title, "axis": axis, "pubmed_query": query}


def six_axis_batch(prefix="T"):
    return {"candidates": [cand(f"{prefix}{i}", ax) for i, ax in enumerate(SIX)]}


class SeqLLM:
    """Returns each payload in turn (the last one repeats)."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        idx = min(len(self.calls) - 1, len(self.payloads) - 1)
        return self.payloads[idx]


def test_generate_candidates_parses_and_filters():
    payload = six_axis_batch()
    payload["candidates"] += [
        {"title": "", "axis": "Unpooled outcome", "pubmed_query": "q2"},  # no title
        {"title": "C", "axis": "Unpooled outcome", "pubmed_query": ""},  # no query
    ]
    payload["candidates"][0]["rationale"] = "r"
    out = generate_candidates(FakeLLM(payload), "sepsis")
    assert [c.title for c in out] == [f"T{i}" for i in range(6)]
    assert out[0].rationale == "r"


def test_generate_candidates_raises_when_empty():
    with pytest.raises(LLMError):
        generate_candidates(FakeLLM({"candidates": []}), "sepsis")
    with pytest.raises(LLMError):
        generate_candidates(FakeLLM({"candidates": [{"title": "x"}]}), "sepsis")  # no query


def test_prompt_lists_all_14_axes_and_two_person_rule():
    llm = FakeLLM(six_axis_batch())
    generate_candidates(llm, "sepsis")
    _system, user = llm.calls[0]
    for axis in AXES:
        assert axis in user
    assert "at least two people" in user
    for axis in HIGH_YIELD_AXES:
        assert axis in HIGH_YIELD_AXES and axis in AXES


def test_axis_names_are_normalised_and_unknown_axes_dropped():
    payload = six_axis_batch()
    payload["candidates"][0]["axis"] = "  unexamined SUBGROUP "  # case/space tolerant
    payload["candidates"].append(cand("Bad", "population"))  # old generic axis
    out = generate_candidates(FakeLLM(payload), "sepsis")
    assert out[0].axis == "Unexamined subgroup"
    assert "Bad" not in [c.title for c in out]


def test_no_more_than_two_candidates_per_axis():
    payload = six_axis_batch()
    payload["candidates"] += [cand(f"Extra{i}", "Discordance") for i in range(3)]
    out = generate_candidates(FakeLLM(payload), "sepsis")
    assert sum(c.axis == "Discordance" for c in out) == 2
    assert [c.title for c in out if c.axis == "Discordance"] == ["T5", "Extra0"]


def test_too_few_axes_is_topped_up_from_unused_axes():
    narrow = {"candidates": [cand(f"N{i}", SIX[i % 3]) for i in range(6)]}  # 3 axes
    top_up = {
        "candidates": [
            cand("N0", "Emerging technology"),  # duplicate title -> dropped
            cand("U1", "Indirect comparison"),
            cand("U2", "Emerging technology"),
            cand("U3", "Discordance"),
        ]
    }
    llm = SeqLLM(narrow, top_up)
    out = generate_candidates(llm, "sepsis")
    assert len(llm.calls) == 2
    prompt = llm.calls[1][1]
    assert "Unexamined subgroup:" not in prompt  # already-used axes not offered
    assert "Discordance:" in prompt and "- N0" in prompt  # unused axes + taken titles
    assert [c.title for c in out] == [f"N{i}" for i in range(6)] + ["U1", "U2", "U3"]
    assert len({c.axis for c in out}) == 6


def test_top_up_respects_per_axis_cap_across_calls():
    narrow = {"candidates": [cand(f"N{i}", SIX[i % 5]) for i in range(10)]}  # 5 axes x2
    top_up = {"candidates": [cand("X", SIX[0]), cand("Y", "Timing or dose")]}
    out = generate_candidates(SeqLLM(narrow, top_up), "sepsis")
    assert "X" not in [c.title for c in out]  # SIX[0] already has 2
    assert "Y" in [c.title for c in out]


def test_too_few_axes_after_top_ups_raises():
    narrow = {"candidates": [cand(f"N{i}", SIX[i % 3]) for i in range(6)]}
    llm = SeqLLM(narrow)  # every top-up repeats the same (now duplicate) titles
    with pytest.raises(LLMError, match="distinct axes"):
        generate_candidates(llm, "sepsis")
    assert len(llm.calls) == 3  # first call + 2 top-ups


def test_avoided_titles_are_in_prompt_and_never_returned():
    payload = six_axis_batch()
    payload["candidates"].append(cand("Old, Rejected title!", "Timing or dose"))
    llm = FakeLLM(payload)
    out = generate_candidates(llm, "sepsis", avoid=["old rejected title"])
    assert "old rejected title" in llm.calls[0][1]
    assert "Old, Rejected title!" not in [c.title for c in out]  # normalised match


def test_plain_terms_strips_pubmed_syntax():
    q = '("vitamin D"[MeSH Terms] OR vitamin[tiab]) AND sepsis[tiab] NOT review[pt]'
    assert plain_terms(q) == "vitamin D vitamin sepsis review"


def test_generate_candidates_trials_query_fallback():
    payload = six_axis_batch()
    payload["candidates"][0]["pubmed_query"] = "sepsis[tiab] AND fluids"
    payload["candidates"][1]["trials_query"] = "given plainly"
    out = generate_candidates(FakeLLM(payload), "sepsis")
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
    llm = FakeLLM(six_axis_batch())
    pubmed, ct = make_sources(routed_handler(eligible=50, recent=0, active=0), tmp_path)
    result = screen_candidates(llm, pubmed, ct, "sepsis", TH, current_year=2026)
    assert len(result.assessments) == 6
    assert result.batches == 1 and len(llm.calls) == 1  # a pass stops generation
    assert result.top is not None and result.top.gate.passed
    assert all(a.batch == 1 for a in result.assessments)


def eligible_by_title_handler(passing_query):
    """Only candidates whose query is `passing_query` have a workable count."""

    def handler(request):
        if "clinicaltrials" in request.url.host:
            return httpx.Response(200, json={"totalCount": 0})
        term = dict(request.url.params).get("term", "")
        if "systematic[sb]" in term:
            count = 0
        else:
            count = 50 if term == passing_query else 2
        return httpx.Response(200, json={"esearchresult": {"count": str(count)}})

    return handler


def test_screen_generates_new_batch_when_all_fail(tmp_path):
    first = six_axis_batch("A")  # all use query "q" -> 2 studies -> all fail
    second = six_axis_batch("B")
    second["candidates"][2]["pubmed_query"] = "winner"
    llm = SeqLLM(first, second)
    pubmed, ct = make_sources(eligible_by_title_handler("winner"), tmp_path)
    result = screen_candidates(llm, pubmed, ct, "sepsis", TH, current_year=2026)
    assert result.batches == 2
    assert len(result.assessments) == 12  # every candidate in both batches evaluated
    assert result.top.candidate.title == "B2"
    assert {a.batch for a in result.assessments} == {1, 2}
    # rejected titles from batch 1 were passed back as negative context
    assert "A0" in llm.calls[1][1] and "A5" in llm.calls[1][1]


def test_screen_stops_after_max_batches(tmp_path):
    th = Thresholds(min_eligible_studies=8, max_candidate_batches=2)
    llm = SeqLLM(six_axis_batch("A"), six_axis_batch("B"), six_axis_batch("C"))
    pubmed, ct = make_sources(eligible_by_title_handler("nothing"), tmp_path)
    result = screen_candidates(llm, pubmed, ct, "sepsis", th, current_year=2026)
    assert result.batches == 2 and len(llm.calls) == 2
    assert result.top is None and not result.survivors


def test_prompt_requires_axes_outside_high_yield():
    llm = FakeLLM(six_axis_batch())
    generate_candidates(llm, "sepsis", min_axes=6)
    assert "At least 2 of the axes you use must be OUTSIDE" in llm.calls[0][1]
