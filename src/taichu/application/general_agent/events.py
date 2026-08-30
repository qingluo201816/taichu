"""通用写作助手独立的运行事件中心。"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from typing import Any

from taichu.application.general_agent.models import GeneralAgentRun


class GeneralAgentEventCenter:
    """广播通用 Runtime 事件，不混入知识沉淀 Workflow 业务日志。"""

    def __init__(
        self,
        *,
        subscriber_queue_size: int = 64,
        snapshot_cache_size: int = 256,
    ) -> None:
        if subscriber_queue_size <= 0:
            raise ValueError("订阅队列容量必须大于零。")
        if snapshot_cache_size <= 0:
            raise ValueError("事件快照缓存容量必须大于零。")
        self._subscriber_queue_size = subscriber_queue_size
        self._snapshot_cache_size = snapshot_cache_size
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._snapshots: OrderedDict[str, GeneralAgentRun] = OrderedDict()
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
            self._snapshots.move_to_end(run.run_id)
            while len(self._snapshots) > self._snapshot_cache_size:
                self._snapshots.popitem(last=False)
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            self._put_latest(queue, event)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=self._subscriber_queue_size
        )
        try:
            async with self._lock:
                snapshots = list(self._snapshots.values())
                self._subscribers.add(queue)
            for run in snapshots:
                yield {
                    "type": "snapshot",
                    "event_type": "snapshot",
                    "run_id": run.run_id,
                    "status": run.status.value,
                    "checkpoint_revision": run.checkpoint_revision,
                    "detail": "",
                    "run": run.model_dump(mode="json"),
                }
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def get_snapshot(self, run_id: str) -> GeneralAgentRun | None:
        async with self._lock:
            return self._snapshots.get(run_id)

    async def delete_snapshot(self, run_id: str) -> None:
        async with self._lock:
            self._snapshots.pop(run_id, None)

    @staticmethod
    def _put_latest(
        queue: asyncio.Queue[dict[str, Any] | None],
        event: dict[str, Any],
    ) -> None:
        """队列满时淘汰最旧投影，确保慢订阅者仍能收到最新状态。"""

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            queue.get_nowait()
            queue.put_nowait(event)
