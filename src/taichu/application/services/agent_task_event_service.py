"""In-memory task event center for Agent task monitoring."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from taichu.application.agents.models.agent_run import (
    AgentBatchChapterProgress,
    AgentLLMCall,
    AgentRun,
    AgentRunNode,
    AgentRunStatus,
)


class AgentTaskEventCenter:
    """Broadcast Agent task events and keep active task snapshots."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._tasks: dict[str, AgentRun] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish one structured task event to all subscribers."""
        normalized = _normalize_event(event)
        await self._remember(normalized)
        for queue in list(self._subscribers):
            await queue.put(normalized)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to future events until the client disconnects."""
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

    async def list_active_tasks(self) -> list[AgentRun]:
        """Return in-memory tasks, newest first."""
        async with self._lock:
            return sorted(
                self._tasks.values(),
                key=lambda task: task.started_at,
                reverse=True,
            )

    async def get_active_task(self, task_id: str) -> AgentRun | None:
        """Return one in-memory task snapshot."""
        async with self._lock:
            return self._tasks.get(task_id)

    async def delete_task(self, task_id: str) -> bool:
        """Remove one in-memory task snapshot and broadcast deletion."""
        async with self._lock:
            existed = self._tasks.pop(task_id, None) is not None
        if existed:
            await self.publish(
                {
                    "type": "task_deleted",
                    "event_type": "task_deleted",
                    "run_id": task_id,
                    "message": "任务监控记录已删除。",
                }
            )
        return existed

    async def _remember(self, event: dict[str, Any]) -> None:
        async with self._lock:
            event_type = str(event.get("event_type") or event.get("type") or "")
            if event_type == "task_deleted":
                run_id = str(event.get("run_id") or "")
                if run_id:
                    self._tasks.pop(run_id, None)
                return
            run_payload = event.get("run")
            if isinstance(run_payload, dict):
                updated = AgentRun.model_validate(run_payload)
                run_id = updated.run_id
            else:
                run_id = str(event.get("run_id") or "")
                if not run_id:
                    return
                current = self._tasks.get(run_id)
                if current is None:
                    return
                updated = current
            node_payload = event.get("node")
            if isinstance(node_payload, dict):
                node = AgentRunNode.model_validate(node_payload)
                updated = updated.model_copy(
                    update={"nodes": _upsert_by_name(updated.nodes, node)}
                )
            llm_payload = event.get("llm_call")
            if isinstance(llm_payload, dict):
                llm_call = AgentLLMCall.model_validate(llm_payload)
                updated = updated.model_copy(
                    update={"llm_calls": _upsert_by_call_id(updated.llm_calls, llm_call)}
                )
            progress_payload = event.get("chapter_progress")
            if isinstance(progress_payload, dict):
                progress = AgentBatchChapterProgress.model_validate(progress_payload)
                progress_items = _upsert_progress(
                    updated.batch_chapter_progress,
                    progress,
                )
                updated = updated.model_copy(
                    update={
                        "batch_chapter_progress": progress_items,
                        "current_concurrency": sum(
                            1 for item in progress_items if item.status.value == "running"
                        ),
                        "completed_chapter_count": sum(
                            1 for item in progress_items if item.status.value == "success"
                        ),
                        "failed_chapter_count": sum(
                            1 for item in progress_items if item.status.value == "failed"
                        ),
                    }
                )
            if event_type in {"run_failed", "task_failed"}:
                updated = updated.model_copy(update={"status": AgentRunStatus.FAILED})
            elif event_type in {"run_completed", "task_completed"}:
                updated = updated.model_copy(update={"status": AgentRunStatus.COMPLETED})
            self._tasks[run_id] = updated


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or event.get("type") or "")
    if not event_type:
        event_type = "task_event"
    return {"type": event_type, "event_type": event_type, **event}


def _upsert_by_name(
    items: list[AgentRunNode],
    item: AgentRunNode,
) -> list[AgentRunNode]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.node_name == item.node_name:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items


def _upsert_by_call_id(
    items: list[AgentLLMCall],
    item: AgentLLMCall,
) -> list[AgentLLMCall]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.call_id == item.call_id:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items


def _upsert_progress(
    items: list[AgentBatchChapterProgress],
    item: AgentBatchChapterProgress,
) -> list[AgentBatchChapterProgress]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.chapter_id == item.chapter_id:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items
