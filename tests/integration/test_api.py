from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from transcribe3.api.main import DEFAULT_CORS_ORIGINS, app, get_cors_origins
from transcribe3.core.llm.client import OllamaClient
from transcribe3.data.session import SessionRepository
from transcribe3.shared.types import TranscriptSession

SAMPLE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.txt"


# ---------------------------------------------------------------------------
# Mock helper (mirrors the CLI helper)
# ---------------------------------------------------------------------------


def make_mock_complete():
    def fake_complete(prompt: str, model: str) -> str:
        ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        speakers = re.findall(r'"speaker":\s*"([^"]+)"', prompt)
        return json.dumps(
            [{"id": i, "speaker": s, "confidence": 0.92} for i, s in zip(ids, speakers)]
        )

    return fake_complete


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sessions_client(tmp_path, monkeypatch):
    """TestClient with TRANSCRIBE3_SESSIONS_DIR and TRANSCRIBE3_CONFIG_DIR both
    pointed at tmp_path — tests don't care that they're separate directories in
    production, only that settings.json ends up somewhere the test can see."""
    monkeypatch.setenv("TRANSCRIBE3_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIBE3_CONFIG_DIR", str(tmp_path))
    # Re-import app so dependencies pick up the new env var
    from transcribe3.api import dependencies

    def overridden_sessions_dir() -> Path:
        return tmp_path

    app.dependency_overrides[dependencies.get_sessions_dir] = overridden_sessions_dir
    app.dependency_overrides[dependencies.get_config_dir] = overridden_sessions_dir
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()


def _upload_sample(client: TestClient) -> dict:
    """Helper: POST /sessions with sample.txt, return parsed response JSON."""
    with open(SAMPLE_FIXTURE, "rb") as f:
        with patch(
            "transcribe3.core.llm.client.OllamaClient.complete",
            side_effect=make_mock_complete(),
        ):
            resp = client.post(
                "/sessions",
                files={"file": ("sample.txt", f, "text/plain")},
            )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_audio_session(sessions_dir: Path, name: str = "recording.m4a") -> TranscriptSession:
    session = TranscriptSession(source_file=name, audio_file=name)
    session_dir = sessions_dir / session.session_id
    session_dir.mkdir(parents=True)
    (session_dir / name).write_bytes(b"a small but real recording payload")
    SessionRepository.save(session, sessions_dir)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_check(sessions_client):
    resp = sessions_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_cors_origins_default_to_localhost():
    assert get_cors_origins("") == list(DEFAULT_CORS_ORIGINS)


def test_cors_origins_accept_explicit_lan_origins():
    assert get_cors_origins("http://192.168.1.50:3015, https://transcribe3.local") == [
        "http://192.168.1.50:3015",
        "https://transcribe3.local",
    ]


def test_cors_origins_reject_wildcard():
    with pytest.raises(ValueError, match="must list explicit origins"):
        get_cors_origins("*")


def test_upload_transcript(sessions_client):
    data = _upload_sample(sessions_client)
    assert "session_id" in data
    assert "segments" in data
    assert len(data["segments"]) > 0


def test_upload_unsupported_format(sessions_client, tmp_path):
    fake_docx = tmp_path / "doc.docx"
    fake_docx.write_bytes(b"PK fake docx content")
    with open(fake_docx, "rb") as f:
        resp = sessions_client.post(
            "/sessions",
            files={"file": ("doc.docx", f, "application/octet-stream")},
        )
    assert resp.status_code == 422


def test_get_session(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]

    resp = sessions_client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id


def test_get_session_not_found(sessions_client):
    resp = sessions_client.get("/sessions/nonexistent-id-xyz")
    assert resp.status_code == 404


def test_list_sessions(sessions_client):
    # Upload two sessions
    _upload_sample(sessions_client)
    _upload_sample(sessions_client)

    resp = sessions_client.get("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2


def test_update_speaker_map(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]

    # Collect the actual anonymous speaker IDs from the uploaded session
    speakers_in_session = {seg["speaker"]["anonymous_id"] for seg in data["segments"]}
    speaker_map = {sid: sid.replace("_", " ").title() for sid in speakers_in_session}

    resp = sessions_client.put(
        f"/sessions/{session_id}/speakers",
        json={"speaker_map": speaker_map},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["speaker_map"] == speaker_map


def test_update_segment_speaker(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]
    first_seg_id = data["segments"][0]["id"]

    resp = sessions_client.put(
        f"/sessions/{session_id}/segments/{first_seg_id}/speaker",
        json={"speaker": "Alice", "confidence": 0.99},
    )
    assert resp.status_code == 200
    body = resp.json()
    updated_seg = next(s for s in body["segments"] if s["id"] == first_seg_id)
    assert updated_seg["speaker"]["resolved_name"] == "Alice"
    assert abs(updated_seg["confidence"] - 0.99) < 1e-6


def test_update_segment_text_preserves_the_first_original(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]
    segment = data["segments"][0]

    first_edit = sessions_client.put(
        f"/sessions/{session_id}/segments/{segment['id']}/text",
        json={"text": "Edited transcript text."},
    )
    assert first_edit.status_code == 200
    first_updated = first_edit.json()["segments"][0]
    assert first_updated["text"] == "Edited transcript text."
    assert first_updated["original_text"] == segment["text"]

    second_edit = sessions_client.put(
        f"/sessions/{session_id}/segments/{segment['id']}/text",
        json={"text": "Final edited transcript text."},
    )
    assert second_edit.status_code == 200
    second_updated = second_edit.json()["segments"][0]
    assert second_updated["text"] == "Final edited transcript text."
    assert second_updated["original_text"] == segment["text"]


def test_export_json(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]

    resp = sessions_client.get(f"/sessions/{session_id}/export?format=json")
    assert resp.status_code == 200
    assert "Content-Disposition" in resp.headers


def test_export_srt(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]

    resp = sessions_client.get(f"/sessions/{session_id}/export?format=srt")
    assert resp.status_code == 200
    assert "-->" in resp.text


def test_delete_session(sessions_client):
    data = _upload_sample(sessions_client)
    session_id = data["session_id"]

    del_resp = sessions_client.delete(f"/sessions/{session_id}")
    assert del_resp.status_code == 200

    get_resp = sessions_client.get(f"/sessions/{session_id}")
    assert get_resp.status_code == 404


def test_get_models(sessions_client):
    with patch.object(OllamaClient, "list_models", return_value=["llama3"]):
        resp = sessions_client.get("/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "llama3" in body.get("models", [])


def test_archive_copy_offload_and_restore(sessions_client, tmp_path):
    sessions_dir = tmp_path
    archive_dir = tmp_path.parent / f"{tmp_path.name}-external-archive"
    session = _create_audio_session(sessions_dir)
    local_audio = sessions_dir / session.session_id / "recording.m4a"

    configure = sessions_client.put("/archive/configuration", json={"archive_dir": str(archive_dir)})
    assert configure.status_code == 200, configure.text
    assert configure.json()["archive_connected"] is True

    archive_copy = sessions_client.post(
        f"/archive/{session.session_id}/archive", json={"remove_local": False}
    )
    assert archive_copy.status_code == 200, archive_copy.text
    assert archive_copy.json()["local_available"] is True
    assert archive_copy.json()["archive_available"] is True
    archived_audio = archive_dir / "recordings" / session.session_id / "recording.m4a"
    assert archived_audio.read_bytes() == local_audio.read_bytes()

    delete_local = sessions_client.delete(f"/archive/{session.session_id}/local-copy")
    assert delete_local.status_code == 200, delete_local.text
    assert delete_local.json()["local_available"] is False
    assert local_audio.exists() is False

    restore = sessions_client.post(f"/archive/{session.session_id}/restore")
    assert restore.status_code == 200, restore.text
    assert restore.json()["local_available"] is True
    assert local_audio.read_bytes() == archived_audio.read_bytes()

    offload = sessions_client.post(
        f"/archive/{session.session_id}/archive", json={"remove_local": True}
    )
    assert offload.status_code == 200, offload.text
    assert offload.json()["archive_available"] is True
    assert offload.json()["local_available"] is False


def test_local_audio_delete_requires_verified_archive(sessions_client, tmp_path):
    session = _create_audio_session(tmp_path)
    sessions_client.put(
        "/archive/configuration",
        json={"archive_dir": str(tmp_path.parent / f"{tmp_path.name}-external")},
    )

    response = sessions_client.delete(f"/archive/{session.session_id}/local-copy")
    assert response.status_code == 422
    assert "verified archive copy" in response.json()["detail"]["error"]


def test_archive_configuration_rejects_local_sessions_folder(sessions_client, tmp_path):
    response = sessions_client.put("/archive/configuration", json={"archive_dir": str(tmp_path)})
    assert response.status_code == 409
    assert "separate from the local sessions folder" in response.json()["detail"]["error"]


# ---------------------------------------------------------------------------
# Optional pipeline stages + per-stage timings
# ---------------------------------------------------------------------------


def _write_settings(sessions_dir: Path, **overrides) -> None:
    from transcribe3.data.settings import SettingsRepository
    from transcribe3.shared.types import AppSettings

    SettingsRepository.save(AppSettings(**overrides), sessions_dir)


def test_run_records_timing_for_each_stage(sessions_client):
    data = _upload_sample(sessions_client)
    stages = [t["stage"] for t in data["stage_timings"]]

    assert "Cleaning transcript…" in stages
    assert "Validating speaker attribution with LLM…" in stages
    assert all(t["seconds"] >= 0 for t in data["stage_timings"])
    assert data["processing_params"]["cleaning_enabled"] is True
    assert data["processing_params"]["attribution_enabled"] is True


def test_attribution_can_be_switched_off(sessions_client, tmp_path):
    """With attribution off the LLM must not be called at all — that is the point."""
    _write_settings(tmp_path, run_attribution=False)

    with open(SAMPLE_FIXTURE, "rb") as f:
        with patch("transcribe3.core.llm.client.OllamaClient.complete") as mock_complete:
            resp = sessions_client.post("/sessions", files={"file": ("sample.txt", f, "text/plain")})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    mock_complete.assert_not_called()

    stages = [t["stage"] for t in data["stage_timings"]]
    assert "Validating speaker attribution with LLM…" not in stages
    assert "Cleaning transcript…" in stages
    assert data["processing_params"]["attribution_enabled"] is False
    assert "turned off in Settings" in data["warning"]


def test_cleaning_can_be_switched_off(sessions_client, tmp_path):
    _write_settings(tmp_path, run_cleaning=False)

    with open(SAMPLE_FIXTURE, "rb") as f:
        with patch(
            "transcribe3.core.llm.client.OllamaClient.complete",
            side_effect=make_mock_complete(),
        ):
            resp = sessions_client.post("/sessions", files={"file": ("sample.txt", f, "text/plain")})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    stages = [t["stage"] for t in data["stage_timings"]]
    assert "Cleaning transcript…" not in stages
    assert "Validating speaker attribution with LLM…" in stages
    assert data["processing_params"]["cleaning_enabled"] is False


def test_session_list_carries_stage_timings(sessions_client):
    _upload_sample(sessions_client)
    summary = sessions_client.get("/sessions").json()[0]

    assert [t["stage"] for t in summary["stage_timings"]]


def _fake_pipeline_segments():
    from transcribe3.shared.types import SpeakerLabel, TranscriptSegment

    return [
        TranscriptSegment(
            start_time=float(i), end_time=float(i) + 1.0,
            speaker=SpeakerLabel(anonymous_id=f"SPEAKER_{i % 2:02d}"),
            text=f"Segment number {i}, um, with some content.", confidence=0.8,
        )
        for i in range(4)
    ]


def _run_audio_worker(tmp_path: Path, **settings_overrides):
    """Drive the audio background worker with the pipeline stubbed out."""
    from transcribe3.api.routes.audio import _process_audio_session
    from transcribe3.data.settings import SettingsRepository
    from transcribe3.shared.types import AppSettings

    SettingsRepository.save(AppSettings(**settings_overrides), tmp_path)
    session = _create_audio_session(tmp_path)
    audio_path = tmp_path / session.session_id / session.audio_file

    def fake_pipeline(path, token, model, backend, advance_stage):
        advance_stage("Transcribing audio…")
        advance_stage("Identifying speakers…")
        return _fake_pipeline_segments()

    with patch("transcribe3.core.audio.pipeline.run_audio_pipeline", side_effect=fake_pipeline):
        with patch(
            "transcribe3.core.llm.client.OllamaClient.complete",
            side_effect=make_mock_complete(),
        ):
            _process_audio_session(
                session, audio_path, "base", "whisperx", "hf_token", tmp_path, tmp_path,
            )

    return SessionRepository.load(session.session_id, tmp_path)


def test_audio_run_records_every_stage(tmp_path):
    session = _run_audio_worker(tmp_path)
    stages = [t.stage for t in session.stage_timings]

    assert stages == [
        "Transcribing audio…",
        "Identifying speakers…",
        "Cleaning transcript…",
        "Validating speaker attribution with LLM…",
    ]
    assert session.status.value == "complete"
    assert session.warning is None


def test_audio_run_with_attribution_off_skips_the_slow_stage(tmp_path):
    session = _run_audio_worker(tmp_path, run_attribution=False)
    stages = [t.stage for t in session.stage_timings]

    assert "Validating speaker attribution with LLM…" not in stages
    assert stages[-1] == "Cleaning transcript…"
    assert session.status.value == "complete"
    assert session.processing_params.attribution_enabled is False
    assert "turned off in Settings" in session.warning
    # The diarization labels must survive untouched — that is what makes skipping usable.
    assert [s.speaker.anonymous_id for s in session.segments] == [
        "SPEAKER_00", "SPEAKER_01", "SPEAKER_00", "SPEAKER_01",
    ]
