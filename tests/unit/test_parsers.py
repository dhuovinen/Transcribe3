from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from transcribe3.data.parsers import (
    parse_transcript,
    parse_srt,
    parse_txt,
    parse_vtt,
    parse_json,
    _timecode_to_seconds,
)
from transcribe3.data.exporters import export_json
from transcribe3.shared.types import TranscriptSession

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# SRT tests
# ---------------------------------------------------------------------------


def test_parse_srt_returns_correct_segment_count():
    segments = parse_srt(FIXTURES / "sample.srt")
    assert len(segments) == 6


def test_parse_srt_timecodes_to_seconds():
    segments = parse_srt(FIXTURES / "sample.srt")
    first = segments[0]
    assert first.start_time == pytest.approx(1.0, abs=0.01)
    assert first.end_time == pytest.approx(4.5, abs=0.01)


def test_parse_srt_detects_speaker_label():
    segments = parse_srt(FIXTURES / "sample.srt")
    speakers = {s.speaker.anonymous_id for s in segments}
    assert "Jane Smith" in speakers
    assert "John Doe" in speakers
    # No unknown speakers
    assert "Speaker_Unknown" not in speakers


# ---------------------------------------------------------------------------
# Plain-text tests
# ---------------------------------------------------------------------------


def test_parse_txt_groups_consecutive_same_speaker():
    """Lines from the same speaker that appear consecutively should be merged."""
    content = "ALICE: Hello there.\nHow are you doing today?\n\nBOB: I'm fine, thanks.\n"
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_txt(tmp)
        alice_segs = [s for s in segments if s.speaker.anonymous_id == "ALICE"]
        assert len(alice_segs) == 1
        assert "Hello there." in alice_segs[0].text
        assert "How are you doing today?" in alice_segs[0].text
    finally:
        tmp.unlink()


def test_parse_txt_detects_colon_speaker_pattern():
    segments = parse_txt(FIXTURES / "sample.txt")
    speakers = {s.speaker.anonymous_id for s in segments}
    assert "JANE SMITH" in speakers
    assert "JOHN DOE" in speakers


def test_parse_txt_detects_bracket_speaker_pattern():
    content = "[Jane Smith] Hello, welcome.\n[John Doe] Thank you for having me.\n"
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_txt(tmp)
        speakers = {s.speaker.anonymous_id for s in segments}
        assert "Jane Smith" in speakers
        assert "John Doe" in speakers
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


def test_parse_transcript_dispatches_by_extension():
    segments_srt = parse_transcript(FIXTURES / "sample.srt")
    segments_txt = parse_transcript(FIXTURES / "sample.txt")
    assert len(segments_srt) == 6
    assert len(segments_txt) == 6


def test_parse_transcript_raises_on_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = Path(f.name)
    try:
        with pytest.raises(ValueError, match="Unsupported transcript format"):
            parse_transcript(tmp)
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_json_roundtrip():
    """parse_txt → export_json → parse_json should preserve segment count and text."""
    original_segments = parse_txt(FIXTURES / "sample.txt")
    session = TranscriptSession(
        source_file="sample.txt",
        segments=original_segments,
    )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
        tmp = Path(f.name)
    try:
        export_json(session, tmp)
        reloaded = parse_json(tmp)
        assert len(reloaded) == len(original_segments)
        for orig, reloaded_seg in zip(original_segments, reloaded):
            assert orig.text == reloaded_seg.text
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# VTT parser tests
# ---------------------------------------------------------------------------


_SAMPLE_VTT = """\
WEBVTT

00:00:01.000 --> 00:00:04.500
Jane Smith: Welcome to the interview.

00:00:05.200 --> 00:00:10.800
John Doe: Happy to be here.

00:00:11.300 --> 00:00:16.000
Jane Smith: What are you proud of?
"""

_SAMPLE_VTT_WITH_CUE_IDS = """\
WEBVTT

1
00:00:01.000 --> 00:00:04.500
Jane Smith: Cue ID test.

2
00:00:05.000 --> 00:00:09.000
John Doe: Second cue.
"""

_SAMPLE_VTT_WITH_NOTE = """\
WEBVTT

NOTE This is a comment block

00:00:01.000 --> 00:00:03.000
Speaker_Unknown: Only cue.
"""


def _write_vtt(content: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".vtt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        return Path(f.name)


def test_parse_vtt_returns_correct_segment_count():
    tmp = _write_vtt(_SAMPLE_VTT)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 3
    finally:
        tmp.unlink()


def test_parse_vtt_timecodes_to_seconds():
    tmp = _write_vtt(_SAMPLE_VTT)
    try:
        segments = parse_vtt(tmp)
        assert segments[0].start_time == pytest.approx(1.0, abs=0.01)
        assert segments[0].end_time == pytest.approx(4.5, abs=0.01)
        assert segments[1].start_time == pytest.approx(5.2, abs=0.01)
    finally:
        tmp.unlink()


def test_parse_vtt_detects_speaker_labels():
    tmp = _write_vtt(_SAMPLE_VTT)
    try:
        segments = parse_vtt(tmp)
        speakers = {s.speaker.anonymous_id for s in segments}
        assert "Jane Smith" in speakers
        assert "John Doe" in speakers
    finally:
        tmp.unlink()


def test_parse_vtt_with_cue_ids():
    """VTT files with numeric cue IDs before the timecode line are handled."""
    tmp = _write_vtt(_SAMPLE_VTT_WITH_CUE_IDS)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 2
        assert segments[0].speaker.anonymous_id == "Jane Smith"
        assert segments[1].speaker.anonymous_id == "John Doe"
    finally:
        tmp.unlink()


def test_parse_vtt_skips_note_blocks():
    """NOTE blocks are ignored; only real cue blocks are parsed."""
    tmp = _write_vtt(_SAMPLE_VTT_WITH_NOTE)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 1
    finally:
        tmp.unlink()


def test_parse_vtt_no_speaker_falls_back_to_unknown():
    """Cue text with no speaker prefix gets Speaker_Unknown."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nNo speaker prefix here.\n"
    tmp = _write_vtt(content)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 1
        assert segments[0].speaker.anonymous_id == "Speaker_Unknown"
        assert segments[0].text == "No speaker prefix here."
    finally:
        tmp.unlink()


def test_parse_transcript_dispatches_vtt():
    tmp = _write_vtt(_SAMPLE_VTT)
    try:
        segments = parse_transcript(tmp)
        assert len(segments) == 3
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# parse_json bare-list variant
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SRT edge cases (malformed blocks)
# ---------------------------------------------------------------------------


def test_parse_srt_skips_blocks_with_fewer_than_3_lines():
    """Blocks with fewer than 3 lines (malformed) are silently skipped."""
    content = (
        "1\n"
        "00:00:01,000 --> 00:00:03,000\n"
        "Jane Smith: Good block.\n"
        "\n"
        "2\n"
        # Only 2 lines — no text line
        "00:00:04,000 --> 00:00:06,000\n"
        "\n"
        "3\n"
        "00:00:07,000 --> 00:00:09,000\n"
        "John Doe: Another good block.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_srt(tmp)
        # Block 2 is skipped; blocks 1 and 3 are parsed
        assert len(segments) == 2
    finally:
        tmp.unlink()


def test_parse_srt_skips_blocks_with_bad_timecode():
    """Blocks with a malformed timecode line are silently skipped."""
    content = (
        "1\n"
        "NOT A TIMECODE\n"
        "Jane Smith: This block has no valid timecode.\n"
        "\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "John Doe: This one is fine.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_srt(tmp)
        assert len(segments) == 1
        assert segments[0].speaker.anonymous_id == "John Doe"
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# VTT edge cases
# ---------------------------------------------------------------------------


def test_parse_vtt_skips_block_with_no_timecode_line():
    """VTT blocks that contain no '-->' are silently skipped."""
    content = (
        "WEBVTT\n\n"
        "This block has no timecode.\n"
        "Just some text.\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "John Doe: Valid cue.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".vtt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 1
        assert segments[0].speaker.anonymous_id == "John Doe"
    finally:
        tmp.unlink()


def test_parse_vtt_skips_cue_with_no_text_after_timecode():
    """VTT cues that have no text lines after the timecode are skipped."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n\n"  # timecode only, no text
        "00:00:04.000 --> 00:00:06.000\n"
        "Jane Smith: Valid.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".vtt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_vtt(tmp)
        assert len(segments) == 1
        assert segments[0].speaker.anonymous_id == "Jane Smith"
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# parse_txt — same-speaker continuation line
# ---------------------------------------------------------------------------


def test_parse_txt_same_speaker_continuation_line():
    """A new speaker-labeled line from the *same* speaker is appended to current segment."""
    content = (
        "ALICE: First line.\n"
        "ALICE: Second line from same speaker.\n"
        "\n"
        "BOB: Bob speaks.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_txt(tmp)
        alice_segs = [s for s in segments if s.speaker.anonymous_id == "ALICE"]
        # Both ALICE lines merged into one segment
        assert len(alice_segs) == 1
        assert "First line." in alice_segs[0].text
        assert "Second line from same speaker." in alice_segs[0].text
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# _extract_speaker — bracket pattern in SRT context
# ---------------------------------------------------------------------------


def test_parse_srt_bracket_speaker_label():
    """SRT cue text starting with [Name] is parsed using the bracket pattern."""
    content = (
        "1\n"
        "00:00:01,000 --> 00:00:04,000\n"
        "[Jane Smith] This uses bracket notation.\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".srt", mode="w", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        segments = parse_srt(tmp)
        assert len(segments) == 1
        assert segments[0].speaker.anonymous_id == "Jane Smith"
        assert segments[0].text == "This uses bracket notation."
    finally:
        tmp.unlink()


def test_parse_json_accepts_bare_segment_list():
    """parse_json handles a raw JSON array of segment dicts (not a full session)."""
    import json as _json
    from transcribe3.shared.types import SpeakerLabel, TranscriptSegment

    segs = [
        TranscriptSegment(
            start_time=0.0, end_time=2.0,
            speaker=SpeakerLabel(anonymous_id="SPEAKER_00"),
            text="Hello.",
        ),
        TranscriptSegment(
            start_time=2.0, end_time=5.0,
            speaker=SpeakerLabel(anonymous_id="SPEAKER_01"),
            text="World.",
        ),
    ]
    raw_list = [s.model_dump(mode="json") for s in segs]

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        _json.dump(raw_list, f)
        tmp = Path(f.name)
    try:
        result = parse_json(tmp)
        assert len(result) == 2
        assert result[0].text == "Hello."
        assert result[1].text == "World."
    finally:
        tmp.unlink()
