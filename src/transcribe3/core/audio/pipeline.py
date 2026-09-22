from __future__ import annotations

from pathlib import Path
from typing import Callable

from transcribe3.core.audio.diarizer import diarize_audio
from transcribe3.core.audio.transcriber import transcribe_audio
from transcribe3.shared.types import SpeakerLabel, TranscriptSegment


def _best_speaker(seg_start: float, seg_end: float, diarization: list[dict]) -> str:
    """Return the speaker with maximum time overlap with [seg_start, seg_end]."""
    best_speaker = "SPEAKER_00"
    best_overlap = 0.0

    for d in diarization:
        overlap = max(0.0, min(seg_end, d["end"]) - max(seg_start, d["start"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = d["speaker"]

    return best_speaker


def run_audio_pipeline(
    audio_path: Path,
    hf_token: str,
    whisper_model: str = "base",
    backend: str = "whisperx",
    on_stage: Callable[[str], None] | None = None,
) -> list[TranscriptSegment]:
    """Transcribe and diarize an audio file, returning attributed segments.

    on_stage, if given, is called before each of the two sub-steps so callers
    can surface progress finer-grained than "processing" for the whole thing.
    """
    if on_stage:
        on_stage("Transcribing audio…")
    transcription = transcribe_audio(audio_path, whisper_model, backend)

    if on_stage:
        on_stage("Diarizing speakers…")
    diarization = diarize_audio(audio_path, hf_token)

    segments: list[TranscriptSegment] = []
    for raw in transcription:
        start = float(raw.get("start", 0.0))
        end = float(raw.get("end", start))
        text = raw.get("text", "").strip()
        if not text:
            continue

        speaker_id = _best_speaker(start, end, diarization)
        segments.append(
            TranscriptSegment(
                start_time=start,
                end_time=end,
                speaker=SpeakerLabel(anonymous_id=speaker_id),
                text=text,
                confidence=0.8,
            )
        )

    return segments
