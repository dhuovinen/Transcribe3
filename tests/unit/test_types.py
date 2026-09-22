"""Unit tests for transcribe3.shared.types — validators and domain helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from transcribe3.shared.types import (
    SpeakerLabel,
    TranscriptSegment,
    TranscriptSession,
    CleaningConfig,
)


# ---------------------------------------------------------------------------
# TranscriptSegment — end_time validator
# ---------------------------------------------------------------------------


def test_segment_end_time_before_start_time_raises():
    """end_time < start_time should raise a ValidationError."""
    with pytest.raises(ValidationError, match="end_time must be >= start_time"):
        TranscriptSegment(
            start_time=5.0,
            end_time=3.0,  # before start
            speaker=SpeakerLabel(anonymous_id="SPEAKER_00"),
            text="This should fail.",
        )


def test_segment_end_time_equal_to_start_time_is_valid():
    """end_time == start_time is allowed (zero-duration segment)."""
    seg = TranscriptSegment(
        start_time=2.0,
        end_time=2.0,
        speaker=SpeakerLabel(anonymous_id="SPEAKER_00"),
        text="Zero duration.",
    )
    assert seg.start_time == seg.end_time == 2.0


def test_segment_end_time_after_start_time_is_valid():
    seg = TranscriptSegment(
        start_time=1.0,
        end_time=5.0,
        speaker=SpeakerLabel(anonymous_id="SPEAKER_00"),
        text="Normal segment.",
    )
    assert seg.end_time > seg.start_time


# ---------------------------------------------------------------------------
# SpeakerLabel.display_name
# ---------------------------------------------------------------------------


def test_speaker_display_name_uses_resolved_when_present():
    label = SpeakerLabel(anonymous_id="SPEAKER_00", resolved_name="Jane Smith")
    assert label.display_name == "Jane Smith"


def test_speaker_display_name_falls_back_to_anonymous_id():
    label = SpeakerLabel(anonymous_id="SPEAKER_00")
    assert label.display_name == "SPEAKER_00"


# ---------------------------------------------------------------------------
# TranscriptSession.apply_speaker_map
# ---------------------------------------------------------------------------


def test_apply_speaker_map_resolves_names():
    """apply_speaker_map() fills resolved_name for each segment's speaker."""
    speaker = SpeakerLabel(anonymous_id="SPEAKER_00")
    seg = TranscriptSegment(
        start_time=0.0, end_time=2.0,
        speaker=speaker, text="Hello.",
    )
    session = TranscriptSession(
        source_file="test.wav",
        speaker_map={"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"},
        segments=[seg],
    )

    updated = session.apply_speaker_map()

    assert updated.segments[0].speaker.resolved_name == "Alice"
    assert updated.segments[0].speaker.anonymous_id == "SPEAKER_00"


def test_apply_speaker_map_unknown_speaker_gets_none():
    """A speaker not in the map gets resolved_name=None."""
    speaker = SpeakerLabel(anonymous_id="SPEAKER_UNKNOWN")
    seg = TranscriptSegment(
        start_time=0.0, end_time=2.0,
        speaker=speaker, text="Hello.",
    )
    session = TranscriptSession(
        source_file="test.wav",
        speaker_map={"SPEAKER_00": "Alice"},
        segments=[seg],
    )

    updated = session.apply_speaker_map()

    assert updated.segments[0].speaker.resolved_name is None


def test_apply_speaker_map_returns_new_session_not_mutated():
    """apply_speaker_map() returns a new session object; the original is unchanged."""
    speaker = SpeakerLabel(anonymous_id="SPEAKER_00")
    seg = TranscriptSegment(
        start_time=0.0, end_time=2.0,
        speaker=speaker, text="Hello.",
    )
    session = TranscriptSession(
        source_file="test.wav",
        speaker_map={"SPEAKER_00": "Alice"},
        segments=[seg],
    )

    updated = session.apply_speaker_map()

    # Original not mutated
    assert session.segments[0].speaker.resolved_name is None
    # Updated has the resolved name
    assert updated.segments[0].speaker.resolved_name == "Alice"


def test_apply_speaker_map_empty_session():
    """apply_speaker_map() on a session with no segments returns an empty list."""
    session = TranscriptSession(
        source_file="empty.wav",
        speaker_map={"SPEAKER_00": "Alice"},
        segments=[],
    )
    updated = session.apply_speaker_map()
    assert updated.segments == []
