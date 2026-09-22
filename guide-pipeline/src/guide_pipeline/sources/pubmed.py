"""PubMed via NCBI E-utilities (esearch + esummary).

Counts come straight from `esearchresult.count`; MeSH terms come from the MeSH
database via esearch(db=mesh) + esummary(db=mesh). The model never supplies a
count or a MeSH term — both are read from the API response (CLAUDE.md rule 1).

An API key (free) raises the rate limit from 3 to 10 requests/second and is sent
as a request param; it is kept out of the cache key by the HTTP layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..http import CachedHttpClient, CachedResponse

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@dataclass(frozen=True)
class MeshTerm:
    """A real MeSH descriptor: main heading + unique id (e.g. D014808)."""

    name: str
    ui: str


def _has_count(resp: CachedResponse) -> bool:
    try:
        return "count" in resp.json().get("esearchresult", {})
    except ValueError:
        return False


def _has_result(resp: CachedResponse) -> bool:
    try:
        return "result" in resp.json()
    except ValueError:
        return False


@dataclass(frozen=True)
class PubMedClient:
    http: CachedHttpClient
    api_key: Optional[str] = None
    tool: str = "symposed-guide-pipeline"
    email: Optional[str] = None

    def _base_params(self) -> dict[str, str]:
        params: dict[str, str] = {"db": "pubmed", "retmode": "json", "tool": self.tool}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    def count(
        self,
        query: str,
        *,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> int:
        """Number of PubMed records matching `query` (optionally bounded by pub year)."""
        params = {**self._base_params(), "term": query, "rettype": "count"}
        if min_year is not None or max_year is not None:
            params["datetype"] = "pdat"
            if min_year is not None:
                params["mindate"] = str(min_year)
            if max_year is not None:
                params["maxdate"] = str(max_year)
        data = self.http.get_json(ESEARCH_URL, params, validate=_has_count)
        return int(data["esearchresult"]["count"])

    def mesh_terms(self, topic: str, *, max_terms: int = 5) -> list[MeshTerm]:
        """Real MeSH descriptors matching `topic`, via the MeSH database.

        Never invents a term: searches db=mesh for matching descriptor records,
        then reads each one's main heading + UI from esummary.
        """
        search = {
            **self._base_params(),
            "db": "mesh",
            "term": topic,
            "retmax": str(max_terms),
        }
        found = self.http.get_json(ESEARCH_URL, search, validate=_has_count)
        ids = found["esearchresult"].get("idlist", [])
        if not ids:
            return []

        summary = {**self._base_params(), "db": "mesh", "id": ",".join(ids)}
        result = self.http.get_json(ESUMMARY_URL, summary, validate=_has_result)["result"]

        terms: list[MeshTerm] = []
        for uid in result.get("uids", []):
            record = result.get(uid, {})
            headings = record.get("ds_meshterms") or []
            if headings:  # first entry is the main descriptor heading
                terms.append(MeshTerm(name=headings[0], ui=record.get("ds_meshui", "")))
        return terms
