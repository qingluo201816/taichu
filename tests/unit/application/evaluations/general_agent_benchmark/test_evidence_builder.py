"""需求 7.1—7.23：八类 Runtime 事实到证据包与五类观察工件。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

from taichu.application.contracts.runtime_evidence import (
    CheckpointSourceRecord,
    ContextSourceRecord,
    EffectSourceRecord,
    EvidenceItem,
    EvidenceProblem,
    InvocationSourceRecord,
    NodeSourceRecord,
    ReplaySourceRecord,
    RunSourceRecord,
    UsageSourceRecord,
)
from taichu.application.evaluations.general_agent_benchmark.evidence_builder import (
    EvidenceBuildRequest,
    EvidenceBundleBuilder,
    ObservedArtifactAvailability,
)
from taichu.application.evaluations.general_agent_benchmark.models import ArtifactType
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    EvidenceAvailability,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


class _Reader:
    def __init__(
        self,
        *,
        missing: str | None = None,
        corrupt: str | None = None,
        mismatched_run: bool = False,
    ) -> None:
        self.missing = missing
        self.corrupt = corrupt
        self.mismatched_run = mismatched_run

    def _unavailable(self, kind: str) -> EvidenceItem[object] | None:
        if self.corrupt == kind:
            raise OSError(f"{kind} 无法读取")
        if self.missing == kind:
            return EvidenceItem(
                value=None,
                availability=EvidenceAvailability.MISSING,
                problems=(
                    EvidenceProblem(
                        code="missing",
                        message=f"{kind} 不存在",
                    ),
                ),
            )
        return None

    async def read_run(self, run_id: str) -> EvidenceItem[RunSourceRecord]:
        if item := self._unavailable("run"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=RunSourceRecord(
                run_id=run_id,
                task_id="task_fixture",
                conversation_id="conversation_fixture",
                status="completed",
                plan_revision=1,
                context_snapshot_id="context_fixture",
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_nodes(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[NodeSourceRecord, ...]]:
        if item := self._unavailable("nodes"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=(
                NodeSourceRecord(
                    run_id="other_run" if self.mismatched_run else run_id,
                    plan_revision=1,
                    node_id="read",
                    status="success",
                    attempt_id="attempt_" + "a" * 32,
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_invocations(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]:
        if item := self._unavailable("invocations"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=(
                InvocationSourceRecord(
                    call_id="call_llm",
                    run_id=run_id,
                    capability_type="llm",
                    capability_name="orchestrator",
                    status="completed",
                    started_at="2026-07-27T00:00:00Z",
                ),
                InvocationSourceRecord(
                    call_id="call_tool",
                    parent_call_id="call_llm",
                    run_id=run_id,
                    capability_type="tool",
                    capability_name="read_manuscript",
                    status="completed",
                    started_at="2026-07-27T00:00:01Z",
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_context(
        self,
        snapshot_id: str,
        run_id: str,
    ) -> EvidenceItem[ContextSourceRecord]:
        if item := self._unavailable("context"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=ContextSourceRecord(
                snapshot_id=snapshot_id,
                run_id=run_id,
                conversation_id="conversation_fixture",
                content_sha256="a" * 64,
                category_stats=({"category": "working_memory", "count": 1},),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_checkpoint(
        self,
        thread_id: str,
    ) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]:
        if item := self._unavailable("checkpoint"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=(
                CheckpointSourceRecord(
                    thread_id=thread_id,
                    revision=1,
                    previous_sha256=None,
                    content_sha256="b" * 64,
                    integrity="valid",
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_effects(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[EffectSourceRecord, ...]]:
        if item := self._unavailable("effects"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=(
                EffectSourceRecord(
                    effect_id="effect_" + "c" * 32,
                    attempt_id="attempt_" + "a" * 32,
                    run_id=run_id,
                    plan_revision=1,
                    node_id="read",
                    status="completed",
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_llm_replays(
        self,
        run_id: str,
    ) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]:
        if item := self._unavailable("replays"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=(
                ReplaySourceRecord(
                    call_id="call_llm",
                    run_id=run_id,
                    provider="fixture",
                    model_id="fixture-model",
                    status="completed",
                    request_sha256="c" * 64,
                    response_sha256="d" * 64,
                    started_at="2026-07-27T00:00:00Z",
                ),
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )

    async def read_llm_usage(
        self,
        call_ids: tuple[str, ...],
    ) -> EvidenceItem[tuple[UsageSourceRecord, ...]]:
        if item := self._unavailable("usage"):
            return item  # type: ignore[return-value]
        return EvidenceItem(
            value=tuple(
                UsageSourceRecord(
                    call_id=call_id,
                    run_id="general_run_20260727_000000_abcdef",
                    provider="fixture",
                    model_id="fixture-model",
                    status="completed",
                    total_tokens=10,
                )
                for call_id in call_ids
            ),
            availability=EvidenceAvailability.AVAILABLE,
        )


def _request() -> EvidenceBuildRequest:
    return EvidenceBuildRequest(
        suite_id="general_writing_agent_core",
        case_id="single_manuscript_search",
        case_execution_id="benchmark_case_" + "a" * 32,
        run_id="general_run_20260727_000000_abcdef",
        checkpoint_thread_id="thread_fixture",
        track="live_provider",
        fixture_snapshot_id="fixture_" + "f" * 64,
    )


def test_complete_sources_build_deterministic_bundle_and_five_artifact_slots() -> None:
    first = _run(EvidenceBundleBuilder(_Reader()).build(_request()))
    second = _run(EvidenceBundleBuilder(_Reader()).build(_request()))

    assert first.bundle == second.bundle
    assert set(first.bundle.availability) == {
        "run",
        "nodes",
        "invocations",
        "context",
        "checkpoint",
        "effects",
        "replays",
        "usage",
    }
    assert set(first.bundle.availability.values()) == {
        EvidenceAvailability.AVAILABLE
    }
    assert {item.artifact_type for item in first.artifacts} == set(ArtifactType)
    assert len(first.artifacts) == 5


def test_missing_or_unreadable_source_is_preserved_without_invented_artifacts() -> None:
    missing = _run(
        EvidenceBundleBuilder(_Reader(missing="context")).build(_request())
    )
    corrupt = _run(
        EvidenceBundleBuilder(_Reader(corrupt="checkpoint")).build(_request())
    )

    assert missing.bundle.availability["context"] is EvidenceAvailability.MISSING
    assert corrupt.bundle.availability["checkpoint"] is EvidenceAvailability.CORRUPT
    assert missing.bundle.problems
    assert corrupt.bundle.problems
    assert any(
        item.availability is ObservedArtifactAvailability.UNAVAILABLE
        for item in missing.artifacts
    )


def test_cross_run_record_marks_source_conflicting_instead_of_repairing_by_similarity() -> None:
    result = _run(
        EvidenceBundleBuilder(_Reader(mismatched_run=True)).build(_request())
    )

    assert (
        result.bundle.availability["nodes"]
        is EvidenceAvailability.CONFLICTING
    )
    assert any("run_id" in problem for problem in result.bundle.problems)
