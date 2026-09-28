"""Europe PMC via its REST search and full-text endpoints.

The count comes straight from `hitCount` in the API response. Open-access full
text (JATS XML) is fetched only for articles Europe PMC marks open access — no
publisher APIs, no institutional logins (spec update). No key required.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from ..http import CachedHttpClient, CachedResponse
from .pubmed import Paper

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
_ID_CHUNK = 100  # PMIDs per open-access lookup query


# PubMed field tags -> Europe PMC fields. Verified live: TITLE_ABS matches PubMed
# [tiab] closely, and MeSH must go to KW (Europe PMC's MESH field is sparse and
# breaks OR logic). PubMed-only subsets such as systematic[sb] have no
# equivalent and are dropped, so only concept queries should be translated.
_TAG = re.compile(r"\[([A-Za-z: ]+)\]")
_BOOL = re.compile(r"\b(AND|OR|NOT)\b")
_EPMC_FIELD = {"tiab": "TITLE_ABS", "tw": "TITLE_ABS", "all": "TITLE_ABS",
               "ti": "TITLE", "mh": "KW", "mesh": "KW", "mesh terms": "KW",
               "mesh:noexp": "KW", "majr": "KW", "pt": "PUB_TYPE"}


def pubmed_to_europepmc(query: str) -> str:
    """Translate a PubMed concept query into Europe PMC search syntax."""
    out, i = [], 0
    for m in _TAG.finditer(query):
        before = query[i:m.start()]
        # The term is the quoted phrase, or the words back to the last
        # parenthesis or boolean operator, immediately before the tag.
        term_match = re.search(r'("[^"]*"|[^()"]*?)\s*$', before)
        term = term_match.group(1).strip() if term_match else ""
        pieces = _BOOL.split(term)
        term = pieces[-1].strip() if pieces else term
        head = before[: before.rfind(term)] if term else before
        tag = m.group(1).strip().lower()
        field = _EPMC_FIELD.get(tag)
        years = re.fullmatch(r"(\d{4}):(\d{4})", term)
        if tag in ("dp", "pdat") and years:
            out.append(f"{head}PUB_YEAR:[{years.group(1)} TO {years.group(2)}]")
        elif field and term:
            keep_as_is = term.startswith('"') or (term.endswith("*") and " " not in term)
            quoted = term if keep_as_is else f'"{term.strip(chr(34))}"'
            out.append(f"{head}{field}:{quoted}")
        else:
            out.append(head)  # unsupported tag: drop the term
        i = m.end()
    out.append(query[i:])
    text = re.sub(r"\s+", " ", "".join(out)).strip()
    # Tidy what dropped terms leave behind: empty groups and dangling operators.
    for _ in range(5):
        text = re.sub(r"\(\s*\)", "", text)
        text = re.sub(r"\s*\b(AND|OR|NOT)\s*(?=\)|$)", "", text)
        text = re.sub(r"(?<=\()\s*(AND|OR|NOT)\b", "", text)
        text = re.sub(r"^\s*(AND|OR)\b", "", text)
        text = re.sub(r"\b(AND|OR)\s+(AND|OR)\b", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean(text: str) -> str:
    """Strip markup; no stray space before punctuation where a tag closed."""
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())
    return re.sub(r"\s+([.,;:!?)])", r"\1", text)


def _record_to_paper(rec: dict) -> Paper | None:
    title = _clean(rec.get("title", "")).rstrip(".").strip()
    if not title:
        return None
    preprint = rec.get("source") == "PPR"
    ident = str(rec.get("pmid") or rec.get("id") or "")
    authors = tuple(
        f"{a.get('lastName', '')} {a.get('initials', '')}".strip()
        for a in (rec.get("authorList") or {}).get("author", [])
        if a.get("lastName")
    )
    journal = ((rec.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
    if preprint:
        publisher = (rec.get("bookOrReportDetails") or {}).get("publisher", "")
        journal = f"{publisher} (preprint)" if publisher else "Preprint"
    year = rec.get("pubYear")
    return Paper(
        pmid=ident,
        title=title,
        abstract=_clean(rec.get("abstractText", "")),
        authors=authors,
        journal=journal,
        year=int(year) if str(year).isdigit() else None,
        doi=rec.get("doi"),
        id_type="PPR" if preprint else "PMID",
        source="Europe PMC (preprint)" if preprint else "Europe PMC",
    )


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

    def search_records(self, query: str, *, max_records: int = 100) -> list[Paper]:
        """Full records (with abstracts) for a Europe PMC query, paged by cursor."""
        papers: list[Paper] = []
        cursor = "*"
        while len(papers) < max_records:
            params = {
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": str(min(1000, max_records - len(papers))),
                "cursorMark": cursor,
            }
            data = self.http.get_json(SEARCH_URL, params, validate=_has_hitcount)
            results = data.get("resultList", {}).get("result", [])
            papers += [p for p in (_record_to_paper(r) for r in results) if p]
            nxt = data.get("nextCursorMark")
            if not results or not nxt or nxt == cursor:
                break
            cursor = nxt
        return papers[:max_records]

    def preprints(self, pubmed_concept_query: str, *, max_records: int = 50) -> tuple[int, list[Paper]]:
        """(total, records) of preprints matching a PubMed concept query."""
        query = f"({pubmed_to_europepmc(pubmed_concept_query)}) AND SRC:PPR"
        return self.count(query), self.search_records(query, max_records=max_records)
