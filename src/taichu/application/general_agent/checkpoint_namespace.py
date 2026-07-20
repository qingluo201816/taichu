"""把独立编译的能力图隔离到同一 LangGraph 线程的计划命名空间。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, TypeVar

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

V = TypeVar("V", int, float, str)


class NamespacedCheckpointSaver(BaseCheckpointSaver[V]):
    """在不伪造第二个 thread_id 的前提下固定检查点命名空间。"""

    def __init__(
        self,
        delegate: BaseCheckpointSaver[V],
        *,
        namespace: str,
    ) -> None:
        super().__init__(serde=delegate.serde)
        self._delegate = delegate
        self._namespace = namespace

    @property
    def config_specs(self) -> list:
        return self._delegate.config_specs

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self._delegate.get_tuple(self._config(config))

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        return self._delegate.list(
            self._config(config) if config is not None else None,
            filter=filter,
            before=self._config(before) if before is not None else None,
            limit=limit,
        )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self._delegate.put(
            self._config(config),
            checkpoint,
            metadata,
            new_versions,
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._delegate.put_writes(
            self._config(config),
            writes,
            task_id,
            task_path,
        )

    def delete_thread(self, thread_id: str) -> None:
        self._delegate.delete_thread(thread_id)

    async def aget_tuple(
        self,
        config: RunnableConfig,
    ) -> CheckpointTuple | None:
        return await self._delegate.aget_tuple(self._config(config))

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        async for item in self._delegate.alist(
            self._config(config) if config is not None else None,
            filter=filter,
            before=self._config(before) if before is not None else None,
            limit=limit,
        ):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await self._delegate.aput(
            self._config(config),
            checkpoint,
            metadata,
            new_versions,
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self._delegate.aput_writes(
            self._config(config),
            writes,
            task_id,
            task_path,
        )

    async def adelete_thread(self, thread_id: str) -> None:
        await self._delegate.adelete_thread(thread_id)

    def get_next_version(self, current: V | None, channel: None) -> V:
        return self._delegate.get_next_version(current, channel)

    def _config(self, config: RunnableConfig) -> RunnableConfig:
        configurable = dict(config.get("configurable", {}))
        configurable["checkpoint_ns"] = self._namespace
        return {**config, "configurable": configurable}
