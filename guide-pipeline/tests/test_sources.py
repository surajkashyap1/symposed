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
