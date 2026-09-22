from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from transcribe3.api.dependencies import (
    build_provider_client,
    get_config_dir,
    get_session_repo,
    get_sessions_dir,
    resolve_provider,
)
from transcribe3.core.attributor import attribute_speakers
from transcribe3.core.audio.duration import probe_audio_duration_seconds
from transcribe3.core.cleaner import clean_transcript
from transcribe3.api.llm_errors import describe_llm_failure
from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.data.session import SessionRepository
from transcribe3.data.settings import SettingsRepository
from transcribe3.shared.constants import SUPPORTED_AUDIO_FORMATS
from transcribe3.shared.types import (
    AppSettings,
    CleaningConfig,
    LLMProviderConfig,
    ProcessingParams,
    SessionStatus,
    StageTiming,
    TranscriptSession,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _save_stage(session: TranscriptSession, stage: str, sessions_dir: Path) -> TranscriptSession:
    session = session.model_copy(update={"processing_stage": stage})
    SessionRepository.save(session, sessions_dir)
    return session


def _finish(
    *,
    session: TranscriptSession,
    segments: list,
    warning: str | None,
    timings: list[StageTiming],
    settings: AppSettings,
    provider: LLMProviderConfig,
    config: CleaningConfig,
    backend: str,
    whisper_model: str,
    sessions_dir: Path,
) -> TranscriptSession:
    """Mark the session complete and persist what produced it.

    Both endings of the pipeline — attribution ran, or attribution was switched
    off in Settings — go through here so a skipped run still records its stage
    timings and the parameters it used.
    """
    session = session.model_copy(update={
        "segments": segments,
        "status": SessionStatus.COMPLETE,
        "processing_stage": None,
        "warning": warning,
        "stage_timings": timings,
        "processing_params": ProcessingParams(
            llm_provider_id=provider.id,
            llm_provider_label=provider.label,
            llm_model=config.llm_model,
            cleaning_mode=config.mode,
            filler_words=config.filler_words,
            remove_false_starts=config.remove_false_starts,
            handle_crosstalk=config.handle_crosstalk,
            low_confidence_threshold=config.low_confidence_threshold,
            cleaning_enabled=settings.run_cleaning,
            attribution_enabled=settings.run_attribution,
            transcription_backend=backend,
            whisper_model=whisper_model,
        ),
    })
    SessionRepository.save(session, sessions_dir)
    return session


def _process_audio_session(
    session: TranscriptSession,
    audio_path: Path,
    whisper_model: str,
    backend: str,
    hf_token: str,
    sessions_dir: Path,
    config_dir: Path,
) -> None:
    """Background worker: transcribe, diarize, then run the Phase 1 cleaning
    and LLM attribution pass so audio sessions get the same quality layer as
    transcript uploads."""
    pipeline_start = time.monotonic()
    try:
        from transcribe3.core.audio.pipeline import run_audio_pipeline

        logger.info(
            "Session %s: starting audio processing (backend=%s, whisper_model=%s)",
            session.session_id, backend, whisper_model,
        )

        # Logs how long each pipeline stage actually took, since the LLM
        # attribution stage in particular can dominate total time for long
        # recordings (one sequential call per 10-segment window).
        current_session = session
        stage_start = time.monotonic()
        current_stage: str | None = None
        timings: list[StageTiming] = []

        def close_stage() -> None:
            """Record how long the stage that just ended took.

            The label comes from what advance_stage was called with, not from
            session.processing_stage: attribution rewrites that field on every
            window ("… (7/45 windows)"), which would otherwise split one stage
            into dozens of entries.
            """
            nonlocal current_stage
            if current_stage is None:
                return
            elapsed = time.monotonic() - stage_start
            logger.info(
                "Session %s: stage %r took %.1fs", session.session_id, current_stage, elapsed
            )
            timings.append(StageTiming(stage=current_stage, seconds=round(elapsed, 1)))
            current_stage = None

        def advance_stage(stage: str) -> None:
            nonlocal current_session, stage_start, current_stage
            close_stage()
            current_session = _save_stage(current_session, stage, sessions_dir)
            current_stage = stage
            stage_start = time.monotonic()

        # run_audio_pipeline calls this before each of its two sub-steps, so
        # progress advances beyond one flat "processing audio" stage.
        segments = run_audio_pipeline(audio_path, hf_token, whisper_model, backend, advance_stage)
        session = current_session

        # Chain the Phase 1 quality layer: cleaning + LLM speaker attribution
        settings = SettingsRepository.load(config_dir, sessions_dir)
        provider = resolve_provider(settings, None)
        config = CleaningConfig(
            llm_model=settings.default_model,
            llm_provider_id=provider.id,
            low_confidence_threshold=settings.low_confidence_threshold,
        )
        warning: str | None = None

        if settings.run_cleaning:
            advance_stage("Cleaning transcript…")
            segments = clean_transcript(segments, config)

        if not settings.run_attribution:
            # Deliberately off in Settings — the diarization labels stand as they are.
            close_stage()
            logger.info("Session %s: LLM attribution skipped (disabled in Settings)", session.session_id)
            _finish(
                session=current_session,
                segments=segments,
                warning=(
                    "LLM speaker attribution is turned off in Settings, so diarization "
                    "labels are unvalidated and segment confidence is unscored."
                ),
                timings=timings,
                settings=settings,
                provider=provider,
                config=config,
                backend=backend,
                whisper_model=whisper_model,
                sessions_dir=sessions_dir,
            )
            logger.info(
                "Session %s: audio processing complete in %.1fs total (attribution off)",
                session.session_id, time.monotonic() - pipeline_start,
            )
            return

        advance_stage("Validating speaker attribution with LLM…")

        def on_window_progress(windows_done: int, total_windows: int) -> None:
            nonlocal current_session
            current_session = _save_stage(
                current_session,
                f"Validating speaker attribution with LLM… ({windows_done}/{total_windows} windows)",
                sessions_dir,
            )

        logger.info(
            "Session %s: LLM attribution using provider=%s model=%s at %s (timeout=%.0fs, %d segments)",
            session.session_id, provider.id, config.llm_model, provider.base_url, settings.llm_timeout, len(segments),
        )
        try:
            llm_client = build_provider_client(settings, provider)
            segments = attribute_speakers(segments, config, llm_client, config.llm_model, on_window_progress)
        except LLMUnavailableError as exc:
            warning = (
                f"LLM attribution skipped — {describe_llm_failure(provider, exc)} "
                "Diarization speaker labels are unvalidated."
            )
        except Exception as exc:
            # Never discard a completed transcription because the LLM step failed —
            # keep the diarized segments and surface the problem as a warning.
            warning = (
                f"LLM attribution failed ({exc}) — diarization speaker labels are "
                f"unvalidated. Try raising the LLM timeout in Settings and re-uploading."
            )
        close_stage()
        session = _finish(
            session=current_session,
            segments=segments,
            warning=warning,
            timings=timings,
            settings=settings,
            provider=provider,
            config=config,
            backend=backend,
            whisper_model=whisper_model,
            sessions_dir=sessions_dir,
        )
        logger.info(
            "Session %s: audio processing complete in %.1fs total",
            session.session_id, time.monotonic() - pipeline_start,
        )
    except Exception as exc:
        logger.exception(
            "Audio processing failed for session %s after %.1fs",
            session.session_id, time.monotonic() - pipeline_start,
        )
        session = session.model_copy(update={
            "status": SessionStatus.ERROR,
            "processing_stage": None,
            "error": f"Audio processing failed: {exc}",
        })
        SessionRepository.save(session, sessions_dir)


@router.post("/upload-audio")
def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    whisper_model: str = Form("base"),
    backend: str = Form("whisperx"),
    sessions_dir: Path = Depends(get_sessions_dir),
    config_dir: Path = Depends(get_config_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    original_filename = file.filename or "audio"
    suffix = Path(original_filename).suffix.lower()

    if suffix not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Unsupported audio format: {suffix!r}. Supported: {SUPPORTED_AUDIO_FORMATS}"},
        )

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise HTTPException(
            status_code=503,
            detail={"error": "HF_TOKEN not set. Add HF_TOKEN=hf_... to your .env file."},
        )

    session = TranscriptSession(
        source_file=original_filename,
        audio_file=original_filename,
        status=SessionStatus.PROCESSING,
        processing_stage="Queued…",
    )
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_dir = sessions_dir / session.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    audio_dest = session_dir / original_filename
    with audio_dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    duration = probe_audio_duration_seconds(audio_dest)
    if duration is not None:
        session = session.model_copy(update={"audio_duration_seconds": duration})

    repo.save(session, sessions_dir)

    background_tasks.add_task(
        _process_audio_session,
        session, audio_dest, whisper_model, backend, hf_token, sessions_dir, config_dir,
    )

    # Returns immediately — the client polls GET /sessions/{id} for status
    return JSONResponse(content=session.model_dump(mode="json"))


@router.get("/{session_id}/audio")
def get_audio_file(
    session_id: str,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> FileResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    if not session.audio_file:
        raise HTTPException(status_code=404, detail={"error": "No audio file for this session"})

    audio_path = sessions_dir / session_id / session.audio_file
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail={"error": "Audio file not found on disk"})

    # `filename=` gives the browser a sensible save-as name for the list view's
    # download link. It also sets Content-Disposition: attachment, but browsers
    # ignore that for <audio src="…">, so ReviewView's inline player is unaffected.
    return FileResponse(str(audio_path), filename=session.audio_file)
