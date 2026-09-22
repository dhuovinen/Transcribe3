from __future__ import annotations

import json
import re
from pathlib import Path

from transcribe3.shared.types import TranscriptSegment, SpeakerLabel
from transcribe3.shared.constants import SUPPORTED_TRANSCRIPT_FORMATS


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def parse_transcript(path: Path) -> list[TranscriptSegment]:
    """Dispatch parsing to the appropriate parser based on file suffix."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_TRANSCRIPT_FORMATS:
        raise ValueError(
            f"Unsupported transcript format: {suffix!r}. "
            f"Supported: {SUPPORTED_TRANSCRIPT_FORMATS}"
        )
    dispatch = {
        ".srt": parse_srt,
        ".vtt": parse_vtt,
        ".json": parse_json,
        ".txt": parse_txt,
    }
    return dispatch[suffix](path)


# ---------------------------------------------------------------------------
# SRT parser
# ---------------------------------------------------------------------------


def parse_srt(path: Path) -> list[TranscriptSegment]:
    """Parse a standard SRT file into TranscriptSegment objects."""
    text = path.read_text(encoding="utf-8")
    segments: list[TranscriptSegment] = []

    # Split on blank lines to get blocks; each block is one cue
    blocks = re.split(r"\n\s*\n", text.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        # Line 0: sequence index (we ignore the number, just validate)
        # Line 1: timecode
        timecode_line = lines[1].strip()
        tc_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            timecode_line,
        )
        if not tc_match:
            continue

        start = _timecode_to_seconds(tc_match.group(1))
        end = _timecode_to_seconds(tc_match.group(2))

        # Remaining lines: text (may be multi-line)
        text_lines = lines[2:]
        raw_text = " ".join(line.strip() for line in text_lines)

        speaker, clean_text = _extract_speaker(raw_text)
        segments.append(
            TranscriptSegment(
                start_time=start,
                end_time=end,
                speaker=speaker,
                text=clean_text,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# VTT parser
# ---------------------------------------------------------------------------


def parse_vtt(path: Path) -> list[TranscriptSegment]:
    """Parse a WebVTT file into TranscriptSegment objects."""
    text = path.read_text(encoding="utf-8")
    segments: list[TranscriptSegment] = []

    # Strip WEBVTT header line and any NOTE/STYLE blocks
    lines = text.splitlines()
    # Find where the first cue block starts (first line with --> after header)
    content = "\n".join(lines)

    # Split into blocks on blank lines
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        block = block.strip()
        # Skip the WEBVTT header block and NOTE/STYLE blocks
        if block.startswith("WEBVTT") or block.startswith("NOTE") or block.startswith("STYLE"):
            continue

        block_lines = block.splitlines()

        # Find the timecode line (may be first or second line if cue ID present)
        tc_line_idx = None
        for i, line in enumerate(block_lines):
            if re.search(r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}", line):
                tc_line_idx = i
                break
        if tc_line_idx is None:
            continue

        tc_line = block_lines[tc_line_idx].strip()
        tc_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            tc_line,
        )
        if not tc_match:
            continue

        start = _timecode_to_seconds(tc_match.group(1))
        end = _timecode_to_seconds(tc_match.group(2))

        text_lines = block_lines[tc_line_idx + 1:]
        if not text_lines:
            continue
        raw_text = " ".join(line.strip() for line in text_lines)

        speaker, clean_text = _extract_speaker(raw_text)
        segments.append(
            TranscriptSegment(
                start_time=start,
                end_time=end,
                speaker=speaker,
                text=clean_text,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Plain text parser
# ---------------------------------------------------------------------------

# Patterns (checked in order):
#   1. ALL-CAPS NAME: text
#   2. [Any Name] text
#   3. Title Case Name: text
_SPEAKER_PATTERNS = [
    # ALL CAPS or MIXED CAPS followed by colon (e.g. "JANE SMITH: hello")
    re.compile(r"^([A-Z][A-Z0-9 _\-]+?):\s+(.+)$"),
    # Bracket-wrapped name (e.g. "[Jane Smith] hello")
    re.compile(r"^\[([^\]]+?)\]\s*(.*)$"),
    # Title Case name: text (e.g. "Jane Smith: hello")
    re.compile(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+):\s+(.+)$"),
]


def parse_txt(path: Path) -> list[TranscriptSegment]:
    """Parse a plain-text transcript with speaker labels into segments."""
    lines = path.read_text(encoding="utf-8").splitlines()
    segments: list[TranscriptSegment] = []

    current_speaker: str | None = None
    current_text_parts: list[str] = []

    def flush() -> None:
        if current_speaker is not None and current_text_parts:
            segments.append(
                TranscriptSegment(
                    start_time=0.0,
                    end_time=0.0,
                    speaker=SpeakerLabel(anonymous_id=current_speaker),
                    text=" ".join(current_text_parts),
                )
            )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        matched_speaker: str | None = None
        matched_text: str | None = None
        for pattern in _SPEAKER_PATTERNS:
            m = pattern.match(stripped)
            if m:
                matched_speaker = m.group(1).strip()
                matched_text = m.group(2).strip()
                break

        if matched_speaker is not None:
            if matched_speaker != current_speaker:
                flush()
                current_speaker = matched_speaker
                current_text_parts = [matched_text] if matched_text else []
            else:
                # Same speaker, new line
                if matched_text:
                    current_text_parts.append(matched_text)
        else:
            # Continuation line — append to current speaker
            if current_speaker is not None:
                current_text_parts.append(stripped)

    flush()
    return segments


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------


def parse_json(path: Path) -> list[TranscriptSegment]:
    """Parse our own TranscriptSession JSON (or bare segment list) into segments."""
    from transcribe3.shared.types import TranscriptSession

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        return [TranscriptSegment.model_validate(item) for item in raw]

    # Full session object
    session = TranscriptSession.model_validate(raw)
    return session.segments


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _timecode_to_seconds(tc: str) -> float:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to float seconds."""
    # Normalise separator
    tc = tc.replace(",", ".")
    parts = tc.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_ms = float(parts[2])
    return hours * 3600 + minutes * 60 + sec_ms


def _extract_speaker(raw_text: str) -> tuple[SpeakerLabel, str]:
    """
    Detect a speaker prefix in a text string.

    Recognised patterns:
      - ``SPEAKER NAME: text``  (upper/title case before colon)
      - ``[Speaker Name] text`` (bracket-wrapped)

    Returns (SpeakerLabel, cleaned_text).
    """
    # Try bracket pattern first (more explicit)
    bracket = re.match(r"^\[([^\]]+?)\]\s*(.*)$", raw_text)
    if bracket:
        speaker_id = bracket.group(1).strip()
        text = bracket.group(2).strip()
        return SpeakerLabel(anonymous_id=speaker_id), text

    # Try "NAME: text" — name is all-caps or title-case words
    colon = re.match(r"^([A-Z][A-Za-z0-9 _\-]+?):\s+(.+)$", raw_text)
    if colon:
        speaker_id = colon.group(1).strip()
        text = colon.group(2).strip()
        return SpeakerLabel(anonymous_id=speaker_id), text

    return SpeakerLabel(anonymous_id="Speaker_Unknown"), raw_text
