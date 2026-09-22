"""Unit tests for transcribe3.data.session.SessionRepository."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import TranscriptSession, TranscriptSegment, SpeakerLabel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(source_file: str = "test_audio.wav") -> TranscriptSession:
    speaker = SpeakerLabel(anonymous_id="SPEAKER_00", resolved_name="Alice")
    segments = [
        TranscriptSegment(
            start_time=0.0, end_time=3.0,
            speaker=speaker, text="Hello, welcome.",
        ),
        TranscriptSegment(
            start_time=3.0, end_time=7.5,
            speaker=speaker, text="This is a test.",
        ),
    ]
    return TranscriptSession(
        source_file=source_file,
        segments=segments,
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_makes_directory_and_file(tmp_path):
    """SessionRepository.create() creates a session directory and session.json."""
    source = tmp_path / "audio.wav"
    source.touch()

    session = SessionRepository.create(source, tmp_path)

    session_dir = tmp_path / session.session_id
    session_file = session_dir / "session.json"

    assert session_dir.is_dir(), "Session directory should be created"
    assert session_file.is_file(), "session.json should be written"


def test_create_returns_session_with_correct_source_file(tmp_path):
    """Created session has source_file matching the input filename (not full path)."""
    source = tmp_path / "my_recording.wav"
    source.touch()

    session = SessionRepository.create(source, tmp_path)

    assert session.source_file == "my_recording.wav"


def test_create_session_id_is_uuid_like(tmp_path):
    """session_id should look like a UUID (36 chars, four hyphens)."""
    source = tmp_path / "audio.wav"
    source.touch()

    session = SessionRepository.create(source, tmp_path)

    assert len(session.session_id) == 36
    assert session.session_id.count("-") == 4


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    """A session saved with save() can be reloaded with load() intact."""
    session = _make_session()
    SessionRepository.save(session, tmp_path)

    loaded = SessionRepository.load(session.session_id, tmp_path)

    assert loaded.session_id == session.session_id
    assert loaded.source_file == session.source_file
    assert len(loaded.segments) == len(session.segments)


def test_save_and_load_preserves_segment_text(tmp_path):
    """Segment text survives the JSON serialisation round-trip."""
    session = _make_session()
    SessionRepository.save(session, tmp_path)

    loaded = SessionRepository.load(session.session_id, tmp_path)

    for orig, reloaded in zip(session.segments, loaded.segments):
        assert orig.text == reloaded.text


def test_save_and_load_preserves_speaker_labels(tmp_path):
    """Speaker anonymous_id survives the round-trip."""
    session = _make_session()
    SessionRepository.save(session, tmp_path)

    loaded = SessionRepository.load(session.session_id, tmp_path)

    for orig, reloaded in zip(session.segments, loaded.segments):
        assert orig.speaker.anonymous_id == reloaded.speaker.anonymous_id


def test_save_creates_sessions_dir_if_needed(tmp_path):
    """save() creates the session sub-directory if it doesn't exist yet."""
    session = _make_session()
    sessions_dir = tmp_path / "sessions"  # does not exist yet

    SessionRepository.save(session, sessions_dir)

    dest = sessions_dir / session.session_id / "session.json"
    assert dest.is_file()


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_raises_file_not_found(tmp_path):
    """load() raises FileNotFoundError for a non-existent session_id."""
    with pytest.raises(FileNotFoundError):
        SessionRepository.load("nonexistent-id-0000", tmp_path)


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def test_list_sessions_sorted_by_created_desc(tmp_path):
    """list_sessions() returns sessions ordered newest-first."""
    sessions_dir = tmp_path / "sessions"

    # Create three sessions with different created_at timestamps
    early = TranscriptSession(
        source_file="early.wav",
        created_at=datetime(2024, 1, 1, 10, 0, 0),
    )
    middle = TranscriptSession(
        source_file="middle.wav",
        created_at=datetime(2024, 6, 15, 12, 0, 0),
    )
    late = TranscriptSession(
        source_file="late.wav",
        created_at=datetime(2025, 3, 1, 9, 0, 0),
    )

    for s in (early, middle, late):
        SessionRepository.save(s, sessions_dir)

    result = SessionRepository.list_sessions(sessions_dir)

    assert len(result) == 3
    # Most recent first
    assert result[0].source_file == "late.wav"
    assert result[1].source_file == "middle.wav"
    assert result[2].source_file == "early.wav"


def test_list_sessions_empty_directory_returns_empty(tmp_path):
    """list_sessions() on an empty directory returns an empty list."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    result = SessionRepository.list_sessions(sessions_dir)
    assert result == []


def test_list_sessions_returns_all_sessions(tmp_path):
    """list_sessions() returns every saved session."""
    sessions_dir = tmp_path / "sessions"

    for i in range(4):
        s = TranscriptSession(source_file=f"file_{i}.wav")
        SessionRepository.save(s, sessions_dir)

    result = SessionRepository.list_sessions(sessions_dir)
    assert len(result) == 4


def test_list_sessions_skips_corrupt_files(tmp_path):
    """list_sessions() logs a warning and skips session files that cannot be parsed."""
    sessions_dir = tmp_path / "sessions"

    # Write one valid session
    good = TranscriptSession(source_file="good.wav")
    SessionRepository.save(good, sessions_dir)

    # Write a corrupt session.json in a different sub-directory
    corrupt_dir = sessions_dir / "corrupt-id-0000"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "session.json").write_text("NOT VALID JSON {{{", encoding="utf-8")

    result = SessionRepository.list_sessions(sessions_dir)
    # Corrupt file is skipped; only the valid session is returned
    assert len(result) == 1
    assert result[0].source_file == "good.wav"
