from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from transcribe3.data.exporters import (
    export,
    export_json,
    export_txt,
    export_srt,
    export_vtt,
    _seconds_to_srt_timecode,
    _seconds_to_vtt_timecode,
)
from transcribe3.data.parsers import parse_json
from transcribe3.shared.types import (
    TranscriptSession,
    TranscriptSegment,
    SpeakerLabel,
    OutputFormat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(with_timestamps: bool = True) -> TranscriptSession:
    jane = SpeakerLabel(anonymous_id="SPEAKER_00", resolved_name="Jane Smith")
    john = SpeakerLabel(anonymous_id="SPEAKER_01", resolved_name="John Doe")

    if with_timestamps:
        segments = [
            TranscriptSegment(start_time=1.0, end_time=4.5, speaker=jane, text="Welcome to the interview."),
            TranscriptSegment(start_time=5.2, end_time=10.8, speaker=john, text="Happy to be here."),
            TranscriptSegment(start_time=11.3, end_time=16.0, speaker=jane, text="What projects are you proud of?"),
        ]
    else:
        segments = [
            TranscriptSegment(start_time=0.0, end_time=0.0, speaker=jane, text="Welcome to the interview."),
            TranscriptSegment(start_time=0.0, end_time=0.0, speaker=john, text="Happy to be here."),
            TranscriptSegment(start_time=0.0, end_time=0.0, speaker=jane, text="What projects are you proud of?"),
        ]

    return TranscriptSession(source_file="test.srt", segments=segments)


# ---------------------------------------------------------------------------
# TXT export
# ---------------------------------------------------------------------------


def test_export_txt_format(tmp_path):
    session = _make_session()
    out = tmp_path / "output.txt"
    export_txt(session, out)
    content = out.read_text(encoding="utf-8")

    assert "Jane Smith: Welcome to the interview." in content
    assert "John Doe: Happy to be here." in content
    # Blank line separates different speakers
    assert "\n\n" in content


# ---------------------------------------------------------------------------
# SRT export
# ---------------------------------------------------------------------------


def test_export_srt_format(tmp_path):
    session = _make_session()
    out = tmp_path / "output.srt"
    export_srt(session, out)
    content = out.read_text(encoding="utf-8")

    # Index
    assert "1\n" in content
    # Timecode format HH:MM:SS,mmm --> HH:MM:SS,mmm
    assert "00:00:01,000 --> 00:00:04,500" in content
    # Speaker in text line
    assert "Jane Smith: Welcome to the interview." in content


def test_export_srt_fake_timestamps_when_no_audio(tmp_path):
    """Segments with start=end=0.0 should receive sequential 2-second timestamps."""
    session = _make_session(with_timestamps=False)
    out = tmp_path / "output.srt"
    export_srt(session, out)
    content = out.read_text(encoding="utf-8")

    # First segment: 0–2 seconds
    assert "00:00:00,000 --> 00:00:02,000" in content
    # Second segment: 2–4 seconds
    assert "00:00:02,000 --> 00:00:04,000" in content


# ---------------------------------------------------------------------------
# VTT export
# ---------------------------------------------------------------------------


def test_export_vtt_format(tmp_path):
    session = _make_session()
    out = tmp_path / "output.vtt"
    export_vtt(session, out)
    content = out.read_text(encoding="utf-8")

    # WEBVTT header
    assert content.startswith("WEBVTT")
    # Timecode uses dot separator
    assert "00:00:01.000 --> 00:00:04.500" in content
    # Speaker in cue text
    assert "Jane Smith: Welcome to the interview." in content


# ---------------------------------------------------------------------------
# JSON roundtrip
# ---------------------------------------------------------------------------


def test_export_json_roundtrip(tmp_path):
    session = _make_session()
    out = tmp_path / "output.json"
    export_json(session, out)
    reloaded = parse_json(out)
    assert len(reloaded) == len(session.segments)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_export_dispatch(tmp_path):
    """export() should call the correct exporter based on OutputFormat."""
    session = _make_session()
    out = tmp_path / "output.txt"
    result = export(session, OutputFormat.TXT, out)
    assert result == out
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Jane Smith:" in content


def test_export_dispatch_raises_for_unsupported_format(tmp_path):
    """export() raises ValueError for formats not in the dispatch table (e.g. DOCX)."""
    session = _make_session()
    out = tmp_path / "output.docx"
    with pytest.raises(ValueError, match="not supported"):
        export(session, OutputFormat.DOCX, out)


def test_export_vtt_fake_timestamps_when_no_audio(tmp_path):
    """VTT segments with start=end=0.0 should receive sequential 2-second timestamps."""
    session = _make_session(with_timestamps=False)
    out = tmp_path / "output.vtt"
    export_vtt(session, out)
    content = out.read_text(encoding="utf-8")

    # First segment: 0–2 seconds
    assert "00:00:00.000 --> 00:00:02.000" in content
    # Second segment: 2–4 seconds
    assert "00:00:02.000 --> 00:00:04.000" in content
