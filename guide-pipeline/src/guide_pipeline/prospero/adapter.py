"""The ONE place that knows how PROSPERO data is acquired (spec §3.3).

Today that is the undocumented JSON endpoint behind PROSPERO's search page. It
is not a public API: it can change without notice, and CRD have not (yet) given
permission to automate it. So everything about it is confined to this file. If
CRD grant a proper feed, add a class implementing `ProsperoSource` here and
switch to it; the mirror, the merge path and the pipeline do not change. The
manual route (an administrator uploads an export file) needs no source at all —
see `service.import_export_file`.

Etiquette: requests are spaced out (`min_interval`, default 3 s), the full
register is harvested once, and weekly refreshes pull only new registrations.
"""

from __future__ import annotations

import base64
import time
from datetime import date
from typing import Any, Callable, Optional, Protocol

import httpx

from .records import ProsperoError, ProsperoRecord, clean_text, parse_ris

PROSPERO_SEARCH_URL = "https://www.crd.york.ac.uk/PROSPERO/api/search"
# The UI caps a single export at 10,000 records.
EXPORT_CAP = 10_000
_RETRY_STATUS = {429, 500, 502, 503, 504}


class ProsperoSource(Protocol):
    """How registrations are acquired. Swap implementations, not the pipeline."""

    mode: str  # recorded against each refresh, e.g. "automated"
    export_cap: int  # most records one fetch_range call may return

    def count_range(self, start: date, end: date, id_prefix: str = "") -> int:
        """Registrations in [start, end], inclusive; optionally only IDs with a prefix."""
        ...

    def fetch_range(
        self, start: date, end: date, id_prefix: str = ""
    ) -> list[ProsperoRecord]:
        """Every registration in [start, end] (and prefix); at most `export_cap`."""
        ...


def _uk_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class EndpointSource:
    """PROSPERO's undocumented search endpoint (the same call its web UI makes)."""

    mode = "automated"

    def __init__(
        self,
        *,
        url: str = PROSPERO_SEARCH_URL,
        client: Optional[httpx.Client] = None,
        min_interval: float = 3.0,
        max_retries: int = 4,
        backoff_base: float = 5.0,
        timeout: float = 300.0,  # a 10,000-record export is ~12 MB and slow
        export_cap: int = EXPORT_CAP,
        user_agent: str = "symposed-guide-pipeline",
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self._client = client or httpx.Client(timeout=timeout)
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.export_cap = export_cap
        self.user_agent = user_agent
        self._sleep = sleep
        self._monotonic = monotonic
        self._next_allowed = 0.0
        # Export rows without data: withdrawn protocols (no public title; they
        # block nothing, so they are rightly absent) and anything else we
        # could not resolve (worth a look).
        self.withdrawn: list[str] = []
        self.unresolved: list[str] = []

    def count_range(self, start: date, end: date, id_prefix: str = "") -> int:
        return int(self._search(start, end, id_prefix, download=False)["hits"])

    def fetch_range(
        self, start: date, end: date, id_prefix: str = ""
    ) -> list[ProsperoRecord]:
        result = self._search(start, end, id_prefix, download=True)
        expected = int(result["hits"])
        if expected > self.export_cap:
            raise ProsperoError(
                f"{expected} records in {start}..{end} exceeds the export cap "
                f"of {self.export_cap}; split the window"
            )
        hits = result.get("retvals", {}).get("hits", {}).get("hits", [])
        if len(hits) != expected:
            raise ProsperoError(
                f"export for {start}..{end} returned {len(hits)} of {expected} records"
            )
        # A few export rows come back with `ris: null` (seen live: 1 in 5,657).
        # Their ID is still in the sort key; look each one up individually.
        with_ris = [h["_source"]["ris"] for h in hits if h.get("_source", {}).get("ris")]
        missing = [
            str((h.get("sort") or [""])[0])
            for h in hits
            if not h.get("_source", {}).get("ris")
        ]
        records = parse_ris("".join(with_ris))
        if len(records) != len(with_ris):
            raise ProsperoError(
                f"export for {start}..{end}: parsed {len(records)} of {len(with_ris)} RIS rows"
            )
        for rid in missing:
            found = self._lookup(rid) if rid.startswith("CRD") else None
            if isinstance(found, ProsperoRecord):
                records.append(found)
            elif found == "withdrawn":
                self.withdrawn.append(rid)
            else:
                self.unresolved.append(rid or "(no id)")
        return records

    def _lookup(self, registration_id: str) -> ProsperoRecord | str | None:
        """One record by ID via the ordinary search results (which carry the title).

        Returns the record, "withdrawn" for a withdrawn protocol, or None.
        """
        term = f"({registration_id}):AN"
        data = self._post(
            {"term": term, "actual": term, "line": 0, "page": 1, "nperpage": 1,
             "sort": "id", "sortorder": "asc", "filters": [], "download": False}
        )
        try:
            source = data[0]["retvals"]["hits"]["hits"][0]["_source"]
        except (KeyError, IndexError, TypeError):
            return None
        if source.get("editingstatus") == "withdrawn":
            return "withdrawn"
        title = clean_text(source.get("title") or "")
        if not title:
            return None
        return ProsperoRecord(
            registration_id=registration_id,
            title=title,
            status=source.get("reviewstatus") or None,
        )

    # -- transport -------------------------------------------------------------
    def _search(
        self, start: date, end: date, id_prefix: str, *, download: bool
    ) -> dict[str, Any]:
        # An accession-number wildcard partitions a day too big for one export.
        term = f"({id_prefix}*):AN" if id_prefix else "*"
        payload = {
            "term": term,
            "actual": term,
            "line": 0,
            "page": 1,
            "nperpage": 1,  # ignored by exports, which return every hit
            "sort": "id",
            "sortorder": "asc",
            "filters": [
                {"name": "dateinprospero", "value": [f"{_uk_date(start)} to {_uk_date(end)}"]}
            ],
            "download": download,
        }
        data = self._post(payload)
        if isinstance(data, dict) and data.get("status") == "error":
            raise ProsperoError(f"PROSPERO error: {data.get('errormessage')}")
        if not isinstance(data, list) or not data or "hits" not in data[0]:
            raise ProsperoError("Unexpected PROSPERO response shape")
        return data[0]

    def _post(self, payload: dict[str, Any]) -> Any:
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            headers = {
                "User-Agent": self.user_agent,
                # The web UI sends the current time in base64 on every request.
                "prospero-auth-token": base64.b64encode(
                    str(int(time.time() * 1000)).encode()
                ).decode(),
            }
            try:
                resp = self._client.post(self.url, json=payload, headers=headers)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise ProsperoError(f"PROSPERO unreachable: {exc}") from exc
                self._sleep(self.backoff_base * 2**attempt)
                continue
            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                self._sleep(self.backoff_base * 2**attempt)
                continue
            if resp.status_code != 200:
                raise ProsperoError(f"PROSPERO HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise ProsperoError("PROSPERO returned non-JSON") from exc
        raise ProsperoError("PROSPERO retries exhausted")  # pragma: no cover

    def _wait_turn(self) -> None:
        now = self._monotonic()
        if now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._monotonic()
        self._next_allowed = now + self.min_interval
