"""ClinicalTrials.gov via API v2 (studies).

The count comes straight from `totalCount` in the API response, requested with
`countTotal=true`. No key required.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..http import CachedHttpClient, CachedResponse

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"


def _has_total(resp: CachedResponse) -> bool:
    try:
        return "totalCount" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class ClinicalTrialsClient:
    http: CachedHttpClient

    def count(self, query: str) -> int:
        """Number of ClinicalTrials.gov studies matching `query`."""
        params = {
            "query.term": query,
            "countTotal": "true",
            "pageSize": "1",
        }
        data = self.http.get_json(STUDIES_URL, params, validate=_has_total)
        return int(data["totalCount"])
