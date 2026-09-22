"""Reads provider credentials from the process environment (populated from .env).

Secrets live here rather than in settings.json for two reasons: that file is
returned verbatim by the unauthenticated GET /settings endpoint, and it is
rewritten wholesale on every save, so a token stored there would be echoed to
every browser on the LAN and easy to clobber. `core/` never reads the
environment itself — the resolved token is injected into the client it builds.
"""
from __future__ import annotations

import os

from transcribe3.shared.types import LLMProviderConfig


def resolve_provider_api_key(provider: LLMProviderConfig) -> str | None:
    """Return the bearer token configured for `provider`, or None if unset.

    The variable is `provider.api_key_env` when the registry entry names one,
    otherwise the convention TRANSCRIBE3_LLM_API_KEY_<ID>. Blank values count as
    unset so an empty line in .env doesn't send an "Authorization: Bearer "
    header that most servers reject with a confusing 401.
    """
    value = os.environ.get(provider.api_key_env_var)
    return value.strip() or None if value else None
