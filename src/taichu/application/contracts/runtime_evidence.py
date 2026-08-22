"""既有 Runtime 审计事实的八个窄只读端口。"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import ConfigDict, Field

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    EvidenceAvailability,
)


class EvidenceProblem(BenchmarkModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    locator: str | None = None


ValueT = TypeVar("ValueT")


class EvidenceItem(BenchmarkModel, Generic[ValueT]):
    value: ValueT | None
    availability: EvidenceAvailability
    problems: tuple[EvidenceProblem, ...] = ()


class RunSourceRecord(BenchmarkModel):
    run_id: str
    task_id: str
    conversation_id: str
    status: str
    plan_revision: int = Field(ge=0)
    context_snapshot_id: str | None = None


class NodeSourceRecord(BenchmarkModel):
    run_id: str
    plan_revision: int = Field(ge=0)
    node_id: str
    status: str
    attempt_id: str | None = None
    effect_id: str | None = None


class InvocationSourceRecord(BenchmarkModel):
    call_id: str
    parent_call_id: str | None = None
    run_id: str
    capability_type: str
    capability_name: str
    status: str
    started_at: str


class ContextSourceRecord(BenchmarkModel):
    snapshot_id: str
    run_id: str
    conversation_id: str
    content_sha256: str
    category_stats: tuple[dict[str, object], ...] = ()


class ReplaySourceRecord(BenchmarkModel):
    call_id: str
    run_id: str
    provider: str
    model_id: str
    status: str
    request_sha256: str
    response_sha256: str
    started_at: str


class CheckpointSourceRecord(BenchmarkModel):
    thread_id: str
    revision: int = Field(ge=1)
    previous_sha256: str | None
    content_sha256: str
    integrity: str


class EffectSourceRecord(BenchmarkModel):
    effect_id: str
    attempt_id: str
    run_id: str
    plan_revision: int = Field(ge=1)
    node_id: str
    status: str


class UsageSourceRecord(BenchmarkModel):
    call_id: str
    run_id: str | None
    provider: str
    model_id: str
    status: str
    total_tokens: int | None = Field(default=None, ge=0)


@runtime_checkable
class RunEvidenceSource(Protocol):
    async def read_run(self, run_id: str) -> EvidenceItem[RunSourceRecord]: ...


@runtime_checkable
class NodeEvidenceSource(Protocol):
    async def read_nodes(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[NodeSourceRecord, ...]]: ...


@runtime_checkable
class InvocationEvidenceSource(Protocol):
    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]: ...


@runtime_checkable
class ContextSnapshotEvidenceSource(Protocol):
    async def read_snapshot(
        self,
        snapshot_id: str,
    ) -> EvidenceItem[ContextSourceRecord]: ...


@runtime_checkable
class ReplayEvidenceSource(Protocol):
    async def read_replays(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]: ...


@runtime_checkable
class CheckpointEvidenceSource(Protocol):
    async def read_revisions(
        self,
        thread_id: str,
    ) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]: ...


@runtime_checkable
class EffectEvidenceSource(Protocol):
    async def read_effects(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[EffectSourceRecord, ...]]: ...


@runtime_checkable
class UsageEvidenceSource(Protocol):
    async def read_usage(
        self,
        call_id: str,
    ) -> EvidenceItem[UsageSourceRecord]: ...


class RuntimeEvidenceSources(BenchmarkModel):
    """只保存八个窄 facade，不接收完整 repository。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    run: RunEvidenceSource
    nodes: NodeEvidenceSource
    invocations: InvocationEvidenceSource
    context_snapshots: ContextSnapshotEvidenceSource
    replays: ReplayEvidenceSource
    checkpoints: CheckpointEvidenceSource
    effects: EffectEvidenceSource
    usage: UsageEvidenceSource

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.run
        yield self.nodes
        yield self.invocations
        yield self.context_snapshots
        yield self.replays
        yield self.checkpoints
        yield self.effects
        yield self.usage


@runtime_checkable
class RuntimeEvidenceReader(Protocol):
    async def read_run(self, run_id: str) -> EvidenceItem[RunSourceRecord]: ...

    async def read_nodes(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[NodeSourceRecord, ...]]: ...

    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]: ...

    async def read_context(
        self,
        snapshot_id: str,
        run_id: str,
    ) -> EvidenceItem[ContextSourceRecord]: ...

    async def read_checkpoint(
        self,
        thread_id: str,
    ) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]: ...

    async def read_effects(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[EffectSourceRecord, ...]]: ...

    async def read_llm_replays(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]: ...

    async def read_llm_usage(
        self,
        call_ids: tuple[str, ...],
    ) -> EvidenceItem[tuple[UsageSourceRecord, ...]]: ...
