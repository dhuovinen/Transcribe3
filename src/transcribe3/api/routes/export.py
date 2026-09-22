from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from transcribe3.api.dependencies import get_session_repo, get_sessions_dir
from transcribe3.data.exporters import export
from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import OutputFormat

router = APIRouter()

_CONTENT_TYPES: dict[OutputFormat, str] = {
    OutputFormat.JSON: "application/json",
    OutputFormat.TXT: "text/plain",
    OutputFormat.SRT: "text/plain",
    OutputFormat.VTT: "text/vtt",
    OutputFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{session_id}/export")
def export_session(
    session_id: str,
    format: OutputFormat = Query(...),
    sessions_dir: Path = Depends(get_sessions_dir),
    repo: SessionRepository = Depends(get_session_repo),
) -> FileResponse:
    try:
        session = repo.load(session_id, sessions_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": f"Session not found: {session_id}"})

    stem = Path(session.source_file).stem
    filename = f"{stem}.{format.value}"
    content_type = _CONTENT_TYPES[format]

    suffix = f".{format.value}"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    if format == OutputFormat.DOCX:
        # DOCX export is not implemented in exporters.py — raise 422
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail={"error": "DOCX export is not yet implemented"},
        )

    export(session, format, tmp_path)

    return FileResponse(
        path=str(tmp_path),
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
