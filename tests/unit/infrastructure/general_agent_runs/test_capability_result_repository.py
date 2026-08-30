"""LangGraph Store 能力结果仓储测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultConflictError,
    CapabilityResultOwner,
    CapabilityResultOwnerMismatchError,
    CapabilityResultRecordCorruptError,
    DeleteRunOutcome,
    ResultIdentityPayload,
    build_capability_result_record,
)
from tests.fakes.capability_results import (
    in_memory_capability_result_repository,
)


def _owner(
    conversation_id: str = "conversation_001",
    run_id: str = "general_run_20260730_120000_abc123",
) -> CapabilityResultOwner:
    return CapabilityResultOwner(
        conversation_id=conversation_id,
        run_id=run_id,
    )


def _identity(
    *,
    owner: CapabilityResultOwner | None = None,
    node_id: str = "read_chapter",
) -> ResultIdentityPayload:
    return ResultIdentityPayload(
        owner=owner or _owner(),
        plan_revision=1,
        node_id=node_id,
        attempt_id=f"attempt_{'1' * 32}",
        capability_kind="tool",
        capability_name="read_manuscript",
        input_sha256="2" * 64,
        handler_identity_sha256="3" * 64,
        input_schema_sha256="4" * 64,
        output_schema_sha256="5" * 64,
    )


def _record(
    *,
    identity: ResultIdentityPayload | None = None,
    answer: str = "已读取正文。",
    committed_at: str = "2026-07-30T12:00:00Z",
):
    return build_capability_result_record(
        identity=identity or _identity(),
        output={"answer": answer},
        source_refs=("chapter_001",),
        artifact_refs=("artifact_001",),
        trace_id="trace_001",
        committed_at=committed_at,
    )


@pytest.mark.anyio
async def test_commit_read_list_and_restart_use_official_store(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "capability_results"
    repository = in_memory_capability_result_repository(scope)
    record = _record()

    committed = await repository.commit_completed(record.owner, record)
    restarted = in_memory_capability_result_repository(scope)

    assert await restarted.get_completed(record.owner, record.result_id) == committed
    assert await restarted.list_for_run(record.owner) == (committed,)
    stored = await repository.store.aget(
        (
            "taichu",
            "general_agent_capability_results",
            record.owner.conversation_id,
            record.owner.run_id,
        ),
        record.result_id,
    )
    assert stored is not None


@pytest.mark.anyio
async def test_unknown_owner_and_delete_have_explicit_semantics(
    tmp_path: Path,
) -> None:
    repository = in_memory_capability_result_repository(tmp_path / "results")
    owner = _owner()
    unknown_id = "cr_" + "a" * 64

    assert await repository.get_completed(owner, unknown_id) is None
    assert await repository.list_for_run(owner) == ()
    assert await repository.delete_run(owner) is DeleteRunOutcome.NOT_FOUND

    record = _record()
    await repository.commit_completed(owner, record)
    assert await repository.delete_run(owner) is DeleteRunOutcome.DELETED
    assert await repository.list_for_run(owner) == ()


@pytest.mark.anyio
async def test_same_identity_is_idempotent_and_rejects_conflict(
    tmp_path: Path,
) -> None:
    repository = in_memory_capability_result_repository(tmp_path / "results")
    first = _record(committed_at="2026-07-30T12:00:00Z")
    same_semantics = _record(committed_at="2026-07-30T12:00:01Z")
    conflict = _record(answer="另一份结果。")

    winner = await repository.commit_completed(first.owner, first)
    assert await repository.commit_completed(
        same_semantics.owner,
        same_semantics,
    ) == winner
    with pytest.raises(CapabilityResultConflictError):
        await repository.commit_completed(conflict.owner, conflict)


@pytest.mark.anyio
async def test_owner_mismatch_and_corrupt_store_value_are_rejected(
    tmp_path: Path,
) -> None:
    repository = in_memory_capability_result_repository(tmp_path / "results")
    record = _record()
    with pytest.raises(CapabilityResultOwnerMismatchError):
        await repository.commit_completed(_owner(run_id="other_run"), record)

    namespace = (
        "taichu",
        "general_agent_capability_results",
        record.owner.conversation_id,
        record.owner.run_id,
    )
    await repository.store.aput(
        namespace,
        record.result_id,
        {"result_id": record.result_id, "broken": True},
    )
    with pytest.raises(CapabilityResultRecordCorruptError):
        await repository.get_completed(record.owner, record.result_id)


@pytest.mark.anyio
async def test_distinct_results_are_sorted_and_isolated_by_owner(
    tmp_path: Path,
) -> None:
    repository = in_memory_capability_result_repository(tmp_path / "results")
    first = _record(identity=_identity(node_id="first"))
    second = _record(
        identity=_identity(node_id="second"),
        committed_at="2026-07-30T12:00:01Z",
    )
    other = _record(
        identity=_identity(
            owner=_owner(run_id="general_run_20260730_120001_def456"),
            node_id="other",
        )
    )
    for record in (second, other, first):
        await repository.commit_completed(record.owner, record)

    assert await repository.list_for_run(first.owner) == (first, second)
    assert await repository.list_for_run(other.owner) == (other,)
