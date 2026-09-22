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
