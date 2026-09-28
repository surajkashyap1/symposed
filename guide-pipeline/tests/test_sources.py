import httpx

from guide_pipeline.http import CachedHttpClient
from guide_pipeline.settings import Settings
from guide_pipeline.sources import (
    ClinicalTrialsClient,
    EuropePmcClient,
    PubMedClient,
    build_sources,
)


def http_for(handler, tmp_path):
    return CachedHttpClient(
        cache_dir=tmp_path / ".cache",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def test_pubmed_count_parses_esearchresult(tmp_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"esearchresult": {"count": "1234"}})

    client = PubMedClient(http=http_for(handler, tmp_path), api_key="K", email="a@b.c")
    assert client.count("vitamin d AND sepsis") == 1234
    assert seen["path"].endswith("/esearch.fcgi")
    assert seen["params"]["rettype"] == "count"
    assert seen["params"]["term"] == "vitamin d AND sepsis"
    assert seen["params"]["api_key"] == "K"


def test_pubmed_omits_api_key_when_absent(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"esearchresult": {"count": "0"}})

    client = PubMedClient(http=http_for(handler, tmp_path))
    assert client.count("x") == 0
    assert "api_key" not in seen["params"]


def test_europepmc_count_parses_hitcount(tmp_path):
    def handler(request):
        assert "europepmc" in request.url.path
        return httpx.Response(200, json={"hitCount": 987, "resultList": {"result": []}})

    client = EuropePmcClient(http=http_for(handler, tmp_path))
    assert client.count("stroke thrombectomy") == 987


def test_clinicaltrials_count_parses_totalcount(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"totalCount": 55, "studies": []})

    client = ClinicalTrialsClient(http=http_for(handler, tmp_path))
    assert client.count("semaglutide") == 55
    assert seen["params"]["countTotal"] == "true"
    assert seen["params"]["query.term"] == "semaglutide"


def test_build_sources_uses_faster_interval_with_key():
    with_key = build_sources(Settings(ncbi_api_key="K"))
    without_key = build_sources(Settings(ncbi_api_key=None))
    assert (
        with_key.pubmed.http._limiter.min_interval
        < without_key.pubmed.http._limiter.min_interval
    )
    # keys/tool flow through to the PubMed client
    assert with_key.pubmed.api_key == "K"


def test_pubmed_titles_via_esummary(tmp_path):
    def handler(request):
        assert request.url.path.endswith("/esummary.fcgi")
        assert dict(request.url.params)["id"] == "1,2"
        return httpx.Response(
            200,
            json={"result": {"uids": ["1", "2"], "1": {"title": "First."}, "2": {"title": ""}}},
        )

    client = PubMedClient(http=http_for(handler, tmp_path))
    assert client.titles(["1", "2"]) == [("1", "First.")]  # empty titles dropped
    assert client.titles([]) == []


def test_clinicaltrials_completes_by_filter(tmp_path):
    from datetime import date

    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"totalCount": 3, "studies": []})

    client = ClinicalTrialsClient(http=http_for(handler, tmp_path))
    assert client.count("x", completes_by=date(2027, 9, 25)) == 3
    assert (
        seen["params"]["filter.advanced"]
        == "AREA[PrimaryCompletionDate]RANGE[MIN,2027-09-25]"
    )


def test_pubmed_year_filter_always_sends_both_ends(tmp_path):
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"esearchresult": {"count": "3"}})

    client = PubMedClient(http=http_for(handler, tmp_path))
    client.count("x", min_year=2023)
    client.count("y", max_year=2010)
    assert (seen[0]["mindate"], seen[0]["maxdate"]) == ("2023", "3000")
    assert (seen[1]["mindate"], seen[1]["maxdate"]) == ("1800", "2010")
    assert seen[0]["datetype"] == "pdat"


def test_pubmed_to_europepmc_translation():
    from guide_pipeline.sources.europepmc import pubmed_to_europepmc as t

    assert t('("Pulmonary Disease, Chronic Obstructive"[Mesh] OR COPD[tiab]) AND inhaler*[tiab]') == \
        '(KW:"Pulmonary Disease, Chronic Obstructive" OR TITLE_ABS:"COPD") AND TITLE_ABS:inhaler*'
    assert t("(vitamin D[tiab] OR calcitriol[tiab]) AND 2010:2022[dp]") == \
        '(TITLE_ABS:"vitamin D" OR TITLE_ABS:"calcitriol") AND PUB_YEAR:[2010 TO 2022]'
    assert t("sepsis[tiab] AND systematic[sb]") == 'TITLE_ABS:"sepsis"'  # no dangling AND
    assert t("(sepsis[tiab] AND systematic[sb]) AND fluid*[tiab]") == \
        '(TITLE_ABS:"sepsis") AND TITLE_ABS:fluid*'


def test_europepmc_records_map_preprints_and_page(tmp_path):
    pages = []

    def handler(request):
        params = dict(request.url.params)
        pages.append(params["cursorMark"])
        if params["cursorMark"] == "*":
            results = [{"source": "PPR", "id": "PPR123", "title": "A <i>preprint</i>.",
                        "abstractText": "<p>Abs</p>", "pubYear": "2025", "doi": "10.1101/x",
                        "bookOrReportDetails": {"publisher": "medRxiv"},
                        "authorList": {"author": [{"lastName": "Lee", "initials": "K"}]}}]
            return httpx.Response(200, json={"hitCount": 2, "nextCursorMark": "c2",
                                             "resultList": {"result": results}})
        results = [{"source": "MED", "id": "999", "pmid": "999", "title": "Published",
                    "journalInfo": {"journal": {"title": "BMJ"}}, "pubYear": "2024"}]
        return httpx.Response(200, json={"hitCount": 2, "nextCursorMark": "c2",
                                         "resultList": {"result": results}})

    papers = EuropePmcClient(http=http_for(handler, tmp_path)).search_records("q", max_records=5)
    pre, pub = papers
    assert (pre.pmid, pre.id_type, pre.is_preprint, pre.journal) == ("PPR123", "PPR", True, "medRxiv (preprint)")
    assert (pre.title, pre.abstract, pre.authors) == ("A preprint", "Abs", ("Lee K",))
    assert (pub.pmid, pub.id_type, pub.journal) == ("999", "PMID", "BMJ")
    assert pages == ["*", "c2"]  # stopped when the cursor stopped moving
