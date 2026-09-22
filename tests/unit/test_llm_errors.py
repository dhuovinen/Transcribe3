"""Unit tests for transcribe3.api.llm_errors — operator-facing LLM failure messages."""
from __future__ import annotations

import pytest

from transcribe3.api.llm_errors import describe_llm_failure
from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.shared.types import LLMProtocol, LLMProviderConfig

PROVIDER = LLMProviderConfig(
    id="omlx",
    label="oMLX",
    protocol=LLMProtocol.OPENAI_COMPATIBLE,
    base_url="http://192.168.1.112:8090/v1",
)


def test_unauthorized_without_token_names_the_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRANSCRIBE3_LLM_API_KEY_OMLX", raising=False)
    message = describe_llm_failure(PROVIDER, LLMUnavailableError("oMLX returned HTTP 401", status_code=401))

    assert "TRANSCRIBE3_LLM_API_KEY_OMLX" in message
    assert "401" in message
    assert "not running" not in message


def test_unauthorized_with_token_says_it_was_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRANSCRIBE3_LLM_API_KEY_OMLX", "stale-token")
    message = describe_llm_failure(PROVIDER, LLMUnavailableError("oMLX returned HTTP 403", status_code=403))

    assert "rejected" in message
    assert "TRANSCRIBE3_LLM_API_KEY_OMLX" in message


def test_other_http_status_passes_through():
    message = describe_llm_failure(PROVIDER, LLMUnavailableError("oMLX returned HTTP 500", status_code=500))
    assert message == "oMLX returned HTTP 500"


def test_connection_failure_passes_through():
    message = describe_llm_failure(PROVIDER, LLMUnavailableError("oMLX is not running at http://x"))
    assert message == "oMLX is not running at http://x"
