"""Europe PMC via its REST search and full-text endpoints.

The count comes straight from `hitCount` in the API response. Open-access full
text (JATS XML) is fetched only for articles Europe PMC marks open access — no
publisher APIs, no institutional logins (spec update). No key required.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..http import CachedHttpClient, CachedResponse

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
_ID_CHUNK = 100  # PMIDs per open-access lookup query


def _is_xml(resp: CachedResponse) -> bool:
    return resp.text.lstrip().startswith("<")


def _has_hitcount(resp: CachedResponse) -> bool:
    # Europe PMC intermittently returns a 200 of just {"version": "..."} with no
    # hitCount; treat that as transient so the HTTP layer retries instead of
    # caching a bad body.
    try:
        return "hitCount" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class EuropePmcClient:
    http: CachedHttpClient

    def count(self, query: str) -> int:
        """Number of Europe PMC records matching `query`."""
        params = {
            "query": query,
            "format": "json",
            "resultType": "idlist",
            "pageSize": "1",
        }
        data = self.http.get_json(SEARCH_URL, params, validate=_has_hitcount)
        return int(data["hitCount"])

    def open_access_pmcids(self, pmids: list[str]) -> dict[str, str]:
        """{pmid: pmcid} for the given PMIDs that Europe PMC holds as open access."""
        found: dict[str, str] = {}
        for start in range(0, len(pmids), _ID_CHUNK):
            chunk = [p for p in pmids[start : start + _ID_CHUNK] if p.isdigit()]
            if not chunk:
                continue
            ids = " OR ".join(f"EXT_ID:{p}" for p in chunk)
            params = {
                "query": f"({ids}) AND SRC:MED",
                "format": "json",
                "resultType": "lite",
                "pageSize": "1000",
            }
            data = self.http.get_json(SEARCH_URL, params, validate=_has_hitcount)
            for rec in data.get("resultList", {}).get("result", []):
                pmid, pmcid = rec.get("pmid"), rec.get("pmcid")
                if pmid and pmcid and rec.get("isOpenAccess") == "Y":
                    found[str(pmid)] = str(pmcid)
        return found

    def full_text_xml(self, pmcid: str) -> str:
        """The JATS XML full text of an open-access article."""
        return self.http.get(FULLTEXT_URL.format(pmcid=pmcid), None, validate=_is_xml).text
