"""MVP settings preference use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models import EditorPreferences


class SettingsPreferenceService:
    """Manage editor preferences without real LLM configuration."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def get_preferences(self) -> EditorPreferences:
        """Read current settings preferences."""
        return EditorPreferences.model_validate(await self._storage.read_preferences())

    async def patch_preferences(self, updates: dict[str, Any]) -> EditorPreferences:
        """Patch editor display preferences."""
        current = await self.get_preferences()
        payload = current.model_dump(mode="json")
        for key in ("font_size", "font_style", "editor_background"):
            if key in updates:
                payload[key] = updates[key]
        payload["updated_at"] = _now_iso()
        preferences = EditorPreferences.model_validate(payload)
        await self._storage.write_preferences(preferences.model_dump(mode="json"))
        return preferences


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
