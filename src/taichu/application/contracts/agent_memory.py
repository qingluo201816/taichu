"""通用 Runtime 自动记忆仓储与可重建索引契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.agent_memory.models import AgentMemoryEntry, AgentMemoryKind


@runtime_checkable
class AgentMemoryRepository(Protocol):
    async def save(self, entry: AgentMemoryEntry) -> AgentMemoryEntry: ...

    async def get(self, memory_id: str) -> AgentMemoryEntry | None: ...

    async def query(
        self,
        *,
        conversation_id: str | None = None,
        kinds: tuple[AgentMemoryKind, ...] = (),
        run_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[AgentMemoryEntry]: ...

    async def delete(self, memory_id: str, *, deleted_at: str) -> AgentMemoryEntry | None: ...

    async def purge_expired(self, *, as_of: str) -> int: ...


@runtime_checkable
class AgentMemoryLexicalIndex(Protocol):
    async def scores(
        self,
        entries: list[AgentMemoryEntry],
        *,
        query_text: str,
    ) -> dict[str, float]: ...

    async def rebuild(self, entries: list[AgentMemoryEntry]) -> str: ...
