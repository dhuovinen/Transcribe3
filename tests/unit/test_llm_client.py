"""Unit tests for transcribe3.core.llm.client.OllamaClient."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from transcribe3.core.llm.client import LLMUnavailableError, OllamaClient
from transcribe3.shared.constants import OLLAMA_BASE_URL


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_ollama_client_default_base_url():
    client = OllamaClient()
    assert client.base_url == OLLAMA_BASE_URL


def test_ollama_client_custom_base_url():
    client = OllamaClient(base_url="http://myserver:11434")
    assert client.base_url == "http://myserver:11434"


def test_ollama_client_custom_timeout():
    client = OllamaClient(timeout=120.0)
    assert client.timeout == 120.0


# ---------------------------------------------------------------------------
# complete() — success path
# ---------------------------------------------------------------------------


def test_complete_returns_response_text():
    """complete() parses the JSON response and returns the 'response' field."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "This is the LLM output."}
    mock_response.raise_for_status.return_value = None

    with patch("transcribe3.core.llm.client.httpx.post", return_value=mock_response) as mock_post:
        client = OllamaClient()
        result = client.complete("Say hello", "llama3")

    assert result == "This is the LLM output."
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    # Verify the endpoint and payload
    assert "/api/generate" in call_kwargs.args[0]
    assert call_kwargs.kwargs["json"]["model"] == "llama3"
    assert call_kwargs.kwargs["json"]["prompt"] == "Say hello"


# ---------------------------------------------------------------------------
# complete() — failure paths
# ---------------------------------------------------------------------------


def test_complete_raises_llm_unavailable_on_connect_error():
    """ConnectError is wrapped into LLMUnavailableError."""
    import httpx

    with patch(
        "transcribe3.core.llm.client.httpx.post",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        client = OllamaClient()
        with pytest.raises(LLMUnavailableError, match="not running"):
            client.complete("prompt", "llama3")


def test_complete_raises_llm_unavailable_on_http_error():
    """Non-2xx HTTP status is wrapped into LLMUnavailableError."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503",
        request=MagicMock(),
        response=mock_response,
    )

    with patch("transcribe3.core.llm.client.httpx.post", return_value=mock_response):
        client = OllamaClient()
        with pytest.raises(LLMUnavailableError, match="503"):
            client.complete("prompt", "llama3")


# ---------------------------------------------------------------------------
# list_models() — success path
# ---------------------------------------------------------------------------


def test_list_models_returns_model_names():
    """list_models() parses the tags endpoint and returns model names."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3"},
            {"name": "mistral"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("transcribe3.core.llm.client.httpx.get", return_value=mock_response):
        client = OllamaClient()
        result = client.list_models()

    assert result == ["llama3", "mistral"]


def test_list_models_raises_with_no_status_on_connect_error():
    """Nothing answered, so the error says "not running" and carries no status."""
    import httpx

    with patch(
        "transcribe3.core.llm.client.httpx.get",
        side_effect=httpx.ConnectError("refused"),
    ):
        with pytest.raises(LLMUnavailableError, match="not running") as exc_info:
            OllamaClient().list_models()

    assert exc_info.value.status_code is None


def test_list_models_raises_with_status_on_http_error():
    """A server that answers 401 is running — the error must say so, not "not running"."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401",
        request=MagicMock(),
        response=mock_response,
    )

    with patch("transcribe3.core.llm.client.httpx.get", return_value=mock_response):
        with pytest.raises(LLMUnavailableError) as exc_info:
            OllamaClient().list_models()

    assert exc_info.value.status_code == 401
    assert "401" in str(exc_info.value)
    assert "not running" not in str(exc_info.value)


def test_list_models_raises_on_timeout():
    import httpx

    with patch(
        "transcribe3.core.llm.client.httpx.get",
        side_effect=httpx.ReadTimeout("too slow"),
    ):
        with pytest.raises(LLMUnavailableError, match="did not respond within 10s") as exc_info:
            OllamaClient().list_models()

    assert exc_info.value.status_code is None


def test_list_models_empty_models_list():
    """An empty list now means one thing only: reachable, nothing installed."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": []}
    mock_response.raise_for_status.return_value = None

    with patch("transcribe3.core.llm.client.httpx.get", return_value=mock_response):
        client = OllamaClient()
        result = client.list_models()

    assert result == []


# ---------------------------------------------------------------------------
# Bearer-token authentication
# ---------------------------------------------------------------------------


def test_no_auth_header_when_no_api_key():
    """Providers that need no token must not send an empty Authorization header."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"models": []}
    mock_response.raise_for_status.return_value = None

    with patch("transcribe3.core.llm.client.httpx.get", return_value=mock_response) as mock_get:
        OllamaClient().list_models()

    assert mock_get.call_args.kwargs["headers"] == {}


def test_ollama_client_sends_bearer_token():
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"response": "hi"}
    mock_response.raise_for_status.return_value = None

    with patch("transcribe3.core.llm.client.httpx.post", return_value=mock_response) as mock_post:
        OllamaClient(api_key="tok-123").complete("prompt", "llama3")

    assert mock_post.call_args.kwargs["headers"] == {"Authorization": "Bearer tok-123"}


def test_openai_compatible_client_sends_bearer_token_on_both_calls():
    import httpx

    from transcribe3.core.llm.client import OpenAICompatibleClient

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "data": [{"id": "m1"}],
        "choices": [{"message": {"content": "hi"}}],
    }
    mock_response.raise_for_status.return_value = None
    client = OpenAICompatibleClient(base_url="http://server/v1", api_key="tok-456")
    expected = {"Authorization": "Bearer tok-456"}

    with patch("transcribe3.core.llm.client.httpx.get", return_value=mock_response) as mock_get:
        client.list_models()
    with patch("transcribe3.core.llm.client.httpx.post", return_value=mock_response) as mock_post:
        client.complete("prompt", "m1")

    assert mock_get.call_args.kwargs["headers"] == expected
    assert mock_post.call_args.kwargs["headers"] == expected


def test_build_llm_client_passes_api_key_to_both_protocols():
    from transcribe3.core.llm.client import build_llm_client
    from transcribe3.shared.types import LLMProtocol, LLMProviderConfig

    openai_provider = LLMProviderConfig(
        id="olmx", label="olmx", protocol=LLMProtocol.OPENAI_COMPATIBLE, base_url="http://s/v1"
    )
    ollama_provider = LLMProviderConfig(
        id="ollama", label="Ollama", protocol=LLMProtocol.OLLAMA, base_url="http://s:11434"
    )

    assert build_llm_client(openai_provider, api_key="k").api_key == "k"
    assert build_llm_client(ollama_provider, api_key="k").api_key == "k"
    assert build_llm_client(ollama_provider).api_key is None


def test_complete_reports_status_code_on_http_error():
    """complete() carries the status so callers can tell auth failures apart."""
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=mock_response
    )

    with patch("transcribe3.core.llm.client.httpx.post", return_value=mock_response):
        with pytest.raises(LLMUnavailableError) as exc_info:
            OllamaClient().complete("prompt", "llama3")

    assert exc_info.value.status_code == 403


def test_complete_reports_timeout_with_configured_duration():
    import httpx

    with patch(
        "transcribe3.core.llm.client.httpx.post",
        side_effect=httpx.ReadTimeout("too slow"),
    ):
        with pytest.raises(LLMUnavailableError, match="did not respond within 600s"):
            OllamaClient(timeout=600.0).complete("prompt", "llama3")
