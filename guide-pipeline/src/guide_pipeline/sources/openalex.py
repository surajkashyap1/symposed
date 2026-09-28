"""OpenAlex works API: publication-year distribution for the landscape scan.

One call with group_by=publication_year gives the whole distribution (the spec's
Stage 1 source for it). OpenAlex indexes far more than PubMed, so its numbers are
labelled as OpenAlex's wherever they are shown. No key; an optional contact
email joins OpenAlex's faster "polite pool".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..http import CachedHttpClient, CachedResponse

WORKS_URL = "https://api.openalex.org/works"


def _has_groups(resp: CachedResponse) -> bool:
    try:
        return "group_by" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class OpenAlexClient:
    http: CachedHttpClient
    email: Optional[str] = None

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
