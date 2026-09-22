"""Shared HTTP layer for the data-source clients.

One place that every external call goes through, so all three sources
(PubMed / Europe PMC / ClinicalTrials.gov) get the same guarantees:

- **Rate limiting** — a minimum interval between real requests (PubMed allows
  10 req/s with an API key, 3 req/s without; see `settings`).
- **Retry + backoff** — transient failures (429, 5xx, network errors) are retried
  with exponential backoff before giving up.
- **Caching** — every external response is written to disk and reused, so a query
  is never sent twice (CLAUDE.md: "Cache every external API response").

The clock, sleep and underlying transport are all injectable, so the tests run
fully offline and deterministically.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import httpx

# Status codes worth retrying (the rest are permanent — fail fast).
_RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class CachedResponse:
    """A minimal, cache-serialisable view of an HTTP response."""

    status_code: int
    text: str
    url: str

    def json(self) -> Any:
        return json.loads(self.text)


def _cache_key(method: str, url: str, params: Optional[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        {"m": method.upper(), "u": url, "p": _stable(params)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable(params: Optional[Mapping[str, Any]]) -> Any:
    if not params:
        return None
    # Drop secrets from the cache key so the same query caches identically
    # whether or not an API key is configured.
    return {k: v for k, v in sorted(params.items()) if k not in _SECRET_PARAMS}


_SECRET_PARAMS = {"api_key"}


class RateLimiter:
    """Enforces a minimum interval between calls to `wait()`."""

    def __init__(
        self,
        min_interval: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = max(0.0, min_interval)
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed = 0.0

    def wait(self) -> None:
        now = self._monotonic()
        if now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._monotonic()
        self._next_allowed = max(now, self._next_allowed) + self.min_interval


class CachedHttpClient:
    """httpx wrapper adding rate limiting, retry+backoff and on-disk caching."""

    def __init__(
        self,
        *,
        cache_dir: str | Path = ".cache",
        min_interval: float = 0.0,
        max_retries: int = 4,
        backoff_base: float = 0.5,
        timeout: float = 30.0,
        client: Optional[httpx.Client] = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._limiter = RateLimiter(min_interval, monotonic=monotonic, sleep=sleep)
        self._sleep = sleep
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    # -- context management ------------------------------------------------
    def __enter__(self) -> "CachedHttpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # -- requests ----------------------------------------------------------
    def get_json(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        validate: Optional[Callable[[CachedResponse], bool]] = None,
    ) -> Any:
        return self.get(url, params, validate=validate).json()

    def get(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        validate: Optional[Callable[[CachedResponse], bool]] = None,
    ) -> CachedResponse:
        """GET with rate limiting, retry+backoff and caching.

        `validate`, if given, decides whether a 2xx body is acceptable. A response
        that fails it is treated as a transient failure — retried, and never cached.
        This guards against APIs (e.g. Europe PMC) that intermittently return a
        200 with an empty/partial body.
        """
        key = _cache_key("GET", url, params)
        cached = self._read_cache(key)
        if cached is not None:
            return cached
        response = self._request_with_retry("GET", url, params, validate)
        self._write_cache(key, response)
        return response

    # -- internals ---------------------------------------------------------
    def _request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Mapping[str, Any]],
        validate: Optional[Callable[[CachedResponse], bool]] = None,
    ) -> CachedResponse:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._limiter.wait()
            try:
                resp = self._client.request(method, url, params=params)
            except httpx.HTTPError as exc:  # network/timeout — retryable
                last_exc = exc
            else:
                if resp.status_code in _RETRY_STATUS:
                    last_exc = httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                else:
                    resp.raise_for_status()
                    cached = CachedResponse(
                        status_code=resp.status_code,
                        text=resp.text,
                        url=str(resp.url),
                    )
                    if validate is None or validate(cached):
                        return cached
                    last_exc = ValueError(
                        f"response body failed validation (retryable): {url}"
                    )
            if attempt < self.max_retries:
                self._sleep(self.backoff_base * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[CachedResponse]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CachedResponse(
            status_code=data["status_code"], text=data["text"], url=data["url"]
        )

    def _write_cache(self, key: str, response: CachedResponse) -> None:
        self._cache_path(key).write_text(
            json.dumps(
                {
                    "status_code": response.status_code,
                    "text": response.text,
                    "url": response.url,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
