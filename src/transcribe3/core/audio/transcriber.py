from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# mlx-community's Whisper model repos follow this naming pattern.
# Override with MLX_WHISPER_REPO if your local size/name differs.
_MLX_REPO_TEMPLATE = "mlx-community/whisper-{size}-mlx"


def transcribe_audio(
    audio_path: Path, model_size: str = "base", backend: str = "whisperx"
) -> list[dict]:
    """Run Whisper transcription on an audio file via the chosen backend.

    Returns a list of segment dicts with keys: start, end, text, words.
    """
    if backend == "mlx":
        return _transcribe_mlx(audio_path, model_size)
    if backend == "whisperx":
        return _transcribe_whisperx(audio_path, model_size)
    raise RuntimeError(f"Unknown transcription backend: {backend!r}. Use 'whisperx' or 'mlx'.")


def _transcribe_whisperx(audio_path: Path, model_size: str) -> list[dict]:
    """Lazy-imports whisperx so the package remains optional."""
    try:
        import whisperx  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "whisperx is not installed. Run: uv sync --extra audio"
        ) from exc

    device = "cpu"
    compute_type = "int8"

    model = whisperx.load_model(model_size, device, compute_type=compute_type)
    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=4)

    language = result.get("language", "en")

    # Word-level alignment is best-effort — fall through if it fails
    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device=device
        )
    except Exception as exc:
        logger.warning(
            "Word-level alignment failed for %s — falling back to segment-level "
            "timestamps: %s", audio_path, exc,
        )

    return result.get("segments", [])


def _transcribe_mlx(audio_path: Path, model_size: str) -> list[dict]:
    """Runs Whisper via mlx-whisper, which uses Apple's GPU/Neural Engine
    through MLX instead of CPU-only inference. Lazy-imports mlx_whisper so
    the package remains optional (and only installable on Apple Silicon)."""
    import os

    try:
        import mlx_whisper  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "mlx-whisper is not installed. Run: uv sync --extra mlx"
        ) from exc

    repo = os.environ.get("MLX_WHISPER_REPO") or _MLX_REPO_TEMPLATE.format(size=model_size)
    result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=repo)

    return result.get("segments", [])
