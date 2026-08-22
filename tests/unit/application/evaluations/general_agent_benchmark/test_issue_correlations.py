"""需求 15.6-15.32：确定性问题意图与 revision 关联仓储。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

import pytest

from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueCorrelationIntent,
    IssueCorrelationRepository,
    IssueCorrelationRevisionConflict,
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
        frozen_subject_id="first_live_subject_a",
        classification="system_defect",
        evidence_refs=("evidence_a",),
    )


def test_same_failure_creates_one_deterministic_intent() -> None:
    async def scenario() -> None:
        repository = IssueCorrelationRepository()
        first = await repository.create_intent(_intent())
        repeated = await repository.create_intent(_intent())

        assert repeated == first
        assert len(await repository.list_intents()) == 1
        assert first.stable_issue_key.startswith("benchmark_issue_")

    _run(scenario())


def test_legacy_issue_projects_revision_zero_then_appends_monotonically() -> None:
    async def scenario() -> None:
        repository = IssueCorrelationRepository()
        intent = await repository.create_intent(_intent())
        legacy = await repository.observe_legacy_issue(
            intent_id=intent.intent_id,
            issue_id="issue_legacy",
            status="todo",
            content_hash="b" * 64,
            evidence_refs=("legacy_readback",),
        )
        first = await repository.append_revision(
            intent_id=intent.intent_id,
            issue_id="issue_legacy",
            expected_revision=0,
            status="todo",
            content_hash="c" * 64,
            evidence_refs=("create_response", "create_readback"),
        )
        second = await repository.append_revision(
            intent_id=intent.intent_id,
            issue_id="issue_legacy",
            expected_revision=1,
            status="processed",
            content_hash="d" * 64,
            evidence_refs=("close_response", "close_readback"),
        )

        assert (legacy.revision, first.revision, second.revision) == (0, 1, 2)
        assert [
            item.revision
            for item in await repository.list_revisions(intent.intent_id)
        ] == [0, 1, 2]
        assert all(
            item.evidence_refs
            for item in await repository.list_revisions(intent.intent_id)
        )

    _run(scenario())


def test_competing_cas_updates_only_allow_one_winner() -> None:
    async def scenario() -> None:
        repository = IssueCorrelationRepository()
        intent = await repository.create_intent(_intent())
        await repository.observe_legacy_issue(
            intent_id=intent.intent_id,
            issue_id="issue_competing",
            status="todo",
            content_hash="b" * 64,
            evidence_refs=("legacy_readback",),
        )

        async def update(content_hash: str) -> object:
            return await repository.append_revision(
                intent_id=intent.intent_id,
                issue_id="issue_competing",
                expected_revision=0,
                status="todo",
                content_hash=content_hash,
                evidence_refs=("cas_response",),
            )

        results = await asyncio.gather(
            update("c" * 64),
            update("d" * 64),
            return_exceptions=True,
        )

        assert sum(
            isinstance(item, IssueCorrelationRevisionConflict)
            for item in results
        ) == 1
        assert (await repository.latest_revision(intent.intent_id)).revision == 1
        observations = await repository.list_observations(intent.intent_id)
        assert [item.sequence for item in observations] == list(
            range(1, len(observations) + 1)
        )

    _run(scenario())


def test_issue_identity_mismatch_cannot_silently_rebind_intent() -> None:
    async def scenario() -> None:
        repository = IssueCorrelationRepository()
        intent = await repository.create_intent(_intent())
        await repository.observe_legacy_issue(
            intent_id=intent.intent_id,
            issue_id="issue_a",
            status="todo",
            content_hash="b" * 64,
            evidence_refs=("readback_a",),
        )

        with pytest.raises(ValueError, match="绑定"):
            await repository.append_revision(
                intent_id=intent.intent_id,
                issue_id="issue_b",
                expected_revision=0,
                status="todo",
                content_hash="c" * 64,
                evidence_refs=("readback_b",),
            )

    _run(scenario())
