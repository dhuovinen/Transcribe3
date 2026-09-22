from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Uvicorn only configures its own "uvicorn.*" loggers, not the root logger —
# without this, every logger.info() in the app (stage/window timing included)
# is silently dropped, since Python's default root level is WARNING.
_app_logger = logging.getLogger("transcribe3")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _app_logger.addHandler(_handler)
_app_logger.propagate = False

from transcribe3.api.routes import sessions, speakers, export, models as models_router, settings as settings_router
from transcribe3.api.routes import audio as audio_router
from transcribe3.api.routes import archive as archive_router


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3015",
    "http://127.0.0.1:3015",
)


def get_cors_origins(value: str | None = None) -> list[str]:
    """Return explicitly configured browser origins for the API.

    `TRANSCRIBE3_CORS_ORIGINS` is a comma-separated list.  A wildcard is
    deliberately rejected because this API has no authentication and allows
    destructive session operations.
    """
    raw_value = os.getenv("TRANSCRIBE3_CORS_ORIGINS") if value is None else value
    if not raw_value or not raw_value.strip():
        return list(DEFAULT_CORS_ORIGINS)

    origins = [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]
    if not origins:
        return list(DEFAULT_CORS_ORIGINS)
    if "*" in origins:
        raise ValueError("TRANSCRIBE3_CORS_ORIGINS must list explicit origins; '*' is not allowed")
    if invalid := [origin for origin in origins if not origin.startswith(("http://", "https://"))]:
        raise ValueError(f"Invalid CORS origin(s): {', '.join(invalid)}")
    return origins


app = FastAPI(
    title="Transcribe3 API",
    description="Transcript validation and enrichment pipeline",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(speakers.router, prefix="/sessions", tags=["speakers"])
app.include_router(export.router, prefix="/sessions", tags=["export"])
app.include_router(models_router.router, prefix="/models", tags=["models"])
app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
app.include_router(audio_router.router, prefix="/sessions", tags=["audio"])
app.include_router(archive_router.router, prefix="/archive", tags=["archive"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
