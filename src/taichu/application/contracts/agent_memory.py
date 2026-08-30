"""通用 Runtime 自动记忆的应用层仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.agent_memory.models import (
    AgentMemoryEntry,
    AgentMemoryKind,
    ProducerMemoryValidityProof,
)


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

    async def delete(
        self, memory_id: str, *, deleted_at: str
    ) -> AgentMemoryEntry | None: ...

    async def purge_expired(self, *, as_of: str) -> int: ...


@runtime_checkable
class AgentMemoryEvidenceResolver(Protocol):
    """把可追溯来源解析为当前内容指纹；暂时不可用时返回 None。"""

    async def fingerprint(self, reference: str) -> str | None: ...


@runtime_checkable
class ProducerMemoryValidityProvider(Protocol):
    """节点复用前后共用的 producer 有效性证明边界。"""

    async def producer_validity_proof(
        self,
        conversation_id: str,
        producer_ref: str,
        *,
        current_request_index: int | None = None,
    ) -> ProducerMemoryValidityProof: ...

    async def require_active_producer(
        self,
        conversation_id: str,
        producer_ref: str,
        *,
        expected_source_fingerprint: str,
        expected_dependency_fingerprint: str,
        current_request_index: int | None = None,
    ) -> ProducerMemoryValidityProof: ...
