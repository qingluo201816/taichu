"""追加保存脱敏能力调用记录。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from threading import Lock

from pydantic import ValidationError

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

    async def list_for_run(
        self,
        run_id: str,
        *,
        limit: int = 500,
    ) -> tuple[list[InvocationTraceRecord], int]:
        if not run_id.strip():
            raise ValueError("运行标识不能为空。")
        if limit < 1 or limit > 2_000:
            raise ValueError("调用记录读取数量必须在 1 到 2000 之间。")
        return await asyncio.to_thread(self._list_for_run_sync, run_id, limit)

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

    def _list_for_run_sync(
        self,
        run_id: str,
        limit: int,
    ) -> tuple[list[InvocationTraceRecord], int]:
        if not self._path.exists():
            return [], 0
        records: list[InvocationTraceRecord] = []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                record = InvocationTraceRecord.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError):
                continue
            if record.run_id == run_id:
                records.append(record)
        records.sort(key=lambda item: (item.started_at, item.call_id))
        return records[-limit:], len(records)
