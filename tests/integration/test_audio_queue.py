import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from transcribe3.api import audio_queue
from transcribe3.api.main import app
from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import SessionStatus, TranscriptSession


def _save_session(sessions_dir: Path, status: SessionStatus, stage: str | None) -> TranscriptSession:
    session = TranscriptSession(
        source_file="talk.mp3", audio_file="talk.mp3", status=status, processing_stage=stage,
    )
    SessionRepository.save(session, sessions_dir)
    return session


def test_jobs_run_one_at_a_time_in_upload_order():
    lock = threading.Lock()
    running = 0
    peak = 0
    order: list[int] = []

    def job(n: int) -> None:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
            order.append(n)

    for n in range(4):
        audio_queue.submit(lambda n=n: job(n))
    audio_queue._jobs.join()

    assert peak == 1
    assert order == [0, 1, 2, 3]


def test_a_crashing_job_does_not_stall_the_queue():
    ran: list[str] = []

    def boom() -> None:
        raise RuntimeError("unexpected")

    audio_queue.submit(boom)
    audio_queue.submit(lambda: ran.append("next"))
    audio_queue._jobs.join()

    assert ran == ["next"]


def test_upload_queues_the_job_instead_of_running_it(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE3_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIBE3_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("HF_TOKEN", "hf_test")

    with patch("transcribe3.api.audio_queue.submit") as submit:
        response = TestClient(app).post(
            "/sessions/upload-audio",
            files={"file": ("talk.mp3", b"not really audio", "audio/mpeg")},
        )

    assert response.status_code == 200
    assert response.json()["processing_stage"] == "Queued…"
    submit.assert_called_once()


def test_startup_deletes_sessions_a_previous_run_left_processing(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE3_SESSIONS_DIR", str(tmp_path))
    stuck = _save_session(tmp_path, SessionStatus.PROCESSING, "Transcribing audio…")
    (tmp_path / stuck.session_id / "talk.mp3").write_bytes(b"audio")
    done = _save_session(tmp_path, SessionStatus.COMPLETE, None)
    failed = _save_session(tmp_path, SessionStatus.ERROR, None)
    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    (corrupt_dir / "session.json").write_text("{not json")

    with TestClient(app):  # entering runs the lifespan startup
        pass

    assert not (tmp_path / stuck.session_id).exists()
    assert SessionRepository.load(done.session_id, tmp_path).status == SessionStatus.COMPLETE
    assert SessionRepository.load(failed.session_id, tmp_path).status == SessionStatus.ERROR
    assert (corrupt_dir / "session.json").exists()


def test_deleting_interrupted_sessions_tolerates_a_missing_sessions_dir(tmp_path):
    assert audio_queue.delete_interrupted_sessions(tmp_path / "nope") == 0
