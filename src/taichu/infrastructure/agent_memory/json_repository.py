"""基于独立 JSON 记录的通用 Runtime 记忆仓储。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from taichu.application.agent_memory.models import (
    AgentMemoryEntry,
    AgentMemoryKind,
)

_MEMORY_ID_PATTERN = re.compile(r"^memory_\d{8}_\d{6}_[a-z0-9]{8}$")


class JsonAgentMemoryRepository:
    """每条记忆独立原子写入，记录始终是可重建索引的事实源。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "general_agent_memory"

    async def save(self, entry: AgentMemoryEntry) -> AgentMemoryEntry:
        await asyncio.to_thread(self._save_sync, entry)
        return entry

    async def get(self, memory_id: str) -> AgentMemoryEntry | None:
        return await asyncio.to_thread(self._get_sync, memory_id)

    async def query(
        self,
        *,
        conversation_id: str | None = None,
        kinds: tuple[AgentMemoryKind, ...] = (),
        run_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[AgentMemoryEntry]:
        return await asyncio.to_thread(
            self._query_sync,
            conversation_id,
            kinds,
            run_id,
            include_deleted,
        )

    async def delete(
        self,
        memory_id: str,
        *,
        deleted_at: str,
    ) -> AgentMemoryEntry | None:
        entry = await self.get(memory_id)
        if entry is None:
            return None
        deleted = entry.model_copy(
            update={
                "updated_at": deleted_at,
                "deleted_at": deleted_at,
            }
        )
        return await self.save(deleted)

    async def purge_expired(self, *, as_of: str) -> int:
        return await asyncio.to_thread(self._purge_expired_sync, as_of)

    def _save_sync(self, entry: AgentMemoryEntry) -> None:
        _validate_memory_id(entry.memory_id)
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(entry.memory_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(
                    entry.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _get_sync(self, memory_id: str) -> AgentMemoryEntry | None:
        _validate_memory_id(memory_id)
        path = self._path(memory_id)
        if not path.exists():
            return None
        return _load(path)

    def _query_sync(
        self,
        conversation_id: str | None,
        kinds: tuple[AgentMemoryKind, ...],
        run_id: str | None,
        include_deleted: bool,
    ) -> list[AgentMemoryEntry]:
        self._root.mkdir(parents=True, exist_ok=True)
        entries = [_load(path) for path in self._root.glob("*.json")]
        if conversation_id is not None:
            entries = [
                entry
                for entry in entries
                if entry.conversation_id == conversation_id
            ]
        if kinds:
            expected_kinds = set(kinds)
            entries = [entry for entry in entries if entry.kind in expected_kinds]
        if run_id is not None:
            entries = [entry for entry in entries if run_id in entry.run_ids]
        if not include_deleted:
            entries = [entry for entry in entries if entry.deleted_at is None]
        return sorted(
            entries,
            key=lambda entry: (entry.updated_at, entry.memory_id),
            reverse=True,
        )

    def _purge_expired_sync(self, as_of: str) -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        count = 0
        for path in self._root.glob("*.json"):
            entry = _load(path)
            if (
                entry.expires_at is None
                or entry.expires_at > as_of
                or entry.deleted_at is not None
            ):
                continue
            expired = entry.model_copy(
                update={
                    "updated_at": as_of,
                    "deleted_at": as_of,
                }
            )
            self._save_sync(expired)
            count += 1
        return count

    def _path(self, memory_id: str) -> Path:
        return self._root / f"{memory_id}.json"


class AgentMemoryStoreError(ValueError):
    """运行记忆文件损坏或标识不符合稳定契约。"""


def _load(path: Path) -> AgentMemoryEntry:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AgentMemoryStoreError(f"运行记忆文件无法读取：{path.name}") from error
    if not isinstance(payload, dict):
        raise AgentMemoryStoreError(f"运行记忆记录必须是对象：{path.name}")
    try:
        return AgentMemoryEntry.model_validate(payload)
    except ValueError as error:
        raise AgentMemoryStoreError(f"运行记忆记录校验失败：{path.name}") from error


def _validate_memory_id(memory_id: str) -> None:
    if not _MEMORY_ID_PATTERN.fullmatch(memory_id):
        raise AgentMemoryStoreError("运行记忆 ID 格式不正确。")
