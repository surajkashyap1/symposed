import httpx

from guide_pipeline.http import CachedHttpClient
from guide_pipeline.landscape import (
    FILTER_GUIDELINE,
    FILTER_SYSTEMATIC_REVIEW,
    assess_landscape,
)
from guide_pipeline.sources.pubmed import MeshTerm, PubMedClient


def pubmed_for(handler, tmp_path):
    return PubMedClient(
        http=CachedHttpClient(
            cache_dir=tmp_path / ".cache",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )
    )


def _esearch(count, idlist=None):
    body = {"esearchresult": {"count": str(count)}}
    if idlist is not None:
        body["esearchresult"]["idlist"] = idlist
    return httpx.Response(200, json=body)


def test_mesh_terms_parses_main_headings(tmp_path):
    def handler(request):
        if request.url.path.endswith("esearch.fcgi"):
            assert dict(request.url.params)["db"] == "mesh"
            return _esearch(2, idlist=["68014808", "68014807"])
        # esummary
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["68014808", "68014807"],
                    "68014808": {
                        "ds_meshterms": ["Vitamin D Deficiency", "Deficiency, Vitamin D"],
                        "ds_meshui": "D014808",
                    },
                    "68014807": {"ds_meshterms": ["Vitamin D"], "ds_meshui": "D014807"},
                }
            },
        )

    terms = pubmed_for(handler, tmp_path).mesh_terms("vitamin d deficiency")
    assert terms == [
        MeshTerm("Vitamin D Deficiency", "D014808"),
        MeshTerm("Vitamin D", "D014807"),
    ]


def test_mesh_terms_empty_when_no_match(tmp_path):
    calls = {"esummary": 0}

    def handler(request):
        if request.url.path.endswith("esummary.fcgi"):
            calls["esummary"] += 1
        if request.url.path.endswith("esearch.fcgi"):
            return _esearch(0, idlist=[])
        return httpx.Response(200, json={"result": {"uids": []}})

    assert pubmed_for(handler, tmp_path).mesh_terms("asdfqwerty") == []
    assert calls["esummary"] == 0  # no ids -> no wasted esummary call


def test_count_adds_year_bounds(tmp_path):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return _esearch(123)

    pubmed_for(handler, tmp_path).count("topic", min_year=2020, max_year=2020)
    assert seen["params"]["datetype"] == "pdat"
    assert seen["params"]["mindate"] == "2020"
    assert seen["params"]["maxdate"] == "2020"


def test_assess_landscape_gathers_all_figures(tmp_path):
    def handler(request):
        params = dict(request.url.params)
        if request.url.path.endswith("esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "uids": ["1"],
                        "1": {"ds_meshterms": ["Sepsis"], "ds_meshui": "D018805"},
                    }
                },
            )
        if params.get("db") == "mesh":
            return _esearch(1, idlist=["1"])
        term = params.get("term", "")
        if FILTER_SYSTEMATIC_REVIEW in term:
            return _esearch(11)
        if "Guideline[ptyp]" in term:
            return _esearch(3)
        if "mindate" in params:  # per-year query
            return _esearch({"2024": 40, "2025": 55, "2026": 60}[params["mindate"]])
        return _esearch(500)  # total

    pubmed = pubmed_for(handler, tmp_path)
    result = assess_landscape(pubmed, "sepsis", years=3, current_year=2026)

    assert result.mesh_terms == [MeshTerm("Sepsis", "D018805")]
    assert result.total_literature == 500
    assert result.systematic_reviews == 11
    assert result.guidelines == 3
    assert result.by_year == {2024: 40, 2025: 55, 2026: 60}


def test_landscape_as_dict_is_json_shaped(tmp_path):
    from guide_pipeline.landscape import Landscape

    lc = Landscape(
        topic="sepsis",
        mesh_terms=[MeshTerm("Sepsis", "D018805")],
        total_literature=500,
        by_year={2025: 55},
        systematic_reviews=11,
        guidelines=3,
    )
    assert lc.as_dict() == {
        "topic": "sepsis",
        "mesh_terms": [{"name": "Sepsis", "ui": "D018805"}],
        "total_literature": 500,
        "by_year": {"2025": 55},
        "systematic_reviews": 11,
        "guidelines": 3,
        "by_year_source": "PubMed",
        "openalex_total": None,
    }


def test_guideline_filter_uses_publication_types():
    assert "Guideline[ptyp]" in FILTER_GUIDELINE
    assert "Practice Guideline" in FILTER_GUIDELINE


def test_landscape_uses_one_openalex_call_for_years(tmp_path):
    from types import SimpleNamespace

    from guide_pipeline.landscape import assess_landscape

    calls = []

    class FakePubMed:
        def mesh_terms(self, topic):
            return []

        def count(self, q, **kw):
            calls.append(kw)
            return 7

    oa = SimpleNamespace(works_by_year=lambda s, first_year, last_year:
                         (9000, {y: 100 for y in range(first_year, last_year + 1)}))
    lc = assess_landscape(FakePubMed(), "copd", years=3, current_year=2026, openalex=oa)
    assert lc.by_year_source == "OpenAlex" and lc.openalex_total == 9000
    assert lc.by_year == {2024: 100, 2025: 100, 2026: 100}
    assert all("min_year" not in kw for kw in calls)  # no per-year PubMed calls
