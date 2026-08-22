"""CapabilityResult per-result record/index 持久化测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultConflictError,
    CapabilityResultIndexCorruptError,
    CapabilityResultInvalidIdentityError,
    CapabilityResultOwner,
    CapabilityResultOwnerMismatchError,
    CapabilityResultRecordCorruptError,
    DeleteRunOutcome,
    ResultIdentityPayload,
    build_capability_result_record,
)
from taichu.infrastructure.general_agent_runs.capability_result_repository import (
    JsonGeneralAgentCapabilityResultRepository,
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
async def test_commit_read_list_and_restart_use_persisted_index(
    tmp_path: Path,
) -> None:
    root = tmp_path / "capability_results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    record = _record()

    committed = await repository.commit_completed(record.owner, record)

    restarted = JsonGeneralAgentCapabilityResultRepository(root)
    assert await restarted.get_completed(record.owner, record.result_id) == committed
    assert await restarted.list_for_run(record.owner) == (committed,)
    owner_root = root / record.owner.conversation_id / record.owner.run_id
    assert (owner_root / "completed" / f"{record.result_id}.json").is_file()
    assert (owner_root / "index" / f"{record.result_id}.json").is_file()


@pytest.mark.anyio
async def test_unknown_known_owner_storage_has_explicit_empty_semantics(
    tmp_path: Path,
) -> None:
    repository = JsonGeneralAgentCapabilityResultRepository(tmp_path / "results")
    owner = _owner()

    assert await repository.get_completed(owner, "cr_" + "a" * 64) is None
    assert await repository.list_for_run(owner) == ()
    assert await repository.delete_run(owner) is DeleteRunOutcome.NOT_FOUND
    assert not (tmp_path / "results").exists()


@pytest.mark.anyio
async def test_record_published_before_index_is_repaired_by_direct_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    record = _record()

    def interrupt_index_publish(*args, **kwargs):
        raise RuntimeError("模拟 record 已发布、index 尚未发布时退出")

    monkeypatch.setattr(repository, "_publish_index", interrupt_index_publish)
    with pytest.raises(RuntimeError, match="模拟"):
        await repository.commit_completed(record.owner, record)

    owner_root = root / record.owner.conversation_id / record.owner.run_id
    assert (owner_root / "completed" / f"{record.result_id}.json").is_file()
    assert not (owner_root / "index" / f"{record.result_id}.json").exists()

    restarted = JsonGeneralAgentCapabilityResultRepository(root)
    assert await restarted.get_completed(record.owner, record.result_id) == record
    assert (owner_root / "index" / f"{record.result_id}.json").is_file()


@pytest.mark.anyio
async def test_same_result_same_semantics_is_create_once_idempotent(
    tmp_path: Path,
) -> None:
    repository = JsonGeneralAgentCapabilityResultRepository(tmp_path / "results")
    first = _record(committed_at="2026-07-30T12:00:00Z")
    second = _record(committed_at="2026-07-30T12:00:01Z")

    left, right = await asyncio.gather(
        repository.commit_completed(first.owner, first),
        repository.commit_completed(second.owner, second),
    )

    assert left == right
    assert left.committed_at in {first.committed_at, second.committed_at}
    assert await repository.list_for_run(first.owner) == (left,)


@pytest.mark.anyio
async def test_same_result_different_semantics_is_conflict(
    tmp_path: Path,
) -> None:
    repository = JsonGeneralAgentCapabilityResultRepository(tmp_path / "results")
    winner = _record(answer="结果甲")
    conflict = _record(answer="结果乙")
    await repository.commit_completed(winner.owner, winner)

    with pytest.raises(CapabilityResultConflictError):
        await repository.commit_completed(conflict.owner, conflict)

    assert await repository.get_completed(winner.owner, winner.result_id) == winner


@pytest.mark.anyio
async def test_different_results_do_not_share_mutable_index(
    tmp_path: Path,
) -> None:
    repository = JsonGeneralAgentCapabilityResultRepository(tmp_path / "results")
    first = _record(identity=_identity(node_id="read_chapter"))
    second = _record(identity=_identity(node_id="read_structure"))

    await asyncio.gather(
        repository.commit_completed(first.owner, first),
        repository.commit_completed(second.owner, second),
    )

    records = await repository.list_for_run(first.owner)
    assert {record.result_id for record in records} == {
        first.result_id,
        second.result_id,
    }
    index_root = (
        tmp_path
        / "results"
        / first.owner.conversation_id
        / first.owner.run_id
        / "index"
    )
    assert len(list(index_root.glob("*.json"))) == 2


@pytest.mark.anyio
async def test_list_uses_index_and_ignores_unindexed_completed_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    indexed = _record(identity=_identity(node_id="indexed"))
    orphan = _record(identity=_identity(node_id="orphan"))
    await repository.commit_completed(indexed.owner, indexed)
    completed_root = (
        root
        / indexed.owner.conversation_id
        / indexed.owner.run_id
        / "completed"
    )
    (completed_root / f"{orphan.result_id}.json").write_text(
        json.dumps(orphan.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )

    assert await repository.list_for_run(indexed.owner) == (indexed,)


@pytest.mark.anyio
async def test_index_corruption_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    record = _record()
    await repository.commit_completed(record.owner, record)
    index_path = (
        root
        / record.owner.conversation_id
        / record.owner.run_id
        / "index"
        / f"{record.result_id}.json"
    )
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["entry_sha256"] = "f" * 64
    index_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CapabilityResultIndexCorruptError):
        await repository.get_completed(record.owner, record.result_id)


@pytest.mark.anyio
async def test_missing_or_tampered_record_behind_index_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    record = _record()
    await repository.commit_completed(record.owner, record)
    record_path = (
        root
        / record.owner.conversation_id
        / record.owner.run_id
        / "completed"
        / f"{record.result_id}.json"
    )
    record_path.unlink()

    with pytest.raises(CapabilityResultRecordCorruptError):
        await repository.get_completed(record.owner, record.result_id)


@pytest.mark.anyio
async def test_cross_owner_record_copy_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)
    record = _record()
    await repository.commit_completed(record.owner, record)
    other_owner = _owner(conversation_id="conversation_other")
    other_completed = root / other_owner.conversation_id / other_owner.run_id / "completed"
    other_completed.mkdir(parents=True)
    source = (
        root
        / record.owner.conversation_id
        / record.owner.run_id
        / "completed"
        / f"{record.result_id}.json"
    )
    (other_completed / source.name).write_bytes(source.read_bytes())

    with pytest.raises(CapabilityResultOwnerMismatchError):
        await repository.get_completed(other_owner, record.result_id)


@pytest.mark.anyio
async def test_invalid_result_id_fails_before_directory_creation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "results"
    repository = JsonGeneralAgentCapabilityResultRepository(root)

    with pytest.raises(CapabilityResultInvalidIdentityError):
        await repository.get_completed(_owner(), "../escape")

    assert not root.exists()


@pytest.mark.anyio
async def test_delete_removes_only_exact_owner_tree(tmp_path: Path) -> None:
    repository = JsonGeneralAgentCapabilityResultRepository(tmp_path / "results")
    first = _record()
    second_owner = _owner(conversation_id="conversation_002")
    second = _record(identity=_identity(owner=second_owner))
    await repository.commit_completed(first.owner, first)
    await repository.commit_completed(second.owner, second)

    assert await repository.delete_run(first.owner) is DeleteRunOutcome.DELETED
    assert await repository.get_completed(first.owner, first.result_id) is None
    assert await repository.get_completed(second.owner, second.result_id) == second
