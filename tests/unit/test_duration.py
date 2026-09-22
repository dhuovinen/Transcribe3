from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from transcribe3.core.audio.duration import probe_audio_duration_seconds


def test_probe_audio_duration_returns_seconds_on_success():
    fake_result = MagicMock(stdout="723.710000\n")
    with patch("subprocess.run", return_value=fake_result) as mock_run:
        duration = probe_audio_duration_seconds(Path("recording.m4a"))

    assert duration == 723.71
    assert mock_run.call_args.args[0][0] == "ffprobe"


def test_probe_audio_duration_returns_none_when_ffprobe_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        duration = probe_audio_duration_seconds(Path("recording.m4a"))

    assert duration is None


def test_probe_audio_duration_returns_none_on_ffprobe_error():
    error = subprocess.CalledProcessError(1, ["ffprobe"], stderr="Invalid data")
    with patch("subprocess.run", side_effect=error):
        duration = probe_audio_duration_seconds(Path("corrupt.m4a"))

    assert duration is None


def test_probe_audio_duration_returns_none_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)):
        duration = probe_audio_duration_seconds(Path("recording.m4a"))

    assert duration is None


def test_probe_audio_duration_returns_none_on_unparseable_output():
    fake_result = MagicMock(stdout="not-a-number\n")
    with patch("subprocess.run", return_value=fake_result):
        duration = probe_audio_duration_seconds(Path("recording.m4a"))

    assert duration is None
