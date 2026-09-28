"""Crossref works API: DOI gap-filling for records PubMed returned without one.

The guide lists unclear papers without open access by DOI, so a missing DOI is
looked up by title. A DOI is accepted only when Crossref's own title matches the
paper's closely and the year agrees within one — it always comes from Crossref's
response, never a model (rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..http import CachedHttpClient, CachedResponse
from ..prospero import match_key, similarity

WORKS_URL = "https://api.crossref.org/works"
MIN_TITLE_SIMILARITY = 0.9


def _has_items(resp: CachedResponse) -> bool:
    try:
        return "items" in resp.json().get("message", {})
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class CrossrefClient:
    http: CachedHttpClient
    email: Optional[str] = None

    def find_doi(self, title: str, year: Optional[int]) -> Optional[str]:
        params = {"query.bibliographic": title, "rows": "3",
                  "select": "DOI,title,issued,published"}
        if self.email:
            params["mailto"] = self.email
        items = self.http.get_json(WORKS_URL, params, validate=_has_items)["message"]["items"]
        key = match_key(title)
        for item in items:
            their = (item.get("title") or [""])[0]
            parts = ((item.get("issued") or item.get("published") or {}).get("date-parts") or [[None]])
            their_year = parts[0][0] if parts and parts[0] else None
            year_ok = year is None or their_year is None or abs(int(their_year) - year) <= 1
            if their and year_ok and similarity(key, match_key(their)) >= MIN_TITLE_SIMILARITY:
                return str(item.get("DOI", "")).lower() or None
        return None
