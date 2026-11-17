"""The ONE place that knows how OSF registrations are acquired.

The public OSF API v2 registrations endpoint: no key needed for public reads.
Requests are spaced out (`min_interval`, default 1 s) and a sparse field set
keeps each page of 100 to about 240 KB. If the anonymous rate limit bites, a
free personal access token goes in `OSF_TOKEN`.

Registrations can be filtered by `date_created` (a registration's node is
created when it is registered, so this tracks the registration date) and by
`date_modified` (which also moves when a registration is withdrawn or edited),
so the harvest walks `date_created` windows and the delta pull asks for
everything modified since the mirror was last current.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable, Optional, Protocol

import httpx

from .records import OsfRecord, parse_registration

REGISTRATIONS_URL = "https://api.osf.io/v2/registrations/"
FIELDS = ("title,description,date_registered,date_created,date_modified,"
          "registration_supplement,subjects,tags,withdrawn")
PAGE_SIZE = 100
_RETRY_STATUS = {429, 500, 502, 503, 504}


class OsfError(RuntimeError):
    """OSF access or parsing failed."""


class OsfSource(Protocol):
    mode: str  # recorded against each refresh, e.g. "automated"

    def count_window(self, start: date, end: date, *, field: str = "date_created") -> int:
        """Registrations with `field` in [start, end) (end exclusive)."""
        ...

    def fetch_window(self, start: date, end: date, *,
                     field: str = "date_created") -> list[OsfRecord]:
        """Every registration with `field` in [start, end), all pages."""
        ...


class ApiSource:
    mode = "automated"

    def __init__(
        self,
        *,
        url: str = REGISTRATIONS_URL,
        client: Optional[httpx.Client] = None,
        token: Optional[str] = None,
        min_interval: float = 1.0,
        max_retries: int = 5,
        backoff_base: float = 5.0,
        timeout: float = 120.0,
        user_agent: str = "symposed-guide-pipeline",
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self._client = client or httpx.Client(timeout=timeout)
        self.token = token
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.user_agent = user_agent
        self._sleep = sleep
        self._monotonic = monotonic
        self._next_allowed = 0.0
        self.unparsed: list[str] = []  # registrations we could not read (worth a look)

    def _params(self, start: date, end: date, field: str, size: int) -> dict[str, str]:
        return {
            f"filter[{field}][gte]": start.isoformat(),
            f"filter[{field}][lt]": end.isoformat(),
            "fields[registrations]": FIELDS,
            "page[size]": str(size),
            "sort": field,
        }

    def count_window(self, start: date, end: date, *, field: str = "date_created") -> int:
        data = self._get(self.url, self._params(start, end, field, 1))
        return int(data["links"]["meta"]["total"])

    def fetch_window(self, start: date, end: date, *,
                     field: str = "date_created") -> list[OsfRecord]:
        records: list[OsfRecord] = []
        data = self._get(self.url, self._params(start, end, field, PAGE_SIZE))
        expected = int(data["links"]["meta"]["total"])
        seen = 0
        while True:
            for item in data.get("data") or []:
                seen += 1
                try:
                    records.append(parse_registration(item))
                except (KeyError, TypeError, ValueError):
                    self.unparsed.append(str(item.get("id", "(no id)")))
            nxt = (data.get("links") or {}).get("next")
            if not nxt:
                break
            data = self._get(nxt, None)  # the next link carries every parameter
        if seen < expected:
            raise OsfError(f"OSF window {start}..{end} returned {seen} of {expected} "
                           "registrations")
        return records

    # -- transport -------------------------------------------------------------
    def _get(self, url: str, params: Optional[dict[str, str]]) -> dict[str, Any]:
        headers = {"User-Agent": self.user_agent}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            try:
                resp = self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise OsfError(f"OSF unreachable: {exc}") from exc
                self._sleep(self.backoff_base * 2**attempt)
                continue
            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                wait = resp.headers.get("retry-after")
                self._sleep(float(wait) if wait and wait.isdigit()
                            else self.backoff_base * 2**attempt)
                continue
            if resp.status_code != 200:
                raise OsfError(f"OSF HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise OsfError("OSF returned non-JSON") from exc
            if "data" not in data or "links" not in data:
                raise OsfError("Unexpected OSF response shape")
            return data
        raise OsfError("OSF retries exhausted")  # pragma: no cover

    def _wait_turn(self) -> None:
        now = self._monotonic()
        if now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._monotonic()
        self._next_allowed = now + self.min_interval
