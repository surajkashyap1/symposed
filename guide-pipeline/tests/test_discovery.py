from datetime import date

import pytest
from docx import Document

from guide_pipeline.candidates import CANDIDATES_SCHEMA, RequestPreferences
from guide_pipeline.discovery import (
    FINAL_SCHEMA,
    GAP_AXIS,
    GAP_SCHEMA,
    LENS_SCHEMA,
    READING_SCHEMA,
    TOPICS_SCHEMA,
    AwaitingFullTexts,
    FullTextStore,
    ReviewRef,
    choose_topics,
    closest_reviews,
    discover,
    final_check,
)
from guide_pipeline.llm_cache import CachedLLM
from guide_pipeline.settings import Thresholds
from guide_pipeline.sources.pubmed import Paper
from test_candidates import make_mirror

TODAY = date(2026, 9, 25)
TH = Thresholds(min_eligible_studies=8, max_records_to_screen=400, recent_review_years=4,
                max_fulltexts=3, final_check_reviews=2, topic_max_reviews=60,
                topic_min_primary=30)
PREFS = RequestPreferences(context="The user is an SHO.", specialties=("Cardiology",))
JATS = ("<article><front><article-meta><title-group><article-title>R</article-title>"
        "</title-group><abstract>A</abstract></article-meta></front><body>"
        "<sec><title>Discussion</title><p>Older adults were never studied.</p></sec>"
        "<sec><title>References</title><p>x</p></sec></body></article>")


class FakePubMed:
    """Counts by topic word; reviews numbered per topic; everything else fixed."""

    def __init__(self, reviews=None, primary=None, eligible=40, recent=0):
        self.reviews = reviews or {}
        self.primary = primary or {}
        self.eligible, self.recent = eligible, recent
        self.papers = {}

    def _topic(self, query):
        return next((k for k in {**self.reviews, **self.primary} if k in query), "")

    def count(self, query, *, min_year=None, max_year=None):
        if "NOT (review[pt]" in query:
            return self.primary.get(self._topic(query), self.eligible)
        if "review[pt] OR" in query:
            return self.reviews.get(self._topic(query), 0)
        if "AND systematic[sb]" in query:
            return self.recent
        if "protocol[ti]" in query:
            return 0
        return 200

    def search_pmids(self, query, *, retmax=400, sort="most+recent", min_year=None):
        topic = self._topic(query)
        n = min(retmax, self.reviews.get(topic, 0))
        ids = [f"{abs(hash(topic)) % 1000:03d}{i}" for i in range(n)]
        for i, pmid in enumerate(ids):
            self.papers.setdefault(pmid, None)
            self.papers[pmid] = self.papers[pmid] or Paper(pmid, f"Review {i} of {topic}", f"Abstract {i}",
                                      ("Smith J",), "J", 2024, None,
                                      publication_types=("Systematic Review",))
        return ids

    def fetch_details(self, pmids):
        return [self.papers[p] for p in pmids if p in self.papers]

    def titles(self, pmids):
        return [(p, self.papers[p].title) for p in pmids if p in self.papers]


class FakeTrials:
    def count(self, *a, **kw):
        return 0


class FakeEPMC:
    def __init__(self, oa=()):
        self.oa = set(oa)

    def open_access_pmcids(self, pmids):
        return {p: f"PMC{p}" for p in pmids if p in self.oa}

    def full_text_xml(self, pmcid):
        return JATS


class SchemaLLM:
    """Replies by schema; each schema's replies are used in turn (last repeats)."""

    def __init__(self, **replies):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.calls = []

    def complete_json(self, system, user, schema=None, cache_system=False):
        name = {id(TOPICS_SCHEMA): "topics", id(READING_SCHEMA): "reading",
                id(GAP_SCHEMA): "gaps", id(LENS_SCHEMA): "lens",
                id(FINAL_SCHEMA): "final", id(CANDIDATES_SCHEMA): "axes"}[id(schema)]
        self.calls.append((name, user))
        queue = self.replies.get(name) or [{"candidates": []}]  # axes top up: nothing
        return queue.pop(0) if len(queue) > 1 else queue[0]


def topics_reply(stated_query="", topics=()):
    return {"stated_topic_query": stated_query,
            "topics": [{"name": n, "pubmed_query": q, "why": "w"} for n, q in topics]}


READ = {"achieves": "Pooled 10 trials.", "limitations": ["No older adults; small trials"],
        "open_questions": ["Does it work in older adults?"],
        "gaps": ["Older adults — never pooled"], "search_to": "2023"}


def gap(found=True, titles=("Ablation in older adults with atrial fibrillation",)):
    return {"gap_found": found, "gap_summary": "Older adults are missing; a clear gap.",
            "candidates": [{"title": t, "pubmed_query": "af_q older", "trials_query": "af",
                            "rationale": "From R1", "from_reviews": ["R1"]} for t in titles]}


def llms(llm):
    return {k: llm for k in ("topic_generation", "review_reading", "gap_candidates",
                             "axis_lens", "final_check", "candidate_generation")}


# -- topics ----------------------------------------------------------------------
def test_concrete_topic_first_then_narrow_topics_fewest_reviews_first():
    llm = SchemaLLM(topics=[topics_reply("af_q", [("AF in athletes", "athletes_q"),
                                                  ("Post op AF", "postop_q"),
                                                  ("Rare thing", "rare_q"),
                                                  ("Whole field", "field_q")])])
    pm = FakePubMed(reviews={"af_q": 20, "athletes_q": 9, "postop_q": 3, "rare_q": 1,
                             "field_q": 500},
                    primary={"af_q": 900, "athletes_q": 80, "postop_q": 200, "rare_q": 5,
                             "field_q": 9000})
    topics = choose_topics(llm, pm, stated="Atrial fibrillation", prefs=PREFS, th=TH,
                           today=TODAY)
    usable = [t.name for t in topics if t.usable]
    assert usable == ["Atrial fibrillation", "Post op AF", "AF in athletes"]
    notes = {t.name: t.note for t in topics if not t.usable}
    assert "too broad" in notes["Whole field"] and "primary" in notes["Rare thing"]


def test_a_broad_stated_topic_gives_way_to_narrower_ones():
    llm = SchemaLLM(topics=[topics_reply("cardio_q", [("Atrial fibrillation", "af_q")])])
    pm = FakePubMed(reviews={"cardio_q": 4000, "af_q": 12}, primary={"cardio_q": 10**5,
                                                                    "af_q": 900})
    topics = choose_topics(llm, pm, stated="Cardiology", prefs=PREFS, th=TH, today=TODAY)
    assert [t.name for t in topics if t.usable] == ["Atrial fibrillation"]
    assert any(t.stated and "too broad" in t.note for t in topics)
    assert "atrial fibrillation" in llm.calls[0][1].lower()  # the examples are in the prompt


# -- full texts ----------------------------------------------------------------------
def ref(pmid):
    return ReviewRef(pmid, f"Review {pmid}", "J", 2024, "10.1/x", ())


def test_store_uses_open_access_then_supplied_files_and_pauses_for_the_rest(tmp_path):
    store = FullTextStore(tmp_path / "ft", FakeEPMC(oa={"1"}))
    with pytest.raises(AwaitingFullTexts) as exc:
        store.require([ref("1"), ref("2"), ref("3")], stage="topic one")
    assert [r.pmid for r in exc.value.missing] == ["2", "3"]
    needed = exc.value.request_path.read_text()
    assert "`2.docx`" in needed and "`3.docx`" in needed and "1: Review 1" in needed
    doc = Document()
    doc.add_paragraph("Pasted full text of review two.")
    doc.save(tmp_path / "ft" / "2.docx")
    (tmp_path / "ft" / "3.skip").write_text("")
    store.require([ref("1"), ref("2"), ref("3")], stage="topic one")  # no pause now
    assert store.text(ref("1"))[1] == "full text (Europe PMC open access)"
    assert "Older adults were never studied" in store.text(ref("1"))[0]
    assert "References" not in store.text(ref("1"))[0] or "x" not in store.text(ref("1"))[0][-5:]
    assert store.text(ref("2")) == ("Pasted full text of review two.", "full text (supplied docx)")
    assert store.text(ref("3")) == (None, "abstract only")


def test_abstracts_ok_never_pauses(tmp_path):
    FullTextStore(tmp_path, FakeEPMC(), abstracts_ok=True).require([ref("9")], stage="s")


# -- the loop --------------------------------------------------------------------------
def run_discover(tmp_path, llm, pm, *, oa=None, stated="Atrial fibrillation"):
    store = FullTextStore(tmp_path / "ft", FakeEPMC(oa=oa if oa is not None else
                                                    set(pm.papers) | {f"{abs(hash(k)) % 1000:03d}{i}"
                                                                      for k in pm.reviews
                                                                      for i in range(9)}))
    return discover(llms=llms(llm), pubmed=pm, clinicaltrials=FakeTrials(),
                    mirror=make_mirror(tmp_path), store=store, stated_topic=stated,
                    prefs=PREFS, th=TH, today=TODAY)


def test_gaps_in_the_reviews_become_gated_candidates(tmp_path):
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[gap()])
    pm = FakePubMed(reviews={"af_q": 5}, primary={"af_q": 900})
    d = run_discover(tmp_path, llm, pm)
    assert d.screen.outcome == "found"
    top = d.screen.top.candidate
    assert top.axis == GAP_AXIS and "older adults" in top.title.lower()
    assert "gap found in PMID" in top.rationale
    trial = d.trials[0]
    assert trial.route == "gaps" and len(trial.readings) == 3  # capped at max_fulltexts
    assert trial.readings[0].basis == "full text (Europe PMC open access)"
    assert "—" not in trial.readings[0].gaps[0]  # house style applied
    assert ";" not in trial.readings[0].limitations[0]


def test_no_gap_moves_to_the_next_topic(tmp_path):
    llm = SchemaLLM(topics=[topics_reply("", [("Topic A", "a_q"), ("Topic B", "b_q")])],
                    reading=[READ], gaps=[gap(found=False, titles=()), gap()])
    pm = FakePubMed(reviews={"a_q": 2, "b_q": 4}, primary={"a_q": 100, "b_q": 100})
    d = run_discover(tmp_path, llm, pm, stated="")
    assert [t.route for t in d.trials] == ["no gap", "gaps"]
    assert d.screen.outcome == "found"


def test_questions_that_are_not_new_are_reworked_through_the_axes(tmp_path):
    lens = {"candidates": [{"title": "AF ablation in rural settings", "axis": "Setting transfer",
                            "pubmed_query": "af rural", "trials_query": "af",
                            "rationale": "r", "from_reviews": ["R2"]}]}
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[gap()],
                    lens=[lens])
    pm = FakePubMed(reviews={"af_q": 3}, primary={"af_q": 900}, recent=5)  # recent SRs reject
    d = run_discover(tmp_path, llm, pm)
    assert d.trials[0].route == "gaps+axes"
    assert any(a.candidate.axis == "Setting transfer" for a in d.screen.assessments)
    assert "did not pass" in [u for n, u in llm.calls if n == "lens"][0]


def test_paused_discovery_lists_what_to_fetch(tmp_path):
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[gap()])
    pm = FakePubMed(reviews={"af_q": 2}, primary={"af_q": 900})
    with pytest.raises(AwaitingFullTexts) as exc:
        run_discover(tmp_path, llm, pm, oa=set())
    assert len(exc.value.missing) == 2 and "af_q" not in exc.value.stage
    assert not [n for n, _ in llm.calls if n == "reading"]  # nothing read before the files


# -- final check -----------------------------------------------------------------------
def test_final_check_reads_the_closest_reviews_and_judges_three_things(tmp_path):
    pm = FakePubMed(reviews={"af_q": 4}, primary={"af_q": 900})
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[gap()],
                    final=[{"novel": False, "novel_reason": "R1 did this; in 2024",
                            "publishable": True, "publishable_reason": "ok",
                            "realistic": True, "realistic_reason": "ok",
                            "suggested_change": "Limit to people over 80"}])
    d = run_discover(tmp_path, llm, pm)
    check = final_check(llms=llms(llm), pubmed=pm, store=FullTextStore(
        tmp_path / "ft", FakeEPMC(oa=set(pm.papers))), assessment=d.screen.top,
        prefs=PREFS, th=TH, today=TODAY)
    assert not check.passed and check.suggested_change == "Limit to people over 80"
    assert ";" not in check.reasons["novel"]
    assert len(check.reviews) == 2 and len(check.readings) == 2


def test_closest_reviews_prefers_similar_titles():
    pm = FakePubMed(reviews={"af_q": 4})
    pm.search_pmids("(af_q)", retmax=4)
    pm.papers[list(pm.papers)[3]] = Paper(list(pm.papers)[3],
                                          "Ablation for atrial fibrillation in older adults",
                                          "", (), "J", 2024, None)
    out = closest_reviews(pm, "Ablation for atrial fibrillation in older adults: a review",
                          "af_q", n=1, since=2017)
    assert out[0].title.startswith("Ablation for atrial fibrillation")


# -- resume ------------------------------------------------------------------------------
def test_cached_llm_replays_the_same_request_for_free(tmp_path):
    class Inner:
        model, effort, n = "m", "low", 0

        def complete_json(self, system, user, schema=None, cache_system=False):
            Inner.n += 1
            return {"n": Inner.n}

    c = CachedLLM(Inner(), tmp_path, task="t")
    assert c.complete_json("s", "u") == {"n": 1}
    assert CachedLLM(Inner(), tmp_path, task="t").complete_json("s", "u") == {"n": 1}
    assert c.complete_json("s", "different") == {"n": 2}
    assert c.model == "m"  # everything else passes through


def test_too_few_passing_gap_questions_are_topped_up_through_the_axes(tmp_path):
    pm = FakePubMed(reviews={"af_q": 3, "busy_q": 3}, primary={"af_q": 900, "busy_q": 900})
    orig = pm.count
    pm.count = lambda q, **kw: (5 if "AND systematic[sb]" in q and "busy_q" in q
                                else orig(q, **kw))
    reply = gap(titles=("Passes",))
    reply["candidates"].append({"title": "Already reviewed", "pubmed_query": "busy_q x",
                                "trials_query": "x", "rationale": "r", "from_reviews": []})
    lens = {"candidates": [{"title": "Reworked", "axis": "Unexamined subgroup",
                            "pubmed_query": "af_q y", "trials_query": "y", "rationale": "r",
                            "from_reviews": []}]}
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[reply],
                    lens=[lens])
    d = run_discover(tmp_path, llm, pm)
    assert d.trials[0].route == "gaps+axes"
    assert any(n == "axes" for n, _ in llm.calls)  # still short of 3: one axes batch tried
    assert {a.candidate.title for a in d.screen.survivors} == {"Passes", "Reworked"}
    lens_prompt = [u for n, u in llm.calls if n == "lens"][0]
    assert "Already reviewed" in lens_prompt and "Passes" not in lens_prompt.split("did not pass")[1].split("The reviews")[0]


def test_internal_review_labels_never_reach_the_user(tmp_path):
    reply = gap()
    reply["candidates"][0]["rationale"] = "R1 left older adults out, and [R2] agrees."
    llm = SchemaLLM(topics=[topics_reply("af_q", [])], reading=[READ], gaps=[reply])
    pm = FakePubMed(reviews={"af_q": 2}, primary={"af_q": 900})
    d = run_discover(tmp_path, llm, pm)
    r = d.screen.top.candidate.rationale
    assert "R1" not in r and "[R2]" not in r and r.startswith("A review (PMID ")
