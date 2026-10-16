"""Run the audio pipeline in a short-lived child process.

Whisper (MLX or CTranslate2) and pyannote/torch keep several GB resident after a
job even once their objects are freed and caches cleared, so running them inside
the API process pins it at its high-water mark until restart. A spawned child
hands all of it back to the OS when it exits.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from transcribe3.shared.types import TranscriptSegment

_POLL_SECONDS = 1.0


def _exit_if_orphaned(parent_pid: int) -> None:
    """End this child as soon as the API process that started it is gone.

    daemon=True only covers a clean API exit. A hard kill (SIGKILL, crash, OOM)
    reparents the child, which would keep transcribing with several GB resident,
    and macOS has no parent-death signal, so poll for the reparenting instead.
    """
    while True:
        if os.getppid() != parent_pid:
            os._exit(1)
        time.sleep(_POLL_SECONDS)


def _child(
    events: mp.Queue,
    audio_path: Path,
    hf_token: str,
    whisper_model: str,
    backend: str,
    parent_pid: int,
) -> None:
    threading.Thread(target=_exit_if_orphaned, args=(parent_pid,), daemon=True).start()
    from transcribe3.core.audio.pipeline import run_audio_pipeline

    try:
        segments = run_audio_pipeline(
            audio_path, hf_token, whisper_model, backend,
            lambda stage: events.put(("stage", stage)),
        )
    except Exception as exc:
        traceback.print_exc()
        events.put(("error", str(exc)))
        return
    events.put(("result", segments))


def run_audio_pipeline_isolated(
    audio_path: Path,
    hf_token: str,
    whisper_model: str,
    backend: str,
    on_stage: Callable[[str], None] | None = None,
) -> list[TranscriptSegment]:
    """Same contract as core.audio.pipeline.run_audio_pipeline, in a child process."""
    ctx = mp.get_context("spawn")
    events = ctx.Queue()
    # daemon=True: if the API process exits mid-job, the child is terminated
    # rather than left orphaned holding the models.
    proc = ctx.Process(
        target=_child,
        args=(events, audio_path, hf_token, whisper_model, backend, os.getpid()),
        daemon=True,
    )
    proc.start()
    try:
        while True:
            # Sampled before the get: if the child was already dead, everything
            # it sent is in the pipe, so an empty get means it died without a result.
            alive = proc.is_alive()
            try:
                kind, payload = events.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                if alive:
                    continue
                raise RuntimeError(
                    f"audio worker process exited unexpectedly (exit code {proc.exitcode}) — "
                    "it may have run out of memory"
                )
            if kind == "stage":
                if on_stage:
                    on_stage(payload)
            elif kind == "error":
                raise RuntimeError(payload)
            else:
                return payload
    finally:
        if proc.is_alive():
            proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
        events.close()
