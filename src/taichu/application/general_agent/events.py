"""通用写作助手独立的运行事件中心。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from taichu.application.general_agent.models import GeneralAgentRun


class GeneralAgentEventCenter:
    """广播通用 Runtime 事件，不混入知识沉淀 Workflow 业务日志。"""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._snapshots: dict[str, GeneralAgentRun] = {}
        self._lock = asyncio.Lock()

    async def publish(
        self,
        *,
        event_type: str,
        run: GeneralAgentRun,
        detail: str = "",
    ) -> None:
        event = {
            "type": event_type,
            "event_type": event_type,
            "run_id": run.run_id,
            "status": run.status.value,
            "checkpoint_revision": run.checkpoint_revision,
            "detail": detail,
            "run": run.model_dump(mode="json"),
        }
        async with self._lock:
            self._snapshots[run.run_id] = run
        for queue in list(self._subscribers):
            await queue.put(event)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self._subscribers.discard(queue)

    async def get_snapshot(self, run_id: str) -> GeneralAgentRun | None:
        async with self._lock:
            return self._snapshots.get(run_id)

    async def delete_snapshot(self, run_id: str) -> None:
        async with self._lock:
            self._snapshots.pop(run_id, None)
