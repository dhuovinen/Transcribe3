from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, HTTPException

from transcribe3.core.llm.client import LLMClient, build_llm_client
from transcribe3.data.secrets import resolve_provider_api_key
from transcribe3.data.session import SessionRepository
from transcribe3.data.settings import SettingsRepository
from transcribe3.shared.types import AppSettings, LLMProviderConfig


def get_sessions_dir() -> Path:
    return Path(os.getenv("TRANSCRIBE3_SESSIONS_DIR", "./sessions"))


def get_session_repo() -> SessionRepository:
    return SessionRepository()


def get_settings(sessions_dir: Path = Depends(get_sessions_dir)) -> AppSettings:
    return SettingsRepository.load(sessions_dir)


def resolve_provider(settings: AppSettings, provider_id: str | None) -> LLMProviderConfig:
    """Resolve a provider id (or the configured default) to its registry entry.

    Raises HTTPException(400) if the id is unknown or the provider is disabled, so
    callers get a clear message instead of a confusing downstream connection error.
    """
    chosen_id = provider_id or settings.default_provider_id
    provider = settings.find_provider(chosen_id)
    if provider is None:
        known = [p.id for p in settings.llm_providers]
        raise HTTPException(
            status_code=400,
            detail={"error": f"Unknown LLM provider {chosen_id!r}. Configured providers: {known}"},
        )
    if not provider.enabled:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Provider {provider.label!r} is disabled in Settings."},
        )
    return provider


def build_provider_client(settings: AppSettings, provider: LLMProviderConfig) -> LLMClient:
    """Build a client for `provider` with the configured timeout and its bearer token.

    Every API route builds its client through here so a provider that needs
    authentication gets it consistently, whether the call lists models or runs a
    cleaning pass.
    """
    return build_llm_client(
        provider,
        timeout=settings.llm_timeout,
        api_key=resolve_provider_api_key(provider),
    )
