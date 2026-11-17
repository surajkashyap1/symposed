"""The two agentic filters (mining/agent.py) and how the pipeline uses them, on fakes."""

import json
from types import SimpleNamespace as NS

import pytest

from guide_pipeline.discovery import AwaitingFullTexts
from guide_pipeline.llm import UsageMeter, task_config
from guide_pipeline.mining import agent as ag
from guide_pipeline.mining import pipeline as pipe
from guide_pipeline.mining.store import MiningStore
from guide_pipeline.request import from_proforma
from guide_pipeline.settings import Settings
from test_updates import (
    EXTRACTED,
    FULLTEXT,
    FakeEPMC,
    FakePubMed,
    RuleLLM,
    WordEmbedder,
    _update_rule,
    _screen_rule,
    paper,
)


# -- the prompts ------------------------------------------------------------------------
def _values(settings):
    runner = ag.StageRunner(settings, pubmed=None, client=object())
    return {**runner._params(), "customer_context": "{}", "candidates": [],
            "stage1_output": [], "screening_results": "not yet available"}


@pytest.mark.parametrize("name", [ag.STAGE1_PROMPT, ag.STAGE2_PROMPT])
def test_each_stage_prompt_is_read_from_its_file_with_every_placeholder_filled(name):
    settings = Settings.load()
    text = ag.load_prompt(settings.agent_prompts_dir / name, _values(settings))
    assert "{{" not in text and "PIPELINE NOTES" not in text
    assert text.startswith("You are the")
    assert "<final_output>" in text


def test_a_prompt_edit_is_used_on_the_next_run(tmp_path):
    p = tmp_path / "p.md"
    p.write_text("notes\n=== PROMPT START ===\nHello {{today}}", encoding="utf-8")
    assert ag.load_prompt(p, {"today": "2026-10-27"}) == "Hello 2026-10-27"
    p.write_text("notes\n=== PROMPT START ===\nBye {{today}}", encoding="utf-8")
    assert ag.load_prompt(p, {"today": "x"}) == "Bye x"
    p.write_text("Hello {{unknown}}", encoding="utf-8")
    with pytest.raises(ag.AgentError):
        ag.load_prompt(p, {})
    p.write_text("=== PROMPT START ===\nHello {{unknown}}", encoding="utf-8")
    with pytest.raises(ag.AgentError, match="unknown"):
        ag.load_prompt(p, {})


def test_customer_context_leaves_out_the_institution():
    ctx = json.loads(ag.customer_context({"grade": "FY1", "institution": "Somewhere",
                                          "collaborators": 5, "anythingElse": ""}))
    assert ctx == {"grade": "FY1", "collaborators": 5}


# -- the loop, on a scripted client ---------------------------------------------------
def _usage():
    return NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0,
              cache_read_input_tokens=0)


def _resp(stop, *blocks):
    return NS(stop_reason=stop, content=list(blocks), usage=_usage(), stop_details=None)


def _text(t):
    return NS(type="text", text=t)


def _tool(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


class ScriptedClient:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **params):
        self.requests.append(json.loads(json.dumps(params, default=ag._dump)))
        reply = self.replies.pop(0)

        class Ctx:
            def __enter__(s):
                return NS(get_final_message=lambda: reply)

            def __exit__(s, *a):
                return False
        return Ctx()


FINAL = {"run_date": "2026-10-27", "assumptions": ["a"], "top_5": [{
    "rank": 1, "candidate_id": "10", "option_type": "alternative_angle",
    "proposed_title": "X in India",
    "searches": [{"source": "PubMed", "query": "x[tiab]  AND india[tiab]", "hits": 42}],
    "competing_reviews_found": [
        {"title": "Seen", "pmid_or_url": "601"},
        {"title": "Made up", "pmid_or_url": "999"},
        {"title": "Web", "pmid_or_url": "https://www.crd.york.ac.uk/prospero/display_record.php?RecordID=1"}],
}], "database_records": []}


def _run(client, tools, **kw):
    args = dict(client=client, model="claude-opus-5-5", effort="high", task="stage1_triage",
                system="SYSTEM", user_content=[{"type": "text", "text": "Begin."}],
                tools=tools, max_tool_calls=10, budget_usd=5.0, meter=UsageMeter(),
                transcript=kw.pop("transcript"))
    args.update(kw)
    return ag.run_agent(**args)


def test_the_loop_runs_tools_resumes_paused_turns_and_checks_the_output(tmp_path):
    pm = FakePubMed([paper("601", "Seen trial")], hits={"india": ["601"]})
    pm.search_dated_orig = pm.search_dated
    pm.search_dated = lambda q, **kw: (40, pm.search_dated_orig(q, **kw)[1])
    url = "https://www.crd.york.ac.uk/prospero/display_record.php?RecordID=1"
    client = ScriptedClient([
        _resp("tool_use", _text("Searching."),
              _tool("t1", "pubmed_search", {"query": "x[tiab] AND india[tiab]",
                                            "date_from": "2019"})),
        _resp("pause_turn", NS(type="server_tool_use", id="s1", name="web_search",
                               input={"query": "prospero x india"}),
              NS(type="web_search_tool_result", tool_use_id="s1",
                 content=[NS(type="web_search_result", url=url, title="PROSPERO")])),
        _resp("end_turn", _text("Summary here.\n<final_output>\n" + json.dumps(FINAL)
                                + "\n</final_output>")),
    ])
    tools = ag.AgentTools(pm)
    result = _run(client, tools, transcript=tmp_path / "t.json")

    assert result.summary == "Summary here."
    first = client.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["betas"] == [ag.CONTEXT_BETA]
    edit = first["context_management"]["edits"][0]
    assert edit["type"] == "clear_tool_uses_20250919"
    assert edit["trigger"]["value"] >= 400_000 and edit["keep"]["value"] >= 30
    assert edit["clear_at_least"]["value"] >= 150_000  # rare, large clears only
    assert "fallbacks" not in json.dumps(first)  # never a smaller model
    assert {t.get("name") for t in first["tools"]} >= {"pubmed_search", "pubmed_fetch",
                                                      "db_lookup", "web_search", "web_fetch"}
    second = client.requests[1]["messages"]
    tool_result = second[-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and '"hits": 40' in tool_result["content"]
    assert pm.calls[-1][2] == "2019/01/01"  # date_from as a publication date
    # the paused turn is resumed as is, with no extra user message
    assert client.requests[2]["messages"][-1]["role"] == "assistant"
    assert tools.log.web_searches == 1 and url in tools.log.urls_seen

    warnings = ag.verify_output(result.output, result.log)
    s = result.output["top_5"][0]["searches"][0]
    assert (s["hits"], s["hits_reported"], s["verified"]) == (40, 42, True)
    seen, made_up, web = result.output["top_5"][0]["competing_reviews_found"]
    assert seen["verified"] and not made_up["verified"] and web["verified"]
    assert any("Made up" in w for w in warnings)
    assert json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))["system"] == "SYSTEM"


def test_a_search_never_run_is_marked_unverified():
    out = {"top_5": [{"searches": [{"source": "PubMed", "query": "never run", "hits": 5}]}]}
    warnings = ag.verify_output(out, ag.ToolLog())
    assert out["top_5"][0]["searches"][0]["verified"] is False and warnings


def test_the_tool_budget_asks_for_the_final_output(tmp_path):
    pm = FakePubMed([], hits={})
    client = ScriptedClient([
        _resp("tool_use", _tool("t1", "pubmed_search", {"query": "a"})),
        _resp("tool_use", _tool("t2", "pubmed_search", {"query": "b"})),
        _resp("end_turn", _text("<final_output>{\"top_5\": []}</final_output>")),
    ])
    tools = ag.AgentTools(pm)
    _run(client, tools, max_tool_calls=1, transcript=tmp_path / "t.json")
    budget_reply = client.requests[2]["messages"][-1]["content"][0]
    assert budget_reply["is_error"] and "used up" in budget_reply["content"]
    assert [c[0] for c in pm.calls] == ["a"]  # the second search never ran


def test_a_reply_without_the_json_is_asked_for_again(tmp_path):
    client = ScriptedClient([
        _resp("end_turn", _text("Here is my answer but no tags.")),
        _resp("end_turn", _text("<final_output>```json\n{\"top_5\": []}\n```</final_output>")),
    ])
    result = _run(client, ag.AgentTools(FakePubMed([])), transcript=tmp_path / "t.json")
    assert result.output == {"top_5": []}
    assert "final_output" in client.requests[1]["messages"][-1]["content"][0]["text"]


def test_a_refusal_stops_the_stage_and_keeps_the_transcript(tmp_path):
    client = ScriptedClient([_resp("refusal")])
    with pytest.raises(ag.AgentError, match="declined"):
        _run(client, ag.AgentTools(FakePubMed([])), transcript=tmp_path / "t.json")
    assert (tmp_path / "t.json").exists()


def test_bad_tool_input_comes_back_as_an_error_not_a_crash():
    tools = ag.AgentTools(FakePubMed([]))
    assert tools.run("pubmed_search", {"query": ""})[1]
    assert tools.run("pubmed_search", {"query": "a", "date_from": "last year"})[1]
    assert tools.run("pubmed_fetch", {"pmids": [str(i) for i in range(60)]})[1]
    assert tools.run("nope", {})[1]


# -- the store --------------------------------------------------------------------------
def test_assessments_are_kept_and_found_again(tmp_path):
    store = MiningStore(tmp_path / "m.sqlite")
    store.save_triage(1, "req01", [{"candidate_id": "32923331",
                                    "original_title": "Arrhythmias in Sub-Saharan Africa",
                                    "option": "India", "status": "shortlisted",
                                    "record": {"why": "few reviews"}}], model="m")
    store.save_triage(1, "req01", [{"candidate_id": "32923331", "original_title": "Arrhythmias",
                                    "option": "India", "status": "deferred", "record": {}}])
    found = store.lookup_triage("arrhythmias india")
    assert [r["status"] for r in found] == ["deferred"]  # a rerun replaces, never duplicates
    assert store.lookup_triage("32923331")[0]["candidate_id"] == "32923331"
    assert store.lookup_triage("myocarditis") == []
    tools = ag.AgentTools(FakePubMed([]), store)
    text, err = tools.run("db_lookup", {"query": "32923331"})
    assert not err and "32923331" in text
    store.close()


# -- model routing ----------------------------------------------------------------------
def test_models_per_task(monkeypatch):
    s = Settings.load()
    assert task_config(s, "stage1_triage").model == "claude-opus-5-5"
    assert task_config(s, "stage2_appraisal").model == "claude-opus-5-5"
    for t in ("quick_screening", "review_extraction", "strategy_translation", "search_revision"):
        assert task_config(s, t).model == "claude-haiku-5-5", t
    for t in ("search_strategy", "protocol_drafting", "prospero_form", "plain_language"):
        assert task_config(s, t).model == "claude-sonnet-5-5", t


def test_the_stages_refuse_a_smaller_model(monkeypatch):
    monkeypatch.setenv("CANDIDATE_SOURCE", "updates")
    monkeypatch.setenv("ANTHROPIC_DECISION_MODEL", "claude-sonnet-5-5")
    with pytest.raises(ValueError, match="Step 3b"):
        Settings.load().check()


# -- the pipeline with both stages ----------------------------------------------------
class FakeAgents:
    def __init__(self, shortlist, selected):
        self.shortlist, self.selected, self.seen = shortlist, selected, {}

    def stage1(self, *, request, reviews, folder):
        self.seen["stage1"] = [(p.pmid, why) for p, why in reviews]
        return {"output": {"top_5": [{"candidate_id": i} for i in self.shortlist]}}

    def stage2(self, *, request, stage1, documents, screening, folder):
        self.seen["stage2"] = {"documents": [p.pmid for p, _ in documents],
                               "screening": screening}
        return {"output": {"selected": self.selected}}


SELECTED = {
    "candidate_id": "10", "option_type": "alternative_angle",
    "final_title": "Probiotics for NEC in preterm infants in India: a systematic review",
    "research_question": "Do probiotics prevent NEC in Indian preterm infants?",
    "pico": {"population": "Preterm infants in India", "exposure_or_intervention": "Probiotics",
             "comparator": "Placebo", "outcomes": ["NEC"], "setting": "India"},
    "inclusion_criteria": ["Randomised trials"], "exclusion_criteria": ["Case reports"],
    "search_strings": {"pubmed": "probiotic* AND india", "adaptation_notes": "Embase: emtree"},
    "estimated_eligible": {"low": 10, "high": 20, "method": "sample"},
    "differs_from_original": "The original pooled all countries. This one is India only.",
}


def test_stage_1_limits_the_full_texts_and_stage_2_decides_the_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("MINING_DB", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("REVIEW_PMIDS", "10, 20")
    settings = Settings.load()
    review = paper("10", "Probiotics for NEC in preterm infants: a systematic review", 2016)
    other = paper("20", "Zinc for diarrhoea: a systematic review", 2017)
    trials = [paper(str(i), f"Trial {i}", 2021, pts=("Randomized Controlled Trial",))
              for i in (601, 602, 603)]
    pm = FakePubMed([review, other, *trials],
                    hits={"india": ["601", "602"], "probiotic*": ["601", "602", "603"]})
    pm.count = lambda q: 2

    def rule(system, user, schema):
        props = (schema or {}).get("properties", {})
        if "already_updated" in props:
            return _update_rule(set())(system, user, schema)
        if "search_end_quote" in props:
            return EXTRACTED
        if "built_from_criteria" in props:
            return {"pubmed_query": "probiotic*[tiab]", "changes": [], "built_from_criteria": False}
        return _screen_rule({"Trial 601"})(system, user, schema)
    llm = RuleLLM(rule)
    llms = {t: llm for t in ("update_check", "review_extraction", "strategy_translation",
                             "search_revision", "quick_screening")}

    class Sources:
        pubmed, europepmc = pm, FakeEPMC()
    agents = FakeAgents(["10"], SELECTED)
    folder = tmp_path / "out" / "updates" / "ord1"
    built = {}
    monkeypatch.setattr(pipe, "build_guide", lambda **kw: built.update(kw) or {"title": "t"})
    go = lambda: pipe.run_updates(from_proforma({"topics": "probiotics"}, order_id="ord1"),
                                  settings=settings, sources=Sources, llms=llms, folder=folder,
                                  embedder=WordEmbedder(), agents=agents)

    with pytest.raises(AwaitingFullTexts) as exc:
        go()
    assert [r.pmid for r in exc.value.missing] == ["10"]  # only Step 3b's shortlist
    assert [pmid for pmid, _ in agents.seen["stage1"]] == ["10", "20"]
    assert "Named by Symposed staff" in agents.seen["stage1"][0][1]
    (folder / "fulltexts" / "10.txt").write_text(FULLTEXT * 20, encoding="utf-8")

    with pytest.raises(pipe.AwaitingPick) as pick:
        go()
    assert pick.value.selected["candidate_id"] == "10"
    assert pick.value.table.name == "STAGE2.md"
    assert agents.seen["stage2"]["documents"] == ["10"]
    (summary,) = agents.seen["stage2"]["screening"]
    assert summary["candidate_id"] == "10" and summary["records_added_since_search_end"] == 3

    pipe.save_pick(folder, "10")
    run = go()
    assert run.recall is None  # an alternative angle skips the recall test
    assert built["title"] == SELECTED["final_title"]
    assert built["axis"] == pipe.ANGLE_AXIS and built["kind"] == "alternative-angle"
    assert built["query"] == "probiotic* AND india"
    assert built["count"].since is None and built["count"].hits == 2  # every date
    assert built["extraction"].criteria.setting == "India"
    assert "Case reports" in built["extraction"].criteria.exclusion
    assert "builds on Smith J" in built["parallel"]
    assert any("recall test" in w for w in built["warnings"])
    assert built["extra_results"]["stage2_selected"] == SELECTED


def test_a_selected_search_pubmed_rejects_stops_with_a_clear_message(tmp_path):
    class PM:
        def count(self, q):
            return 0
    with pytest.raises(pipe.BadSelection, match="cannot be run"):
        pipe.run_selected({"search_strings": {"pubmed": "bad"}}, review=paper("1", "R"),
                          ex=None, request=None, settings=Settings.load(),
                          sources=type("S", (), {"pubmed": PM()}), llms={}, folder=tmp_path,
                          warnings=[], screenshots=False, say=lambda m: None)


# -- the registry mirrors ---------------------------------------------------------------
class FakeProspero:
    def search(self, title, *, limit=5, review_threshold=0.0):
        return [NS(registration_id="CRD42021234567", title="Arrhythmias in India",
                   registration_date="2021-05-01", score=0.81,
                   url="https://www.crd.york.ac.uk/PROSPERO/view/CRD42021234567")]


class FakeOsf:
    def search(self, text, *, limit=50, registered_before=None):
        return [NS(id="abc12", title="AF in South Asia: a scoping review", date_registered=None,
                   link="https://osf.io/abc12", registration_schema="Generalized Systematic "
                                                                   "Review Registration")]


def test_registries_are_searched_in_the_mirrors_only():
    web = {t["name"]: t for t in ag.server_tools()}
    assert web["web_search"]["blocked_domains"] == ["crd.york.ac.uk", "osf.io"]
    assert web["web_fetch"]["blocked_domains"] == ["crd.york.ac.uk", "osf.io"]
    tools = ag.AgentTools(FakePubMed([]), prospero=FakeProspero(), osf=FakeOsf())
    text, err = tools.run("registry_search", {"query": "arrhythmia india"})
    found = json.loads(text)
    assert not err and found["checked"]
    assert found["prospero"][0]["id"] == "CRD42021234567" and found["osf"][0]["id"] == "abc12"
    out = {"competing_reviews_found": [{"title": "P", "pmid_or_url": "CRD42021234567"},
                                       {"title": "O", "pmid_or_url": "https://osf.io/abc12"},
                                       {"title": "X", "pmid_or_url": "CRD42099999999"}]}
    ag.verify_output(out, tools.log)
    assert [r["verified"] for r in out["competing_reviews_found"]] == [True, True, False]


def test_a_testing_run_says_the_registries_were_not_checked():
    text, err = ag.AgentTools(FakePubMed([])).run("registry_search", {"query": "x"})
    assert not err and json.loads(text)["checked"] is False and "not" in text


def test_a_stale_mirror_stops_a_stage_before_any_model_call(tmp_path):
    class Stale:
        def ensure_fresh(self, *, max_age_days):
            raise RuntimeError("stale")
    client = ScriptedClient([])
    runner = ag.StageRunner(Settings.load(), FakePubMed([]), client=client, prospero=Stale())
    with pytest.raises(RuntimeError, match="stale"):
        runner.stage1(request=from_proforma({"topics": "x"}), reviews=[(paper("1", "R"), "")],
                      folder=tmp_path)
    assert client.requests == []


def test_a_dropped_connection_is_retried(tmp_path):
    import httpx2

    class Flaky(ScriptedClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.drops = 1

        def _stream(self, **params):
            if self.drops:
                self.drops -= 1
                raise httpx2.RemoteProtocolError("peer closed connection")
            return super()._stream(**params)
    client = Flaky([_resp("end_turn", _text("<final_output>{\"top_5\": []}</final_output>"))])
    client.beta = NS(messages=NS(stream=client._stream))
    waits = []
    result = _run(client, ag.AgentTools(FakePubMed([])), transcript=tmp_path / "t.json",
                  sleep=waits.append)
    assert result.output == {"top_5": []} and waits == [5.0]


def test_a_step_call_whose_reply_is_cut_off_is_sent_again():
    import httpx2

    from guide_pipeline.llm import AnthropicClient

    calls = []

    def create(**params):
        calls.append(params)
        if len(calls) == 1:
            raise httpx2.RemoteProtocolError("incomplete chunked read")
        return NS(stop_reason="end_turn", usage=_usage(), stop_details=None,
                  content=[NS(type="text", text='{"ok": true}')])
    llm = AnthropicClient(api_key="x", model="claude-haiku-5-5",
                          client=NS(messages=NS(create=create)), sleep=lambda s: None)
    assert llm.complete_json("s", "u") == {"ok": True} and len(calls) == 2


def test_a_note_after_the_search_becomes_a_date_limit():
    q = 'upadacitinib[tiab] AND axSpA[tiab]; date 2017 to present'
    assert pipe.clean_query(q) == ('(upadacitinib[tiab] AND axSpA[tiab]) AND '
                                   '("2017"[dp] : "3000"[dp])')
    assert pipe.clean_query("a[tiab]; restricted to English") == "a[tiab]"
    assert pipe.clean_query(" a[tiab] ") == "a[tiab]"


# -- resuming a stopped stage -----------------------------------------------------------
class B(dict):
    """A content block that reads like an SDK object and saves like a dict."""
    __getattr__ = dict.get


def test_a_stage_stopped_by_an_api_error_resumes_where_it_stopped(tmp_path):
    import anthropic
    import httpx2

    pm = FakePubMed([paper("601", "Seen trial")], hits={"india": ["601"]})
    pm.search_dated_orig = pm.search_dated
    pm.search_dated = lambda q, **kw: (40, pm.search_dated_orig(q, **kw)[1])
    first = ScriptedClient([_resp("tool_use", B(type="tool_use", id="t1", name="pubmed_search",
                                                input={"query": "x AND india"}))])
    credit = anthropic.BadRequestError(
        "Your credit balance is too low", body=None,
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://api")))

    def stop(**params):
        if first.replies:
            return ScriptedClient._stream(first, **params)
        raise credit
    first.beta = NS(messages=NS(stream=stop))
    path = tmp_path / "t.json"
    with pytest.raises(ag.AgentError, match="credit"):
        _run(first, ag.AgentTools(pm), transcript=path)
    assert len(pm.calls) == 1

    resume = ag.load_resume(path, "SYSTEM", "claude-opus-5-5")
    assert resume and len(resume["messages"]) == 3 and resume["model_cost_usd"] > 0
    final = {"top_5": [{"searches": [{"source": "PubMed", "query": "x AND india", "hits": 40}]}]}
    second = ScriptedClient([_resp("end_turn", _text(
        "<final_output>" + json.dumps(final) + "</final_output>"))])
    tools = ag.AgentTools(pm)
    result = _run(second, tools, transcript=path, resume=resume)
    sent = second.requests[0]["messages"]
    assert len(sent) == 3 and sent[-1]["content"][0]["type"] == "tool_result"  # no restart
    assert len(pm.calls) == 1  # the search was not run again
    assert tools.log.client_calls == 1 and tools.log.searches[0]["hits"] == 40
    assert ag.verify_output(result.output, result.log) == []  # the old search still counts
    assert result.cost_usd > resume["model_cost_usd"]  # earlier spend is carried over


def test_a_saved_conversation_from_another_prompt_is_not_resumed(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"model": "claude-opus-5-5", "system": "OLD PROMPT",
                                "messages": [{"role": "user", "content": "a"},
                                             {"role": "assistant", "content": "b"}]}),
                    encoding="utf-8")
    assert ag.load_resume(path, "NEW PROMPT", "claude-opus-5-5") is None
    assert ag.load_resume(path, "OLD PROMPT", "claude-sonnet-5-5") is None
    assert ag.load_resume(path, "OLD PROMPT", "claude-opus-5-5") is not None
    assert ag.load_resume(tmp_path / "missing.json", "OLD PROMPT", "claude-opus-5-5") is None


# -- refusal fallback -------------------------------------------------------------------
def test_refusal_fallback_settings():
    assert ag.fallback_params("") == (None, None)
    assert ag.fallback_params("off") == (None, None)
    assert ag.fallback_params("default") == (ag.FALLBACK_DEFAULT_BETA, "default")
    assert ag.fallback_params("claude-opus-5, claude-opus-4-8") == (
        ag.FALLBACK_LIST_BETA, [{"model": "claude-opus-5"}, {"model": "claude-opus-4-8"}])


def test_a_declined_turn_served_by_the_fallback_is_sent_back_correctly(tmp_path):
    reply = _resp("end_turn",
                  B(type="thinking", thinking="", signature="s"),
                  B(type="tool_use", id="x", name="pubmed_search", input={}),
                  B(type="fallback", **{"from": {"model": "claude-opus-5-5"}},
                    to={"model": "claude-opus-5"}),
                  B(type="text", text="<final_output>{\"top_5\": []}</final_output>"))
    reply.model = "claude-opus-5"
    client = ScriptedClient([reply])
    result = _run(client, ag.AgentTools(FakePubMed([])), transcript=tmp_path / "t.json",
                  fallback="default")
    sent = client.requests[0]
    assert ag.FALLBACK_DEFAULT_BETA in sent["betas"]
    assert '"fallbacks": "default"' in json.dumps(sent)
    assert result.models_used == ["claude-opus-5"]
    saved = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))["messages"][-1]
    assert [b["type"] for b in saved["content"]] == ["fallback", "text"]  # internal blocks dropped


def test_no_fallback_is_sent_unless_switched_on(tmp_path):
    client = ScriptedClient([_resp("end_turn", _text("<final_output>{}</final_output>"))])
    _run(client, ag.AgentTools(FakePubMed([])), transcript=tmp_path / "t.json")
    assert "fallbacks" not in json.dumps(client.requests[0])


def test_a_declined_reply_is_never_saved_and_an_old_one_is_dropped_on_resume(tmp_path):
    path = tmp_path / "t.json"
    client = ScriptedClient([_resp("tool_use", B(type="tool_use", id="t1", name="db_lookup",
                                                 input={"query": "x"})),
                             _resp("refusal", B(type="thinking", thinking="", signature="s"))])
    with pytest.raises(ag.AgentError, match="declined"):
        _run(client, ag.AgentTools(FakePubMed([])), transcript=path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["messages"][-1]["role"] == "user"  # the declined reply was not kept
    saved["messages"].append({"role": "assistant",
                              "content": [{"type": "thinking", "thinking": "", "signature": "s"}]})
    path.write_text(json.dumps(saved), encoding="utf-8")
    resume = ag.load_resume(path, "SYSTEM", "claude-opus-5-5")
    assert resume["messages"][-1]["role"] == "user"
