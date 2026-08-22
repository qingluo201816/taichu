"""通用写作助手多阶段上下文快照历史仓储。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import shutil
import threading
from uuid import uuid4

from taichu.application.general_agent.models import GeneralAgentContextSnapshot


_RUN_ID_PATTERN = re.compile(r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_SNAPSHOT_ID_PATTERN = re.compile(r"^context_\d{8}_\d{6}_[a-z0-9]{8}$")


class JsonGeneralAgentContextSnapshotRepository:
    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "general_agent_context_snapshots"
        self._lock = threading.RLock()

    async def save(self, snapshot: GeneralAgentContextSnapshot) -> None:
        await asyncio.to_thread(self._save_sync, snapshot)

    async def list_for_run(self, run_id: str) -> list[GeneralAgentContextSnapshot]:
        return await asyncio.to_thread(self._list_for_run_sync, run_id)

    async def delete_run(self, run_id: str) -> None:
        await asyncio.to_thread(self._delete_run_sync, run_id)

    def _save_sync(self, snapshot: GeneralAgentContextSnapshot) -> None:
        _validate_run_id(snapshot.run_id)
        _validate_snapshot_id(snapshot.snapshot_id)
        with self._lock:
            directory = self._root / snapshot.run_id
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{snapshot.snapshot_id}.json"
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(
                        snapshot.model_dump(mode="json"),
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    def _list_for_run_sync(self, run_id: str) -> list[GeneralAgentContextSnapshot]:
        _validate_run_id(run_id)
        directory = self._root / run_id
        if not directory.exists():
            return []
        snapshots: list[GeneralAgentContextSnapshot] = []
        for path in directory.glob("context_*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            envelope = payload.get("envelope") if isinstance(payload, dict) else None
            if not isinstance(envelope, dict) or "stable_memory" not in envelope:
                continue
            snapshots.append(GeneralAgentContextSnapshot.model_validate(payload))
        return sorted(snapshots, key=lambda item: (item.created_at, item.snapshot_id))

    def _delete_run_sync(self, run_id: str) -> None:
        _validate_run_id(run_id)
        with self._lock:
            directory = (self._root / run_id).resolve()
            root = self._root.resolve()
            if directory.parent != root:
                raise ValueError("上下文快照目录超出允许范围。")
            if directory.exists():
                shutil.rmtree(directory)


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("通用 Agent 运行标识格式不正确。")


def _validate_snapshot_id(snapshot_id: str) -> None:
    if not _SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise ValueError("上下文快照标识格式不正确。")
