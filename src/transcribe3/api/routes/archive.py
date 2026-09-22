from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from transcribe3.api.dependencies import get_session_repo, get_sessions_dir
from transcribe3.api.schemas import (
    ArchiveConfigurationUpdate,
    ArchiveRecordingRequest,
    ArchiveRecordingStatus,
    ArchiveStatusResponse,
)
from transcribe3.data.archive import (
    ArchiveConfigurationError,
    ArchiveConflictError,
    ArchiveError,
    ArchiveRepository,
)
from transcribe3.data.session import SessionRepository
from transcribe3.data.settings import SettingsRepository
from transcribe3.shared.types import SessionStatus, TranscriptSession

router = APIRouter()

DEFAULT_ARCHIVE_DIR = "/Volumes/Extreme SSD/Transcribe3 Archive"


def _raise_archive_error(error: ArchiveError) -> None:
    status = 409 if isinstance(error, (ArchiveConfigurationError, ArchiveConflictError)) else 422
    raise HTTPException(status_code=status, detail={"error": str(error)}) from error


def _safe_file_size(path: Path | None) -> int | None:
    if path is None or not path.is_file():
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _safe_free_space(path: Path | None) -> int | None:
    if path is None or not path.is_dir():
        return None
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _recording_status(
    session: TranscriptSession,
    sessions_dir: Path,
    archive_dir: str | None,
) -> ArchiveRecordingStatus | None:
    if not session.audio_file:
        return None
    try:
        local_path = ArchiveRepository.local_audio_path(session, sessions_dir)
    except ArchiveError:
        local_path = None

    archive_path = None
    if archive_dir:
        try:
            archive_path = ArchiveRepository.configured_archive_path(
                session, Path(archive_dir).expanduser().resolve()
            )
        except ArchiveError:
            archive_path = None
    return ArchiveRecordingStatus(
        session_id=session.session_id,
        source_file=session.source_file,
        display_name=session.display_name,
        audio_file=session.audio_file,
        local_available=bool(local_path and local_path.is_file()),
        archive_available=bool(archive_path and archive_path.is_file()),
        local_size_bytes=_safe_file_size(local_path),
        archive_size_bytes=_safe_file_size(archive_path),
    )


def _load_session(session_id: str, sessions_dir: Path, repo: SessionRepository) -> TranscriptSession:
    try:
        return repo.load(session_id, sessions_dir)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail={"error": "Session not found."}) from error


def _require_not_processing(session: TranscriptSession) -> None:
    if session.status == SessionStatus.PROCESSING:
        raise HTTPException(
            status_code=409,
            detail={"error": "Wait for processing to finish before moving its recording."},
        )


@router.get("")
def get_archive_status(
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> ArchiveStatusResponse:
    settings = SettingsRepository.load(sessions_dir)
    archive_path = Path(settings.archive_dir).expanduser().resolve() if settings.archive_dir else None
    recordings = [
        status
        for session in repo.list_sessions(sessions_dir) if (status := _recording_status(session, sessions_dir, settings.archive_dir))
    ] if sessions_dir.exists() else []
    return ArchiveStatusResponse(
        archive_dir=settings.archive_dir,
        suggested_archive_dir=DEFAULT_ARCHIVE_DIR,
        archive_connected=bool(archive_path and archive_path.is_dir()),
        local_free_bytes=_safe_free_space(sessions_dir),
        archive_free_bytes=_safe_free_space(archive_path),
        recordings=recordings,
    )


@router.put("/configuration")
def configure_archive(
    body: ArchiveConfigurationUpdate,
    sessions_dir: Path = Depends(get_sessions_dir),
) -> ArchiveStatusResponse:
    try:
        archive_root = ArchiveRepository.configure_root(body.archive_dir, sessions_dir)
    except ArchiveError as error:
        _raise_archive_error(error)

    settings = SettingsRepository.load(sessions_dir)
    SettingsRepository.save(settings.model_copy(update={"archive_dir": str(archive_root)}), sessions_dir)
    return get_archive_status(sessions_dir=sessions_dir, repo=SessionRepository())


@router.post("/{session_id}/archive")
def archive_recording(
    session_id: str,
    body: ArchiveRecordingRequest,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> ArchiveRecordingStatus:
    session = _load_session(session_id, sessions_dir, repo)
    _require_not_processing(session)
    settings = SettingsRepository.load(sessions_dir)
    try:
        updated = ArchiveRepository.archive(session, sessions_dir, settings.archive_dir, body.remove_local)
        status = _recording_status(updated, sessions_dir, settings.archive_dir)
    except ArchiveError as error:
        _raise_archive_error(error)
    if status is None:
        raise HTTPException(status_code=422, detail={"error": "This session has no audio recording."})
    return status


@router.post("/{session_id}/restore")
def restore_recording(
    session_id: str,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> ArchiveRecordingStatus:
    session = _load_session(session_id, sessions_dir, repo)
    _require_not_processing(session)
    settings = SettingsRepository.load(sessions_dir)
    try:
        restored = ArchiveRepository.restore(session, sessions_dir, settings.archive_dir)
        status = _recording_status(restored, sessions_dir, settings.archive_dir)
    except ArchiveError as error:
        _raise_archive_error(error)
    if status is None:
        raise HTTPException(status_code=422, detail={"error": "This session has no audio recording."})
    return status


@router.delete("/{session_id}/local-copy")
def delete_local_recording(
    session_id: str,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> ArchiveRecordingStatus:
    session = _load_session(session_id, sessions_dir, repo)
    _require_not_processing(session)
    settings = SettingsRepository.load(sessions_dir)
    try:
        updated = ArchiveRepository.delete_local_copy(session, sessions_dir, settings.archive_dir)
        status = _recording_status(updated, sessions_dir, settings.archive_dir)
    except ArchiveError as error:
        _raise_archive_error(error)
    if status is None:
        raise HTTPException(status_code=422, detail={"error": "This session has no audio recording."})
    return status
