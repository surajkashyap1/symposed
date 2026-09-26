"""Provider-agnostic LLM layer, routed per task.

Claude Sonnet 5 runs every task (decision 2026-09-25); each task sets its own
reasoning effort and whether thinking is on, following the model table in
`docs/spec-update-screening.md` — high where the model designs, low or off where
it only extracts. Any task's model or effort can be overridden from the
environment (`MODEL_<TASK>`, `EFFORT_<TASK>`, `THINKING_<TASK>`) without code
changes. Groq remains selectable (`LLM_PROVIDER=groq`) for free local trials.

Every call returns parsed JSON that the caller validates. The model is never
trusted to supply counts, PMIDs, DOIs or titles-of-record (CLAUDE.md rule 1); it
only proposes candidate review questions and search terms.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

import httpx

from .settings import Settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_TRY_AGAIN_RE = re.compile(r"try again in ([0-9.]+)s")


class LLMError(RuntimeError):
    """Raised when the provider errors or returns a body we can't parse as JSON."""


class LLMClient(Protocol):
    def complete_json(
        self,
        system: str,
        user: str,
        *,
        schema: Optional[dict] = None,
        cache_system: bool = False,
    ) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object.

        `schema`, when given, is a JSON Schema the provider enforces where it can.
        `cache_system` marks a system prompt reused across many calls (e.g. the
        review's criteria for every paper) for prompt caching where supported.
        """
        ...


# -- per-task routing -----------------------------------------------------------
@dataclass(frozen=True)
class TaskConfig:
    model: str
    effort: str  # low | medium | high | xhigh | max
    thinking: bool


# (effort, thinking) per pipeline task — the spec update's table, applied to
# Sonnet 5. "None" effort in the table means thinking off at low effort.
TASKS: dict[str, tuple[str, bool]] = {
    "concept_mapping": ("low", False),
    "candidate_generation": ("high", True),
    "search_strategy": ("medium", True),
    "attribute_extraction": ("low", False),
    "screening": ("medium", True),
    "criteria_writing": ("high", True),
    "protocol_drafting": ("medium", True),
    "prospero_form": ("low", True),
    "guide_drafting": ("low", False),
    "tie_break": ("max", True),
    # Grouping stated primary outcomes for the heterogeneity check.
    "outcome_grouping": ("low", False),
}
_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def task_config(settings: Settings, task: str) -> TaskConfig:
    """Model, effort and thinking for a task, with env overrides applied."""
    if task not in TASKS:
        raise LLMError(f"Unknown LLM task: {task!r}")
    effort, thinking = TASKS[task]
    key = task.upper()
    model = os.environ.get(f"MODEL_{key}") or settings.anthropic_model
    effort = os.environ.get(f"EFFORT_{key}") or effort
    if effort not in _EFFORTS:
        raise LLMError(f"EFFORT_{key} must be one of {', '.join(_EFFORTS)}")
    flag = os.environ.get(f"THINKING_{key}")
    if flag:
        thinking = flag.lower() in ("1", "true", "yes", "on")
    return TaskConfig(model=model, effort=effort, thinking=thinking)


# -- cost ------------------------------------------------------------------------
# USD per million tokens (input, output), Claude API list prices. Cache writes
# (5-minute TTL) bill at 1.25x input, cache reads at 0.1x input.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5-1": (10.0, 50.0),
}


@dataclass
class UsageMeter:
    """Running token + dollar totals across every model call in a run."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    by_task: dict[str, float] = field(default_factory=dict)
    unpriced_models: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record(self, model: str, task: str, usage: Any) -> None:
        with self._lock:  # calls run concurrently during screening
            self._record(model, task, usage)

    def _record(self, model: str, task: str, usage: Any) -> None:
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.cache_write_tokens += cw
        self.cache_read_tokens += cr
        price = PRICES.get(model)
        if price is None:
            self.unpriced_models.add(model)
            return
        p_in, p_out = price
        cost = (inp * p_in + out * p_out + cw * p_in * 1.25 + cr * p_in * 0.1) / 1_000_000
        self.cost_usd += cost
        self.by_task[task] = self.by_task.get(task, 0.0) + cost

    def summary(self) -> str:
        parts = [
            f"{self.calls} model call(s), {self.input_tokens:,} in / "
            f"{self.output_tokens:,} out tokens",
        ]
        if self.cache_read_tokens or self.cache_write_tokens:
            parts.append(
                f"cache {self.cache_write_tokens:,} written / {self.cache_read_tokens:,} read"
            )
        line = "; ".join(parts) + f" — about ${self.cost_usd:.3f}"
        if self.unpriced_models:
            line += f" (no price on file for {', '.join(sorted(self.unpriced_models))})"
        return line


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(_FENCE_RE.sub("", text.strip()))
    except ValueError as exc:
        raise LLMError(f"Model did not return valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("Model JSON was not an object")
    return data


@dataclass
class GroqClient:
    """Groq via its OpenAI-compatible chat-completions API, in JSON mode."""

    api_key: str
    model: str = "openai/gpt-oss-120b"
    temperature: float = 0.4
    base_url: str = GROQ_BASE_URL
    timeout: float = 60.0
    client: Optional[httpx.Client] = None
    # Groq's JSON mode intermittently rejects a generation (400
    # json_validate_failed) on long prompts; a fresh sample usually succeeds.
    json_retries: int = 2
    # The free tier has a tokens-per-minute cap; a 429 says how long to wait.
    rate_limit_retries: int = 2
    max_rate_limit_wait: float = 65.0
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        schema: Optional[dict] = None,
        cache_system: bool = False,
    ) -> dict[str, Any]:
        # Groq's JSON mode takes no schema and has no prompt caching; callers
        # validate the shape.
        json_failures = rate_limits = 0
        while True:
            resp = self._post(system, user)
            if (
                resp.status_code == 400
                and "json_validate_failed" in resp.text
                and json_failures < self.json_retries
            ):
                json_failures += 1
                continue
            if resp.status_code == 429 and rate_limits < self.rate_limit_retries:
                wait = self._rate_limit_wait(resp)
                if wait is not None:
                    rate_limits += 1
                    self.sleep(wait)
                    continue
            return self._parse(resp)

    def _rate_limit_wait(self, resp: httpx.Response) -> Optional[float]:
        """Seconds to wait from Retry-After or the error text, if within the cap."""
        wait: Optional[float] = None
        header = resp.headers.get("retry-after")
        if header:
            try:
                wait = float(header)
            except ValueError:
                wait = None
        if wait is None:
            match = _TRY_AGAIN_RE.search(resp.text)
            wait = float(match.group(1)) if match else None
        if wait is None or wait > self.max_rate_limit_wait:
            return None
        return wait + 1.0  # small margin past the window

    def _post(self, system: str, user: str) -> httpx.Response:
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            return client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": self.temperature,
                },
            )
        finally:
            if self.client is None:
                client.close()

    def _parse(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code != 200:
            raise LLMError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected Groq response shape: {exc}") from exc
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise LLMError(f"Model did not return valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("Model JSON was not an object")
        return data


@dataclass
class AnthropicClient:
    """Claude via the official SDK, configured for one pipeline task."""

    api_key: str
    model: str = "claude-sonnet-5"
    effort: str = "medium"
    thinking: bool = True
    task: str = "default"
    max_tokens: int = 16000
    client: Any = None  # anthropic.Anthropic, injectable for tests
    meter: Optional[UsageMeter] = None

    def __post_init__(self) -> None:
        # Built up front, not lazily: screening calls this from several threads.
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)

    def _sdk(self) -> Any:
        return self.client

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        schema: Optional[dict] = None,
        cache_system: bool = False,
    ) -> dict[str, Any]:
        output_config: dict[str, Any] = {"effort": self.effort}
        system_param: Any = system
        if cache_system:
            system_param = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        import anthropic  # noqa: F401  (typed errors below)

        try:
            response = self._sdk().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_param,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"} if self.thinking else {"type": "disabled"},
                output_config=output_config,
            )
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Anthropic unreachable: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic HTTP {exc.status_code}: {exc.message}") from exc
        if self.meter is not None:
            self.meter.record(self.model, self.task, response.usage)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMError(f"Model refused ({getattr(details, 'category', None)})")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"Reply cut off at max_tokens ({self.max_tokens})")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return _parse_json_object(text)


def build_llm(
    settings: Settings, task: str = "default", *, meter: Optional[UsageMeter] = None
) -> LLMClient:
    """The LLM client for one pipeline task, on the configured provider."""
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise LLMError("LLM_PROVIDER=groq but GROQ_API_KEY is not set.")
        return GroqClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=settings.llm_temperature,
        )
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        cfg = (
            task_config(settings, task)
            if task != "default"
            else TaskConfig(settings.anthropic_model, "medium", True)
        )
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=cfg.model,
            effort=cfg.effort,
            thinking=cfg.thinking,
            task=task,
            meter=meter,
        )
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
