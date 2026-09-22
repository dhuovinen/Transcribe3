from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def probe_audio_duration_seconds(audio_path: Path) -> float | None:
    """Return an audio file's duration via ffprobe, or None if it can't be read.

    Best-effort: duration is a display nicety, not something the pipeline
    depends on, so any failure (ffprobe missing, corrupt file, unexpected
    output) is logged and degrades to None rather than failing the upload.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return float(result.stdout.strip())
    except FileNotFoundError:
        logger.warning("ffprobe not found — skipping audio duration for %s", audio_path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning("Could not determine audio duration for %s: %s", audio_path, exc)
    return None
