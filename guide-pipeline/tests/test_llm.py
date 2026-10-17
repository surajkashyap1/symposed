import json

import httpx
import pytest

from guide_pipeline.llm import (
    AnthropicClient,
    GroqClient,
    LLMError,
    JsonCall,
    UsageMeter,
    build_llm,
    run_many,
    task_config,
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


from types import SimpleNamespace


class FakeAnthropic:
    """Stands in for anthropic.Anthropic: records create() kwargs, returns canned replies."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def reply(text, *, stop="end_turn", inp=1000, out=500, cache_write=0, cache_read=0):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=inp,
            output_tokens=out,
            cache_creation_input_tokens=cache_write,
            cache_read_input_tokens=cache_read,
        ),
    )


SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"],
          "additionalProperties": False}


def test_anthropic_sends_task_effort_thinking_and_schema():
    fake = FakeAnthropic(reply('{"a": 1}'))
    client = AnthropicClient(
        api_key="k", model="claude-sonnet-5", effort="high", thinking=True, client=fake
    )
    assert client.complete_json("sys", "user", schema=SCHEMA) == {"a": 1}
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5" and call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "user"}]
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {
        "effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}
    }


def test_anthropic_thinking_off_and_no_schema():
    fake = FakeAnthropic(reply('```json\n{"a": 2}\n```'))
    client = AnthropicClient(api_key="k", effort="low", thinking=False, client=fake)
    assert client.complete_json("s", "u") == {"a": 2}  # fenced JSON tolerated
    call = fake.calls[0]
    assert call["thinking"] == {"type": "between_tools"}  # Sonnet 5.5's "off"
    assert call["output_config"] == {"effort": "low"}


def test_thinking_off_is_spelled_per_model_and_fallbacks_only_where_supported():
    def thinking(model, effort="low"):
        return AnthropicClient(api_key="k", model=model, effort=effort, thinking=False,
                               client=FakeAnthropic())._thinking()
    assert thinking("claude-opus-5-5") == {"type": "adaptive"}  # cannot be switched off
    assert thinking("claude-sonnet-5-5", "xhigh") == {"type": "adaptive"}
    assert thinking("claude-sonnet-5") == {"type": "disabled"}
    fake = FakeAnthropic(reply('{"a": 1}'))
    AnthropicClient(api_key="k", model="claude-opus-5-5", client=fake).complete_json("s", "u")
    assert fake.calls[0]["extra_body"] == {"fallbacks": "default"}
    assert "server-side-fallback-2026-07-01" in fake.calls[0]["extra_headers"]["anthropic-beta"]
    fake = FakeAnthropic(reply('{"a": 1}'))
    AnthropicClient(api_key="k", model="claude-haiku-4-5", client=fake).complete_json("s", "u")
    assert "extra_body" not in fake.calls[0]


def test_anthropic_refusal_and_truncation_raise():
    with pytest.raises(LLMError, match="refused"):
        AnthropicClient(api_key="k", client=FakeAnthropic(reply("", stop="refusal"))).complete_json("s", "u")
    with pytest.raises(LLMError, match="max_tokens"):
        AnthropicClient(api_key="k", client=FakeAnthropic(reply('{"a"', stop="max_tokens"))).complete_json("s", "u")
    with pytest.raises(LLMError, match="valid JSON"):
        AnthropicClient(api_key="k", client=FakeAnthropic(reply("not json"))).complete_json("s", "u")


def test_usage_meter_prices_every_call():
    meter = UsageMeter()
    fake = FakeAnthropic(
        reply('{"a": 1}', inp=1_000_000, out=100_000),
        reply('{"a": 1}', inp=0, out=0, cache_write=1_000_000, cache_read=1_000_000),
    )
    client = AnthropicClient(api_key="k", model="claude-sonnet-5", client=fake, meter=meter, task="t")
    client.complete_json("s", "u")
    client.complete_json("s", "u")
    # $2/M input + $10/M output; cache writes 1.25x input, reads 0.1x input
    assert meter.cost_usd == pytest.approx(2.0 + 1.0 + 2.5 + 0.2)
    assert meter.calls == 2 and meter.by_task["t"] == pytest.approx(5.7)


def test_task_settings_follow_the_spec_table_and_env_overrides(monkeypatch):
    s = Settings(llm_provider="anthropic", anthropic_api_key="k")
    extraction = task_config(s, "attribute_extraction")
    assert (extraction.model, extraction.effort, extraction.thinking) == ("claude-sonnet-5-5", "low", False)
    assert task_config(s, "candidate_generation").effort == "high"
    # decisions go to the decider model, reading to the reader
    assert task_config(s, "gap_candidates").model == "claude-opus-5-5"
    assert task_config(s, "final_check").model == "claude-opus-5-5"
    assert task_config(s, "review_reading").model == "claude-sonnet-5-5"
    assert task_config(s, "tie_break").effort == "max"
    monkeypatch.setenv("EFFORT_CANDIDATE_GENERATION", "xhigh")
    monkeypatch.setenv("MODEL_CANDIDATE_GENERATION", "claude-fable-5-1")
    gen = task_config(s, "candidate_generation")
    assert (gen.model, gen.effort) == ("claude-fable-5-1", "xhigh")
    with pytest.raises(LLMError):
        task_config(s, "no_such_task")


def test_build_llm_anthropic_is_configured_per_task():
    s = Settings(llm_provider="anthropic", anthropic_api_key="k")
    client = build_llm(s, task="screening")
    assert isinstance(client, AnthropicClient)
    assert (client.effort, client.thinking, client.task) == ("high", True, "screening")
    with pytest.raises(LLMError):
        build_llm(Settings(llm_provider="anthropic", anthropic_api_key=None))


def test_build_llm_groq_requires_key():
    assert isinstance(
        build_llm(Settings(llm_provider="groq", groq_api_key="K")), GroqClient
    )
    with pytest.raises(LLMError):
        build_llm(Settings(llm_provider="groq", groq_api_key=None))


def test_build_llm_unknown_provider():
    with pytest.raises(LLMError):
        build_llm(Settings(llm_provider="mystery"))


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


def test_anthropic_cache_system_marks_the_system_block():
    fake = FakeAnthropic(reply('{"a": 1}'))
    AnthropicClient(api_key="k", client=fake).complete_json("criteria...", "paper", cache_system=True)
    assert fake.calls[0]["system"] == [
        {"type": "text", "text": "criteria...", "cache_control": {"type": "ephemeral"}}
    ]


def test_usage_meter_is_thread_safe():
    from concurrent.futures import ThreadPoolExecutor

    meter = UsageMeter()
    usage = SimpleNamespace(input_tokens=1, output_tokens=1,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: meter.record("claude-sonnet-5", "t", usage), range(400)))
    assert meter.calls == 400 and meter.input_tokens == 400


class FakeBatches:
    """Stands in for client.messages.batches: ends after `polls` retrievals."""

    def __init__(self, outcomes, polls=2):
        self.outcomes, self.polls, self.created = outcomes, polls, None

    def create(self, requests):
        self.created = requests
        return SimpleNamespace(id="b1", processing_status="in_progress",
                               request_counts=SimpleNamespace(succeeded=0, errored=0))

    def retrieve(self, batch_id):
        self.polls -= 1
        status = "ended" if self.polls <= 0 else "in_progress"
        return SimpleNamespace(id=batch_id, processing_status=status,
                               request_counts=SimpleNamespace(succeeded=1, errored=0))

    def results(self, batch_id):
        # deliberately out of order: results must be keyed by custom_id
        for custom_id, outcome in reversed(list(self.outcomes.items())):
            if isinstance(outcome, str):
                yield SimpleNamespace(custom_id=custom_id,
                                      result=SimpleNamespace(type=outcome))
            else:
                yield SimpleNamespace(custom_id=custom_id,
                                      result=SimpleNamespace(type="succeeded", message=outcome))


def batch_client(batches, meter=None):
    fake = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    sleeps = []
    client = AnthropicClient(api_key="k", model="claude-sonnet-5", client=fake, batch=True,
                             poll_seconds=5, sleep=sleeps.append, meter=meter, task="screening")
    return client, sleeps


def test_batch_mode_submits_one_batch_and_keys_results_by_id():
    meter = UsageMeter()
    batches = FakeBatches({
        "c0": reply('{"a": 0}', inp=1_000_000, out=0),
        "c1": "errored",
        "c2": reply('{"a": 2}', inp=1_000_000, out=0),
    })
    client, sleeps = batch_client(batches, meter)
    calls = [JsonCall("sys", f"u{i}", SCHEMA, cache_system=True) for i in range(3)]
    out = run_many(client, calls)
    assert out[0] == {"a": 0} and out[2] == {"a": 2}
    assert isinstance(out[1], LLMError) and "errored" in str(out[1])
    assert [r["custom_id"] for r in batches.created] == ["c0", "c1", "c2"]
    params = batches.created[0]["params"]
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["output_config"]["format"]["schema"] == SCHEMA
    assert sleeps == [5, 5]  # polled until ended
    assert meter.cost_usd == pytest.approx(2.0)  # 2M input tokens at half of $2/M


def test_batch_timeout_cancels():
    class Never(FakeBatches):
        cancelled = False

        def retrieve(self, batch_id):
            return SimpleNamespace(id=batch_id, processing_status="in_progress",
                                   request_counts=SimpleNamespace(succeeded=0, errored=0))

        def cancel(self, batch_id):
            Never.cancelled = True

    client, _ = batch_client(Never({}))
    client.batch_timeout_seconds = 10
    with pytest.raises(LLMError, match="did not finish"):
        client.complete_json_many([JsonCall("s", "u")])
    assert Never.cancelled


def test_sync_mode_runs_calls_in_parallel_threads():
    fake = FakeAnthropic(*(reply(f'{{"a": {i}}}') for i in range(3)))
    client = AnthropicClient(api_key="k", client=fake, batch=False, concurrency=1)
    out = run_many(client, [JsonCall("s", f"u{i}") for i in range(3)])
    assert out == [{"a": 0}, {"a": 1}, {"a": 2}] and len(fake.calls) == 3

def _conn_error():
    import anthropic
    import httpx
    return anthropic.APIConnectionError(request=httpx.Request("GET", "https://x"))


def test_batch_poll_survives_a_dropped_connection():
    class Flaky(FakeBatches):
        failures = 2

        def retrieve(self, batch_id):
            if Flaky.failures:
                Flaky.failures -= 1
                raise _conn_error()
            return super().retrieve(batch_id)

    client, sleeps = batch_client(Flaky({"c0": reply('{"a": 0}')}, polls=1))
    assert client.complete_json_many([JsonCall("s", "u")]) == [{"a": 0}]
    assert len(sleeps) == 3  # one poll wait + two retry waits


def test_batch_poll_gives_up_on_a_persistent_outage():
    class Down(FakeBatches):
        def retrieve(self, batch_id):
            raise _conn_error()

    client, _ = batch_client(Down({}))
    client.poll_retries = 2
    with pytest.raises(LLMError, match="unreachable"):
        client.complete_json_many([JsonCall("s", "u")])
