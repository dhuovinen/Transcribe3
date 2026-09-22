from __future__ import annotations

import json
import logging
from pathlib import Path

from transcribe3.shared.constants import OLLAMA_BASE_URL, OLMX_BASE_URL
from transcribe3.shared.types import AppSettings

logger = logging.getLogger(__name__)


class SettingsRepository:
    _FILENAME = "settings.json"

    @staticmethod
    def load(config_dir: Path, legacy_sessions_dir: Path | None = None) -> AppSettings:
        """Load app settings from `config_dir/settings.json`.

        `legacy_sessions_dir`, if given, is where settings.json used to live
        (inside the sessions directory, before the two were split apart). If
        the new location is empty but a file is still sitting in the old one,
        move it over once so existing installs upgrade without losing their
        configured providers — see `_migrate_legacy_location`.
        """
        path = config_dir / SettingsRepository._FILENAME
        if not path.exists() and legacy_sessions_dir is not None:
            SettingsRepository._migrate_legacy_location(config_dir, legacy_sessions_dir)
        if not path.exists():
            return AppSettings()
        try:
            raw = json.loads(path.read_text())
            raw = SettingsRepository._migrate(raw)
            return AppSettings.model_validate(raw)
        except Exception as exc:
            logger.warning(
                "Ignoring unreadable settings file %s, falling back to defaults: %s",
                path, exc,
            )
            return AppSettings()

    @staticmethod
    def _migrate_legacy_location(config_dir: Path, legacy_sessions_dir: Path) -> None:
        """One-time upgrade: settings.json used to live in the sessions directory.

        Moves it to config_dir so there's exactly one file to edit — leaving the
        old copy in place would silently stop taking effect, which is worse than
        not having it at all.
        """
        legacy_path = legacy_sessions_dir / SettingsRepository._FILENAME
        if not legacy_path.is_file():
            return
        config_dir.mkdir(parents=True, exist_ok=True)
        new_path = config_dir / SettingsRepository._FILENAME
        try:
            legacy_path.replace(new_path)
            logger.info("Moved settings.json from %s to %s", legacy_path, new_path)
        except OSError as exc:
            logger.warning(
                "Could not move settings.json from %s to %s (%s) — copying instead",
                legacy_path, new_path, exc,
            )
            new_path.write_text(legacy_path.read_text())

    @staticmethod
    def _migrate(raw: dict) -> dict:
        """Upgrade a pre-registry settings.json (single ollama_base_url/olmx_base_url
        pair + llm_backend) to the llm_providers list, preserving any custom base URLs
        the user had configured rather than silently dropping them."""
        if "llm_providers" in raw or not isinstance(raw, dict):
            return raw
        if "ollama_base_url" not in raw and "olmx_base_url" not in raw and "llm_backend" not in raw:
            return raw

        raw = dict(raw)
        raw["llm_providers"] = [
            {
                "id": "ollama",
                "label": "Ollama",
                "protocol": "ollama",
                "base_url": raw.pop("ollama_base_url", OLLAMA_BASE_URL),
                "enabled": True,
            },
            {
                "id": "olmx",
                "label": "olmx (OpenAI-compatible)",
                "protocol": "openai_compatible",
                "base_url": raw.pop("olmx_base_url", OLMX_BASE_URL),
                "enabled": True,
            },
        ]
        raw["default_provider_id"] = raw.pop("llm_backend", "ollama")
        return raw

    @staticmethod
    def save(settings: AppSettings, config_dir: Path) -> None:
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / SettingsRepository._FILENAME
        path.write_text(json.dumps(settings.model_dump(), indent=2))
