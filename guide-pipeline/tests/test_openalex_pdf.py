import httpx

from guide_pipeline.http import CachedHttpClient
from guide_pipeline.sources.openalex import OpenAlexClient, pdf_links

WORK = {
    "open_access": {"is_oa": True, "oa_status": "hybrid"},
    "best_oa_location": {"is_oa": True, "pdf_url": "https://pub/a.pdf"},
    "locations": [
        {"is_oa": True, "pdf_url": "https://pub/a.pdf"},
        {"is_oa": False, "pdf_url": "https://paywalled/b.pdf"},
        {"is_oa": True, "pdf_url": "https://repo/c.pdf"},
        {"is_oa": True, "pdf_url": None},
    ],
}


def test_pdf_links_are_open_access_best_first_without_duplicates():
    assert pdf_links(WORK) == ["https://pub/a.pdf", "https://repo/c.pdf"]


def client(tmp_path, handler, email="team@example.org"):
    transport = httpx.MockTransport(handler)
    return OpenAlexClient(http=CachedHttpClient(cache_dir=tmp_path, client=httpx.Client(transport=transport)),
                          email=email, pdf_client=httpx.Client(transport=transport))


def test_closed_works_give_no_links(tmp_path):
    closed = {**WORK, "open_access": {"is_oa": False}}
    c = client(tmp_path, lambda req: httpx.Response(200, json=closed))
    assert c.open_access_pdf_urls("10.1/x") == []


def test_download_names_the_pipeline_and_only_accepts_a_pdf(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers["user-agent"])
        if req.url.path == "/ok.pdf":
            return httpx.Response(200, content=b"%PDF-1.7 body")
        if req.url.path == "/page.pdf":
            return httpx.Response(200, content=b"<html>Sign in</html>")
        return httpx.Response(403)

    c = client(tmp_path, handler)
    assert c.download_pdf("https://pub/ok.pdf") == b"%PDF-1.7 body"
    assert c.download_pdf("https://pub/page.pdf") is None
    assert c.download_pdf("https://pub/blocked.pdf") is None
    assert seen[0] == "symposed-guide-pipeline (mailto:team@example.org)"
