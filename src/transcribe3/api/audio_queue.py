"""Run audio jobs one at a time, in upload order.

Each job spawns a child that loads Whisper and pyannote (several GB) and then
sends every attribution window to the same local LLM. Running uploads side by
side doesn't finish any of them sooner — it splits the GPU and memory between
them and can run the machine out of memory. Uploads land here instead, and one
worker thread works through them.

The queue lives in memory: jobs still waiting or running when the API stops are
lost. delete_interrupted_sessions() removes them on the next start so they don't
sit at "processing" forever.
"""
from __future__ import annotations

import logging
import queue
import shutil
import threading
from pathlib import Path
from typing import Callable

from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import SessionStatus

logger = logging.getLogger(__name__)

_jobs: queue.Queue[Callable[[], None]] = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def _run_jobs() -> None:
    while True:
        job = _jobs.get()
        try:
            job()
        except Exception:
            # Jobs record their own failures on the session; this only keeps one
            # unexpected crash from killing the worker and stalling the queue.
            logger.exception("Audio job raised outside its own error handling")
        finally:
            _jobs.task_done()


def submit(job: Callable[[], None]) -> None:
    """Queue a job behind any already waiting, starting the worker if needed."""
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            # daemon: the API can exit without waiting for the queue to drain.
            _worker = threading.Thread(target=_run_jobs, name="audio-queue", daemon=True)
            _worker.start()
    _jobs.put(job)
    logger.info("Audio job queued (%d waiting, including this one)", _jobs.qsize())


def delete_interrupted_sessions(sessions_dir: Path) -> int:
    """Delete sessions a previous API run left at "processing", audio and all.

    Call only at startup, before any upload can be queued: at that point nothing
    in this process is working on them, so any still "processing" were orphaned
    and will never finish. Returns how many were deleted.
    """
    if not sessions_dir.is_dir():
        return 0
    deleted = 0
    for session_file in sessions_dir.glob("*/session.json"):
        session_dir = session_file.parent
        try:
            session = SessionRepository.load(session_dir.name, sessions_dir)
        except Exception as exc:
            logger.warning("Skipping unreadable session %s: %s", session_dir.name, exc)
            continue
        if session.status != SessionStatus.PROCESSING:
            continue
        shutil.rmtree(session_dir)
        logger.warning(
            "Deleted interrupted session %s (%s)", session_dir.name, session.source_file,
        )
        deleted += 1
    return deleted
