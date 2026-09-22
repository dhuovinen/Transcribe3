from __future__ import annotations

import json

from transcribe3.data.settings import SettingsRepository
from transcribe3.shared.types import AppSettings


def test_load_with_no_files_returns_defaults(tmp_path):
    config_dir = tmp_path / "config"
    sessions_dir = tmp_path / "sessions"

    settings = SettingsRepository.load(config_dir, sessions_dir)

    assert settings == AppSettings()


def test_load_migrates_legacy_settings_from_sessions_dir(tmp_path):
    config_dir = tmp_path / "config"
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    legacy_path = sessions_dir / "settings.json"
    legacy_path.write_text(json.dumps({"default_model": "legacy-model"}))

    settings = SettingsRepository.load(config_dir, sessions_dir)

    assert settings.default_model == "legacy-model"
    # The old file is moved, not copied, so there's exactly one file to edit.
    assert not legacy_path.exists()
    assert (config_dir / "settings.json").exists()


def test_load_prefers_config_dir_over_legacy_location(tmp_path):
    config_dir = tmp_path / "config"
    sessions_dir = tmp_path / "sessions"
    config_dir.mkdir()
    sessions_dir.mkdir()
    (config_dir / "settings.json").write_text(json.dumps({"default_model": "current-model"}))
    (sessions_dir / "settings.json").write_text(json.dumps({"default_model": "stale-model"}))

    settings = SettingsRepository.load(config_dir, sessions_dir)

    assert settings.default_model == "current-model"
    # The legacy file is left alone once the new location already has one.
    assert (sessions_dir / "settings.json").exists()


def test_save_writes_to_config_dir(tmp_path):
    config_dir = tmp_path / "config"

    SettingsRepository.save(AppSettings(default_model="saved-model"), config_dir)

    saved = json.loads((config_dir / "settings.json").read_text())
    assert saved["default_model"] == "saved-model"


def test_default_audio_processing_settings():
    settings = AppSettings()

    assert settings.default_transcription_backend == "whisperx"
    assert settings.default_whisper_model == "base"
