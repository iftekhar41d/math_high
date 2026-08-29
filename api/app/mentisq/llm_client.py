"""The `MentisQLLMClient` boundary — the only code that talks to OpenRouter.

It takes an OpenAI-style message list plus a model name and returns the
completion text and token/cost usage. It enforces a hard 30s timeout. The API key
is read from the `OPENROUTER_API_KEY` environment variable, **never** from the
database.

On timeout, provider outage, or a bad response it raises `LLMTimeoutError` /
`LLMError`; the caller (ticket 06) turns those into the fixed fallback message and
records a `failed` `MentisQMessage` that does not count toward any usage cap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class LLMError(RuntimeError):
    """The provider returned an error or an unusable response."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within `TIMEOUT_SECONDS`."""


class MentisQLLMClient:
    """Interface. The real client calls OpenRouter; the test fake is canned."""

    def complete(
        self, *, messages: list[dict[str, str]], model: str
    ) -> LLMCompletion:  # pragma: no cover - abstract
        raise NotImplementedError


class OpenRouterLLMClient(MentisQLLMClient):
    def __init__(self, api_key: str, *, url: str = OPENROUTER_URL) -> None:
        self._api_key = api_key
        self._url = url

    def complete(
        self, *, messages: list[dict[str, str]], model: str
    ) -> LLMCompletion:
        payload = {
            "model": model,
            "messages": messages,
            # Ask OpenRouter to include the resolved USD cost in the usage block.
            "usage": {"include": True},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.post(
                self._url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"OpenRouter timed out after {TIMEOUT_SECONDS}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(
                f"OpenRouter returned {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"OpenRouter response was not usable: {exc}") from exc

        return LLMCompletion(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            cost_usd=float(usage.get("cost", 0.0) or 0.0),
        )


def get_llm_client() -> MentisQLLMClient:
    """FastAPI dependency. Overridden with a canned fake in tests.

    The key is resolved per-request from the environment; a missing key is only
    an error if something actually tries to call the provider.
    """
    return OpenRouterLLMClient(api_key=os.getenv("OPENROUTER_API_KEY", ""))
