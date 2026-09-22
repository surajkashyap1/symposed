"""Europe PMC via its REST search endpoint.

The count comes straight from `hitCount` in the API response. No key required.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..http import CachedHttpClient, CachedResponse

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


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
