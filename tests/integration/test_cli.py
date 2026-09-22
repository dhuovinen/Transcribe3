from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from transcribe3.cli import app

runner = CliRunner()

SAMPLE_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.txt"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_mock_complete(segments=None):
    """Return a mock complete() that echoes back segment IDs with high confidence."""

    def fake_complete(prompt, model):
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
def filler_fixture(tmp_path):
    """A transcript with known filler words and a false start."""
    content = (
        "ALEX: Um, I think the data is clear.\n"
        "MORGAN: Uh, well, I — I would agree with that.\n"
    )
    p = tmp_path / "filler.txt"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_clean_produces_json_output(tmp_path):
    """clean on sample.txt exits 0, writes a valid JSON session file."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "json"],
        )
    assert result.exit_code == 0, result.output
    json_files = list(tmp_path.glob("*/output.json"))
    assert len(json_files) == 1, f"Expected 1 output.json, found: {json_files}"
    data = json.loads(json_files[0].read_text())
    assert "segments" in data
    assert "session_id" in data


def test_clean_txt_format(tmp_path):
    """clean --format txt writes a .txt file with 'Name: text' lines."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "txt"],
        )
    assert result.exit_code == 0, result.output
    txt_files = list(tmp_path.glob("*/output.txt"))
    assert len(txt_files) == 1, f"Expected 1 output.txt, found: {txt_files}"
    content = txt_files[0].read_text()
    # At least one line must match "Name: text"
    assert re.search(r"[A-Za-z][^:]+:\s+\S", content), f"No speaker lines found:\n{content}"


def test_clean_srt_format(tmp_path):
    """clean --format srt writes a valid SRT file (contains --> arrows)."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "srt"],
        )
    assert result.exit_code == 0, result.output
    srt_files = list(tmp_path.glob("*/output.srt"))
    assert len(srt_files) == 1
    content = srt_files[0].read_text()
    assert "-->" in content


def test_clean_verbatim_preserves_filler_words(tmp_path, filler_fixture):
    """--verbatim overrides --filler-words strip; filler words remain."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        result = runner.invoke(
            app,
            [
                "clean",
                str(filler_fixture),
                "--output-dir",
                str(tmp_path),
                "--format",
                "json",
                "--verbatim",
                "--filler-words",
                "strip",
            ],
        )
    assert result.exit_code == 0, result.output
    json_files = list(tmp_path.glob("*/output.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    all_text = " ".join(s["text"] for s in data["segments"])
    # verbatim mode must preserve filler words despite --filler-words strip
    assert "um" in all_text.lower() or "uh" in all_text.lower(), (
        f"Expected filler words preserved in verbatim mode; got: {all_text}"
    )


def test_clean_strips_filler_words(tmp_path, filler_fixture):
    """--filler-words strip removes 'um' and 'uh' from output text."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        result = runner.invoke(
            app,
            [
                "clean",
                str(filler_fixture),
                "--output-dir",
                str(tmp_path),
                "--format",
                "json",
                "--filler-words",
                "strip",
            ],
        )
    assert result.exit_code == 0, result.output
    json_files = list(tmp_path.glob("*/output.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    all_text = " ".join(s["text"] for s in data["segments"]).lower()
    # Strip should remove standalone 'um' and 'uh'
    assert not re.search(r"\bum\b", all_text), f"'um' still present after strip: {all_text}"
    assert not re.search(r"\buh\b", all_text), f"'uh' still present after strip: {all_text}"


def test_clean_dry_run_writes_nothing(tmp_path):
    """--dry-run prints planned paths and creates no session directory."""
    result = runner.invoke(
        app,
        ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    # Output should mention something about the planned path
    assert "dry" in result.output.lower() or str(tmp_path) in result.output or "session" in result.output.lower()
    # No sub-directories should have been created
    subdirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert subdirs == [], f"dry-run should not create directories; found: {subdirs}"


def test_clean_missing_file_exits_1():
    """Passing a non-existent file exits with code 1."""
    result = runner.invoke(app, ["clean", "/nonexistent/file.txt"])
    assert result.exit_code == 1


def test_clean_unsupported_format_exits_1(tmp_path):
    """Passing --format docx exits with code 1 (unsupported format)."""
    result = runner.invoke(
        app,
        ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "docx"],
    )
    assert result.exit_code != 0


def test_sessions_list_empty(tmp_path):
    """sessions list on an empty dir exits 0 and mentions no sessions."""
    empty_dir = tmp_path / "empty_sessions"
    result = runner.invoke(app, ["sessions", "list", "--sessions-dir", str(empty_dir)])
    assert result.exit_code == 0, result.output
    # Output should convey emptiness: empty JSON array or "no sessions" message
    output = result.output.strip()
    assert output == "[]" or "no sessions" in output.lower() or output == ""


def test_sessions_list_after_clean(tmp_path):
    """sessions list --json after clean shows the newly created session."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        clean_result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "json"],
        )
    assert clean_result.exit_code == 0, clean_result.output

    list_result = runner.invoke(
        app,
        ["sessions", "list", "--sessions-dir", str(tmp_path), "--json"],
    )
    assert list_result.exit_code == 0, list_result.output
    sessions = json.loads(list_result.output)
    assert isinstance(sessions, list)
    assert len(sessions) == 1
    assert "session_id" in sessions[0]


def test_sessions_show(tmp_path):
    """sessions show <id> exits 0 after a clean has been run."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        clean_result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "json"],
        )
    assert clean_result.exit_code == 0, clean_result.output

    # Discover created session id from the session directory
    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(session_dirs) == 1
    session_id = session_dirs[0].name

    show_result = runner.invoke(
        app,
        ["sessions", "show", session_id, "--sessions-dir", str(tmp_path)],
    )
    assert show_result.exit_code == 0, show_result.output


def test_export_command(tmp_path):
    """export <id> --format srt creates an SRT file for an existing session."""
    with patch(
        "transcribe3.core.llm.client.OllamaClient.complete",
        side_effect=make_mock_complete(),
    ):
        clean_result = runner.invoke(
            app,
            ["clean", str(SAMPLE_FIXTURE), "--output-dir", str(tmp_path), "--format", "json"],
        )
    assert clean_result.exit_code == 0, clean_result.output

    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(session_dirs) == 1
    session_id = session_dirs[0].name

    export_result = runner.invoke(
        app,
        ["export", session_id, "--format", "srt", "--output-dir", str(tmp_path)],
    )
    assert export_result.exit_code == 0, export_result.output
    srt_files = list(tmp_path.glob("*/output.srt"))
    assert len(srt_files) == 1, f"Expected output.srt; found: {list(tmp_path.glob('*/*'))}"
    assert "-->" in srt_files[0].read_text()
