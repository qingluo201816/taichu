"""需求 11.1—11.15：八个窄只读 Runtime 证据源。"""

from __future__ import annotations

import asyncio
import inspect

from taichu.application.contracts.runtime_evidence import (
    CheckpointEvidenceSource,
    CheckpointSourceRecord,
    ContextSnapshotEvidenceSource,
    ContextSourceRecord,
    EffectEvidenceSource,
    EffectSourceRecord,
    EvidenceAvailability,
    EvidenceItem,
    InvocationEvidenceSource,
    InvocationSourceRecord,
    NodeEvidenceSource,
    NodeSourceRecord,
    ReplayEvidenceSource,
    ReplaySourceRecord,
    RunEvidenceSource,
    RunSourceRecord,
    RuntimeEvidenceSources,
    UsageEvidenceSource,
    UsageSourceRecord,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.evidence_sources import (
    CheckpointEvidenceSourceFacade,
    ContextSnapshotEvidenceSourceFacade,
    EffectEvidenceSourceFacade,
    InvocationEvidenceSourceFacade,
    NodeEvidenceSourceFacade,
    ReplayEvidenceSourceFacade,
    RepositoryRuntimeEvidenceReader,
    RunEvidenceSourceFacade,
    UsageEvidenceSourceFacade,
)


def _run() -> RunSourceRecord:
    return RunSourceRecord(
        run_id="run_001",
        task_id="task_001",
        conversation_id="conversation_001",
        status="completed",
        plan_revision=2,
        context_snapshot_id="context_001",
    )


def _sources(
    *,
    run_reader: object | None = None,
    node_reader: object | None = None,
) -> RuntimeEvidenceSources:
    async def read_run(_: str) -> RunSourceRecord | None:
        return _run()

    async def read_nodes(_: str) -> tuple[NodeSourceRecord, ...]:
        return ()

    async def read_invocations(_: str) -> tuple[InvocationSourceRecord, ...]:
        return ()

    async def read_context(_: str) -> ContextSourceRecord | None:
        return None

    async def read_replays(_: str) -> tuple[ReplaySourceRecord, ...]:
        return ()

    async def read_checkpoints(_: str) -> tuple[CheckpointSourceRecord, ...]:
        return ()

    async def read_effects(_: str) -> tuple[EffectSourceRecord, ...]:
        return ()

    async def read_usage(_: str) -> UsageSourceRecord | None:
        return None

    return RuntimeEvidenceSources(
        run=RunEvidenceSourceFacade(read_one=run_reader or read_run),
        nodes=NodeEvidenceSourceFacade(read_many=node_reader or read_nodes),
        invocations=InvocationEvidenceSourceFacade(read_many=read_invocations),
        context_snapshots=ContextSnapshotEvidenceSourceFacade(read_one=read_context),
        replays=ReplayEvidenceSourceFacade(read_many=read_replays),
        checkpoints=CheckpointEvidenceSourceFacade(read_many=read_checkpoints),
        effects=EffectEvidenceSourceFacade(read_many=read_effects),
        usage=UsageEvidenceSourceFacade(read_one=read_usage),
    )


def test_source_protocols_are_narrow_and_facades_store_only_bound_callable() -> None:
    sources = _sources()
    assert isinstance(sources.run, RunEvidenceSource)
    assert isinstance(sources.nodes, NodeEvidenceSource)
    assert isinstance(sources.invocations, InvocationEvidenceSource)
    assert isinstance(sources.context_snapshots, ContextSnapshotEvidenceSource)
    assert isinstance(sources.replays, ReplayEvidenceSource)
    assert isinstance(sources.checkpoints, CheckpointEvidenceSource)
    assert isinstance(sources.effects, EffectEvidenceSource)
    assert isinstance(sources.usage, UsageEvidenceSource)

    forbidden = {"save", "delete", "repair", "append", "update", "repository", "storage"}
    for source in sources:
        assert not forbidden.intersection(dir(source))
        assert set(vars(source)) == {"_read"}

    assert set(inspect.signature(RepositoryRuntimeEvidenceReader).parameters) == {
        "sources"
    }


def test_missing_and_source_failure_have_distinct_availability() -> None:
    async def missing(_: str) -> RunSourceRecord | None:
        return None

    async def failed(_: str) -> RunSourceRecord | None:
        raise OSError("审计文件损坏")

    async def scenario() -> tuple[
        EvidenceItem[RunSourceRecord],
        EvidenceItem[RunSourceRecord],
    ]:
        return (
            await RepositoryRuntimeEvidenceReader(
                _sources(run_reader=missing)
            ).read_run("run_001"),
            await RepositoryRuntimeEvidenceReader(
                _sources(run_reader=failed)
            ).read_run("run_001"),
        )

    missing_item, failed_item = asyncio.run(scenario())
    assert missing_item.availability is EvidenceAvailability.MISSING
    assert failed_item.availability is EvidenceAvailability.CORRUPT
    assert failed_item.problems[0].code == "SOURCE_READ_FAILED"
    assert failed_item.value is None


def test_reader_sorts_records_and_rejects_wrong_run_correlations() -> None:
    async def read_nodes(_: str) -> tuple[NodeSourceRecord, ...]:
        return (
            NodeSourceRecord(
                run_id="run_001",
                plan_revision=2,
                node_id="review",
                status="completed",
            ),
            NodeSourceRecord(
                run_id="run_001",
                plan_revision=1,
                node_id="plan",
                status="completed",
            ),
        )

    reader = RepositoryRuntimeEvidenceReader(_sources(node_reader=read_nodes))
    nodes = asyncio.run(reader.read_nodes("run_001"))
    assert nodes.availability is EvidenceAvailability.AVAILABLE
    assert [(item.plan_revision, item.node_id) for item in nodes.value or ()] == [
        (1, "plan"),
        (2, "review"),
    ]

    async def conflicting(_: str) -> tuple[NodeSourceRecord, ...]:
        return (
            NodeSourceRecord(
                run_id="other_run",
                plan_revision=1,
                node_id="plan",
                status="completed",
            ),
        )

    conflict = asyncio.run(
        RepositoryRuntimeEvidenceReader(
            _sources(node_reader=conflicting)
        ).read_nodes("run_001")
    )
    assert conflict.availability is EvidenceAvailability.CONFLICTING
    assert conflict.problems[0].code == "RUN_ID_MISMATCH"


def test_usage_batch_preserves_requested_call_order_and_partial_missing() -> None:
    records = {
        "call_a": UsageSourceRecord(
            call_id="call_a",
            run_id="run_001",
            provider="synthetic",
            model_id="synthetic",
            status="completed",
            total_tokens=0,
        ),
        "call_c": UsageSourceRecord(
            call_id="call_c",
            run_id="run_001",
            provider="synthetic",
            model_id="synthetic",
            status="completed",
            total_tokens=0,
        ),
    }

    async def read_usage(call_id: str) -> UsageSourceRecord | None:
        return records.get(call_id)

    sources = _sources()
    sources = sources.model_copy(
        update={"usage": UsageEvidenceSourceFacade(read_one=read_usage)}
    )
    item: EvidenceItem[tuple[UsageSourceRecord, ...]] = asyncio.run(
        RepositoryRuntimeEvidenceReader(sources).read_llm_usage(
            ("call_c", "call_b", "call_a")
        )
    )

    assert item.availability is EvidenceAvailability.MISSING
    assert [record.call_id for record in item.value or ()] == ["call_c", "call_a"]
    assert item.problems[0].locator == "call_b"
