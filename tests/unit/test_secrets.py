"""Unit tests for transcribe3.data.secrets — provider bearer tokens from the environment."""
from __future__ import annotations

import pytest

from transcribe3.data.secrets import resolve_provider_api_key
from transcribe3.shared.types import LLMProtocol, LLMProviderConfig


def provider(**kwargs) -> LLMProviderConfig:
    defaults = dict(
        id="olmx",
        label="olmx",
        protocol=LLMProtocol.OPENAI_COMPATIBLE,
        base_url="http://127.0.0.1:8090/v1",
    )
    return LLMProviderConfig(**{**defaults, **kwargs})


def test_env_var_name_follows_provider_id():
    assert provider().api_key_env_var == "TRANSCRIBE3_LLM_API_KEY_OLMX"
    assert provider(id="lm studio-2").api_key_env_var == "TRANSCRIBE3_LLM_API_KEY_LM_STUDIO_2"


def test_env_var_name_can_be_overridden():
    assert provider(api_key_env="MY_TOKEN").api_key_env_var == "MY_TOKEN"


def test_resolves_token_from_convention_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRANSCRIBE3_LLM_API_KEY_OLMX", "tok-123")
    assert resolve_provider_api_key(provider()) == "tok-123"


def test_resolves_token_from_named_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_TOKEN", "tok-456")
    monkeypatch.setenv("TRANSCRIBE3_LLM_API_KEY_OLMX", "ignored")
    assert resolve_provider_api_key(provider(api_key_env="MY_TOKEN")) == "tok-456"


def test_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRANSCRIBE3_LLM_API_KEY_OLMX", raising=False)
    assert resolve_provider_api_key(provider()) is None


def test_blank_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch):
    """An empty .env line must not produce an 'Authorization: Bearer ' header."""
    monkeypatch.setenv("TRANSCRIBE3_LLM_API_KEY_OLMX", "   ")
    assert resolve_provider_api_key(provider()) is None
