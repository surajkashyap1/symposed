"""The update pipeline (docs/spec-update-pipeline.md), steps 2 to 8, on fakes."""

import json
from types import SimpleNamespace as NS
import re
from datetime import date

import numpy as np
import pytest

from guide_pipeline.discovery import AwaitingFullTexts
from guide_pipeline.mining import pipeline as pipe
from guide_pipeline.mining.count import OverBudget, find_new, screen_new, translate_all
from guide_pipeline.mining.extract import found_in, read_extraction
from guide_pipeline.mining.guide import update_title
from guide_pipeline.mining.overlap import DUPLICATE, NONE
from guide_pipeline.mining.recall_check import resolve_included, run_recall_test
from guide_pipeline.mining.reviews import (
    check_already_updated,
    find_reviews,
    later_reviews,
    topic_terms,
)
from guide_pipeline.request import from_proforma
from guide_pipeline.screening import LIKELY_ELIGIBLE, LIKELY_INELIGIBLE, Criteria
from guide_pipeline.settings import Settings
from guide_pipeline.sources.pubmed import Paper

TODAY = date(2026, 10, 25)


def paper(pmid, title, year=2018, abstract="", pts=("Systematic Review",)):
    return Paper(pmid=pmid, title=title, abstract=abstract or f"Abstract of {title}",
                 authors=("Smith J", "Jones K"), journal="J Test", year=year, doi=None,
                 publication_types=pts)


class FakePubMed:
    """PubMed with a fixed library. Queries are matched by the rules in `hits`."""

    def __init__(self, library, hits=None, similar=None, counts=None):
        self.lib = {p.pmid: p for p in library}
        self.hits = hits or {}          # substring of query -> pmids
        self.similar = similar or {}
        self.counts = counts or {}      # exact query -> count for count()
        self.calls = []

    def search_dated(self, query, *, datetype="pdat", mindate=None, maxdate=None,
                     retmax=10000, sort="relevance", store=True):
        self.calls.append((query, datetype, mindate, maxdate))
        uids = re.findall(r"(\d+)\[uid\]", query)
        if uids:  # narrowing a list of ids by the rest of the query
            rest = re.sub(r"\((?:\d+\[uid\](?: OR )?)+\)", "", query)
            keep = [u for u in uids if u in self.lib]
            if any(key in rest for key in self.hits):
                allowed = set(self._match(rest))
                keep = [u for u in keep if u in allowed]
            if mindate and datetype == "pdat":
                keep = [u for u in keep if (self.lib[u].year or 0) >= int(mindate[:4])]
            return len(keep), keep[:retmax]
        ids = self._match(query)
        return len(ids), ids[:retmax]

    def _match(self, query):
        for key, ids in self.hits.items():
            if key in query:
                return list(ids)
        return []

    def fetch_details(self, pmids, *, store=True):
        self.stored = getattr(self, "stored", []) + ([] if store else list(pmids))
        return [self.lib[p] for p in pmids if p in self.lib]

    def summaries(self, pmids, *, store=True):
        return [{"pmid": p, "title": self.lib[p].title, "year": self.lib[p].year,
                 "publication_types": self.lib[p].publication_types}
                for p in pmids if p in self.lib]

    def similar_pmids(self, pmid, *, limit=200, store=True):
        return self.similar.get(pmid, [])[:limit]

    def titles(self, pmids):
        return [(p, self.lib[p].title) for p in pmids if p in self.lib]

    def count(self, query):
        return self.counts.get(query, 1)

    def mesh_terms(self, term, max_terms=5):
        class M:
            def __init__(self, name):
                self.name = name
        return [M(term)]


class FakeEPMC:
    def __init__(self, citing=None):
        self.citing = citing or {}

    def citing_pmids(self, pmid, max_records=2000, store=True):
        return self.citing.get(pmid, [])


class WordEmbedder:
    name = "fake-words"

    def embed(self, texts):
        rows = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                if len(w) > 2:
                    rows[i, sum(map(ord, w)) % 64] += 1
        n = np.linalg.norm(rows, axis=1, keepdims=True)
        return rows / np.where(n == 0, 1, n)


class RuleLLM:
    """A fake model: `rule(system, user, schema)` returns the reply."""

    model = "fake"
    effort = "low"

    def __init__(self, rule):
        self.rule, self.calls = rule, []

    def complete_json(self, system, user, *, schema=None, cache_system=False):
        self.calls.append(user)
        return self.rule(system, user, schema)


# -- step 2 -----------------------------------------------------------------------
def test_topic_terms_are_searched_one_by_one():
    assert topic_terms("sepsis; vitamin D, \n delirium") == ["sepsis", "vitamin D", "delirium"]
    assert topic_terms("atrial fibrillation") == ["atrial fibrillation"]
    assert topic_terms("") == []
    assert topic_terms("Cardiology", "Cancer in heart") == ["Cardiology", "Cancer in heart"]
    assert topic_terms("Cardiology", "cardiology") == ["Cardiology"]


# -- step 3 -----------------------------------------------------------------------
def test_find_reviews_takes_each_terms_best_in_turn_and_only_older_ones():
    lib = [paper(str(i), f"Review {i}") for i in range(1, 7)]
    pm = FakePubMed(lib, hits={"(sepsis)": ["1", "2", "3"], "(delirium)": ["4", "2", "5", "6"]})
    found = find_reviews(pm, ["sepsis", "delirium"], count=4, min_age_years=3, today=TODAY)
    assert [p.pmid for p in found.reviews] == ["1", "4", "2", "3"]
    assert found.cutoff == date(2023, 10, 25)
    assert all(c[3] == "2023/10/25" and c[1] == "pdat" for c in pm.calls)
    assert all("systematic[sb]" in c[0] and "NOT (protocol[ti]" in c[0]
               and '"practice guideline"[pt]' in c[0] for c in pm.calls)
    assert len(found.searches) == 2


def test_sampling_keeps_older_reviews_and_is_the_same_every_time():
    from guide_pipeline.mining.reviews import Found, sample_reviews

    found = Found(["t"], [paper(str(i), f"R{i}", 2015 + i % 8) for i in range(40)], TODAY)
    a = sample_reviews(found, min_age_years=5, size=10, seed="ord1", today=TODAY)
    b = sample_reviews(found, min_age_years=5, size=10, seed="ord1", today=TODAY)
    assert len(a) == 10 and [p.pmid for p in a] == [p.pmid for p in b]
    assert all(p.year <= 2020 for p in a)
    few = sample_reviews(found, min_age_years=5, size=100, seed="ord1", today=TODAY)
    assert len(few) == sum(1 for p in found.reviews if p.year <= 2020)


def test_later_reviews_come_from_one_filtered_search_with_abstracts():
    orig = paper("10", "Probiotics for necrotising enterocolitis in preterm infants", 2016)
    lib = [orig,
           paper("11", "Probiotics for necrotising enterocolitis in preterm infants: update", 2022,
                 abstract="An updated review of probiotics for NEC."),
           paper("13", "Probiotics necrotising enterocolitis preterm review", 2010),
           paper("15", "Exercise in heart failure: a systematic review", 2021)]

    class PM(FakePubMed):
        def search_dated(self, query, **kw):
            self.calls.append((query, kw))
            return 3, ["11", "13", "15", "10"]
    pm = PM(lib)
    got = later_reviews(pm, orig, shown=1)
    assert [p.pmid for p in got] == ["11"]  # closest title, 13 is older, 10 is itself
    assert got[0].abstract.startswith("An updated review")
    ((query, kw),) = pm.calls  # one search only
    assert "systematic[sb]" in query and kw["mindate"] == "2016/01/01"
    assert pm.stored == ["11"]  # read online, not saved (store=False)


def _update_rule(dup_titles):
    def rule(system, user, schema):
        for label, title in re.findall(r"^\[(PMID \d+|PROSPERO \S+)\][^:]*: ([^\n]*)", user,
                                       re.M):
            if title in dup_titles:
                return {"already_updated": True, "updated_by": label}
        return {"already_updated": False, "updated_by": ""}
    return rule


def test_a_review_already_updated_is_left_out_with_a_decision_only():
    a = paper("10", "Probiotics for NEC in preterm infants", 2016)
    b = paper("20", "Vitamin D in critically ill adults", 2017)
    upd = paper("11", "Probiotics for NEC in preterm infants: an update", 2022)
    pm = FakePubMed([a, b, upd], hits={"probiotics[tiab]": ["11"]})
    judge = RuleLLM(_update_rule({upd.title}))
    checks = check_already_updated([a, b], llm=judge, pubmed=pm, judged_on="2026-10-27")
    assert [c.passes for c in checks] == [False, True]
    assert "PMID 11" in checks[0].verdict.reason
    assert "Abstract of Probiotics for NEC in preterm infants: an update" in judge.calls[0]


def test_registrations_since_the_review_come_from_the_mirror():
    a = paper("10", "Probiotics for NEC in preterm infants", 2016)

    class Prospero:
        def search(self, title, *, limit=5):
            return [NS(registration_id="CRD42015000001", title="Old one",
                       registration_date=date(2015, 1, 1), url="u0"),
                    NS(registration_id="CRD42020000002", title="Probiotics NEC update protocol",
                       registration_date=date(2020, 1, 1), url="u1")]
    judge = RuleLLM(_update_rule({"Probiotics NEC update protocol"}))
    (check,) = check_already_updated([a], llm=judge, pubmed=FakePubMed([a]),
                                     prospero=Prospero())
    assert not check.passes and "CRD42020000002" in check.verdict.reason
    assert "CRD42015000001" not in judge.calls[0]  # registered before the review


# -- step 4 -----------------------------------------------------------------------
FULLTEXT = """Methods. We searched MEDLINE and Embase from inception to 14 March 2019.
The MEDLINE strategy was: 1 exp Probiotics/ 2 probiotic*.tw. 3 1 or 2 4 exp Enterocolitis, Necrotizing/ 5 3 and 4
Results. Twenty two trials were included in the review (n = 4000).
References: Bin-Nun 2005 Oral probiotics prevent necrotizing enterocolitis in very low birth weight neonates."""

EXTRACTED = {
    "search_end_as_written": "inception to 14 March 2019", "search_end_iso": "2019-03-14",
    "search_end_quote": "We searched MEDLINE and Embase from inception to 14 March 2019.",
    "databases": ["MEDLINE", "Embase"],
    "strategies": [{"database": "MEDLINE", "strategy": "1 exp Probiotics/ 2 probiotic*.tw. "
                    "3 1 or 2 4 exp Enterocolitis, Necrotizing/ 5 3 and 4"}],
    "criteria": {"population": "preterm infants", "intervention_or_exposure": "probiotics",
                 "comparator": "placebo", "outcomes": "NEC", "study_designs": "RCTs",
                 "setting": "", "other_inclusion": [], "exclusion": []},
    "included_count": 22, "included_count_quote": "Twenty two trials were included in the review",
    "included_studies": [{"first_author": "Bin-Nun", "year": "2005", "title":
                          "Oral probiotics prevent necrotizing enterocolitis in very low birth "
                          "weight neonates"}],
}


def test_extraction_is_verified_against_the_full_text():
    ex = read_extraction(paper("10", "R"), FULLTEXT, "full text (supplied pdf)", EXTRACTED)
    assert ex.search_end == date(2019, 3, 14) and ex.search_end_verified
    assert not ex.search_end_estimated
    assert ex.medline_strategy.verbatim and ex.included_count == 22
    assert ex.included_count_verified and ex.warnings == []


def test_unverified_or_missing_parts_are_flagged_never_trusted():
    data = {**EXTRACTED, "search_end_iso": "", "strategies": [],
            "included_count_quote": "Thirty trials were included"}
    ex = read_extraction(paper("10", "R", year=2020), FULLTEXT, "b", data)
    assert ex.search_end == date(2020, 1, 1) and ex.search_end_estimated
    assert not ex.included_count_verified
    assert any("no search strategy" in w for w in ex.warnings)
    invented = {**EXTRACTED, "strategies": [{"database": "MEDLINE", "strategy": "made up"}]}
    ex2 = read_extraction(paper("10", "R"), FULLTEXT, "b", invented)
    assert not ex2.medline_strategy.verbatim
    assert any("word for word" in w for w in ex2.warnings)


def test_a_month_only_date_ends_on_the_last_day_of_that_month():
    ex = read_extraction(paper("10", "R"), FULLTEXT + " June 2018",
                         "b", {**EXTRACTED, "search_end_iso": "2018-06",
                               "search_end_quote": "June 2018"})
    assert ex.search_end == date(2018, 6, 30)


def test_found_in_ignores_spacing_and_punctuation():
    assert found_in("1 exp  Probiotics/\n2 probiotic*.tw.", "x 1 exp Probiotics/ 2 probiotic*.tw. y")
    assert not found_in("", "anything")


# -- step 5 -----------------------------------------------------------------------
def _ex(pmid="10", end=date(2019, 3, 14)):
    ex = read_extraction(paper(pmid, "R"), FULLTEXT, "b", EXTRACTED)
    ex.search_end = end
    return ex


def test_translation_is_retried_once_when_pubmed_finds_nothing():
    replies = iter([{"pubmed_query": "bad[tiab]", "changes": [], "built_from_criteria": False},
                    {"pubmed_query": "probiotic*[tiab] AND \"Enterocolitis, Necrotizing\"[Mesh]",
                     "changes": ["exp X/ became [Mesh]"], "built_from_criteria": False}])
    llm = RuleLLM(lambda s, u, sch: next(replies))
    pm = FakePubMed([], counts={"bad[tiab]": 0})
    (s,) = translate_all(llm, pm, [(paper("10", "R"), _ex())])
    assert s.pubmed_query.startswith("probiotic*") and not s.error
    assert "YOUR LAST QUERY FAILED IN PUBMED" in llm.calls[1]
    assert "ORIGINAL STRATEGY (MEDLINE)" in llm.calls[0]


def test_new_studies_are_counted_from_the_day_after_the_search_ended():
    from guide_pipeline.mining.count import UpdateSearch

    pm = FakePubMed([], hits={"probiotic": ["1", "2", "3"], "huge": [str(i) for i in range(50)]})
    found = find_new(pm, [(paper("10", "R"), _ex(), UpdateSearch("probiotic*[tiab]", [], False)),
                          (paper("20", "R2"), _ex("20"), UpdateSearch("huge", [], False))],
                     max_hits=10, today=TODAY)
    (a, ids_a), (b, ids_b) = found
    assert a.since == date(2019, 3, 15) and a.hits == 3 and ids_a == ["1", "2", "3"]
    assert pm.calls[0][1:] == ("edat", "2019/03/15", "2026/10/25")
    assert b.too_broad and ids_b == []


def _screen_rule(eligible):
    def rule(system, user, schema):
        if "status" in (schema or {}).get("properties", {}):
            title = re.search(r"TITLE: ([^\n]*)", user).group(1)
            return {"status": LIKELY_ELIGIBLE if title in eligible else LIKELY_INELIGIBLE,
                    "reason": "criteria"}
        return {f: "x" for f in ("design", "population", "sample_size", "intervention",
                                 "comparator", "primary_outcome", "country")} | {"outcomes": []}
    return rule


def test_screening_counts_possibly_eligible_and_respects_the_budget():
    from guide_pipeline.mining.count import UpdateCount, UpdateSearch

    lib = [paper(str(i), f"Trial {i}", 2021, pts=("Randomized Controlled Trial",))
           for i in range(1, 5)]
    pm = FakePubMed(lib)
    llm = RuleLLM(_screen_rule({"Trial 1", "Trial 2"}))
    uc = UpdateCount("10", UpdateSearch("q", [], False), date(2019, 3, 15), hits=4)
    (done,) = screen_new(llm, pm, [(uc, ["1", "2", "3", "4"])], {"10": _ex()},
                         budget_usd=10)
    assert len(llm.calls) == 4  # one quick call per paper, no separate extraction
    assert done.counts() == {"likely_eligible": 2, "unclear": 0, "possibly_eligible": 2}
    with pytest.raises(OverBudget):
        screen_new(llm, pm, [(uc, ["1", "2", "3", "4"])], {"10": _ex()}, budget_usd=0.001)


# -- step 7 -----------------------------------------------------------------------
def test_included_studies_are_matched_by_title_and_year():
    lib = [paper("501", "Oral probiotics prevent necrotizing enterocolitis in very low birth "
                        "weight neonates", 2005)]
    pm = FakePubMed(lib, hits={"probiotics[ti]": ["501"]})
    matched, unmatched = resolve_included(pm, EXTRACTED["included_studies"] + [
        {"first_author": "Lin", "year": "2008", "title": ""}])
    assert [p for _, p in matched] == ["501"] and len(unmatched) == 1


def test_recall_test_revises_a_search_that_misses_studies():
    lib = [paper("501", "Probiotic study one", 2005), paper("502", "Lactobacillus study two", 2007)]
    pm = FakePubMed(lib, hits={"study[ti]": ["501", "502"]})

    def search(query, **kw):  # the original query finds only 501; the revision finds both
        uids = re.findall(r"(\d+)\[uid\]", query)
        got = [u for u in uids if u == "501" or "lactobacill" in query]
        return len(got), got
    pm.search_dated = lambda q, **kw: search(q) if "[uid]" in q else (2, ["501", "502"])
    revise = RuleLLM(lambda s, u, sch: {"pubmed_query": "probiotic* OR lactobacill*",
                                        "diagnoses": [{"pmid": "502", "reason": "no Lactobacillus"}],
                                        "changes": ["added lactobacill*"]})
    screen = RuleLLM(_screen_rule({"Probiotic study one", "Lactobacillus study two"}))
    studies = [{"first_author": "A", "year": "2005", "title": "Probiotic study one"},
               {"first_author": "B", "year": "2007", "title": "Lactobacillus study two"}]
    r = run_recall_test(pm, pmid="10", query="probiotic*", criteria=_ex().criteria,
                        studies=studies, revise_llm=revise, screen_llm=screen,
                        search_target=0.9, screen_target=0.95, max_revisions=2)
    assert [a.search_recall for a in r.attempts] == [0.5, 1.0]
    assert r.final.query == "probiotic* OR lactobacill*"
    assert r.attempts[0].diagnoses[0]["reason"] == "no Lactobacillus"
    assert r.screen_recall == 1.0 and r.passed


# -- step 8 -----------------------------------------------------------------------
def test_update_titles():
    assert update_title("Probiotics for preventing NEC in preterm infants: a systematic review "
                        "and meta-analysis.") == ("Probiotics for preventing NEC in preterm "
                                                  "infants: an updated systematic review")
    assert update_title("Melatonin for delirium") == "Melatonin for delirium: an updated systematic review"


# -- the whole run, steps 1 to 8 ----------------------------------------------------
def test_whole_run_pauses_for_full_texts_then_a_pick_then_writes_the_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("MINING_DB", str(tmp_path / "m.sqlite"))
    settings = Settings.load()
    review = paper("10", "Probiotics for NEC in preterm infants: a systematic review", 2016)
    trials = [paper(str(i), f"Trial {i}", 2021, pts=("Randomized Controlled Trial",))
              for i in (601, 602, 603)]
    known = paper("501", "Oral probiotics prevent necrotizing enterocolitis in very low birth "
                         "weight neonates", 2005)
    pm = FakePubMed([review, known, *trials],
                    hits={"(probiotics)": ["10"], "probiotics[ti]": ["501"],
                          "probiotic*": ["601", "602", "603"]})
    pm.search_dated_orig = pm.search_dated

    def search(query, **kw):
        if "[uid]" in query and "probiotic*" in query:  # recall: the search finds 501
            return 1, ["501"]
        return pm.search_dated_orig(query, **kw)
    pm.search_dated = search

    def rule(system, user, schema):
        props = (schema or {}).get("properties", {})
        if "already_updated" in props:
            return _update_rule(set())(system, user, schema)
        if "search_end_quote" in props:
            return EXTRACTED
        if "built_from_criteria" in props:
            return {"pubmed_query": "probiotic*[tiab]", "changes": [], "built_from_criteria": False}
        return _screen_rule({"Trial 601", "Trial 602"})(system, user, schema)
    llm = RuleLLM(rule)
    llms = {t: llm for t in ("update_check", "review_extraction", "strategy_translation",
                             "search_revision", "quick_screening")}

    class Sources:
        pubmed, europepmc = pm, FakeEPMC()
    request = from_proforma({"topics": "probiotics"}, order_id="ord1")
    folder = tmp_path / "out" / "updates" / "ord1"
    built = {}
    monkeypatch.setattr(pipe, "build_guide", lambda **kw: built.update(kw) or {"title": "t"})
    go = lambda: pipe.run_updates(request, settings=settings, sources=Sources, llms=llms,
                                  folder=folder, embedder=WordEmbedder())

    with pytest.raises(AwaitingFullTexts) as exc:  # step 4 pauses
        go()
    assert [r.pmid for r in exc.value.missing] == ["10"]
    assert "not checked" in (folder / "REVIEWS.md").read_text(encoding="utf-8")
    (folder / "fulltexts" / "10.txt").write_text(FULLTEXT * 20, encoding="utf-8")

    with pytest.raises(pipe.AwaitingPick) as pick:  # step 6 pauses
        go()
    (row,) = pick.value.rows
    assert (row["pmid"], row["possibly_eligible"], row["hits"]) == ("10", 2, 3)
    assert "**2**" in (folder / "UPDATES.md").read_text(encoding="utf-8")
    assert "601, 602" in pipe.papers_text(pipe.load_rows(folder)[0])

    pipe.save_pick(folder, "10")
    run = go()
    assert run.recall.final.search_recall == 1.0
    assert (folder / "RECALL.md").exists()
    assert built["query"] == "probiotic*[tiab]" and built["review"].pmid == "10"
    assert any("not checked" in w for w in built["warnings"])


def test_step_8_hands_the_guide_writer_the_original_reviews_criteria_and_search(tmp_path,
                                                                                 monkeypatch):
    from guide_pipeline.mining import guide as g
    from guide_pipeline.mining.count import UpdateCount, UpdateSearch
    from guide_pipeline.screening import ScreeningResult

    seen = {}

    class Content:
        warnings = ["from assemble"]

    def fake_assemble(**kw):
        seen.update(kw)
        return Content()
    monkeypatch.setattr(g, "assemble", fake_assemble)
    monkeypatch.setattr(g, "build_model", lambda content, **kw: {"m": 1})
    monkeypatch.setattr("guide_pipeline.deliver.build_outputs",
                        lambda ws, model, **kw: {"guide": ws.dir / "guide.docx",
                                                 "warnings": []})
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    ex = _ex()
    count = UpdateCount("10", UpdateSearch("probiotic*[tiab]", [], False), date(2019, 3, 15),
                        hits=3, screening=ScreeningResult(ex.criteria, []))
    review = paper("10", "Probiotics for NEC in preterm infants: a systematic review", 2016)
    out = g.build_guide(review=review, extraction=ex, count=count, query="probiotic*[tiab]",
                        request=from_proforma({"topics": "probiotics"}, order_id="o"),
                        settings=Settings.load(), sources=type("S", (), {"pubmed": None}),
                        llms={}, warnings=["registries not checked"], say=lambda m: None)
    assert seen["criteria"] == ex.criteria
    assert seen["title"] == "Probiotics for NEC in preterm infants: an updated systematic review"
    assert seen["retrieval"].query == ('(probiotic*[tiab]) AND ("2019/03/15"[EDAT] : '
                                       '"3000"[EDAT])')
    assert seen["assessment"].candidate.axis == g.UPDATE_AXIS
    assert out["warnings"][:2] == ["registries not checked", "from assemble"]
    results = json.loads((out["workspace"] / "results.json").read_text(encoding="utf-8"))
    assert results["original_pmid"] == "10"


def test_a_parallel_review_names_the_review_it_mirrors(tmp_path, monkeypatch):
    from guide_pipeline.mining import guide as g
    from guide_pipeline.mining.count import UpdateCount, UpdateSearch
    from guide_pipeline.screening import ScreeningResult

    seen = {}

    class Content:
        warnings = []
    monkeypatch.setattr(g, "assemble", lambda **kw: seen.update(kw) or Content())
    monkeypatch.setattr(g, "build_model", lambda content, **kw: {
        "rationale": "Why it matters.", "similar": [], "prospero": {"review_question": "Q."}})
    monkeypatch.setattr("guide_pipeline.deliver.build_outputs",
                        lambda ws, model, **kw: seen.update(model=model) or {"warnings": []})
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    ex = _ex()
    count = UpdateCount("10", UpdateSearch("x[tiab]", [], False), None, hits=3,
                        screening=ScreeningResult(ex.criteria, []))
    review = paper("10", "Arrhythmias in Africa: a systematic review", 2020)
    out = g.build_guide(review=review, extraction=ex, count=count, query="x[tiab]",
                        request=from_proforma({"topics": "x"}, order_id="o"),
                        settings=Settings.load(), sources=type("S", (), {"pubmed": None}),
                        llms={}, warnings=[], say=lambda m: None,
                        title="Arrhythmias in India: a systematic review", axis=g.PARALLEL_AXIS,
                        rationale="hint", kind="parallel-india",
                        parallel="A parallel of the Africa review.", parallel_difference="Africa only.")
    m = seen["model"]
    assert seen["title"] == "Arrhythmias in India: a systematic review"
    assert seen["assessment"].candidate.axis == g.PARALLEL_AXIS
    assert seen["retrieval"].query == "x[tiab]"  # every date, not only since a search
    assert m["rationale"] == "A parallel of the Africa review. Why it matters."
    assert m["similar"][0]["url"].endswith("/10/") and m["similar"][0]["difference"] == "Africa only."
    assert m["prospero"]["review_question"] == "Q. A parallel of the Africa review."
    assert out["workspace"].name.endswith("parallel-india-10")


def test_named_reviews_skip_step_3(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    monkeypatch.setenv("REVIEW_PMIDS", "10, 20")
    monkeypatch.setenv("MINING_DB", str(tmp_path / "m.sqlite"))
    settings = Settings.load()
    pm = FakePubMed([paper("10", "Review A", 2016), paper("20", "Review B", 2018)])

    class Sources:
        pubmed, europepmc = pm, FakeEPMC()
    judge = RuleLLM(lambda *a: (_ for _ in ()).throw(AssertionError("no judging")))
    llms = {t: judge for t in ("update_check", "review_extraction", "strategy_translation",
                               "search_revision", "quick_screening")}
    folder = tmp_path / "run"
    with pytest.raises(AwaitingFullTexts) as exc:
        pipe.run_updates(from_proforma({"topics": "x"}), settings=settings, sources=Sources,
                         llms=llms, folder=folder)
    assert [r.pmid for r in exc.value.missing] == ["10", "20"]
    assert "named by a person" in (folder / "REVIEWS_NAMED.md").read_text(encoding="utf-8")
    assert not any("search_dated" in str(c) for c in pm.calls)  # no review search


def test_quick_tasks_run_on_the_fast_model_without_effort(monkeypatch):
    from guide_pipeline.llm import AnthropicClient, JsonCall, task_config

    monkeypatch.delenv("MODEL_QUICK_SCREENING", raising=False)
    cfg = task_config(Settings.load(), "quick_screening")
    assert cfg.model == "claude-haiku-5-5" and not cfg.thinking
    c = AnthropicClient(api_key="x", model="claude-haiku-5-5", thinking=False, client=object())
    params = c._params(JsonCall("s", "u", {"type": "object"}))
    assert "effort" not in params["output_config"] and params["thinking"] == {"type": "disabled"}


def test_a_printed_strategy_the_model_leaves_out_is_added_from_the_text():
    from guide_pipeline.mining.extract import find_strategy_blocks

    text = ("Methods. We searched MEDLINE (see Data S2).\n" + "Body text. " * 50 + "\n"
            "Data S2- Search strategy for Medline using OVID\nMedline\n"
            "1 exp Myocardial Ischemia/\n2 (MYOCARD$4 adj4 ISCHEMI$2).tw.\n3 CORONARY.ti,ab.\n"
            "4 exp Heart Failure/\n5 or/1-4\n6 Randomized controlled trial.pt.\n7 5 and 6\n"
            "Data S3 - Screening form\n1. Eligible RCT report?\n")
    (block,) = find_strategy_blocks(text)
    assert block[0] == "Medline" and block[1].startswith("1 exp Myocardial Ischemia/")
    assert "Eligible RCT" not in block[1]
    ex = read_extraction(paper("10", "R"), text, "b", {**EXTRACTED, "strategies": []})
    assert ex.medline_strategy.text.startswith("1 exp Myocardial Ischemia/")
    assert ex.medline_strategy.verbatim


def test_a_translated_search_is_frozen_and_reused(tmp_path):
    replies = iter([{"pubmed_query": "first[tiab]", "changes": [], "built_from_criteria": False},
                    {"pubmed_query": "second[tiab]", "changes": [], "built_from_criteria": False}])
    llm = RuleLLM(lambda s, u, sch: next(replies))
    path = tmp_path / "searches.json"
    items = [(paper("10", "R"), _ex())]
    (a,) = pipe.frozen_searches(path, llm, FakePubMed([]), items)
    (b,) = pipe.frozen_searches(path, llm, FakePubMed([]), items)
    assert a.pubmed_query == b.pubmed_query == "first[tiab]" and len(llm.calls) == 1


# -- step 3 with no topic, and stopping once enough pass (Samarth, 2026-10-27) ------------
def test_no_topic_draws_reviews_from_the_whole_literature_the_same_way_each_time():
    from guide_pipeline.mining.reviews import sample_all_reviews

    class PM:
        def __init__(self):
            self.calls = []

        def search_dated(self, q, *, datetype, mindate=None, maxdate=None, retmax=10000,
                         sort="relevance", store=True, retstart=0):
            self.calls.append((mindate, retmax, retstart))
            n = 40 if mindate.startswith("2021/06") else 0  # one month holds reviews
            return n, ([] if retmax == 0 else [f"{mindate[:7].replace('/', '')}{retstart:02d}"])

        def fetch_details(self, ids):
            return [paper(i, f"Review {i}", 2021) for i in ids]

    a = sample_all_reviews(PM(), count=5, min_age_years=3, since_year=2021, seed="req02",
                           today=TODAY)
    b = sample_all_reviews(PM(), count=5, min_age_years=3, since_year=2021, seed="req02",
                           today=TODAY)
    assert len(a.reviews) == 5 and [p.pmid for p in a.reviews] == [p.pmid for p in b.reviews]
    assert all(p.pmid.startswith("202106") for p in a.reviews)
    assert "no topic" in next(iter(a.found_by.values()))
    assert a.searches[0].result == 40


def test_step_3_stops_once_enough_reviews_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    monkeypatch.setenv("MINING_DB", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("REVIEW_COUNT", "2")
    monkeypatch.setenv("REVIEW_BATCH", "2")
    settings = Settings.load()
    reviews = [paper(str(i), f"Review number {i}", 2015) for i in range(10, 16)]
    pm = FakePubMed(reviews, hits={"(x)": [p.pmid for p in reviews]})
    checked = []

    def fake_check(batch, **kw):
        checked.extend(p.pmid for p in batch)
        return [type("C", (), {"review": p, "passes": p.pmid != "10",
                               "verdict": type("V", (), {"status": "clear", "reason": "ok",
                                                  "error": ""})()})()
                for p in batch]
    monkeypatch.setattr(pipe, "check_already_updated", fake_check)
    monkeypatch.setattr(pipe.MiningStore, "save_overlap", lambda self, v: None)

    class Sources:
        pubmed, europepmc = pm, FakeEPMC()
    with pytest.raises(AwaitingFullTexts) as exc:
        pipe.run_updates(from_proforma({"topics": "x"}), settings=settings, sources=Sources,
                         llms={"update_check": None}, folder=tmp_path / "run")
    assert checked == ["10", "11", "12", "13"]  # stopped after the second batch
    assert [r.pmid for r in exc.value.missing] == ["11", "12"]


def test_a_failed_novelty_judge_stops_the_run_instead_of_passing_the_review(tmp_path,
                                                                            monkeypatch):
    from guide_pipeline.llm import LLMError

    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    monkeypatch.setenv("MINING_DB", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("REVIEW_COUNT", "2")
    settings = Settings.load()
    reviews = [paper(str(i), f"Review number {i}", 2015) for i in range(10, 13)]
    pm = FakePubMed(reviews, hits={"(x)": [p.pmid for p in reviews]})
    verdict = type("V", (), {"status": "unverified", "reason": "judge failed",
                             "error": "credit balance is too low"})()
    monkeypatch.setattr(pipe, "check_already_updated", lambda batch, **kw: [
        type("C", (), {"review": p, "passes": True, "verdict": verdict})() for p in batch])
    monkeypatch.setattr(pipe.MiningStore, "save_overlap", lambda self, v: None)

    class Sources:
        pubmed, europepmc = pm, FakeEPMC()
    with pytest.raises(LLMError, match="credit balance"):
        pipe.run_updates(from_proforma({"topics": "x"}), settings=settings, sources=Sources,
                         llms={"update_check": None}, folder=tmp_path / "run")


def test_a_review_judged_in_an_earlier_run_keeps_its_verdict(tmp_path):
    from guide_pipeline.mining.overlap import UNVERIFIED, OverlapVerdict
    from guide_pipeline.mining.reviews import update_question
    from guide_pipeline.mining.store import MiningStore

    a = paper("10", "Probiotics for NEC in preterm infants", 2016)
    b = paper("20", "Vitamin D in critically ill adults", 2017)
    store = MiningStore(tmp_path / "m.sqlite")
    store.save_overlap(OverlapVerdict(update_question(a), "rejected, duplicate",
                                      "Duplicate of an earlier review", [], "claude-opus-5-5",
                                      "2026-10-26"))
    store.save_overlap(OverlapVerdict(update_question(b), UNVERIFIED, "judge failed", [],
                                      "claude-opus-5-5", "2026-10-26"))
    judge = RuleLLM(_update_rule(set()))
    checks = check_already_updated([a, b], llm=judge, pubmed=FakePubMed([a, b]), store=store)
    assert [c.passes for c in checks] == [False, True]
    assert checks[0].verdict.reason == "Duplicate of an earlier review"
    assert len(judge.calls) == 1 and "Vitamin D" in judge.calls[0]  # only the failed one
    store.close()


def test_osf_registrations_are_ranked_by_title_similarity():
    from guide_pipeline.mining.reviews import registered_since

    a = paper("10", "Probiotics for NEC in preterm infants", 2016)

    class Osf:
        def search(self, text, *, limit=50, registered_before=None):
            return [NS(id="x1", title="Diet and sleep in adults", link="l1",
                       date_registered=date(2021, 1, 1)),
                    NS(id="x2", title="Probiotics for NEC in preterm infants: update protocol",
                       link="l2", date_registered=date(2021, 1, 1))]
    got = registered_since(a, None, Osf(), shown=1)
    assert got == [("OSF x2", "Probiotics for NEC in preterm infants: update protocol", "l2")]


def test_a_prose_topic_is_turned_into_short_terms():
    from guide_pipeline.mining.reviews import extract_topic_terms, looks_like_prose

    prose = ("I'm interested in how political rhetoric, religious beliefs, and media "
             "disinformation shape reproductive health, especially abortion and "
             "gender-affirming care")
    assert looks_like_prose(prose) and not looks_like_prose("Cardiology, cancer in heart")
    llm = RuleLLM(lambda s, u, schema: {"terms": ["abortion", "gender-affirming care",
                                                   "Abortion", " "]})
    assert extract_topic_terms(llm, prose, "My idea") == ["abortion", "gender-affirming care",
                                                         "My idea"]
