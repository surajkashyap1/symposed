from datetime import date

from guide_pipeline import novelty
from guide_pipeline.settings import Thresholds
from guide_pipeline.sources.pubmed import Paper
from test_run import assessment

TODAY = date(2026, 10, 18)
TH = Thresholds(novelty_reviews=2, novelty_primary=2, novelty_max_checks=3)


class FakePubMed:
    def __init__(self):
        self.queries = []
        self.reviews = [Paper("11", "Pharmacist outreach for SGLT2 inhibitor uptake: a review", "R abs",
                              (), "J", 2025, None, publication_types=("Review",))]
        self.studies = [Paper("21", "Pharmacist Outreach and SGLT2 Inhibitor Uptake", "S abs",
                              (), "JAMA Netw Open", 2026, None),
                        Paper("11", "duplicate of the review", "x", (), "J", 2025, None)]

    def search_pmids(self, query, *, retmax=400, sort="most+recent", min_year=None):
        self.queries.append((query, sort, min_year))
        return [p.pmid for p in (self.reviews if "review[pt] OR" in query and "NOT (" not in query
                                 else self.studies)]

    def fetch_details(self, pmids):
        pool = {p.pmid: p for p in self.reviews + self.studies[:1]}
        return [pool[p] for p in pmids if p in pool]


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete_json(self, system, user, schema=None, cache_system=False):
        self.calls.append(user)
        return self.reply


def reply(verdict, overlap="partial", **kw):
    return {"papers": [{"id": "R1", "overlap": "partial", "why": "Background."},
                       {"id": "S1", "overlap": overlap, "why": "Same intervention; outcome."}],
            "closest_id": "S1", "verdict": verdict,
            "editor_view": kw.get("view", "S1 already tests this directly."),
            "adds": "", "worth_answering": "", "suggested_change": ""}


def test_reviews_of_any_kind_and_recent_primary_studies_are_both_judged():
    pm, llm = FakePubMed(), FakeLLM(reply("not novel", "same question"))
    nc = novelty.check(llm, pm, assessment("Pharmacist-led SGLT2 uptake", "pass"), th=TH,
                       publication_type="systematic review", context="team", today=TODAY)
    assert [(q[1], q[2]) for q in pm.queries] == [("relevance", 2017), ("relevance", 2021)]
    assert "[R1] review" in llm.calls[0] and "[S1] primary study" in llm.calls[0]
    assert [e.pmid for e in nc.papers] == ["11", "21"]  # the duplicate is not shown twice
    assert not nc.passed and nc.closest_pmid == "21"
    assert nc.ranked()[0].pmid == "21" and nc.ranked()[0].overlap == "same question"
    assert "PMID 21 already tests this" in nc.editor_view  # labels named for the reader


def test_novel_is_downgraded_when_a_paper_is_labelled_the_same_question():
    nc = novelty.check(FakeLLM(reply("novel", "same question")), FakePubMed(),
                       assessment("Q", "pass"), th=TH, publication_type="review",
                       context="", today=TODAY)
    assert nc.verdict == novelty.UNCERTAIN and nc.passed


def test_a_dead_review_does_not_pass():
    nc = novelty.check(FakeLLM(reply("dead")), FakePubMed(), assessment("Q", "pass"), th=TH,
                       publication_type="review", context="", today=TODAY)
    assert not nc.passed


def test_a_failed_model_call_is_uncertain_never_novel():
    class Broken:
        def complete_json(self, *a, **k):
            raise RuntimeError("down")

    nc = novelty.check(Broken(), FakePubMed(), assessment("Q", "pass"), th=TH,
                       publication_type="review", context="", today=TODAY)
    assert nc.verdict == novelty.UNCERTAIN and nc.error


def test_screen_keeps_checking_until_enough_pass():
    from types import SimpleNamespace

    scored = [SimpleNamespace(assessment=assessment(t, "pass")) for t in ("A", "B", "C", "D")]
    verdicts = iter(["not novel", "novel", "dead", "uncertain"])

    class Seq:
        def complete_json(self, *a, **k):
            return reply(next(verdicts))

    kept, checks = novelty.screen(scored, llm=Seq(), pubmed=FakePubMed(), th=TH,
                                  publication_type="review", context="", want=2)
    # only 3 checks allowed (novelty_max_checks): A fails, B passes, C is dead
    assert [s.assessment.candidate.title for s in kept] == ["B"]
    assert [c.verdict for c in checks] == ["not novel", "novel", "dead"]


def test_the_shortlist_shows_the_verdict_and_the_closest_papers(tmp_path):
    from guide_pipeline import shortlist
    from guide_pipeline.alternatives import Alternative

    nc = novelty.check(FakeLLM(reply("uncertain", view="Check PMID 21.")), FakePubMed(),
                       assessment("Q", "pass"), th=TH, publication_type="review",
                       context="", today=TODAY)
    o = Alternative(1, "Q", "axis", "why", "new", 10, 50, "q", 50, "18/10/2026", "clear",
                    novelty=nc.as_dict())
    text = shortlist.write(tmp_path, [o], topic="T", key="k", failed={}).read_text()
    assert "Uncertain: a person must check the closest papers" in text
    closest = text.split("**Closest existing papers**")[1]
    assert closest.index("pubmed.ncbi.nlm.nih.gov/21/") < closest.index("pubmed.ncbi.nlm.nih.gov/11/")
    assert "**(closest)**" in closest
    assert (tmp_path / "shortlist.docx").exists()
