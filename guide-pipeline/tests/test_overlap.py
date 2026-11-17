import json
import re
from datetime import date

import numpy as np

from guide_pipeline.llm import LLMError
from guide_pipeline.llm_cache import CachedLLM
from guide_pipeline.mining.embed import VectorIndex
from guide_pipeline.mining.models import Pico, Question
from guide_pipeline.mining.overlap import (
    CLEAR,
    DUPLICATE,
    FLAGGED,
    NONE,
    NOTED,
    OSF,
    PARTIAL,
    PROSPERO,
    PUBLISHED,
    REJECTED,
    SUBSTANTIAL,
    UNVERIFIED,
    Judgement,
    OsfRegistry,
    OverlapRecord,
    ProsperoRegistry,
    Retrieved,
    decide,
    judge_call,
    judge_many,
    retrieve,
)
from guide_pipeline.mining.overlap_eval import PairSet, resolve_records, run_eval
from guide_pipeline.mining.store import MiningStore
from guide_pipeline.osf import OsfMirror, OsfRecord
from guide_pipeline.prospero import ProsperoMirror, ProsperoRecord
from guide_pipeline.sources.pubmed import Paper


class WordEmbedder:
    """Bag of words hashed into 64 dimensions: similar wording, similar vector."""

    name = "fake-words"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        rows = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                if len(w) > 2:
                    rows[i, sum(map(ord, w)) % 64] += 1
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return rows / np.where(norms == 0, 1, norms)


Q = Question("q1", "Vitamin D supplementation and mortality in critically ill adults",
             Pico("critically ill adults in intensive care", "vitamin D supplementation",
                  "placebo or no supplementation", "mortality", "randomised controlled trials"))


def paper(pmid, title, abstract="", year=2024):
    return Paper(pmid=pmid, title=title, abstract=abstract, authors=(), journal="J",
                 year=year, doi=None)


# -- retrieval ------------------------------------------------------------------
def mirrors(tmp_path):
    pm = ProsperoMirror(tmp_path / "p.sqlite")
    pm.merge([
        ProsperoRecord("CRD1", "Vitamin D for critically ill adults: mortality",
                       registration_date=date(2025, 1, 1)),
        ProsperoRecord("CRD2", "Statins and falls in older people",
                       registration_date=date(2025, 1, 1)),
        ProsperoRecord("CRD3", "Vitamin D supplementation mortality intensive care",
                       registration_date=date(2026, 6, 1)),
    ])
    om = OsfMirror(tmp_path / "o.sqlite")
    om.merge([OsfRecord("osf1", "Cholecalciferol in intensive care",
                        "Critically ill adults given vitamin D, outcome mortality.",
                        date_registered=date(2025, 3, 1))])
    return pm, om


def test_retrieve_pools_every_source_and_orders_by_similarity(tmp_path):
    pm, om = mirrors(tmp_path)
    published = [OverlapRecord.from_paper(paper("111", "Vitamin D in critically ill adults: "
                                                "a meta-analysis of mortality"))]
    got = retrieve(Q, ["cholecalciferol intensive care survival"], published=published,
                   registries=[ProsperoRegistry(pm), OsfRegistry(om)], embedder=WordEmbedder(),
                   k=10)
    keys = [(r.record.source, r.record.id) for r in got]
    assert (PUBLISHED, "111") in keys and (PROSPERO, "CRD1") in keys and (OSF, "osf1") in keys
    assert (PROSPERO, "CRD2") not in keys  # shares no words
    sims = [r.similarity for r in got]
    assert sims == sorted(sims, reverse=True)


def test_retrieve_caps_at_k_and_respects_a_registration_cutoff(tmp_path):
    pm, om = mirrors(tmp_path)
    got = retrieve(Q, [], published=[], registries=[
        ProsperoRegistry(pm, registered_before=date(2026, 1, 1)),
        OsfRegistry(om, registered_before=date(2026, 1, 1))], embedder=WordEmbedder(), k=30)
    assert "CRD3" not in {r.record.id for r in got}
    got = retrieve(Q, [], published=[], registries=[ProsperoRegistry(pm)],
                   embedder=WordEmbedder(), k=1)
    assert len(got) == 1


def test_semantic_index_finds_records_lexical_search_misses(tmp_path):
    pm = ProsperoMirror(tmp_path / "p.sqlite")
    # No word in common with the FTS query terms except through the index.
    pm.merge([ProsperoRecord("CRD9", "Supplementation mortality critically adults",
                             registration_date=date(2025, 1, 1))])
    emb = WordEmbedder()
    index = VectorIndex(tmp_path / "v.sqlite", emb)
    assert index.sync(PROSPERO, pm.titles()) == 1
    assert index.sync(PROSPERO, pm.titles()) == 0  # nothing new to embed

    class NoLexical(ProsperoRegistry):
        def lexical(self, text, limit):
            return []
    got = retrieve(Q, [], published=[], registries=[NoLexical(pm)], embedder=emb, index=index)
    assert [r.record.id for r in got] == ["CRD9"]


def test_vector_index_drops_records_gone_from_the_mirror(tmp_path):
    index = VectorIndex(tmp_path / "v.sqlite", WordEmbedder())
    index.sync(OSF, {"a": "vitamin d", "b": "statins"})
    index.sync(OSF, {"a": "vitamin d"})
    assert index.count(OSF) == 1


# -- judgement ------------------------------------------------------------------
class FakeJudge:
    """Returns a judgement per record label, chosen by a rule on the record text."""

    model = "fake-opus"
    effort = "high"

    def __init__(self, rule, drop=()):
        self.rule, self.drop, self.calls = rule, set(drop), []

    def complete_json(self, system, user, *, schema=None, cache_system=False):
        self.calls.append(user)
        out = []
        for label, title in re.findall(r"^\[(R\d+)\][^\n]*\nTitle: ([^\n]*)", user, re.M):
            if label in self.drop:
                continue
            level, conf = self.rule(title)
            out.append({"record": label, "overlap": level, "confidence": conf,
                        "population": "same", "intervention": "same", "comparator": "same",
                        "outcomes": "same", "study_designs": "same", "summary": f"{level}"})
        return {"judgements": out}


def ret(*titles, source=PUBLISHED):
    return [Retrieved(OverlapRecord(source, str(i), t, url=f"u{i}"), 0.9 - i / 100)
            for i, t in enumerate(titles)]


def test_prompt_lists_every_record_with_its_basis_and_is_deterministic():
    call = judge_call(Q, ret("A", "B", source=PROSPERO))
    assert "[R1] PROSPERO 0" in call.user and "[R2] PROSPERO 1" in call.user
    assert "title only (PROSPERO export)" in call.user
    assert "Population: critically ill adults" in call.user
    assert judge_call(Q, ret("A", "B", source=PROSPERO)) == call
    assert "outside knowledge" in call.system


def test_duplicate_with_high_confidence_rejects():
    llm = FakeJudge(lambda t: (DUPLICATE, "high") if t == "Same" else (NONE, "high"))
    (judged,) = judge_many(llm, [(Q, ret("Other", "Same"))])
    v = decide(Q, judged)
    assert v.status == REJECTED and v.rejected
    assert "published review 1" in v.reason and "u1" in v.reason  # names the record and link
    assert v.closest[0].record.title == "Same"


def test_verdict_levels():
    def verdict(level, conf):
        (judged,) = judge_many(FakeJudge(lambda t: (level, conf)), [(Q, ret("X"))])
        return decide(Q, judged).status
    assert verdict(DUPLICATE, "medium") == REJECTED  # Samarth, 2026-10-25
    assert verdict(DUPLICATE, "low") == FLAGGED
    assert verdict(SUBSTANTIAL, "medium") == FLAGGED
    assert verdict(SUBSTANTIAL, "high") == FLAGGED
    assert verdict(PARTIAL, "high") == NOTED
    assert verdict(NONE, "high") == CLEAR


def test_a_record_the_judge_left_out_leaves_the_candidate_unverified():
    llm = FakeJudge(lambda t: (NONE, "high"), drop={"R2"})
    (judged,) = judge_many(llm, [(Q, ret("A", "B"))])
    v = decide(Q, judged)
    assert v.status == UNVERIFIED
    assert [j.judged for j in judged] == [True, False]


def test_a_failed_judge_call_is_unverified_not_clear():
    class Broken:
        def complete_json(self, *a, **k):
            raise LLMError("boom")
    (judged,) = judge_many(Broken(), [(Q, ret("A"))])
    assert decide(Q, judged).status == UNVERIFIED


def test_no_records_means_no_call_and_clear():
    llm = FakeJudge(lambda t: (NONE, "high"))
    (judged,) = judge_many(llm, [(Q, [])])
    assert llm.calls == [] and decide(Q, judged).status == CLEAR


def test_unknown_labels_and_levels_are_ignored():
    class Odd:
        def complete_json(self, *a, **k):
            return {"judgements": [
                {"record": "R9", "overlap": DUPLICATE, "confidence": "high"},
                {"record": "R1", "overlap": "identical", "confidence": "high"}]}
    (judged,) = judge_many(Odd(), [(Q, ret("A"))])
    assert decide(Q, judged).status == UNVERIFIED


def test_store_keeps_verdicts_and_every_judgement(tmp_path):
    llm = FakeJudge(lambda t: (PARTIAL, "medium"))
    (judged,) = judge_many(llm, [(Q, ret("A", "B"))])
    store = MiningStore(tmp_path / "m.sqlite")
    store.save_overlap(decide(Q, judged, model="fake-opus", judged_on="2026-10-24"))
    assert store.overlap_verdicts("q1")[0]["status"] == NOTED
    rows = store.judgements("q1")
    assert len(rows) == 2 and rows[0]["overlap"] == PARTIAL
    assert rows[0]["reasoning"]["summary"] == PARTIAL


# -- batch caching (resume without paying twice) --------------------------------
def test_cached_llm_caches_batch_calls_per_call(tmp_path):
    llm = FakeJudge(lambda t: (NONE, "high"))
    cached = CachedLLM(llm, tmp_path, task="overlap_judgement")
    items = [(Q, ret("A")), (Q, ret("B"))]
    first = judge_many(cached, items)
    assert len(llm.calls) == 2
    again = judge_many(cached, items)
    assert len(llm.calls) == 2 and cached.hits == 2
    assert [j.level for js in again for j in js] == [j.level for js in first for j in js]


def test_cached_llm_does_not_keep_failures(tmp_path):
    class Flaky:
        def __init__(self):
            self.n = 0

        def complete_json(self, *a, **k):
            self.n += 1
            if self.n == 1:
                raise LLMError("transient")
            return {"judgements": []}
    inner = Flaky()
    cached = CachedLLM(inner, tmp_path, task="t")
    judge_many(cached, [(Q, ret("A"))])
    judge_many(cached, [(Q, ret("A"))])
    assert inner.n == 2


# -- evaluation on labelled pairs -------------------------------------------------
def test_eval_reports_precision_and_recall_of_high_confidence_duplicates(tmp_path):
    pairs = {"name": "t", "pairs": [
        {"id": "1", "label": "duplicate", "candidate": {"title": "Q1"}, "record": {"pmid": "1"}},
        {"id": "2", "label": "duplicate", "candidate": {"title": "Q2"}, "record": {"pmid": "2"}},
        {"id": "3", "label": "different", "candidate": {"title": "Q3"}, "record": {"pmid": "3"}},
        {"id": "4", "label": "different", "candidate": {"title": "Q4"}, "record": {"pmid": "4"}},
        {"id": "5", "label": "different", "candidate": {"title": "Q5"}, "record": {"pmid": "404"}},
    ]}
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(pairs), encoding="utf-8")
    pair_set = PairSet.load(path)

    class PubMed:
        def fetch_details(self, pmids):
            return [paper(p, f"Record {p}") for p in pmids if p != "404"]
    records = resolve_records(pair_set.pairs, pubmed=PubMed())
    assert records["5"] is None
    outcomes = {"Record 1": (DUPLICATE, "high"), "Record 2": (SUBSTANTIAL, "high"),
                "Record 3": (DUPLICATE, "high"), "Record 4": (NONE, "high")}
    result = run_eval(FakeJudge(lambda t: outcomes[t]), pair_set, records)
    s = result.summary()
    assert (s["true_duplicates_rejected"], s["true_duplicates_missed"]) == (1, 1)
    assert (s["false_rejections"], s["different_kept"]) == (1, 1)
    assert s["precision"] == 0.5 and s["recall"] == 0.5
    assert s["judged"] == 4 and result.results[4].error == "record not found"


def test_the_v1_pair_set_loads_with_its_readable_field_names():
    ps = PairSet.load("overlap_fixtures/pairs-v1.json")
    assert len(ps.pairs) == 20
    assert sum(p.label == "duplicate" for p in ps.pairs) == 11  # n2 relabelled by Samarth
    # only the PMID is used: the reference title in the file is never sent to the judge
    assert all(set(p.record_ref) == {"pmid"} for p in ps.pairs)
