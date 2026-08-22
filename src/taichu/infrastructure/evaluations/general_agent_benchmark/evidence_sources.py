"""只持有已绑定读取函数的 Runtime 审计证据 facade 与聚合器。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from taichu.application.contracts.runtime_evidence import (
    CheckpointSourceRecord,
    ContextSourceRecord,
    EffectSourceRecord,
    EvidenceAvailability,
    EvidenceItem,
    EvidenceProblem,
    InvocationSourceRecord,
    NodeSourceRecord,
    ReplaySourceRecord,
    RunSourceRecord,
    RuntimeEvidenceSources,
    UsageSourceRecord,
)

RecordT = TypeVar("RecordT")


async def _read_one(
    read: Callable[[str], Awaitable[RecordT | EvidenceItem[RecordT] | None]],
    locator: str,
) -> EvidenceItem[RecordT]:
    try:
        result = await read(locator)
    except Exception as error:
        return EvidenceItem(
            value=None,
            availability=EvidenceAvailability.CORRUPT,
            problems=(
                EvidenceProblem(
                    code="SOURCE_READ_FAILED",
                    message=f"证据源读取失败：{type(error).__name__}",
                    locator=locator,
                ),
            ),
        )
    if isinstance(result, EvidenceItem):
        return result
    if result is None:
        return EvidenceItem(
            value=None,
            availability=EvidenceAvailability.MISSING,
            problems=(
                EvidenceProblem(
                    code="EVIDENCE_NOT_FOUND",
                    message="未找到声明的审计证据。",
                    locator=locator,
                ),
            ),
        )
    return EvidenceItem(
        value=result,
        availability=EvidenceAvailability.AVAILABLE,
    )


async def _read_many(
    read: Callable[
        [str],
        Awaitable[tuple[RecordT, ...] | EvidenceItem[tuple[RecordT, ...]]],
    ],
    locator: str,
) -> EvidenceItem[tuple[RecordT, ...]]:
    try:
        result = await read(locator)
    except Exception as error:
        return EvidenceItem(
            value=None,
            availability=EvidenceAvailability.CORRUPT,
            problems=(
                EvidenceProblem(
                    code="SOURCE_READ_FAILED",
                    message=f"证据源读取失败：{type(error).__name__}",
                    locator=locator,
                ),
            ),
        )
    if isinstance(result, EvidenceItem):
        return result
    if not result:
        return EvidenceItem(
            value=(),
            availability=EvidenceAvailability.MISSING,
            problems=(
                EvidenceProblem(
                    code="EVIDENCE_NOT_FOUND",
                    message="未找到声明的审计证据。",
                    locator=locator,
                ),
            ),
        )
    return EvidenceItem(
        value=tuple(result),
        availability=EvidenceAvailability.AVAILABLE,
    )


class RunEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_one: Callable[
            [str],
            Awaitable[RunSourceRecord | EvidenceItem[RunSourceRecord] | None],
        ],
    ) -> None:
        self._read = read_one

    async def read_run(self, run_id: str) -> EvidenceItem[RunSourceRecord]:
        return await _read_one(self._read, run_id)


class NodeEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_many: Callable[
            [str],
            Awaitable[
                tuple[NodeSourceRecord, ...]
                | EvidenceItem[tuple[NodeSourceRecord, ...]]
            ],
        ],
    ) -> None:
        self._read = read_many

    async def read_nodes(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[NodeSourceRecord, ...]]:
        return await _read_many(self._read, run_id)


class InvocationEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_many: Callable[
            [str],
            Awaitable[
                tuple[InvocationSourceRecord, ...]
                | EvidenceItem[tuple[InvocationSourceRecord, ...]]
            ],
        ],
    ) -> None:
        self._read = read_many

    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]:
        return await _read_many(self._read, run_id)


class ContextSnapshotEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_one: Callable[
            [str],
            Awaitable[ContextSourceRecord | EvidenceItem[ContextSourceRecord] | None],
        ],
    ) -> None:
        self._read = read_one

    async def read_snapshot(
        self,
        snapshot_id: str,
    ) -> EvidenceItem[ContextSourceRecord]:
        return await _read_one(self._read, snapshot_id)


class ReplayEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_many: Callable[
            [str],
            Awaitable[
                tuple[ReplaySourceRecord, ...]
                | EvidenceItem[tuple[ReplaySourceRecord, ...]]
            ],
        ],
    ) -> None:
        self._read = read_many

    async def read_replays(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]:
        return await _read_many(self._read, run_id)


class CheckpointEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_many: Callable[
            [str],
            Awaitable[
                tuple[CheckpointSourceRecord, ...]
                | EvidenceItem[tuple[CheckpointSourceRecord, ...]]
            ],
        ],
    ) -> None:
        self._read = read_many

    async def read_revisions(
        self,
        thread_id: str,
    ) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]:
        return await _read_many(self._read, thread_id)


class EffectEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_many: Callable[
            [str],
            Awaitable[
                tuple[EffectSourceRecord, ...]
                | EvidenceItem[tuple[EffectSourceRecord, ...]]
            ],
        ],
    ) -> None:
        self._read = read_many

    async def read_effects(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[EffectSourceRecord, ...]]:
        return await _read_many(self._read, run_id)


class UsageEvidenceSourceFacade:
    def __init__(
        self,
        *,
        read_one: Callable[
            [str],
            Awaitable[UsageSourceRecord | EvidenceItem[UsageSourceRecord] | None],
        ],
    ) -> None:
        self._read = read_one

    async def read_usage(
        self,
        call_id: str,
    ) -> EvidenceItem[UsageSourceRecord]:
        return await _read_one(self._read, call_id)


class RepositoryRuntimeEvidenceReader:
    """仅聚合窄 source facade，不持有或调用写仓储。"""

    def __init__(self, sources: RuntimeEvidenceSources) -> None:
        self._sources = sources

    async def read_run(self, run_id: str) -> EvidenceItem[RunSourceRecord]:
        item = await self._sources.run.read_run(run_id)
        if item.value is not None and item.value.run_id != run_id:
            return _conflicting(item.value, "RUN_ID_MISMATCH", run_id)
        return item

    async def read_nodes(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[NodeSourceRecord, ...]]:
        item = await self._sources.nodes.read_nodes(run_id)
        if item.value is None:
            return item
        if any(record.run_id != run_id for record in item.value):
            return _conflicting(item.value, "RUN_ID_MISMATCH", run_id)
        keys = [(record.plan_revision, record.node_id) for record in item.value]
        if len(keys) != len(set(keys)):
            return _conflicting(item.value, "DUPLICATE_NODE_IDENTITY", run_id)
        return item.model_copy(
            update={
                "value": tuple(
                    sorted(
                        item.value,
                        key=lambda record: (record.plan_revision, record.node_id),
                    )
                )
            }
        )

    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]:
        item = await self._sources.invocations.read_invocations(run_id)
        if item.value is None:
            return item
        records = item.value
        if any(record.run_id != run_id for record in records):
            return _conflicting(records, "RUN_ID_MISMATCH", run_id)
        by_call = {record.call_id: record for record in records}
        if len(by_call) != len(records):
            return _conflicting(records, "DUPLICATE_CALL_ID", run_id)
        if any(
            record.parent_call_id is not None
            and record.parent_call_id not in by_call
            for record in records
        ):
            return _conflicting(records, "PARENT_CALL_NOT_FOUND", run_id)
        ordered = _order_invocations(records)
        return item.model_copy(update={"value": ordered})

    async def read_context(
        self,
        snapshot_id: str,
        run_id: str,
    ) -> EvidenceItem[ContextSourceRecord]:
        item = await self._sources.context_snapshots.read_snapshot(snapshot_id)
        if item.value is not None and (
            item.value.snapshot_id != snapshot_id or item.value.run_id != run_id
        ):
            return _conflicting(item.value, "CONTEXT_IDENTITY_MISMATCH", snapshot_id)
        return item

    async def read_checkpoint(
        self,
        thread_id: str,
    ) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]:
        item = await self._sources.checkpoints.read_revisions(thread_id)
        if item.value is None:
            return item
        if any(record.thread_id != thread_id for record in item.value):
            return _conflicting(item.value, "THREAD_ID_MISMATCH", thread_id)
        ordered = tuple(sorted(item.value, key=lambda record: record.revision))
        if [record.revision for record in ordered] != list(
            range(1, len(ordered) + 1)
        ):
            return _conflicting(ordered, "CHECKPOINT_REVISION_GAP", thread_id)
        return item.model_copy(update={"value": ordered})

    async def read_effects(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[EffectSourceRecord, ...]]:
        item = await self._sources.effects.read_effects(run_id)
        if item.value is None:
            return item
        if any(record.run_id != run_id for record in item.value):
            return _conflicting(item.value, "RUN_ID_MISMATCH", run_id)
        return item.model_copy(
            update={
                "value": tuple(
                    sorted(
                        item.value,
                        key=lambda record: (
                            record.plan_revision,
                            record.node_id,
                            record.effect_id,
                        ),
                    )
                )
            }
        )

    async def read_llm_replays(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]:
        item = await self._sources.replays.read_replays(run_id)
        if item.value is None:
            return item
        if any(record.run_id != run_id for record in item.value):
            return _conflicting(item.value, "RUN_ID_MISMATCH", run_id)
        return item.model_copy(
            update={
                "value": tuple(
                    sorted(
                        item.value,
                        key=lambda record: (record.started_at, record.call_id),
                    )
                )
            }
        )

    async def read_llm_usage(
        self,
        call_ids: tuple[str, ...],
    ) -> EvidenceItem[tuple[UsageSourceRecord, ...]]:
        if len(call_ids) != len(set(call_ids)):
            return _conflicting((), "DUPLICATE_USAGE_LOCATOR", "usage")
        records: list[UsageSourceRecord] = []
        problems: list[EvidenceProblem] = []
        worst = EvidenceAvailability.AVAILABLE
        for call_id in call_ids:
            item = await self._sources.usage.read_usage(call_id)
            if item.value is not None:
                if item.value.call_id != call_id:
                    return _conflicting(
                        tuple(records) + (item.value,),
                        "CALL_ID_MISMATCH",
                        call_id,
                    )
                records.append(item.value)
            if item.availability is not EvidenceAvailability.AVAILABLE:
                problems.extend(item.problems)
                if item.availability is EvidenceAvailability.CORRUPT:
                    worst = EvidenceAvailability.CORRUPT
                elif worst is EvidenceAvailability.AVAILABLE:
                    worst = item.availability
        return EvidenceItem(
            value=tuple(records),
            availability=worst,
            problems=tuple(problems),
        )


def _conflicting(
    value: RecordT,
    code: str,
    locator: str,
) -> EvidenceItem[RecordT]:
    return EvidenceItem(
        value=value,
        availability=EvidenceAvailability.CONFLICTING,
        problems=(
            EvidenceProblem(
                code=code,
                message="审计证据的稳定关联身份不一致。",
                locator=locator,
            ),
        ),
    )


def _order_invocations(
    records: tuple[InvocationSourceRecord, ...],
) -> tuple[InvocationSourceRecord, ...]:
    by_parent: dict[str | None, list[InvocationSourceRecord]] = {}
    for record in records:
        by_parent.setdefault(record.parent_call_id, []).append(record)
    for children in by_parent.values():
        children.sort(key=lambda record: (record.started_at, record.call_id))
    ordered: list[InvocationSourceRecord] = []

    def visit(record: InvocationSourceRecord) -> None:
        ordered.append(record)
        for child in by_parent.get(record.call_id, []):
            visit(child)

    for root in by_parent.get(None, []):
        visit(root)
    return tuple(ordered)
