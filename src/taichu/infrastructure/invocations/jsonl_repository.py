"""追加保存脱敏能力调用记录。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from threading import Lock

from taichu.application.invocations.models import InvocationTraceRecord


class JsonlInvocationTraceRepository:
    """把跨 Tool、子 Agent 和 LLM 的技术记录写入派生层。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._path = (
            project_assets_dir / "derived" / "capability_invocations" / "calls.jsonl"
        )
        self._lock = Lock()

    async def append(self, record: InvocationTraceRecord) -> None:
        await asyncio.to_thread(self._append_sync, record)

    def _append_sync(self, record: InvocationTraceRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._lock:
            with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
