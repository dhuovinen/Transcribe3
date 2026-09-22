from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from transcribe3.shared.types import TranscriptSession

logger = logging.getLogger(__name__)


class SessionRepository:
    """Handles persistence of TranscriptSession objects to disk."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    def create(source_file: Path, sessions_dir: Path) -> TranscriptSession:
        """Build and persist a new empty TranscriptSession."""
        session = TranscriptSession(
            session_id=str(uuid.uuid4()),
            source_file=source_file.name,
            created_at=datetime.utcnow(),
        )
        session_dir = sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        SessionRepository.save(session, sessions_dir)
        return session

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @staticmethod
    def save(session: TranscriptSession, sessions_dir: Path) -> Path:
        """Serialize session to JSON and write it to disk."""
        session_dir = sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        dest = session_dir / "session.json"
        payload = json.dumps(session.model_dump(mode="json"), indent=2, default=str)
        dest.write_text(payload, encoding="utf-8")
        return dest

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @staticmethod
    def load(session_id: str, sessions_dir: Path) -> TranscriptSession:
        """Load a single session by ID."""
        path = sessions_dir / session_id / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {path}")
        return TranscriptSession.model_validate(json.loads(path.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @staticmethod
    def list_sessions(sessions_dir: Path) -> list[TranscriptSession]:
        """Return all sessions sorted by created_at descending."""
        sessions: list[TranscriptSession] = []
        for session_file in sessions_dir.glob("*/session.json"):
            try:
                session = TranscriptSession.model_validate(
                    json.loads(session_file.read_text(encoding="utf-8"))
                )
                sessions.append(session)
            except Exception as exc:
                logger.warning("Skipping corrupt session file %s: %s", session_file, exc)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions
