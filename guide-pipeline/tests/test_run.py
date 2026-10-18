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

    def fake_retrieve(pubmed, query, *, max_records, **kw):
        calls["concept_query"] = kw.get("concept_query")
        calls["query"], calls["max_records"] = query, max_records
        return RetrievalResult(query, [paper("1"), paper("2"), paper("3")])

    def fake_screen(extract, screen, criteria, papers, **kw):
        calls["screened"] = [p.pmid for p in papers]
        items = [ScreenedPaper(p, {}, LIKELY_ELIGIBLE if p.pmid == "1" else UNCLEAR, "r",
                               "abstract only") for p in papers]
        return ScreeningResult(criteria, items, HeterogeneityCheck({"death": ["1"]}, 5),
                               full_text_screened=1,
                               counts={LIKELY_ELIGIBLE: 1, UNCLEAR: len(items) - 1})

    def fake_assemble(**kw):
        calls["assembled_title"] = kw["title"]
        return SimpleNamespace(
            rationale="why", warnings=["check MeSH"], prospero=None, similar=[], rob_tool="RoB 2",
            timeline=[],
            strategies={"strategies": [SimpleNamespace(name="S", pubmed_query="q", count=7,
                                                       unverified_mesh=[])],
                        "recommended": 0, "embase_emtree": "", "cochrane_central": ""})

    def fake_build_model(content, **kw):
        calls["model_query"] = kw["retrieval_query"]
        return {"title": "Winner"}

    def fake_build_outputs(workspace, model, **kw):
        workspace.guide_path.write_text("guide")
        workspace.pack_path.write_text("pack")
        return {"pdf": workspace.guide_path, "pack": workspace.pack_path}

    monkeypatch.setattr(run_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(run_mod, "screen_papers", fake_screen)
    monkeypatch.setattr(run_mod, "assemble", fake_assemble)
    monkeypatch.setattr(run_mod, "build_model", fake_build_model)
    monkeypatch.setattr(run_mod, "build_outputs", fake_build_outputs)
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
    assert report.guide_path.endswith("guide.pdf")
    assert report.pack_path.endswith("guide-pack.zip")
    assert stubbed["assembled_title"] == "Winner"
    # one MeSH warning, plus: the other candidate was rejected, so no alternatives
    assert report.metrics["guide_warnings"] == 2 and report.metrics["strategy_counts"] == [7]
    assert report.alternatives == [] and not report.swap
    assert stubbed["query"].startswith("(heart failure[tiab]) NOT (review[pt]")  # SR filter
    assert stubbed["max_records"] == 400  # team of 2 ("1 other person")
    assert stubbed["concept_query"] == "heart failure[tiab]"  # preprints use concepts

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


def test_missing_dois_filled_from_crossref_for_plausible_papers_only():
    from guide_pipeline.screening import LIKELY_INELIGIBLE

    papers = [
        ScreenedPaper(Paper("1", "Needs DOI", "a", (), "J", 2021, None), {}, UNCLEAR, "r", "abstract only"),
        ScreenedPaper(Paper("2", "Has DOI", "a", (), "J", 2021, "10.1/has"), {}, UNCLEAR, "r", "abstract only"),
        ScreenedPaper(Paper("3", "Ineligible", "a", (), "J", 2021, None), {}, LIKELY_INELIGIBLE, "r", "abstract only"),
    ]
    screening = ScreeningResult(Criteria("p", "i", "c", "o", "d"), papers)
    asked = []
    crossref = SimpleNamespace(find_doi=lambda t, y: asked.append(t) or "10.5/found")
    assert run_mod.fill_missing_dois(crossref, screening) == 1
    assert asked == ["Needs DOI"]
    assert papers[0].paper.doi == "10.5/found"
    assert papers[0].attributes["doi_source"] == "Crossref (title match)"
    assert run_mod.fill_missing_dois(None, screening) == 0


def _reviews_mode(tmp_path, monkeypatch, screen_result, checks, choose_dir=None):
    from dataclasses import replace as _replace

    from guide_pipeline.discovery import Discovery, FinalCheck

    monkeypatch.setattr(run_mod, "discover",
                        lambda **kw: Discovery(topics=[], trials=[], screen=screen_result))
    seen = []

    def fake_check(**kw):
        title = kw["assessment"].candidate.title
        seen.append(title)
        ok = checks[title]
        return FinalCheck(title, [], [], ok, True, True, {}, "" if ok else "narrow it")

    monkeypatch.setattr(run_mod, "final_check", fake_check)
    # novelty: everything passes unless the test names titles to drop
    drop = checks.get("__not_novel__", set())
    monkeypatch.setattr(run_mod.novelty, "screen", lambda scored, **kw: (
        [x for x in scored if x.assessment.candidate.title not in drop][:kw["want"]], []))
    settings = _replace(settings_for(tmp_path), discovery_mode="reviews")
    meter = UsageMeter()
    llms = {t: object() for t in ("criteria_writing", "attribute_extraction", "screening",
                                  "outcome_grouping", "tie_break", "shortlist_brief",
                                  "novelty_check")}
    sources = SimpleNamespace(pubmed=SimpleNamespace(count=lambda q, **kw: 15),
                              clinicaltrials=None, europepmc=None)
    report = run_mod.run_request(
        from_proforma(FORM, order_id="order-1"), settings=settings, sources=sources,
        mirror=fresh_mirror(tmp_path), llms=llms, meter=meter, store=object(),
        choose_dir=choose_dir)
    return report, seen


def test_reviews_mode_takes_the_best_scored_question_that_passes_the_final_check(
        tmp_path, monkeypatch, stubbed):
    a, b = assessment("First", "pass"), assessment("Second", "pass")
    screen = ScreenResult([a, b], [a, b], a, batches=1, outcome=FOUND)
    report, seen = _reviews_mode(tmp_path, monkeypatch, screen, {"First": False, "Second": True})
    assert report.outcome == FOUND
    assert report.title in ("First", "Second") and report.title == seen[-1]
    assert len(report.final_checks) == len(seen) and report.final_checks[-1].passed
    assert report.metrics["discovery_mode"] == "reviews"


def test_reviews_mode_needs_contact_when_every_final_check_fails(tmp_path, monkeypatch, stubbed):
    a = assessment("Only", "pass")
    screen = ScreenResult([a], [a], a, batches=1, outcome=FOUND)
    report, _ = _reviews_mode(tmp_path, monkeypatch, screen, {"Only": False})
    assert report.outcome == "needs_contact"
    assert "narrow it" in report.screen.contact_reason
    assert report.metrics["final_checks_failed"] == 1


def _three():
    a, b, c = (assessment(t, "pass") for t in ("First", "Second", "Third"))
    return ScreenResult([a, b, c], [a, b, c], a, batches=1, outcome=FOUND)


def test_pick_mode_stops_with_a_shortlist_before_any_final_check(tmp_path, monkeypatch, stubbed):
    from guide_pipeline import shortlist

    folder = tmp_path / "pick"
    with pytest.raises(shortlist.AwaitingChoice) as exc:
        _reviews_mode(tmp_path, monkeypatch, _three(), {}, choose_dir=folder)
    assert len(exc.value.options) == 3
    text = (folder / "SHORTLIST.md").read_text()
    assert "## Option 1: " in text and "**Why it is new.**" in text and "**Scope**" in text
    assert "python -m guide_pipeline pick pick <number>" in text
    assert (folder / "shortlist.docx").exists()


def test_pick_mode_checks_only_the_pick_and_keeps_the_others_as_alternatives(
        tmp_path, monkeypatch, stubbed):
    from guide_pipeline import shortlist

    folder = tmp_path / "pick"
    with pytest.raises(shortlist.AwaitingChoice) as exc:
        _reviews_mode(tmp_path, monkeypatch, _three(), {}, choose_dir=folder)
    picked = exc.value.options[1].title
    shortlist.write_choice(folder, 2)
    report, seen = _reviews_mode(tmp_path, monkeypatch, _three(), {picked: True},
                                 choose_dir=folder)
    assert seen == [picked] and report.title == picked and report.outcome == FOUND
    assert [a.number for a in report.alternatives] == [1, 2]
    assert picked not in [a.title for a in report.alternatives]


def test_a_failed_pick_asks_again_and_cannot_be_picked_twice(tmp_path, monkeypatch, stubbed):
    from guide_pipeline import shortlist

    folder = tmp_path / "pick"
    with pytest.raises(shortlist.AwaitingChoice) as exc:
        _reviews_mode(tmp_path, monkeypatch, _three(), {}, choose_dir=folder)
    first = exc.value.options[0].title
    shortlist.write_choice(folder, 1)
    with pytest.raises(shortlist.AwaitingChoice) as exc:
        _reviews_mode(tmp_path, monkeypatch, _three(), {first: False}, choose_dir=folder)
    assert "Option 1 failed the final check" in exc.value.note
    assert shortlist.read_choice(folder) is None
    assert "narrow it" in (folder / "SHORTLIST.md").read_text()
    shortlist.write_choice(folder, 1)  # the same pick again is refused without a new check
    with pytest.raises(shortlist.AwaitingChoice):
        _, seen = _reviews_mode(tmp_path, monkeypatch, _three(), {}, choose_dir=folder)


def test_questions_that_fail_novelty_never_reach_the_shortlist(tmp_path, monkeypatch, stubbed):
    from guide_pipeline import shortlist

    with pytest.raises(shortlist.AwaitingChoice) as exc:
        _reviews_mode(tmp_path, monkeypatch, _three(), {"__not_novel__": {"Second"}},
                      choose_dir=tmp_path / "pick")
    assert "Second" not in [o.title for o in exc.value.options]


def test_pick_mode_needs_contact_when_nothing_is_novel(tmp_path, monkeypatch, stubbed):
    report, _ = _reviews_mode(tmp_path, monkeypatch, _three(),
                              {"__not_novel__": {"First", "Second", "Third"}},
                              choose_dir=tmp_path / "pick")
    assert report.outcome == "needs_contact"
    assert "novelty" in report.screen.contact_reason


def test_pick_mode_needs_contact_when_every_option_fails(tmp_path, monkeypatch, stubbed):
    from guide_pipeline import shortlist

    a = assessment("Only", "pass")
    screen = ScreenResult([a], [a], a, batches=1, outcome=FOUND)
    folder = tmp_path / "pick"
    shortlist.write_choice(folder, 1)
    report, _ = _reviews_mode(tmp_path, monkeypatch, screen, {"Only": False}, choose_dir=folder)
    assert report.outcome == "needs_contact" and "narrow it" in report.screen.contact_reason


def _swap(tmp_path, monkeypatch, outcome):
    from guide_pipeline.candidates import Candidate

    def fake_assess(pubmed, ct, mirror, cand, th, **kw):
        return assessment(cand.title, outcome)

    monkeypatch.setattr(run_mod, "assess_candidate", fake_assess)
    monkeypatch.setattr(run_mod, "screen_candidates",
                        lambda *a, **k: pytest.fail("a swap must not search for new questions"))
    llms = {t: object() for t in ("criteria_writing", "attribute_extraction", "screening",
                                  "outcome_grouping", "tie_break")}
    sources = SimpleNamespace(pubmed=SimpleNamespace(count=lambda q, **kw: 15),
                              clinicaltrials=None, europepmc=None)
    return run_mod.run_request(
        from_proforma(FORM, order_id="order-1"), settings=settings_for(tmp_path),
        sources=sources, mirror=fresh_mirror(tmp_path), llms=llms, meter=UsageMeter(),
        forced=Candidate("Alternative B", "Gap in existing reviews", "alt_q"))


def test_swap_rechecks_the_alternative_then_writes_its_guide(tmp_path, monkeypatch, stubbed):
    report = _swap(tmp_path, monkeypatch, "pass")
    assert report.outcome == FOUND and report.title == "Alternative B"
    assert report.swap and report.alternatives == []  # no new alternatives on a swap


def test_swap_stops_if_the_alternative_no_longer_passes(tmp_path, monkeypatch, stubbed):
    report = _swap(tmp_path, monkeypatch, "reject")
    assert report.outcome == "needs_contact"
    assert "no longer passes" in report.screen.contact_reason
