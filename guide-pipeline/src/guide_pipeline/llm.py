"""Provider-agnostic LLM layer.

Groq (free) is the default and the only provider wired up for now. The Anthropic
(Claude) path is a deliberate stub — flipping `LLM_PROVIDER=anthropic` should one
day switch providers with no other code change, but Claude costs money and we are
trialling the free Groq model first, so it is not implemented yet.

Every call returns parsed JSON that the caller validates. The model is never
trusted to supply counts, PMIDs, DOIs or titles-of-record (CLAUDE.md rule 1); it
only proposes candidate review questions and search terms.
"""

from __future__ import annotations

import json
import re
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
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object."""
        ...


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

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
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
    """Placeholder — the Claude path is not built yet (see module docstring)."""

    api_key: str
    model: str = "claude-sonnet-4-6"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raise NotImplementedError(
            "The Anthropic/Claude provider is not implemented yet. We are trialling "
            "the free Groq model first; wire the Claude Messages API here if you "
            "decide to switch (LLM_PROVIDER=anthropic)."
        )


def build_llm(settings: Settings) -> LLMClient:
    """Construct the LLM client for the configured provider."""
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise LLMError("LLM_PROVIDER=groq but GROQ_API_KEY is not set.")
        return GroqClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=settings.llm_temperature,
        )
    if settings.llm_provider == "anthropic":
        return AnthropicClient(
            api_key=settings.anthropic_api_key or "",
            model=settings.anthropic_model,
        )
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
