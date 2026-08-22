"""需求 15.9-15.32：关联 reconciliation、对称硬门禁与查询。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    FrozenSubjectSnapshot,
    InboxIssueReadback,
    IssueCorrelationIntent,
    IssueCorrelationQueryService,
    IssueCorrelationReconciler,
    IssueCorrelationRelationRevision,
    IssueCorrelationRepository,
    IssueCorrelationSnapshot,
    IssueCorrelationSymmetryGate,
    IssueRelationManifest,
    IssueTypedLink,
    IterationCorrelationSnapshot,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def _intent() -> IssueCorrelationIntent:
    return IssueCorrelationIntent.create(
        iteration_id="deepseek_first_live",
        suite_hash="a" * 64,
        run_id="benchmark_run_20260727T000001Z_abcdef123456",
        failure_record_id="failure_runtime_write",
        frozen_subject_id="b" * 64,
        classification="system_defect",
        evidence_refs=("evidence_a",),
    )


def _snapshot(
    *,
    links: tuple[IssueTypedLink, ...] | None = None,
    pending: tuple[str, ...] = (),
    subject_content_hash: str = "c" * 64,
) -> IssueCorrelationSnapshot:
    intent = _intent()
    relation = IssueCorrelationRelationRevision.create(
        intent_id=intent.intent_id,
        subject_id="b" * 64,
        subject_content_hash="c" * 64,
        issue_id="issue_a",
        issue_revision=1,
        issue_status="todo",
        issue_content_hash="d" * 64,
        relation_kind="observed_in",
    )
    link = IssueTypedLink(
        namespace="general_agent_benchmark",
        relation_id=relation.relation_id,
        subject_id=relation.subject_id,
        relation_kind=relation.relation_kind,
        subject_content_sha256=relation.subject_content_hash,
    )
    return IssueCorrelationSnapshot(
        intent=intent,
        subject=FrozenSubjectSnapshot(
            subject_id="b" * 64,
            content_hash=subject_content_hash,
            artifact_ref="first_live_artifact_a",
        ),
        relation_revision=relation,
        relation_manifest=IssueRelationManifest(
            relation_id=relation.relation_id,
            revision=1,
            latest_confirmed_revision_id=relation.revision_id,
        ),
        inbox_readback=InboxIssueReadback(
            issue_id="issue_a",
            revision=1,
            status="todo",
            content_hash="d" * 64,
            links=(link,) if links is None else links,
        ),
        iteration=IterationCorrelationSnapshot(
            iteration_id="deepseek_first_live",
            pending_intent_ids=pending,
            confirmed_relation_revision_ids=(relation.revision_id,),
        ),
    )


def test_four_sided_snapshot_passes_symmetry_gate() -> None:
    result = IssueCorrelationSymmetryGate.evaluate(_snapshot())

    assert result.passed is True
    assert result.problems == ()


def test_missing_inbox_backlink_is_deterministic_repair_required() -> None:
    snapshot = _snapshot(links=())
    gate = IssueCorrelationSymmetryGate.evaluate(snapshot)
    first = IssueCorrelationReconciler.inspect(snapshot)
    repeated = IssueCorrelationReconciler.inspect(snapshot)

    assert gate.passed is False
    assert first == repeated
    assert first.status == "repair_required"
    assert [item.action for item in first.actions] == ["restore_typed_link"]
    assert IssueCorrelationSymmetryGate.evaluate(_snapshot()).passed is True


def test_subject_content_mismatch_is_conflicting_and_not_auto_repaired() -> None:
    report = IssueCorrelationReconciler.inspect(
        _snapshot(subject_content_hash="e" * 64)
    )

    assert report.status == "conflicting"
    assert report.actions == ()
    assert "冻结 subject 内容哈希不一致。" in report.problems


def test_pending_intent_prevents_symmetry_commit() -> None:
    intent = _intent()
    snapshot = _snapshot(pending=(intent.intent_id,))

    gate = IssueCorrelationSymmetryGate.evaluate(snapshot)
    report = IssueCorrelationReconciler.inspect(snapshot)

    assert gate.passed is False
    assert [item.action for item in report.actions] == [
        "commit_iteration_relation"
    ]


def test_query_resolves_by_subject_and_pages_append_only_observations() -> None:
    async def scenario() -> None:
        repository = IssueCorrelationRepository()
        intent = await repository.create_intent(_intent())
        await repository.observe_legacy_issue(
            intent_id=intent.intent_id,
            issue_id="issue_a",
            status="todo",
            content_hash="d" * 64,
            evidence_refs=("readback",),
        )
        service = IssueCorrelationQueryService(repository)
        service.register(_snapshot())

        status = service.get_by_subject("b" * 64)
        page = await service.list_observations(
            intent_id=intent.intent_id,
            page=1,
            page_size=1,
        )

        assert status.symmetry.passed is True
        assert page.total == 2
        assert len(page.items) == 1
        assert page.total_pages == 2

    _run(scenario())
