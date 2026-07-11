"""Persistent evaluation-result repository boundary."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationRunResult,
    JudgeCallRecord,
    KnowledgeEvaluationRecord,
)


@runtime_checkable
class EvaluationResultRepository(Protocol):
    """Atomic persistence needed by the evaluation background service."""

    async def publish_pending(
        self,
        record: KnowledgeEvaluationRecord,
        snapshot_files: dict[str, bytes],
    ) -> KnowledgeEvaluationRecord:
        """Publish a complete frozen snapshot unless an active duplicate exists."""
        ...

    async def get_record(self, evaluation_id: str) -> KnowledgeEvaluationRecord | None:
        """Return one report summary."""
        ...

    async def list_records(
        self,
        *,
        page: int,
        page_size: int,
        status: str,
    ) -> tuple[list[KnowledgeEvaluationRecord], int]:
        """List non-rejected reports newest first."""
        ...

    async def mutate_record(
        self,
        evaluation_id: str,
        updates: dict[str, Any],
        *,
        expected_status: str | None = None,
        expected_execution_token: str | None = None,
    ) -> KnowledgeEvaluationRecord:
        """Atomically patch a summary with optional compare-and-swap guards."""
        ...

    async def write_judge_call(self, call: JudgeCallRecord) -> None:
        """Persist one judge audit record before updating summary progress."""
        ...

    async def write_run_result(
        self,
        evaluation_id: str,
        result: EvaluationRunResult,
    ) -> None:
        """Persist one complete run result before updating summary progress."""
        ...

    async def get_run_result(
        self,
        evaluation_id: str,
        run_id: str,
    ) -> EvaluationRunResult | None:
        """Read one independently stored run result."""
        ...

    async def get_judge_call(
        self,
        evaluation_id: str,
        call_id: str,
    ) -> JudgeCallRecord | None:
        """Read one judge audit record."""
        ...

    async def read_snapshot_files(self, evaluation_id: str) -> dict[str, bytes]:
        """Return the exact frozen input files used by an existing report."""
        ...

    async def find_active_fingerprint(
        self,
        request_fingerprint: str,
    ) -> KnowledgeEvaluationRecord | None:
        """Find an active duplicate request."""
        ...

    async def discard_unstarted(self, evaluation_id: str) -> None:
        """Remove a pending record that was never exposed or claimed."""
        ...
