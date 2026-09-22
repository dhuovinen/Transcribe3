"""Turns an LLM failure into a message that names the fix, not just the symptom."""
from __future__ import annotations

from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.data.secrets import resolve_provider_api_key
from transcribe3.shared.types import LLMProviderConfig

_AUTH_STATUSES = (401, 403)


def describe_llm_failure(provider: LLMProviderConfig, exc: LLMUnavailableError) -> str:
    """Describe why `provider` failed, in terms the operator can act on.

    A server demanding credentials is running perfectly well, so reporting it as
    "not running" sends people to check the wrong thing. For 401/403 the message
    names the environment variable the token is read from and says whether one is
    currently set — the two cases need different fixes.
    """
    if exc.status_code in _AUTH_STATUSES:
        variable = provider.api_key_env_var
        if resolve_provider_api_key(provider) is None:
            return (
                f"{provider.label} returned HTTP {exc.status_code} — it requires a bearer "
                f"token and none is configured. Set {variable} in .env, then restart the "
                "API server."
            )
        return (
            f"{provider.label} rejected the token in {variable} (HTTP {exc.status_code}). "
            "Check the value, then restart the API server — .env is read at startup only."
        )
    return str(exc)
