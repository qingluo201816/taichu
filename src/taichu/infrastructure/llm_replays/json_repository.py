"""逐调用原子保存 LLM 回放资产。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import threading
from uuid import uuid4

from taichu.application.models.llm_replay import LLMCallReplayRecord


_CALL_ID_PATTERN = re.compile(r"^llm-call-[a-f0-9]{32}$")


class JsonLLMCallReplayRepository:
    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "llm_call_replays"
        self._lock = threading.RLock()

    async def save(self, record: LLMCallReplayRecord) -> None:
        await asyncio.to_thread(self._save_sync, record)

    async def get(self, call_id: str) -> LLMCallReplayRecord | None:
        return await asyncio.to_thread(self._get_sync, call_id)

    async def list_for_run(self, run_id: str) -> list[LLMCallReplayRecord]:
        return await asyncio.to_thread(self._list_for_run_sync, run_id)

    async def delete_run(self, run_id: str) -> None:
        await asyncio.to_thread(self._delete_run_sync, run_id)

    def _save_sync(self, record: LLMCallReplayRecord) -> None:
        _validate_call_id(record.call_id)
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._root / f"{record.call_id}.json"
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(
                        record.model_dump(mode="json"), ensure_ascii=False, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    def _get_sync(self, call_id: str) -> LLMCallReplayRecord | None:
        _validate_call_id(call_id)
        path = self._root / f"{call_id}.json"
        if not path.exists():
            return None
        return _load(path)

    def _list_for_run_sync(self, run_id: str) -> list[LLMCallReplayRecord]:
        if not self._root.exists():
            return []
        records = [
            record
            for path in self._root.glob("llm-call-*.json")
            if (record := _load(path)).run_id == run_id
        ]
        return sorted(records, key=lambda item: (item.started_at, item.call_id))

    def _delete_run_sync(self, run_id: str) -> None:
        if not self._root.exists():
            return
        with self._lock:
            for path in self._root.glob("llm-call-*.json"):
                if _load(path).run_id == run_id:
                    path.unlink(missing_ok=True)


def _load(path: Path) -> LLMCallReplayRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return LLMCallReplayRecord.model_validate(payload)


def _validate_call_id(call_id: str) -> None:
    if not _CALL_ID_PATTERN.fullmatch(call_id):
        raise ValueError("LLM 调用回放标识格式不正确。")
