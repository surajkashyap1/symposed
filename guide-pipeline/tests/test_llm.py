import json

import httpx
import pytest

from guide_pipeline.llm import (
    AnthropicClient,
    GroqClient,
    LLMError,
    build_llm,
)
from guide_pipeline.settings import Settings


def groq_with(handler):
    return GroqClient(
        api_key="K", client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _chat_response(content_obj):
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps(content_obj)}}]}
    )


def test_groq_returns_parsed_json():
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return _chat_response({"candidates": [{"title": "T"}]})

    out = groq_with(handler).complete_json("sys", "user")
    assert out == {"candidates": [{"title": "T"}]}


def test_groq_raises_on_http_error():
    def handler(request):
        return httpx.Response(429, text="rate limited")

    with pytest.raises(LLMError):
        groq_with(handler).complete_json("s", "u")


_JSON_FAILED = httpx.Response(
    400, json={"error": {"code": "json_validate_failed", "failed_generation": ""}}
)


def test_groq_retries_json_validate_failed():
    calls = []

    def handler(request):
        calls.append(1)
        return _JSON_FAILED if len(calls) < 3 else _chat_response({"ok": True})

    assert groq_with(handler).complete_json("s", "u") == {"ok": True}
    assert len(calls) == 3  # two retries, then success


def test_groq_gives_up_after_json_retries():
    calls = []

    def handler(request):
        calls.append(1)
        return _JSON_FAILED

    with pytest.raises(LLMError, match="json_validate_failed"):
        groq_with(handler).complete_json("s", "u")
    assert len(calls) == 3


def test_groq_does_not_retry_other_errors():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, text="bad model")

    with pytest.raises(LLMError):
        groq_with(handler).complete_json("s", "u")
    assert len(calls) == 1


def test_groq_raises_on_non_json_content():
    def handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )

    with pytest.raises(LLMError):
        groq_with(handler).complete_json("s", "u")


def test_anthropic_is_not_implemented():
    with pytest.raises(NotImplementedError):
        AnthropicClient(api_key="x").complete_json("s", "u")


def test_build_llm_groq_requires_key():
    assert isinstance(
        build_llm(Settings(llm_provider="groq", groq_api_key="K")), GroqClient
    )
    with pytest.raises(LLMError):
        build_llm(Settings(llm_provider="groq", groq_api_key=None))


def test_build_llm_unknown_provider():
    with pytest.raises(LLMError):
        build_llm(Settings(llm_provider="mystery"))


def test_build_llm_anthropic_returns_stub():
    client = build_llm(Settings(llm_provider="anthropic", anthropic_api_key="k"))
    assert isinstance(client, AnthropicClient)


def _groq_sleeping(handler, sleeps):
    return GroqClient(
        api_key="K",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )


def test_groq_waits_out_rate_limit_then_succeeds():
    calls, sleeps = [], []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, text="Please try again in 28.2975s. Need more")
        return _chat_response({"ok": True})

    assert _groq_sleeping(handler, sleeps).complete_json("s", "u") == {"ok": True}
    assert sleeps == [pytest.approx(29.2975)]


def test_groq_prefers_retry_after_header():
    calls, sleeps = [], []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "5"}, text="try again in 9s")
        return _chat_response({"ok": True})

    _groq_sleeping(handler, sleeps).complete_json("s", "u")
    assert sleeps == [6.0]


def test_groq_does_not_wait_beyond_cap():
    sleeps = []

    def handler(request):
        return httpx.Response(429, text="Please try again in 3600s")

    with pytest.raises(LLMError):
        _groq_sleeping(handler, sleeps).complete_json("s", "u")
    assert sleeps == []
