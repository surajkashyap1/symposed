import httpx

from guide_pipeline.http import CachedHttpClient
from guide_pipeline.retrieval import _normalize_use, dedupe, retrieve, tag_papers
from guide_pipeline.sources.pubmed import Paper, PubMedClient

SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID>111</PMID>
   <Article>
    <ArticleTitle>A study of <i>vitamin D</i> in sepsis</ArticleTitle>
    <Abstract>
      <AbstractText Label="BACKGROUND">Bg text.</AbstractText>
      <AbstractText Label="RESULTS">Res text.</AbstractText>
    </Abstract>
    <AuthorList>
      <Author><LastName>Smith</LastName><Initials>J</Initials></Author>
      <Author><LastName>Doe</LastName><Initials>A</Initials></Author>
      <Author><CollectiveName>Some Group</CollectiveName></Author>
    </AuthorList>
    <Journal><Title>J Test</Title>
      <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
    </Journal>
   </Article>
  </MedlineCitation>
  <PubmedData>
   <ArticleIdList>
     <ArticleId IdType="pubmed">111</ArticleId>
     <ArticleId IdType="doi">10.1/own</ArticleId>
   </ArticleIdList>
   <ReferenceList>
     <Reference><ArticleIdList>
       <ArticleId IdType="doi">10.9/reference</ArticleId>
     </ArticleIdList></Reference>
   </ReferenceList>
  </PubmedData>
 </PubmedArticle>
 <PubmedArticle>
  <MedlineCitation>
   <PMID>222</PMID>
   <Article>
    <ArticleTitle>Second</ArticleTitle>
    <Journal><Title>J2</Title>
      <JournalIssue><PubDate><MedlineDate>2019 Jan-Feb</MedlineDate></PubDate></JournalIssue>
    </Journal>
   </Article>
  </MedlineCitation>
 </PubmedArticle>
</PubmedArticleSet>
"""


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return self.payload


def pubmed_for(handler, tmp_path):
    return PubMedClient(
        http=CachedHttpClient(
            cache_dir=tmp_path / ".cache",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )
    )


def search_and_fetch_handler(request):
    if request.url.path.endswith("esearch.fcgi"):
        return httpx.Response(
            200, json={"esearchresult": {"count": "2", "idlist": ["111", "222"]}}
        )
    return httpx.Response(200, text=SAMPLE_XML)  # efetch


def test_fetch_details_parses_and_scopes_doi(tmp_path):
    papers = pubmed_for(search_and_fetch_handler, tmp_path).fetch_details(["111", "222"])
    assert len(papers) == 2
    p1, p2 = papers
    assert p1.pmid == "111"
    assert p1.title == "A study of vitamin D in sepsis"  # nested markup captured
    assert p1.abstract == "BACKGROUND: Bg text. RESULTS: Res text."
    assert p1.authors == ("Smith J", "Doe A")  # collective-name author skipped
    assert p1.journal == "J Test"
    assert p1.year == 2021
    assert p1.doi == "10.1/own"  # NOT the reference-list doi 10.9/reference
    assert p2.year == 2019  # parsed from MedlineDate
    assert p2.doi is None and p2.abstract == ""


def test_dedupe_by_doi_pmid_and_title():
    a = Paper("1", "Title One", "", (), "J", 2020, "10.1/x")
    b = Paper("2", "Different", "", (), "J", 2020, "10.1/X")  # same DOI (case)
    c = Paper("1", "Whatever", "", (), "J", 2021, None)  # same PMID as a
    d = Paper("9", "title one", "", (), "J", 2020, None)  # same title+year as a
    e = Paper("5", "Unique", "", (), "J", 2020, "10.1/y")  # kept
    out = dedupe([a, b, c, d, e])
    assert [p.pmid for p in out] == ["1", "5"]


def test_normalize_use_maps_to_vocabulary():
    assert _normalize_use("primary evidence") == "Primary evidence"  # case-insensitive
    assert _normalize_use("Background / context") == "Background / context"
    assert _normalize_use("some freeform label") == "Other"  # unknown -> Other
    assert _normalize_use("") == ""  # empty stays empty (untagged fallback)


def test_tag_papers_maps_and_falls_back(tmp_path):
    papers = [
        Paper("111", "T1", "abs1", (), "J", 2021, None),
        Paper("222", "T2", "abs2", (), "J", 2019, None),
    ]
    llm = FakeLLM(
        {
            "tags": [
                {"pmid": "111", "suggested_use": "Primary evidence", "reason": "trial"}
            ]
        }
    )
    tagged = tag_papers(llm, papers)
    assert tagged[0].suggested_use == "Primary evidence" and tagged[0].reason == "trial"
    assert tagged[1].suggested_use == "(untagged)"  # not returned by the model


def test_retrieve_end_to_end(tmp_path):
    pubmed = pubmed_for(search_and_fetch_handler, tmp_path)
    llm = FakeLLM(
        {
            "tags": [
                {"pmid": "111", "suggested_use": "Primary evidence", "reason": "r"},
                {"pmid": "222", "suggested_use": "Background / context", "reason": ""},
            ]
        }
    )
    result = retrieve(pubmed, llm, "vitamin d sepsis", max_records=10)
    assert len(result.papers) == 2
    d = result.as_dict()
    assert d["count"] == 2
    assert d["papers"][0]["suggested_use"] == "Primary evidence"
    assert d["papers"][0]["doi"] == "10.1/own"
