"""PROSPERO records, export-file parsing, and fuzzy title matching.

Parsing lives here, not in the adapter, because the merge path must be identical
whether records arrived from the endpoint or from a file an administrator
exported by hand (spec §3.4). Both routes produce `ProsperoRecord`s.
"""

from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


class ProsperoError(RuntimeError):
    """PROSPERO access or parsing failed."""


@dataclass(frozen=True)
class ProsperoRecord:
    registration_id: str  # e.g. CRD42024590274
    title: str
    registration_date: Optional[date] = None
    # Not in the public export today; kept so a proper feed can fill them in.
    status: Optional[str] = None
    condition: Optional[str] = None
    outcomes: Optional[str] = None


_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    """Strip markup and entities, collapse whitespace."""
    return " ".join(html.unescape(_TAG_RE.sub(" ", text)).split())


def _parse_date(text: str) -> Optional[date]:
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# -- export files ---------------------------------------------------------------
def parse_ris(text: str) -> list[ProsperoRecord]:
    """Parse PROSPERO's RIS export (what the UI "Download" button produces)."""
    records: list[ProsperoRecord] = []
    fields: dict[str, str] = {}
    for line in text.splitlines():
        tag, _, value = line.partition("  -")
        tag = tag.strip()
        value = value.strip()
        if tag == "TY":
            fields = {}
        elif tag == "ER":
            if fields.get("ID") and fields.get("TI"):
                records.append(
                    ProsperoRecord(
                        registration_id=fields["ID"],
                        title=clean_text(fields["TI"]),
                        registration_date=_parse_date(fields.get("DP", "")),
                    )
                )
            fields = {}
        elif tag:
            fields[tag] = value
    return records


# Header names a CSV feed might plausibly use for each field (lowercased).
_CSV_COLUMNS = {
    "registration_id": ("registration id", "registration_id", "accession number",
                        "accessionnumber", "crd number", "id"),
    "title": ("title", "review title"),
    "registration_date": ("date of registration", "registration date",
                          "registration_date", "date first published", "date"),
    "status": ("review status", "status", "reviewstatus"),
}


def parse_csv(text: str) -> list[ProsperoRecord]:
    """Parse a CSV feed with recognisable ID and title columns."""
    reader = csv.DictReader(io.StringIO(text))
    header = {h.strip().lower(): h for h in (reader.fieldnames or [])}

    def column(field: str) -> Optional[str]:
        for name in _CSV_COLUMNS[field]:
            if name in header:
                return header[name]
        return None

    id_col, title_col = column("registration_id"), column("title")
    if id_col is None or title_col is None:
        raise ProsperoError(
            "CSV has no recognisable registration ID and title columns "
            f"(got: {', '.join(reader.fieldnames or [])})"
        )
    date_col, status_col = column("registration_date"), column("status")
    records = []
    for row in reader:
        rid, title = (row.get(id_col) or "").strip(), clean_text(row.get(title_col) or "")
        if not rid or not title:
            continue
        records.append(
            ProsperoRecord(
                registration_id=rid,
                title=title,
                registration_date=_parse_date(row.get(date_col) or "") if date_col else None,
                status=((row.get(status_col) or "").strip() or None) if status_col else None,
            )
        )
    return records


def parse_export(text: str) -> list[ProsperoRecord]:
    """Parse an export file, RIS or CSV (sniffed from the content)."""
    if re.search(r"^TY  -", text, re.MULTILINE):
        return parse_ris(text)
    return parse_csv(text)


# -- fuzzy matching -------------------------------------------------------------
# Stop words plus words nearly every protocol title carries ("systematic
# review", "meta-analysis"), which would otherwise inflate every similarity.
_STOP_WORDS = frozenset(
    """a an and are as at be by for from in into is of on or the their this to
    with within without versus vs among between its than that what which who how
    does do can
    systematic review reviews meta analysis analyses metaanalysis scoping
    narrative literature protocol umbrella rapid living update updated study
    studies effect effects impact role""".split()
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def match_key(title: str) -> str:
    """Normalised text used for matching: lowercase, no punctuation or stop words."""
    words = _NON_ALNUM.sub(" ", clean_text(title).lower()).split()
    return " ".join(w for w in words if w not in _STOP_WORDS)


def _trigrams(text: str) -> set[str]:
    # pg_trgm style: each word padded with two leading and one trailing space.
    grams: set[str] = set()
    for word in text.split():
        padded = f"  {word} "
        grams.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return grams


def similarity(a: str, b: str) -> float:
    """Trigram similarity (shared / union) of two match keys, 0.0 to 1.0."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
