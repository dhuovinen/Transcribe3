from pathlib import Path

import pytest

import multiprocessing as mp

from transcribe3.api.audio_worker import _exit_if_orphaned, run_audio_pipeline_isolated


def test_child_process_forwards_stages_and_errors(tmp_path: Path):
    stages: list[str] = []

    with pytest.raises(RuntimeError, match="Unknown transcription backend"):
        run_audio_pipeline_isolated(
            tmp_path / "missing.wav", "hf_token", "base", "no-such-backend", stages.append,
        )

    assert stages == ["Transcribing audio…"]


def test_child_exits_once_its_parent_is_gone():
    # A parent pid that can never match stands in for the API being hard-killed.
    proc = mp.get_context("spawn").Process(target=_exit_if_orphaned, args=(-1,))
    proc.start()
    proc.join(timeout=10)

    assert proc.exitcode == 1
