"""按中间产物 ID 保存可审计 JSON 草稿。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re

from taichu.application.artifacts.models import IntermediateArtifactRecord

_ARTIFACT_ID = re.compile(r"^artifact_[a-f0-9]{32}$")


class JsonIntermediateArtifactRepository:
    """把专业子 Agent 输出保存为派生层中间态。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "capability_artifacts"

    async def save(self, record: IntermediateArtifactRecord) -> None:
        await asyncio.to_thread(self._save_sync, record)

    async def get(self, artifact_id: str) -> IntermediateArtifactRecord | None:
        return await asyncio.to_thread(self._get_sync, artifact_id)

    def _save_sync(self, record: IntermediateArtifactRecord) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(record.artifact_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _get_sync(self, artifact_id: str) -> IntermediateArtifactRecord | None:
        path = self._path(artifact_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return IntermediateArtifactRecord.model_validate(payload)

    def _path(self, artifact_id: str) -> Path:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("中间产物 ID 格式不正确。")
        return self._root / f"{artifact_id}.json"
