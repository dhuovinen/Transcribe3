from __future__ import annotations

from typing import Protocol

import httpx

from transcribe3.shared.constants import DEFAULT_LLM_TIMEOUT, OLLAMA_BASE_URL
from transcribe3.shared.types import LLMProtocol, LLMProviderConfig


# Listing models is a liveness check, not a generation call — it must not inherit the
# long generation timeout, or an unreachable host would hang the Settings screen.
LIST_MODELS_TIMEOUT: float = 10.0


class LLMUnavailableError(Exception):
    """A provider could not be reached, refused the request, or timed out.

    `status_code` is the HTTP status when the server actually answered, and None
    when nothing answered. Callers need that distinction: a server returning 401
    is running and demanding credentials, which is a different fix from a server
    that isn't running at all.
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _as_unavailable(
    exc: Exception, *, label: str, base_url: str, timeout: float
) -> LLMUnavailableError:
    """Translate an httpx failure into an error message that names the real cause."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return LLMUnavailableError(f"{label} returned HTTP {code}", status_code=code)
    if isinstance(exc, httpx.TimeoutException):
        return LLMUnavailableError(f"{label} did not respond within {timeout:g}s")
    return LLMUnavailableError(f"{label} is not running at {base_url}")


def _auth_headers(api_key: str | None) -> dict[str, str]:
    """Bearer-token header for servers that require one, empty otherwise.

    The token is passed in by the caller (api/ or cli.py resolve it from the
    environment) — this layer never reads it from the environment itself.
    """
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class LLMClient(Protocol):
    def complete(self, prompt: str, model: str) -> str: ...

    def list_models(self) -> list[str]: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        timeout: float = DEFAULT_LLM_TIMEOUT,
        label: str = "Ollama",
        api_key: str | None = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.label = label
        self.api_key = api_key

    def complete(self, prompt: str, model: str) -> str:
        """Send a prompt and return the response text. Raises LLMUnavailableError if Ollama is unreachable.

        think=False disables chain-of-thought reasoning on models that support
        it (e.g. Qwen3). Measured on qwen3.5:9b: a 10-segment attribution
        window dropped from 2573 generated tokens (~86s) to 562 (~20s) with
        no change in output quality, since attribution is a "respond only
        with this JSON" task that gains nothing from visible reasoning.
        Ollama ignores the field for models that don't support thinking.
        """
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "think": False},
                timeout=self.timeout,
                headers=_auth_headers(self.api_key),
            )
            response.raise_for_status()
            return response.json()["response"]
        except httpx.HTTPError as e:
            raise _as_unavailable(
                e, label=self.label, base_url=self.base_url, timeout=self.timeout
            ) from e

    def list_models(self) -> list[str]:
        """Return available model names, raising LLMUnavailableError if the server
        can't be reached, refuses the request, or times out.

        Failures raise rather than returning [] so that an empty list keeps one
        unambiguous meaning: the server answered and has no models installed.
        """
        try:
            response = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=LIST_MODELS_TIMEOUT,
                headers=_auth_headers(self.api_key),
            )
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except httpx.HTTPError as e:
            raise _as_unavailable(
                e, label=self.label, base_url=self.base_url, timeout=LIST_MODELS_TIMEOUT
            ) from e


class OpenAICompatibleClient:
    """Client for any server speaking the OpenAI v1 protocol (olmx, LM Studio, vLLM, ...)."""

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_LLM_TIMEOUT,
        label: str = "The LLM server",
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.label = label
        self.api_key = api_key

    def complete(self, prompt: str, model: str) -> str:
        """Send a prompt and return the response text. Raises LLMUnavailableError if the server is unreachable."""
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=self.timeout,
                headers=_auth_headers(self.api_key),
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            raise _as_unavailable(
                e, label=self.label, base_url=self.base_url, timeout=self.timeout
            ) from e

    def list_models(self) -> list[str]:
        """Return available model names, raising LLMUnavailableError if the server
        can't be reached, refuses the request, or times out. See OllamaClient.list_models."""
        try:
            response = httpx.get(
                f"{self.base_url}/models",
                timeout=LIST_MODELS_TIMEOUT,
                headers=_auth_headers(self.api_key),
            )
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        except httpx.HTTPError as e:
            raise _as_unavailable(
                e, label=self.label, base_url=self.base_url, timeout=LIST_MODELS_TIMEOUT
            ) from e


def build_llm_client(
    provider: LLMProviderConfig,
    *,
    timeout: float = DEFAULT_LLM_TIMEOUT,
    api_key: str | None = None,
) -> LLMClient:
    """Build the right client adapter for a provider from the registry (AppSettings.llm_providers).

    Adding a new provider that speaks the OpenAI v1 protocol (LM Studio, vLLM, llama.cpp
    server, a hosted API, ...) never needs a new branch here — it needs a new registry
    entry with protocol=OPENAI_COMPATIBLE, added in Settings.

    `api_key` is the provider's bearer token when it needs one; callers resolve it with
    data.secrets.resolve_provider_api_key so this layer stays free of environment access.
    """
    if provider.protocol == LLMProtocol.OPENAI_COMPATIBLE:
        return OpenAICompatibleClient(
            base_url=provider.base_url, timeout=timeout, label=provider.label, api_key=api_key
        )
    return OllamaClient(
        base_url=provider.base_url, timeout=timeout, label=provider.label, api_key=api_key
    )
