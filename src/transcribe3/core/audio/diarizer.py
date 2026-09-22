from __future__ import annotations

from pathlib import Path


def diarize_audio(audio_path: Path, hf_token: str) -> list[dict]:
    """Run pyannote.audio speaker diarization on an audio file.

    Returns a list of dicts with keys: start, end, speaker.

    Uses whisperx.load_audio (faster-whisper backend) to decode the file rather
    than torchaudio or torchcodec, both of which fail against FFmpeg 8.x.
    whisperx returns float32 mono numpy at 16 kHz — the same sample rate
    pyannote's diarization models expect.
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio is not installed. Run: uv sync --extra audio"
        ) from exc

    try:
        import torch
        import whisperx  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "whisperx and torch are required for audio diarization."
        ) from exc

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    # Load audio using faster-whisper's backend (works with FFmpeg 8.x).
    # whisperx.load_audio returns float32 mono numpy array at 16 kHz.
    audio_np = whisperx.load_audio(str(audio_path))
    waveform = torch.from_numpy(audio_np).unsqueeze(0)  # (1, samples)
    audio_input = {"waveform": waveform, "sample_rate": 16000}

    # pyannote.audio 4.x returns a DiarizeOutput dataclass;
    # the Annotation object is in .speaker_diarization
    output = pipeline(audio_input)
    annotation = output.speaker_diarization

    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({"start": turn.start, "end": turn.end, "speaker": speaker})
    return segments
