import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from guide_pipeline import run as run_mod
from guide_pipeline.candidates import (
    FOUND,
    NEEDS_CONTACT,
    Candidate,
    CandidateAssessment,
    ScreenResult,
    SearchRun,
)
from guide_pipeline.gates import GateResult, GateVerdict, TriageCounts
from guide_pipeline.llm import UsageMeter
from guide_pipeline.prospero import ProsperoCheck, ProsperoMirror, StaleMirrorError
from guide_pipeline.request import from_proforma
from guide_pipeline.retrieval import RetrievalResult
from guide_pipeline.screening import (
    LIKELY_ELIGIBLE,
    UNCLEAR,
    Criteria,
    HeterogeneityCheck,
    ScreenedPaper,
    ScreeningResult,
)
from guide_pipeline.settings import Settings
from guide_pipeline.sources.pubmed import Paper

FORM = {"grade": "Foundation doctor", "specialties": ["Cardiology"],
        "topics": "Heart failure", "publicationType": "Systematic review",
        "collaborators": "1", "hoursPerWeek": "3 to 5"}


def assessment(title, outcome, axis="Discordance", eligible=30):
    return CandidateAssessment(
        candidate=Candidate(title, axis, "heart failure[tiab]"),
        counts=TriageCounts(120, eligible, 0, 0),
        verdict=GateVerdict(outcome, [GateResult("too_few_studies", outcome, eligible, 8, ""),
                                      GateResult("already_reviewed", "pass", 0, 0, "")]),
        prospero=ProsperoCheck("t", "t", date(2026, 9, 27), date(2026, 9, 27),
                               datetime(2026, 9, 27, tzinfo=timezone.utc), "clear", []),
        searches=[SearchRun("PubMed", "heart failure[tiab]", 120, "now")],
    )


def fresh_mirror(tmp_path):
    m = ProsperoMirror(tmp_path / "p.sqlite")
    m.log_refresh("automated", covered_to=date.today(), added=0, updated=0)
    return m


@pytest.fixture
def stubbed(monkeypatch):
    """Replace every network/model stage with a recorded fake."""
    calls = {}

    def paper(pmid):
        return Paper(pmid, f"Paper {pmid}", "abs", ("A B",), "J", 2024, None)

    monkeypatch.setattr(run_mod, "assess_landscape", lambda *a, **k: None)
    monkeypatch.setattr(run_mod, "write_criteria",
                        lambda *a, **k: Criteria("adults", "drug", "placebo", "death", "RCTs"))

    def fake_retrieve(pubmed, query, *, max_records):
        calls["query"], calls["max_records"] = query, max_records
        return RetrievalResult(query, [paper("1"), paper("2"), paper("3")])

    def fake_screen(extract, screen, criteria, papers, **kw):
        calls["screened"] = [p.pmid for p in papers]
        items = [ScreenedPaper(p, {}, LIKELY_ELIGIBLE if p.pmid == "1" else UNCLEAR, "r",
                               "abstract only") for p in papers]
        return ScreeningResult(criteria, items, HeterogeneityCheck({"death": ["1"]}, 5),
                               full_text_screened=1,
                               counts={LIKELY_ELIGIBLE: 1, UNCLEAR: len(items) - 1})

    monkeypatch.setattr(run_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(run_mod, "screen_papers", fake_screen)
    return calls


def settings_for(tmp_path):
    return Settings(output_dir=tmp_path / "out", prospero_db=tmp_path / "p.sqlite")


def run(tmp_path, monkeypatch, screen_result, **kw):
    monkeypatch.setattr(run_mod, "screen_candidates", lambda *a, **k: screen_result)
    meter = UsageMeter()
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    meter.record("claude-sonnet-5", "candidate_generation", usage)  # $2
    meter.record("claude-sonnet-5", "screening", usage)  # $2
    llms = {t: object() for t in ("candidate_generation", "criteria_writing",
                                  "attribute_extraction", "screening", "outcome_grouping")}
    llms["tie_break"] = kw.pop("tie_llm", object())
    # scoring asks PubMed how much of the eligible evidence is recent
    sources = SimpleNamespace(pubmed=SimpleNamespace(count=lambda q, **kw: 15),
                              clinicaltrials=None, europepmc=None)
    return run_mod.run_request(
        from_proforma(FORM, order_id="order-1"), settings=settings_for(tmp_path),
        sources=sources, mirror=fresh_mirror(tmp_path), llms=llms, meter=meter, **kw)


def found(tmp_path=None):
    top = assessment("Winner", "pass")
    return ScreenResult([top, assessment("Loser", "reject", "Timing or dose", 2)], [top], top,
                        batches=1, outcome=FOUND)


def test_found_run_writes_guide_results_and_metrics(tmp_path, monkeypatch, stubbed):
    report = run(tmp_path, monkeypatch, found())
    assert report.outcome == FOUND and report.title == "Winner"
    assert report.guide_path.endswith("guide.docx")
    assert stubbed["query"].startswith("(heart failure[tiab]) NOT (review[pt]")  # SR filter
    assert stubbed["max_records"] == 400  # team of 2 ("1 other person")

    m = report.metrics
    assert m["order_id"] == "order-1" and m["topic_given"] is True
    assert m["candidates_generated"] == 2 and m["candidates_passed"] == 1
    assert m["pass_rate"] == 0.5 and m["chosen_axis"] == "Discordance"
    assert m["gate_outcomes"]["too_few_studies"] == {"pass": 1, "reject": 1}
    assert m["papers_screened"] == 3 and m["full_text_share"] == 0.333
    assert m["cost_usd"] == 4.0 and m["cost_candidates_usd"] == 2.0
    assert m["cost_per_screened_paper_usd"] == pytest.approx(2 / 3, abs=1e-4)
    assert set(m["seconds_by_stage"]) >= {"landscape", "candidates", "criteria",
                                           "retrieval", "screening", "guide"}

    line = (tmp_path / "out" / "metrics.jsonl").read_text().splitlines()
    assert json.loads(line[0])["order_id"] == "order-1"
    results = json.loads(report.workspace.results_path.read_text())
    assert results["title"] == "Winner" and results["prospero_check"]["verdict"] == "clear"
    assert len(results["candidates"]) == 2 and results["metrics"] == json.loads(line[0])


def test_limit_caps_papers_screened(tmp_path, monkeypatch, stubbed):
    report = run(tmp_path, monkeypatch, found(), limit=2)
    assert stubbed["screened"] == ["1", "2"]
    assert report.metrics["papers_retrieved"] == 3 and report.metrics["papers_screened"] == 2


def test_needs_contact_stops_before_screening_but_records_metrics(tmp_path, monkeypatch, stubbed):
    nothing = ScreenResult([assessment("Loser", "reject")], [], None, batches=3,
                           outcome=NEEDS_CONTACT, contact_reason="ask about topic")
    report = run(tmp_path, monkeypatch, nothing)
    assert report.outcome == NEEDS_CONTACT and report.guide_path == ""
    assert "screened" not in stubbed
    assert report.metrics["outcome"] == NEEDS_CONTACT and report.metrics["batches"] == 3
    results = json.loads(report.workspace.results_path.read_text())
    assert results["contact_reason"] == "ask about topic"


def test_stale_mirror_refuses_before_spending(tmp_path, monkeypatch, stubbed):
    m = ProsperoMirror(tmp_path / "stale.sqlite")
    monkeypatch.setattr(run_mod, "screen_candidates", lambda *a, **k: pytest.fail("ran"))
    with pytest.raises(StaleMirrorError):
        run_mod.run_request(from_proforma(FORM), settings=settings_for(tmp_path),
                            sources=SimpleNamespace(), mirror=m, llms={}, meter=UsageMeter())


def test_summary_splits_blank_and_given_topics(tmp_path):
    path = tmp_path / "metrics.jsonl"
    rows = [
        {"topic_given": True, "outcome": "found", "cost_usd": 6.0, "cost_candidates_usd": 0.2,
         "cost_per_screened_paper_usd": 0.02, "batches": 2, "pass_rate": 0.1, "seconds_total": 600},
        {"topic_given": False, "outcome": "found", "cost_usd": 5.0, "cost_candidates_usd": 0.1,
         "cost_per_screened_paper_usd": 0.02, "batches": 1, "pass_rate": 0.3, "seconds_total": 500},
        {"topic_given": False, "outcome": "needs_contact", "cost_usd": 0.3,
         "cost_candidates_usd": 0.3, "cost_per_screened_paper_usd": None, "batches": 3,
         "pass_rate": 0.0, "seconds_total": 100},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    s = run_mod.summarise_metrics(path)
    assert s["runs"] == 3
    assert s["topic_given"]["runs"] == 1 and s["topic_given"]["mean_cost_usd"] == 6.0
    assert s["blank_topic"]["found_rate"] == 0.5
    assert s["blank_topic"]["mean_cost_per_paper_usd"] == 0.02  # None ignored


def test_clear_winner_is_screened_alone(tmp_path, monkeypatch, stubbed):
    near = assessment("Near-identical", "pass", eligible=30)
    weak = assessment("Weak", "pass", axis="Timing or dose", eligible=300)
    result = ScreenResult([near, weak], [weak, near], weak, batches=1, outcome=FOUND)
    report = run(tmp_path, monkeypatch, result)
    # scoring, not "most studies", picks the winner, and only it is screened
    assert report.title == "Near-identical"
    assert report.metrics["tied_candidates"] == 1 and not report.metrics["tie_break_used"]
    assert report.selection.as_dict()["unchosen"] == ["Weak"]


class TieLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None, cache_system=False):
        self.calls += 1
        return {"choice": 1, "summary": "second is more useful", "rationale": []}


def test_tied_candidates_are_each_screened_then_tie_broken(tmp_path, monkeypatch, stubbed):
    a, b = assessment("Alpha", "pass"), assessment("Beta", "pass")
    result = ScreenResult([a, b], [a, b], a, batches=1, outcome=FOUND)
    tie = TieLLM()
    report = run(tmp_path, monkeypatch, result, tie_llm=tie)
    assert tie.calls == 1  # identical scores even after re-scoring
    assert report.title == "Beta" and report.metrics["tie_break_used"]
    assert report.metrics["tied_candidates"] == 2
    sel = json.loads(report.workspace.results_path.read_text())["selection"]
    assert sel["tie_break"]["model_choice"] == 1 and sel["unchosen"] == ["Alpha"]
    assert len(sel["rescored"]) == 2


def test_output_folder_is_named_after_the_chosen_question(tmp_path, monkeypatch, stubbed):
    near = assessment("Near-identical", "pass", eligible=30)
    weak = assessment("Weak", "pass", axis="Timing or dose", eligible=300)
    report = run(tmp_path, monkeypatch, ScreenResult([near, weak], [weak, near], weak,
                                                     batches=1, outcome=FOUND))
    assert "near-identical" in report.workspace.dir.name
