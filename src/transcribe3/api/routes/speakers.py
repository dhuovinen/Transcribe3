from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from transcribe3.api.dependencies import get_session_repo, get_sessions_dir
from transcribe3.api.schemas import SegmentSpeakerUpdate, SegmentTextUpdate, SpeakerMapUpdate
from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import SpeakerLabel

router = APIRouter()


@router.put("/{session_id}/speakers")
def update_speaker_map(
    session_id: str,
    body: SpeakerMapUpdate,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    session = session.model_copy(update={"speaker_map": body.speaker_map})
    session = session.apply_speaker_map()
    repo.save(session, sessions_dir)
    return JSONResponse(content=session.model_dump(mode="json"))


@router.put("/{session_id}/segments/{segment_id}/speaker")
def update_segment_speaker(
    session_id: str,
    segment_id: str,
    body: SegmentSpeakerUpdate,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    updated_segments = []
    found = False
    for seg in session.segments:
        if seg.id == segment_id:
            found = True
            new_speaker = SpeakerLabel(
                anonymous_id=seg.speaker.anonymous_id,
                resolved_name=body.speaker,
            )
            seg = seg.model_copy(
                update={"speaker": new_speaker, "confidence": body.confidence}
            )
        updated_segments.append(seg)

    if not found:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Segment not found: {segment_id}"},
        )

    session = session.model_copy(update={"segments": updated_segments})
    repo.save(session, sessions_dir)
    return JSONResponse(content=session.model_dump(mode="json"))


@router.put("/{session_id}/segments/{segment_id}/text")
def update_segment_text(
    session_id: str,
    segment_id: str,
    body: SegmentTextUpdate,
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> JSONResponse:
    """Save the current segment text, retaining only its pre-edit original."""
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    updated_segments = []
    found = False
    for seg in session.segments:
        if seg.id == segment_id:
            found = True
            seg = seg.model_copy(
                update={
                    "text": body.text,
                    "original_text": seg.original_text if seg.original_text is not None else seg.text,
                }
            )
        updated_segments.append(seg)

    if not found:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Segment not found: {segment_id}"},
        )

    session = session.model_copy(update={"segments": updated_segments})
    repo.save(session, sessions_dir)
    return JSONResponse(content=session.model_dump(mode="json"))
