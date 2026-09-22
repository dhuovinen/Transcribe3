from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from transcribe3.api.dependencies import get_sessions_dir
from transcribe3.data.secrets import resolve_provider_api_key
from transcribe3.data.settings import SettingsRepository
from transcribe3.shared.types import AppSettings

router = APIRouter()


def _payload(settings: AppSettings) -> dict[str, Any]:
    """Serialize settings, annotating each provider with whether its bearer-token
    variable currently holds a value.

    The variable NAME travels in `api_key_env_var`; only this flag says whether it
    is set, and the token itself never leaves the server. Without the flag the UI
    cannot tell "this provider needs no token" from "the token is missing", which
    is the difference between a working provider and a 401.
    """
    data = settings.model_dump()
    for provider, raw in zip(settings.llm_providers, data["llm_providers"]):
        raw["api_key_set"] = resolve_provider_api_key(provider) is not None
    return data


@router.get("")
def get_settings(sessions_dir: Path = Depends(get_sessions_dir)) -> JSONResponse:
    return JSONResponse(content=_payload(SettingsRepository.load(sessions_dir)))


@router.put("")
def update_settings(
    settings: AppSettings,
    sessions_dir: Path = Depends(get_sessions_dir),
) -> JSONResponse:
    # Archive destinations are only changed through /archive/configuration,
    # which validates the path and creates the selected folder first.
    existing = SettingsRepository.load(sessions_dir)
    updated = settings.model_copy(update={"archive_dir": existing.archive_dir})
    SettingsRepository.save(updated, sessions_dir)
    return JSONResponse(content=_payload(updated))
