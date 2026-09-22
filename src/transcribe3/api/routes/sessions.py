from __future__ import annotations

import shutil
import time
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from transcribe3.api.dependencies import (
    build_provider_client,
    get_session_repo,
    get_sessions_dir,
    get_settings,
    resolve_provider,
)
from transcribe3.api.schemas import CleaningConfigRequest, SessionRenameUpdate, SessionSummary
from transcribe3.core.attributor import attribute_speakers
from transcribe3.core.cleaner import clean_transcript
from transcribe3.api.llm_errors import describe_llm_failure
from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.data.parsers import parse_transcript
from transcribe3.data.session import SessionRepository
from transcribe3.shared.constants import DEFAULT_LOW_CONFIDENCE_THRESHOLD
from transcribe3.shared.types import (
    AppSettings,
    CleaningConfig,
    CleaningMode,
    FillerWordBehavior,
    ProcessingParams,
    SegmentFlag,
    StageTiming,
    TranscriptSession,
)

router = APIRouter()


def _build_cleaning_config(
    model: str,
    provider_id: str,
    mode: CleaningMode,
    filler_words: FillerWordBehavior,
    remove_false_starts: bool,
    handle_crosstalk: bool,
    low_confidence_threshold: float,
) -> CleaningConfig:
    return CleaningConfig(
        llm_model=model,
        llm_provider_id=provider_id,
        mode=mode,
        filler_words=filler_words,
        remove_false_starts=remove_false_starts,
        handle_crosstalk=handle_crosstalk,
        low_confidence_threshold=low_confidence_threshold,
    )


def _session_to_summary(session: TranscriptSession) -> SessionSummary:
    total = len(session.segments)
    low_conf = 0
    confidence_sum = 0.0
    for s in session.segments:
        if SegmentFlag.LOW_CONFIDENCE in s.flags:
            low_conf += 1
        confidence_sum += s.confidence
    mean_conf = confidence_sum / total if total > 0 else 0.0
    return SessionSummary(
        session_id=session.session_id,
        source_file=session.source_file,
        display_name=session.display_name,
        created_at=session.created_at.isoformat(),
        segment_count=total,
        low_confidence_count=low_conf,
        mean_confidence=mean_conf,
        status=session.status.value,
        warning=session.warning,
        processing_params=session.processing_params,
        stage_timings=session.stage_timings,
        audio_file=session.audio_file,
    )


@router.post("")
def create_session(
    file: UploadFile = File(...),
    model: str = Form("llama3"),
    provider_id: str | None = Form(None),
    mode: CleaningMode = Form(CleaningMode.STANDARD),
    filler_words: FillerWordBehavior = Form(FillerWordBehavior.OFF),
    remove_false_starts: bool = Form(False),
    handle_crosstalk: bool = Form(True),
    low_confidence_threshold: float = Form(DEFAULT_LOW_CONFIDENCE_THRESHOLD),
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
    settings: AppSettings = Depends(get_settings),
) -> JSONResponse:
    # Validate file suffix before writing to disk
    original_filename = file.filename or "upload"
    suffix = Path(original_filename).suffix.lower()
    from transcribe3.shared.constants import SUPPORTED_TRANSCRIPT_FORMATS

    if suffix not in SUPPORTED_TRANSCRIPT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Unsupported file format: {suffix!r}. Supported: {SUPPORTED_TRANSCRIPT_FORMATS}"},
        )

    # Save upload to a temp file preserving suffix so parsers can dispatch by extension
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        segments = parse_transcript(tmp_path)
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    finally:
        tmp_path.unlink(missing_ok=True)

    provider = resolve_provider(settings, provider_id)
    config = _build_cleaning_config(
        model=model,
        provider_id=provider.id,
        mode=mode,
        filler_words=filler_words,
        remove_false_starts=remove_false_starts,
        handle_crosstalk=handle_crosstalk,
        low_confidence_threshold=low_confidence_threshold,
    )
    llm_client = build_provider_client(settings, provider)

    # Both stages are switchable in Settings. Timing them here gives the admin
    # screen the same per-stage breakdown that audio sessions get.
    timings: list[StageTiming] = []
    warning: str | None = None

    try:
        if settings.run_cleaning:
            started = time.monotonic()
            segments = clean_transcript(segments, config)
            timings.append(
                StageTiming(stage="Cleaning transcript…", seconds=round(time.monotonic() - started, 1))
            )
        if settings.run_attribution:
            started = time.monotonic()
            segments = attribute_speakers(segments, config, llm_client, config.llm_model)
            timings.append(
                StageTiming(
                    stage="Validating speaker attribution with LLM…",
                    seconds=round(time.monotonic() - started, 1),
                )
            )
        else:
            warning = (
                "LLM speaker attribution is turned off in Settings, so speaker labels "
                "are unvalidated and segment confidence is unscored."
            )
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": describe_llm_failure(provider, exc)},
        )

    sessions_dir.mkdir(parents=True, exist_ok=True)
    session = TranscriptSession(
        source_file=original_filename,
        segments=segments,
        warning=warning,
        stage_timings=timings,
        processing_params=ProcessingParams(
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
        ),
    )
    repo.save(session, sessions_dir)

    return JSONResponse(content=session.model_dump(mode="json"))


@router.get("")
def list_sessions(
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> list[dict]:
    if not sessions_dir.exists():
        return []
    sessions = repo.list_sessions(sessions_dir)
    return [_session_to_summary(s).model_dump() for s in sessions]


@router.get("/{session_id}")
def get_session(
    session_id: str,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})
    return JSONResponse(content=session.model_dump(mode="json"))


@router.put("/{session_id}/name")
def rename_session(
    session_id: str,
    body: SessionRenameUpdate,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    display_name = body.display_name.strip() if body.display_name else None
    session = session.model_copy(update={"display_name": display_name or None})
    repo.save(session, sessions_dir)
    return JSONResponse(content=session.model_dump(mode="json"))


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    sessions_dir: Path = Depends(get_sessions_dir),
) -> JSONResponse:
    session_dir = sessions_dir / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})
    shutil.rmtree(session_dir)
    return JSONResponse(content={"deleted": session_id})
