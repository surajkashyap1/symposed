"""OpenAlex works API: publication-year distribution and open access PDF links.

One call with group_by=publication_year gives the whole distribution (the spec's
Stage 1 source for it). OpenAlex indexes far more than PubMed, so its numbers are
labelled as OpenAlex's wherever they are shown. No key; an optional contact
email joins OpenAlex's faster "polite pool".

Discovery also asks OpenAlex for the open access PDF of a review that Europe PMC
does not hold (free on the publisher's site, or in a repository). The download
names the pipeline honestly in its User-Agent and gives up quietly when a
publisher refuses it: no browser disguise, no logins, no paywall workarounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from ..http import CachedHttpClient, CachedResponse

WORKS_URL = "https://api.openalex.org/works"
MAX_PDF_BYTES = 40 * 1024 * 1024


def _is_work(resp: CachedResponse) -> bool:
    try:
        return "open_access" in resp.json()
    except ValueError:
        return False


def pdf_links(work: dict) -> list[str]:
    """Open access PDF links for one work, best location first, no duplicates."""
    locations = [work.get("best_oa_location") or {}, *(work.get("locations") or [])]
    out: list[str] = []
    for loc in locations:
        url = (loc or {}).get("pdf_url")
        if url and (loc.get("is_oa") or loc is locations[0]) and url not in out:
            out.append(url)
    return out


def _has_groups(resp: CachedResponse) -> bool:
    try:
        return "group_by" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class OpenAlexClient:
    http: CachedHttpClient
    email: Optional[str] = None
    pdf_client: Optional[httpx.Client] = None  # injectable for tests

    def works_by_year(self, search: str, *, first_year: int, last_year: int) -> tuple[int, dict[int, int]]:
        """(total works, {year: works}) for a plain-text search."""
        params = {"search": search, "group_by": "publication_year", "per_page": "200"}
        if self.email:
            params["mailto"] = self.email
        data = self.http.get_json(WORKS_URL, params, validate=_has_groups)
        counts = {int(g["key"]): int(g["count"]) for g in data.get("group_by", [])
                  if str(g.get("key", "")).isdigit()}
        by_year = {y: counts.get(y, 0) for y in range(first_year, last_year + 1)}
        return int(data.get("meta", {}).get("count", 0)), by_year

    def open_access_pdf_urls(self, doi: str) -> list[str]:
        """Direct PDF links OpenAlex lists as open access for a DOI (may be none)."""
        params = {"mailto": self.email} if self.email else None
        work = self.http.get_json(f"{WORKS_URL}/doi:{quote(doi.strip(), safe='/')}", params,
                                  validate=_is_work)
        return pdf_links(work) if (work.get("open_access") or {}).get("is_oa") else []

    def download_pdf(self, url: str) -> Optional[bytes]:
        """The PDF at `url`, or None when the site refuses or sends something else."""
        agent = "symposed-guide-pipeline" + (f" (mailto:{self.email})" if self.email else "")
        client = self.pdf_client or httpx.Client(timeout=60, follow_redirects=True)
        try:
            resp = client.get(url, headers={"User-Agent": agent})
        except httpx.HTTPError:
            return None
        finally:
            if self.pdf_client is None:
                client.close()
        body = resp.content
        if resp.status_code != 200 or not body.startswith(b"%PDF") or len(body) > MAX_PDF_BYTES:
            return None
        return body
