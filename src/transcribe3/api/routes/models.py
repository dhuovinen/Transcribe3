from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from transcribe3.api.dependencies import build_provider_client, get_settings, resolve_provider
from transcribe3.api.llm_errors import describe_llm_failure
from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.shared.types import AppSettings

router = APIRouter()


@router.get("")
def list_models(
    provider_id: str | None = None,
    settings: AppSettings = Depends(get_settings),
) -> JSONResponse:
    provider = resolve_provider(settings, provider_id)
    client = build_provider_client(settings, provider)
    try:
        models = client.list_models()
    except LLMUnavailableError as exc:
        return JSONResponse(
            content={"models": [], "warning": describe_llm_failure(provider, exc)}
        )
    if not models:
        return JSONResponse(
            content={
                "models": [],
                "warning": f"{provider.label} is reachable but has no models installed",
            }
        )
    return JSONResponse(content={"models": models})
