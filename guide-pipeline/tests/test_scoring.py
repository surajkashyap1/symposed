from datetime import date, datetime, timezone

import pytest

from guide_pipeline.candidates import Candidate, CandidateAssessment, RequestPreferences
from guide_pipeline.gates import GateVerdict, TriageCounts
from guide_pipeline.llm import LLMError
from guide_pipeline.prospero import ProsperoCheck, ProsperoMatch
from guide_pipeline.scoring import (
    TIE_SCHEMA,
    ScoreWeights,
    Selection,
    break_tie,
    rank,
    rescore,
    score_candidate,
    tied_leaders,
)
from guide_pipeline.settings import Thresholds

TH = Thresholds(max_records_to_screen=400, workable_min_studies=12, workable_max_studies=40)
PREFS = RequestPreferences(collaborators=2, context="The user is a Foundation doctor.")


def assessment(title="Statins and delirium in older adults", axis="Discordance", eligible=30,
               records=100, prospero_score=None, protocols=(), outcome="pass", rationale="r"):
    matches = [ProsperoMatch("CRD1", "x", date(2025, 1, 1), prospero_score)] if prospero_score else []
    return CandidateAssessment(
        candidate=Candidate(title, axis, "q", rationale=rationale),
        counts=TriageCounts(records, eligible, 0, 0, list(protocols)),
        verdict=GateVerdict(outcome, []),
        prospero=ProsperoCheck("t", "t", date(2026, 9, 28), date(2026, 9, 28),
                               datetime(2026, 9, 28, tzinfo=timezone.utc), "clear", matches),
        searches=[],
    )


def score(a, share=1.0, topic="statins delirium", **kw):
    return score_candidate(a, recent_share=share, preferences=PREFS, topic=topic,
                           thresholds=TH, weights=kw.pop("weights", ScoreWeights()), **kw)


def test_components_follow_the_spec_factors():
    s = score(assessment(eligible=30, records=100, prospero_score=0.3), share=0.6)
    c = s.components
    assert c["workable"] == 1.0  # inside 12-40
    assert c["recency"] == 0.6
    assert c["rationale"] == 1.0  # Discordance is a high-yield axis
    assert c["alignment"] == 1.0  # every topic word is in the title
    assert c["feasibility"] == 0.75  # 100 of a 400 cap
    assert c["distance"] == 0.7  # nearest registered protocol 0.3
    assert s.total == pytest.approx(sum(c.values()) / 6, abs=1e-4)


def test_workable_band_tapers_outside():
    assert score(assessment(eligible=6)).components["workable"] == 0.5
    assert score(assessment(eligible=220)).components["workable"] == 0.5  # halfway to the cap
    assert score(assessment(eligible=500)).components["workable"] == 0.0


def test_distance_uses_the_nearer_of_prospero_and_published_protocols():
    a = assessment(prospero_score=0.3, protocols=[("9", "p", 0.6)])
    assert score(a).components["distance"] == 0.4


def test_rationale_and_alignment_grades():
    assert score(assessment(axis="Timing or dose")).components["rationale"] == 0.5
    assert score(assessment(axis="Timing or dose", rationale="")).components["rationale"] == 0.0
    assert score(assessment(), topic="statins falls").components["alignment"] == 0.5
    assert score(assessment(), topic="").components["alignment"] == 1.0  # no preference


def test_weights_are_configurable(monkeypatch):
    monkeypatch.setenv("SCORE_WEIGHT_DISTANCE", "5")
    w = ScoreWeights.from_env()
    assert w.distance == 5.0 and w.workable == 1.0
    near = score(assessment(prospero_score=0.9), weights=w)
    far = score(assessment(prospero_score=0.1), weights=w)
    assert far.total - near.total > score(assessment(prospero_score=0.1)).total - score(
        assessment(prospero_score=0.9)).total


def test_clear_leader_goes_alone_otherwise_tied_capped():
    a, b, c, d = (score(assessment(title=t, prospero_score=p)) for t, p in
                  (("A", 0.0), ("B", 0.05), ("C", 0.1), ("D", 0.9)))
    ranked = rank([d, c, b, a])
    assert [s.assessment.candidate.title for s in ranked][:1] == ["A"]
    assert [s.assessment.candidate.title for s in tied_leaders(ranked, margin=0.001, max_tied=3)] == ["A"]
    tied = tied_leaders(ranked, margin=0.05, max_tied=2)
    assert [s.assessment.candidate.title for s in tied] == ["A", "B"]  # D far behind, cap 2


def test_rescore_uses_the_screened_count():
    s = score(assessment(eligible=30))
    r = rescore(s, screened_eligible=5, recent_share=1.0, preferences=PREFS, topic="statins delirium",
                thresholds=TH, weights=ScoreWeights())
    assert r.components["workable"] < s.components["workable"]
    assert r.eligible_basis.startswith("screened")


class TieLLM:
    def __init__(self, choice):
        self.choice, self.user = choice, ""

    def complete_json(self, system, user, schema=None, cache_system=False):
        assert schema is TIE_SCHEMA
        self.user = user
        return {"choice": self.choice, "summary": "B is more useful.",
                "rationale": [{"criterion": "Clinical usefulness", "assessment": "B"}]}


def test_tie_break_records_choice_rationale_and_allows_override():
    tied = [(score(assessment(title="A")), "12 eligible"), (score(assessment(title="B")), "20 eligible")]
    llm = TieLLM(choice=1)
    tb = break_tie(llm, tied, preferences=PREFS)
    assert "Clinical usefulness" in llm.user and "20 eligible" in llm.user
    assert "never papers" in llm.user and "Foundation doctor" in llm.user
    assert tb.final_choice == 1 and tb.summary == "B is more useful."
    tb.reviewer_override, tb.override_reason = 0, "A fits the user's interest better"
    d = tb.as_dict()
    assert (d["model_choice"], d["final_choice"]) == (1, 0)


def test_tie_break_refuses_gate_failures_and_bad_indices():
    ok = (score(assessment(title="A")), "x")
    failed = (score(assessment(title="F", outcome="reject")), "x")
    with pytest.raises(ValueError):
        break_tie(TieLLM(0), [ok, failed], preferences=PREFS)
    with pytest.raises(LLMError):
        break_tie(TieLLM(7), [ok, ok], preferences=PREFS)


def test_selection_keeps_unchosen_candidates():
    a, b = score(assessment(title="A")), score(assessment(title="B"))
    sel = Selection(initial=[a, b], tied=[a, b], winner=b)
    assert sel.as_dict()["unchosen"] == ["A"] and sel.as_dict()["winner"] == "B"
