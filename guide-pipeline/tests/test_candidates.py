from datetime import date

import httpx
import pytest

from guide_pipeline.candidates import (
    AXES,
    HIGH_YIELD_AXES,
    Candidate,
    CandidateAssessment,
    RequestPreferences,
    assess_candidate,
    generate_candidates,
    plain_terms,
    rank_survivors,
    screen_candidates,
)
from guide_pipeline.http import CachedHttpClient
from guide_pipeline.llm import LLMError
from guide_pipeline.prospero import ProsperoMirror, ProsperoRecord, StaleMirrorError
from guide_pipeline.settings import Thresholds
from guide_pipeline.sources.clinicaltrials import ClinicalTrialsClient
from guide_pipeline.sources.pubmed import PubMedClient


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system, user, schema=None):
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

    def complete_json(self, system, user, schema=None):
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


# -- triage + gates (with mocked APIs and a real temp mirror) ---------------
TH = Thresholds(min_eligible_studies=8, max_records_to_screen=400, recent_review_years=4)
TODAY = date(2026, 9, 25)


def make_sources(handler, tmp_path):
    def http():
        return CachedHttpClient(
            cache_dir=tmp_path / str(id(object())),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )

    return PubMedClient(http=http()), ClinicalTrialsClient(http=http())


def make_mirror(tmp_path, titles=()):
    m = ProsperoMirror(tmp_path / "prospero.sqlite")
    m.merge([ProsperoRecord(f"CRD{i}", t, date(2025, 1, 1)) for i, t in enumerate(titles)])
    m.log_refresh("automated", covered_to=TODAY, added=len(titles), updated=0)
    return m


def routed_handler(records=200, eligible=50, recent=0, soon=0, protocols=()):
    """PubMed/CT.gov stand-in routing on which filter the query carries."""

    def handler(request):
        params = dict(request.url.params)
        if "clinicaltrials" in request.url.host:
            return httpx.Response(200, json={"totalCount": soon})
        if request.url.path.endswith("/esummary.fcgi"):
            ids = params["id"].split(",")
            res = {"uids": ids, **{i: {"title": t} for i, (_, t) in zip(ids, protocols)}}
            return httpx.Response(200, json={"result": res})
        term = params.get("term", "")
        if "protocol[ti]" in term:
            n = len(protocols)
            ids = [pmid for pmid, _ in protocols]
            return httpx.Response(200, json={"esearchresult": {"count": str(n), "idlist": ids}})
        if "NOT (review[pt]" in term:
            n = eligible
        elif "AND systematic[sb]" in term:
            n = recent
        else:
            n = records
        return httpx.Response(200, json={"esearchresult": {"count": str(n)}})

    return handler


def assess(tmp_path, handler, cand=None, mirror_titles=(), **kw):
    pubmed, ct = make_sources(handler, tmp_path)
    return assess_candidate(
        pubmed, ct, make_mirror(tmp_path, mirror_titles),
        cand or Candidate("Vitamin D and mortality in sepsis", "Unpooled outcome", "q"),
        TH, today=TODAY, **kw,
    )


def test_assess_runs_three_counts_from_one_concept_query(tmp_path):
    a = assess(tmp_path, routed_handler(records=300, eligible=40, recent=0, soon=0))
    assert (a.counts.records_to_screen, a.counts.eligible_studies, a.counts.recent_reviews) == (
        300, 40, 0
    )
    assert a.verdict.outcome == "pass"
    queries = [r.query for r in a.searches]
    assert queries[0] == "q"
    assert queries[1].startswith("(q) NOT (review[pt]")
    assert queries[2].startswith("(q) AND systematic[sb]") and "pub year >= 2023" in queries[2]
    assert any("protocol[ti]" in q for q in queries)
    assert any(r.source == "ClinicalTrials.gov" and "completing by 2027-09-2" in r.query
               for r in a.searches)
    assert a.prospero.checked_on == TODAY and a.prospero.verdict == "clear"


def test_assess_rejects_on_registered_prospero_protocol(tmp_path):
    a = assess(
        tmp_path, routed_handler(),
        mirror_titles=["Vitamin D and mortality in sepsis: a systematic review"],
    )
    assert a.verdict.outcome == "reject"
    assert any("PROSPERO CRD0" in r for r in a.verdict.reasons)


def test_assess_rejects_on_published_protocol(tmp_path):
    handler = routed_handler(protocols=[("999", "Vitamin D and mortality in sepsis: a protocol")])
    a = assess(tmp_path, handler)
    assert a.counts.protocol_matches[0][0] == "999"
    assert a.verdict.outcome == "reject"


def test_assess_flags_trials_and_survives(tmp_path):
    a = assess(tmp_path, routed_handler(soon=2))
    assert a.verdict.outcome == "flag" and a.verdict.passed
    assert a.counts.trials_reporting_soon == 2


def test_assess_trial_failure_is_nonfatal(tmp_path):
    base = routed_handler()

    def handler(request):
        if "clinicaltrials" in request.url.host:
            return httpx.Response(400, text="bad request")
        return base(request)

    a = assess(tmp_path, handler)
    assert a.counts.trials_reporting_soon is None and a.verdict.outcome == "flag"


def test_assess_refuses_stale_mirror(tmp_path):
    pubmed, ct = make_sources(routed_handler(), tmp_path)
    m = ProsperoMirror(tmp_path / "stale.sqlite")
    m.log_refresh("automated", covered_to=date(2026, 8, 1), added=0, updated=0)
    with pytest.raises(StaleMirrorError):
        assess_candidate(pubmed, ct, m, Candidate("T", "Discordance", "q"), TH, today=TODAY)


# -- ranking + end-to-end ----------------------------------------------------
def test_rank_survivors_orders_by_evidence(tmp_path):
    from guide_pipeline.gates import GateVerdict, TriageCounts

    def a(elig, outcome):
        return CandidateAssessment(
            candidate=Candidate("t", "a", "q"),
            counts=TriageCounts(100, elig, 0, 0),
            verdict=GateVerdict(outcome, []),
            prospero=None,
            searches=[],
        )

    ranked = rank_survivors([a(20, "pass"), a(90, "flag"), a(999, "reject"), a(50, "pass")])
    assert [x.counts.eligible_studies for x in ranked] == [90, 50, 20]


def screen(tmp_path, llm, handler, th=TH):
    pubmed, ct = make_sources(handler, tmp_path)
    return screen_candidates(llm, pubmed, ct, make_mirror(tmp_path), "sepsis", th, today=TODAY)


def test_screen_candidates_end_to_end(tmp_path):
    llm = FakeLLM(six_axis_batch())
    result = screen(tmp_path, llm, routed_handler())
    assert len(result.assessments) == 6
    assert result.batches == 1 and len(llm.calls) == 1  # a pass stops generation
    assert result.top is not None and result.top.verdict.passed
    assert all(a.batch == 1 for a in result.assessments)


def eligible_by_query_handler(passing_query):
    """Only the candidate whose concept query is `passing_query` has enough studies."""
    base = routed_handler()

    def handler(request):
        term = dict(request.url.params).get("term", "")
        if "NOT (review[pt]" in term and "clinicaltrials" not in request.url.host:
            n = 50 if term.startswith(f"({passing_query})") else 2
            return httpx.Response(200, json={"esearchresult": {"count": str(n)}})
        return base(request)

    return handler


def test_screen_generates_new_batch_when_all_fail(tmp_path):
    first = six_axis_batch("A")  # all use query "q" -> 2 studies -> all fail
    second = six_axis_batch("B")
    second["candidates"][2]["pubmed_query"] = "winner"
    llm = SeqLLM(first, second)
    result = screen(tmp_path, llm, eligible_by_query_handler("winner"))
    assert result.batches == 2
    assert len(result.assessments) == 12  # every candidate in both batches evaluated
    assert result.top.candidate.title == "B2"
    assert {a.batch for a in result.assessments} == {1, 2}
    # rejected titles from batch 1 were passed back as negative context
    assert "A0" in llm.calls[1][1] and "A5" in llm.calls[1][1]


def test_screen_keeps_downgraded_candidates(tmp_path):
    th = Thresholds(min_eligible_studies=8, scoping_min_studies=5, max_candidate_batches=1)
    result = screen(tmp_path, FakeLLM(six_axis_batch()), routed_handler(eligible=6), th)
    assert result.top is None and len(result.downgraded) == 6


def test_screen_stops_after_max_batches(tmp_path):
    th = Thresholds(min_eligible_studies=8, max_candidate_batches=2)
    llm = SeqLLM(six_axis_batch("A"), six_axis_batch("B"), six_axis_batch("C"))
    result = screen(tmp_path, llm, eligible_by_query_handler("nothing"), th)
    assert result.batches == 2 and len(llm.calls) == 2
    assert result.top is None and not result.survivors


def test_screen_refuses_stale_mirror_before_any_call(tmp_path):
    llm = FakeLLM(six_axis_batch())
    pubmed, ct = make_sources(routed_handler(), tmp_path)
    m = ProsperoMirror(tmp_path / "empty.sqlite")
    with pytest.raises(StaleMirrorError):
        screen_candidates(llm, pubmed, ct, m, "sepsis", TH, today=TODAY)
    assert llm.calls == []


def test_prompt_requires_axes_outside_high_yield():
    llm = FakeLLM(six_axis_batch())
    generate_candidates(llm, "sepsis", min_axes=6)
    assert "At least 2 of the axes you use must be OUTSIDE" in llm.calls[0][1]


# -- request preferences: review type and topic flexibility -------------------
def test_strict_type_does_not_offer_a_downgrade(tmp_path):
    th = Thresholds(min_eligible_studies=8, scoping_min_studies=5, max_candidate_batches=2)
    llm = SeqLLM(six_axis_batch("A"), six_axis_batch("B"))
    result = screen(tmp_path, llm, routed_handler(eligible=6), th)
    assert result.batches == 2  # kept trying other axes instead of settling
    assert result.outcome == "needs_contact" and result.top is None
    assert "type" in result.contact_reason and "scoping" in result.contact_reason


def test_flexible_type_offers_the_best_downgrade_after_all_batches(tmp_path):
    th = Thresholds(min_eligible_studies=8, scoping_min_studies=5, max_candidate_batches=2)
    pubmed, ct = make_sources(routed_handler(eligible=6), tmp_path)
    result = screen_candidates(
        SeqLLM(six_axis_batch("A"), six_axis_batch("B")), pubmed, ct, make_mirror(tmp_path),
        "sepsis", th, today=TODAY, preferences=RequestPreferences(type_flexible=True),
    )
    assert result.batches == 2  # a systematic review was still tried first
    assert result.outcome == "found_other_type"
    assert result.top is not None and result.top.verdict.outcome == "downgrade"


def test_nothing_found_asks_about_topic_when_type_is_already_flexible(tmp_path):
    th = Thresholds(min_eligible_studies=8, max_candidate_batches=1)
    pubmed, ct = make_sources(routed_handler(eligible=0), tmp_path)
    result = screen_candidates(
        FakeLLM(six_axis_batch()), pubmed, ct, make_mirror(tmp_path), "sepsis", th,
        today=TODAY, preferences=RequestPreferences(type_flexible=True),
    )
    assert result.outcome == "needs_contact"
    assert "topic" in result.contact_reason and "type" not in result.contact_reason


def test_first_batch_stays_on_topic_later_batches_broaden_per_flexibility():
    exact = RequestPreferences(topic_flexibility="exact")
    within = RequestPreferences(topic_flexibility="specialty", specialties=("Cardiology",))
    first = FakeLLM(six_axis_batch())
    generate_candidates(first, "sepsis", preferences=within, batch=1)
    assert "Stay strictly within the stated topic" in first.calls[0][1]
    later = FakeLLM(six_axis_batch())
    generate_candidates(later, "sepsis", preferences=within, batch=2)
    assert "within Cardiology" in later.calls[0][1]
    strict_later = FakeLLM(six_axis_batch())
    generate_candidates(strict_later, "sepsis", preferences=exact, batch=3)
    assert "Stay strictly within the stated topic" in strict_later.calls[0][1]


def test_later_batches_are_told_which_axes_failed(tmp_path):
    first = six_axis_batch("A")
    second = six_axis_batch("B")
    second["candidates"][2]["pubmed_query"] = "winner"
    llm = SeqLLM(first, second)
    screen(tmp_path, llm, eligible_by_query_handler("winner"))
    prompt = llm.calls[1][1]
    assert "Axes already tried without success" in prompt and "Discordance" in prompt


def test_publication_type_is_named_in_the_prompt():
    llm = FakeLLM(six_axis_batch())
    generate_candidates(llm, "sepsis", preferences=RequestPreferences(publication_type="narrative review"))
    assert "narrative review" in llm.calls[0][1]


def test_candidate_calls_send_the_axis_enum_schema():
    seen = []

    class SchemaLLM(FakeLLM):
        def complete_json(self, system, user, schema=None):
            seen.append(schema)
            return super().complete_json(system, user)

    generate_candidates(SchemaLLM(six_axis_batch()), "sepsis")
    axis = seen[0]["properties"]["candidates"]["items"]["properties"]["axis"]
    assert axis["enum"] == list(AXES)


def test_titles_offered_elsewhere_are_avoided_from_the_first_batch(tmp_path):
    llm = FakeLLM(six_axis_batch())
    pubmed, ct = make_sources(routed_handler(), tmp_path)
    screen_candidates(llm, pubmed, ct, make_mirror(tmp_path), "sepsis", TH, today=TODAY,
                      avoid_titles=("Title offered to another customer",))
    assert "Title offered to another customer" in llm.calls[0][1]
