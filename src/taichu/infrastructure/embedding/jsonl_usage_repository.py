"""Embedding 调用的追加式脱敏遥测仓储。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from taichu.application.embeddings.models import EmbeddingCallRecord


class JsonlEmbeddingUsageRepository:
    """按需创建 derived/embedding_usage/calls.jsonl。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._path = (
            project_assets_dir / "derived" / "embedding_usage" / "calls.jsonl"
        )
        self._write_lock = asyncio.Lock()

    async def append(self, record: EmbeddingCallRecord) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._append_sync, record)

    def _append_sync(self, record: EmbeddingCallRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json())
            stream.write("\n")
