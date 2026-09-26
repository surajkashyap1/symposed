import json

from guide_pipeline.recall import Fixture, append_history, run_consistency, run_recall
from guide_pipeline.screening import (
    ATTRIBUTES_SCHEMA,
    LIKELY_ELIGIBLE,
    LIKELY_INELIGIBLE,
    UNCLEAR,
)
from guide_pipeline.sources.pubmed import Paper

FIXTURE = {
    "name": "demo",
    "question": "Vitamin D in ICU",
    "criteria": {"population": "ICU adults", "intervention_or_exposure": "vitamin D",
                 "comparator": "placebo", "outcomes": "mortality", "study_designs": "RCT"},
    "included_pmids": ["1", "2", "3", "4"],
    "search_query": "vitamin d icu",
}


class FakePubMed:
    def __init__(self, missing=()):
        self.missing = set(missing)

    def fetch_details(self, pmids):
        return [Paper(p, f"Paper {p}", "abs", (), "J", 2020, None)
                for p in pmids if p not in self.missing]

    def search_pmids(self, query, retmax=400):
        return ["1", "50", "51", "52"]


class StatusByPmid:
    """Screens by pmid from a table; alternates on repeat calls if given a list."""

    def __init__(self, table):
        self.table, self.seen = table, {}

    def complete_json(self, system, user, schema=None, cache_system=False):
        if schema is ATTRIBUTES_SCHEMA:
            return {}
        pmid = user.split("TITLE: Paper ")[1].split("\n")[0]
        status = self.table.get(pmid, UNCLEAR)
        if isinstance(status, list):
            n = self.seen.get(pmid, 0)
            self.seen[pmid] = n + 1
            status = status[n % len(status)]
        return {"status": status, "reason": "r"}


def fixture(tmp_path, **over):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({**FIXTURE, **over}))
    return Fixture.load(path)


def test_recall_counts_eligible_and_unclear_as_flagged(tmp_path):
    llm = StatusByPmid({"1": LIKELY_ELIGIBLE, "2": UNCLEAR, "3": LIKELY_INELIGIBLE,
                        "4": LIKELY_ELIGIBLE})
    r = run_recall(fixture(tmp_path), FakePubMed(), llm, llm)
    assert r.recall == 0.75
    assert [s.paper.pmid for s in r.missed] == ["3"]
    assert r.counts(r.included) == {LIKELY_ELIGIBLE: 2, UNCLEAR: 1, LIKELY_INELIGIBLE: 1}


def test_recall_reports_included_papers_pubmed_could_not_return(tmp_path):
    llm = StatusByPmid({})
    r = run_recall(fixture(tmp_path), FakePubMed(missing={"4"}), llm, llm)
    assert r.not_retrieved == ["4"] and len(r.included) == 3


def test_recall_others_excludes_included_papers(tmp_path):
    llm = StatusByPmid({})
    r = run_recall(fixture(tmp_path), FakePubMed(), llm, llm, others=2)
    assert [s.paper.pmid for s in r.others] == ["50", "51"]
    assert len(r.included) == 4


def test_consistency_detects_eligible_ineligible_flips(tmp_path):
    llm = StatusByPmid({"1": [LIKELY_ELIGIBLE, LIKELY_INELIGIBLE],
                        "2": [LIKELY_ELIGIBLE, UNCLEAR],
                        "3": LIKELY_ELIGIBLE})
    c = run_consistency(fixture(tmp_path), FakePubMed(), llm, llm, papers=3, concurrency=1)
    assert len(c.pairs) == 3
    assert [a.paper.pmid for a, _ in c.changed] == ["1", "2"]
    assert [a.paper.pmid for a, _ in c.flipped] == ["1"]


def test_history_is_appended(tmp_path):
    path = tmp_path / "history.jsonl"
    append_history(path, {"fixture": "demo", "recall": 0.9})
    append_history(path, {"fixture": "demo", "recall": 1.0})
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["recall"] for r in rows] == [0.9, 1.0] and "run_at" in rows[0]


def test_real_fixture_loads():
    from pathlib import Path

    f = Fixture.load(Path(__file__).parent.parent / "recall_fixtures" / "vitamin-d-icu-mortality.json")
    assert len(f.included_pmids) == 19
    assert f.criteria.study_designs == "Randomised controlled trials"
