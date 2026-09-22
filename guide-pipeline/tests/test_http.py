import httpx
import pytest

from guide_pipeline.http import CachedHttpClient, RateLimiter


def make_client(handler, tmp_path, **kwargs):
    """A CachedHttpClient wired to a mock transport that never really sleeps."""
    transport = httpx.MockTransport(handler)
    return CachedHttpClient(
        cache_dir=tmp_path / ".cache",
        client=httpx.Client(transport=transport),
        sleep=lambda _s: None,
        **kwargs,
    )


def test_get_json_parses_response(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"hello": "world"})

    with make_client(handler, tmp_path) as http:
        assert http.get_json("https://example.test/x") == {"hello": "world"}


def test_response_is_cached_not_refetched(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"count": 7})

    with make_client(handler, tmp_path) as http:
        first = http.get_json("https://example.test/q", {"term": "sepsis"})
        second = http.get_json("https://example.test/q", {"term": "sepsis"})

    assert first == second == {"count": 7}
    assert calls["n"] == 1  # second call served from cache


def test_api_key_excluded_from_cache_key(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    with make_client(handler, tmp_path) as http:
        http.get_json("https://example.test/q", {"term": "x", "api_key": "SECRET"})
        http.get_json("https://example.test/q", {"term": "x"})

    assert calls["n"] == 1  # same query, secret ignored in the cache key


def test_retries_transient_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"count": 42})

    with make_client(handler, tmp_path, max_retries=4) as http:
        assert http.get_json("https://example.test/q") == {"count": 42}
    assert attempts["n"] == 3  # two failures, third succeeded


def test_permanent_error_not_retried(tmp_path):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(404)

    with make_client(handler, tmp_path) as http:
        with pytest.raises(httpx.HTTPStatusError):
            http.get("https://example.test/missing")
    assert attempts["n"] == 1  # 404 is permanent — no retry


def test_gives_up_after_max_retries(tmp_path):
    def handler(request):
        return httpx.Response(500)

    with make_client(handler, tmp_path, max_retries=2) as http:
        with pytest.raises(httpx.HTTPStatusError):
            http.get("https://example.test/down")


def test_invalid_body_is_retried_then_succeeds(tmp_path):
    # Mirrors the real Europe PMC flake: a 200 with a partial body, then a good one.
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(200, json={"version": "6.9"})  # no hitCount
        return httpx.Response(200, json={"hitCount": 99})

    with make_client(handler, tmp_path) as http:
        data = http.get_json(
            "https://example.test/q", validate=lambda r: "hitCount" in r.json()
        )
    assert data == {"hitCount": 99}
    assert attempts["n"] == 3


def test_invalid_body_is_not_cached(tmp_path):
    # A partial 200 must never poison the cache; a later good response must win.
    responses = [
        httpx.Response(200, json={"version": "6.9"}),
        httpx.Response(200, json={"hitCount": 5}),
    ]

    def handler(request):
        return responses.pop(0)

    validate = lambda r: "hitCount" in r.json()
    with make_client(handler, tmp_path, max_retries=0) as http:
        # first call: only the bad response is available, no retries left -> raises
        with pytest.raises(ValueError):
            http.get("https://example.test/q", validate=validate)
        # second call: must hit the network again (bad body was not cached)
        assert http.get_json("https://example.test/q", validate=validate) == {
            "hitCount": 5
        }


def test_rate_limiter_spaces_requests():
    clock = {"t": 0.0}
    slept: list[float] = []
    limiter = RateLimiter(
        0.1,
        monotonic=lambda: clock["t"],
        sleep=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)),
    )
    limiter.wait()  # first is immediate
    limiter.wait()  # must wait the full interval
    limiter.wait()
    assert slept == [pytest.approx(0.1), pytest.approx(0.1)]


def test_rate_limiter_no_wait_when_enough_time_passed():
    clock = {"t": 0.0}
    slept: list[float] = []
    limiter = RateLimiter(
        0.1, monotonic=lambda: clock["t"], sleep=lambda s: slept.append(s)
    )
    limiter.wait()
    clock["t"] = 5.0  # plenty of time later
    limiter.wait()
    assert slept == []
