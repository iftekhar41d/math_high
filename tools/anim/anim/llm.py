"""The OpenRouter boundary for the authoring toolchain.

Deliberately separate from ``api/app/mentisq/llm_client.py``: this code runs off
the VPS, needs no cost metering, and must never be confused with the student
tutor's spend path. It reuses ``OPENROUTER_API_KEY`` but sends its own
``ANIM_LLM_MODEL``.

``complete(messages, ...)`` takes an OpenAI-style message list and returns the
completion text. Timeout / outage / bad response -> ``AnimLLMError``.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from .config import Config


class AnimLLMError(RuntimeError):
    """The provider timed out, errored, or returned an unusable response."""


class LLMClient(Protocol):
    def complete(self, *, messages: list[dict[str, str]], model: str) -> str: ...


class OpenRouterClient:
    """Real client. One blocking POST per call; no streaming, no retries here
    (the pipeline owns the render-retry loop)."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._url = config.base_url.rstrip("/") + "/chat/completions"

    def complete(self, *, messages: list[dict[str, str]], model: str) -> str:
        api_key = self._config.require_api_key()
        payload = {"model": model, "messages": messages}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = httpx.post(
                self._url,
                json=payload,
                headers=headers,
                timeout=self._config.llm_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AnimLLMError(
                f"OpenRouter timed out after {self._config.llm_timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise AnimLLMError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code != 200:
            raise AnimLLMError(
                f"OpenRouter returned {response.status_code}: {response.text[:500]}"
            )
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AnimLLMError(f"OpenRouter response was not usable: {exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise AnimLLMError("OpenRouter returned an empty completion")
        return text


def get_client(config: Config) -> LLMClient:
    return OpenRouterClient(config)
