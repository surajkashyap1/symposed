import httpx

from guide_pipeline.http import CachedHttpClient
from guide_pipeline.retrieval import dedupe, retrieve
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
    <ArticleDate DateType="Electronic"><Year>2019</Year><Month>05</Month></ArticleDate>
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


def test_retrieve_end_to_end(tmp_path):
    pubmed = pubmed_for(search_and_fetch_handler, tmp_path)
    result = retrieve(pubmed, "vitamin d sepsis", max_records=10)
    assert [p.pmid for p in result.papers] == ["111", "222"]
    assert result.papers[0].doi == "10.1/own"
    d = result.as_dict()
    assert (d["query"], d["count"], d["fetched"]) == ("vitamin d sepsis", 2, 2)


def test_parser_keeps_issue_year_and_earlier_online_year(tmp_path):
    pubmed = pubmed_for(search_and_fetch_handler, tmp_path)
    first, second = pubmed.fetch_details(["111", "222"])
    assert (first.year, first.epub_year, first.first_published_year) == (2021, 2019, 2019)
    assert (second.epub_year, second.first_published_year) == (None, 2019)
