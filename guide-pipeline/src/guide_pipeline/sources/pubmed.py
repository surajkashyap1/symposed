"""PubMed via NCBI E-utilities (esearch + esummary).

Counts come straight from `esearchresult.count`; MeSH terms come from the MeSH
database via esearch(db=mesh) + esummary(db=mesh). The model never supplies a
count or a MeSH term — both are read from the API response (CLAUDE.md rule 1).

An API key (free) raises the rate limit from 3 to 10 requests/second and is sent
as a request param; it is kept out of the cache key by the HTTP layer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from ..http import CachedHttpClient, CachedResponse

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# EFetch is fetched by GET with a comma-joined id list; keep chunks small enough
# for the URL and polite to NCBI.
_FETCH_CHUNK = 150


@dataclass(frozen=True)
class MeshTerm:
    """A real MeSH descriptor: main heading + unique id (e.g. D014808)."""

    name: str
    ui: str


@dataclass(frozen=True)
class Paper:
    """A retrieved PubMed record. Every field is read from the API response."""

    pmid: str
    title: str
    abstract: str
    authors: tuple[str, ...]
    journal: str
    year: Optional[int]
    doi: Optional[str]


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


def _is_pubmed_xml(resp: CachedResponse) -> bool:
    try:
        return ET.fromstring(resp.text).tag == "PubmedArticleSet"
    except ET.ParseError:
        return False


def _node_text(node: Optional[ET.Element]) -> str:
    """All text inside a node, including nested markup (e.g. italics in titles)."""
    return "".join(node.itertext()).strip() if node is not None else ""


def _parse_article(art: ET.Element) -> Optional[Paper]:
    citation = art.find("./MedlineCitation")
    article = citation.find("./Article") if citation is not None else None
    if citation is None or article is None:
        return None
    pmid = (citation.findtext("./PMID") or "").strip()
    title = _node_text(article.find("./ArticleTitle"))

    parts: list[str] = []
    for ab in article.findall("./Abstract/AbstractText"):
        label = ab.get("Label")
        text = _node_text(ab)
        if text:
            parts.append(f"{label}: {text}" if label else text)
    abstract = " ".join(parts)

    journal = article.findtext("./Journal/Title") or ""
    year: Optional[int] = None
    pubdate = article.find("./Journal/JournalIssue/PubDate")
    if pubdate is not None:
        y = pubdate.findtext("./Year")
        if y and y.strip().isdigit():
            year = int(y.strip())
        else:
            match = re.search(r"\d{4}", pubdate.findtext("./MedlineDate") or "")
            if match:
                year = int(match.group())

    authors: list[str] = []
    for a in article.findall("./AuthorList/Author"):
        last = a.findtext("./LastName")
        if last:
            initials = a.findtext("./Initials") or ""
            authors.append(f"{last} {initials}".strip())

    doi: Optional[str] = None
    # The article's OWN ids only — NOT ids in the reference list.
    for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = (aid.text or "").strip() or None
            break

    return Paper(
        pmid=pmid,
        title=title,
        abstract=abstract,
        authors=tuple(authors),
        journal=journal,
        year=year,
        doi=doi,
    )


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

    def search_pmids(self, query: str, *, retmax: int = 400) -> list[str]:
        """PMIDs matching `query`, most recent first, up to `retmax`."""
        params = {
            **self._base_params(),
            "term": query,
            "retmax": str(retmax),
            "sort": "most+recent",
        }
        data = self.http.get_json(ESEARCH_URL, params, validate=_has_count)
        return list(data["esearchresult"].get("idlist", []))

    def titles(self, pmids: list[str]) -> list[tuple[str, str]]:
        """(pmid, title) pairs via ESummary — titles only, no abstracts."""
        if not pmids:
            return []
        params = {**self._base_params(), "id": ",".join(pmids)}
        result = self.http.get_json(ESUMMARY_URL, params, validate=_has_result)["result"]
        out: list[tuple[str, str]] = []
        for uid in result.get("uids", []):
            title = str(result.get(uid, {}).get("title", "")).strip()
            if title:
                out.append((uid, title))
        return out

    def fetch_details(self, pmids: list[str]) -> list[Paper]:
        """Full records (incl. abstracts) for `pmids`, fetched via EFetch XML."""
        papers: list[Paper] = []
        for start in range(0, len(pmids), _FETCH_CHUNK):
            chunk = pmids[start : start + _FETCH_CHUNK]
            params = {
                **self._base_params(),
                "id": ",".join(chunk),
                "rettype": "abstract",
                "retmode": "xml",
            }
            # EFetch is XML, not JSON — use the raw response and parse it.
            resp = self.http.get(EFETCH_URL, params, validate=_is_pubmed_xml)
            root = ET.fromstring(resp.text)
            for art in root.findall("./PubmedArticle"):
                paper = _parse_article(art)
                if paper is not None:
                    papers.append(paper)
        return papers

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
