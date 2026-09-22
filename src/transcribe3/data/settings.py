from __future__ import annotations

import json
from pathlib import Path

from transcribe3.shared.constants import OLLAMA_BASE_URL, OLMX_BASE_URL
from transcribe3.shared.types import AppSettings


class SettingsRepository:
    _FILENAME = "settings.json"

    @staticmethod
    def load(sessions_dir: Path) -> AppSettings:
        path = sessions_dir / SettingsRepository._FILENAME
        if not path.exists():
            return AppSettings()
        try:
            raw = json.loads(path.read_text())
            raw = SettingsRepository._migrate(raw)
            return AppSettings.model_validate(raw)
        except Exception:
            return AppSettings()

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
    def save(settings: AppSettings, sessions_dir: Path) -> None:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / SettingsRepository._FILENAME
        path.write_text(json.dumps(settings.model_dump(), indent=2))
