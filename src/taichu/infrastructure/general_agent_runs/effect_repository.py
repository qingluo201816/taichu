"""写 Tool 副作用的追加式、可落盘对账日志。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

from taichu.application.general_agent.recovery import EffectRecord

_RUN_ID_PATTERN = re.compile(r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_EFFECT_ID_PATTERN = re.compile(r"^effect_[a-f0-9]{32}$")


class JsonGeneralAgentEffectRepository:
    """每次状态变化追加一行，崩溃后保留最后一条完整证据。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "general_agent_graph_checkpoints"
        self._lock = RLock()

    async def append(self, record: EffectRecord) -> None:
        await asyncio.to_thread(self._append_sync, record)

    async def latest(self, effect_id: str) -> EffectRecord | None:
        return await asyncio.to_thread(self._latest_sync, effect_id)

    async def list_effects(self, run_id: str) -> list[EffectRecord]:
        return await asyncio.to_thread(self._list_sync, run_id)

    async def delete_run(self, run_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, run_id)

    def _append_sync(self, record: EffectRecord) -> None:
        _validate_run_id(record.run_id)
        path = self._path(record.run_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (
                json.dumps(
                    record.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            with path.open("a", encoding="utf-8", newline="") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())

    def _latest_sync(self, effect_id: str) -> EffectRecord | None:
        if not _EFFECT_ID_PATTERN.fullmatch(effect_id):
            raise GeneralAgentEffectStoreError("副作用标识格式不正确。")
        latest: EffectRecord | None = None
        with self._lock:
            if not self._root.exists():
                return None
            for path in self._root.glob("general_run_*/effects.jsonl"):
                for record in _read_records(path):
                    if record.effect_id == effect_id:
                        latest = record
        return latest

    def _list_sync(self, run_id: str) -> list[EffectRecord]:
        _validate_run_id(run_id)
        path = self._path(run_id)
        with self._lock:
            return _read_records(path) if path.exists() else []

    def _delete_sync(self, run_id: str) -> bool:
        _validate_run_id(run_id)
        path = self._path(run_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True

    def _path(self, run_id: str) -> Path:
        return self._root / run_id / "effects.jsonl"


class GeneralAgentEffectStoreError(ValueError):
    """副作用日志损坏或标识不符合契约。"""


def _read_records(path: Path) -> list[EffectRecord]:
    records: list[EffectRecord] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            payload: Any = json.loads(line)
            records.append(EffectRecord.model_validate(payload))
        except (json.JSONDecodeError, ValueError) as error:
            raise GeneralAgentEffectStoreError(
                f"副作用日志损坏：{path.name} 第 {line_number} 行；{error}"
            ) from error
    return records


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise GeneralAgentEffectStoreError("通用 Agent 运行 ID 格式不正确。")
