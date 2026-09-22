"""ClinicalTrials.gov via API v2 (studies).

The count comes straight from `totalCount` in the API response, requested with
`countTotal=true`. No key required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..http import CachedHttpClient, CachedResponse

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"

# Studies still running: their results are not yet published, so they signal a
# topic whose evidence base is about to change.
ACTIVE_STATUSES = ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION")


def _has_total(resp: CachedResponse) -> bool:
    try:
        return "totalCount" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class ClinicalTrialsClient:
    http: CachedHttpClient

    def count(
        self, query: str, *, statuses: Optional[Sequence[str]] = None
    ) -> int:
        """Number of ClinicalTrials.gov studies matching `query`.

        `statuses` restricts to given overall statuses (e.g. ACTIVE_STATUSES for
        trials still running).
        """
        params = {
            "query.term": query,
            "countTotal": "true",
            "pageSize": "1",
        }
        if statuses:
            params["filter.overallStatus"] = "|".join(statuses)
        data = self.http.get_json(STUDIES_URL, params, validate=_has_total)
        return int(data["totalCount"])
