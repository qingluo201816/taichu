"""召回技术观测的追加式 JSONL 仓储。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from taichu.application.retrieval.models import RetrievalTraceRecord


class JsonlRetrievalTraceRepository:
    """将完成、空结果和失败召回保存为轻量技术记录。"""

    def __init__(self, assets_root: Path) -> None:
        self._path = assets_root / "derived" / "retrieval" / "calls.jsonl"
        self._write_lock = asyncio.Lock()

    async def append(self, record: RetrievalTraceRecord) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._append_sync, record)

    def _append_sync(self, record: RetrievalTraceRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json())
            stream.write("\n")
