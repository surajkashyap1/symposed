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
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import httpx

from .settings import Settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


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

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            resp = client.post(
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
