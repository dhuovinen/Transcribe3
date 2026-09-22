from __future__ import annotations

import json
from pathlib import Path

from transcribe3.shared.types import TranscriptSession, TranscriptSegment, OutputFormat


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def export(session: TranscriptSession, format: OutputFormat, output_path: Path) -> Path:
    """Dispatch to the appropriate exporter and return the written path."""
    dispatch = {
        OutputFormat.JSON: export_json,
        OutputFormat.TXT: export_txt,
        OutputFormat.SRT: export_srt,
        OutputFormat.VTT: export_vtt,
    }
    if format not in dispatch:
        raise ValueError(f"Export format not supported: {format!r}")
    return dispatch[format](session, output_path)


# ---------------------------------------------------------------------------
# Format exporters
# ---------------------------------------------------------------------------


def export_json(session: TranscriptSession, path: Path) -> Path:
    """Write the full session as indented JSON."""
    path.write_text(
        json.dumps(session.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    return path


def export_txt(session: TranscriptSession, path: Path) -> Path:
    """Write one line per segment with speaker prefix; blank line on speaker change."""
    lines: list[str] = []
    prev_speaker: str | None = None

    for seg in session.segments:
        display = seg.speaker.display_name
        if prev_speaker is not None and display != prev_speaker:
            lines.append("")
        lines.append(f"{display}: {seg.text}")
        prev_speaker = display

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_srt(session: TranscriptSession, path: Path) -> Path:
    """Write standard SRT format."""
    blocks: list[str] = []

    # Detect whether all segments lack real timestamps
    all_zero = all(s.start_time == 0.0 and s.end_time == 0.0 for s in session.segments)

    for idx, seg in enumerate(session.segments, start=1):
        if all_zero:
            start = (idx - 1) * 2.0
            end = idx * 2.0
        else:
            start = seg.start_time
            end = seg.end_time

        tc_start = _seconds_to_srt_timecode(start)
        tc_end = _seconds_to_srt_timecode(end)
        display = seg.speaker.display_name

        blocks.append(f"{idx}\n{tc_start} --> {tc_end}\n{display}: {seg.text}\n")

    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def export_vtt(session: TranscriptSession, path: Path) -> Path:
    """Write WebVTT format."""
    blocks: list[str] = ["WEBVTT\n"]

    all_zero = all(s.start_time == 0.0 and s.end_time == 0.0 for s in session.segments)

    for idx, seg in enumerate(session.segments, start=1):
        if all_zero:
            start = (idx - 1) * 2.0
            end = idx * 2.0
        else:
            start = seg.start_time
            end = seg.end_time

        tc_start = _seconds_to_vtt_timecode(start)
        tc_end = _seconds_to_vtt_timecode(end)
        display = seg.speaker.display_name

        blocks.append(f"{tc_start} --> {tc_end}\n{display}: {seg.text}\n")

    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Timecode helpers
# ---------------------------------------------------------------------------


def _seconds_to_srt_timecode(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS,mmm."""
    return _format_timecode(seconds, ms_sep=",")


def _seconds_to_vtt_timecode(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.mmm."""
    return _format_timecode(seconds, ms_sep=".")


def _format_timecode(seconds: float, ms_sep: str) -> str:
    total_ms = round(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d}{ms_sep}{ms:03d}"
