"""Tests for atomic file-backed evaluation result persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationMode,
    EvaluationPhase,
    EvaluationProgress,
    EvaluationRunResult,
    EvaluationStatus,
    JudgeSummary,
    KnowledgeEvaluationRecord,
)
from taichu.infrastructure.evaluations.json_result_store import (
    EvaluationResultStoreError,
    JsonEvaluationResultStore,
    _write_json,
)


class JsonEvaluationResultStoreTest(unittest.IsolatedAsyncioTestCase):
    """Verify snapshot publication, CAS, filtering, and corruption checks."""

    async def test_publish_read_and_verify_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))
            record = _record("knowledge_eval_20260711_120000_a1b2c3")

            published = await store.publish_pending(
                record,
                {
                    "dataset_manifest.json": b"{}\n",
                    "runs/extract_run_20260711_120000_a1b2c3.json": b"{}\n",
                },
            )
            loaded = await store.get_record(record.evaluation_id)
            snapshot = await store.read_snapshot_files(record.evaluation_id)

            self.assertNotEqual(published.snapshot_root_hash, "pending")
            self.assertEqual(loaded, published)
            self.assertEqual(snapshot["dataset_manifest.json"], b"{}\n")

    async def test_rejects_active_duplicate_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))
            first = _record("knowledge_eval_20260711_120000_a1b2c3")
            second = _record("knowledge_eval_20260711_120001_d4e5f6")
            await store.publish_pending(first, {"dataset.json": b"{}"})

            with self.assertRaises(EvaluationResultStoreError) as context:
                await store.publish_pending(second, {"dataset.json": b"{}"})

            self.assertEqual(context.exception.code, "EVALUATION_ALREADY_RUNNING")

    async def test_writes_run_result_before_summary_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))
            record = _record("knowledge_eval_20260711_120000_a1b2c3")
            await store.publish_pending(record, {"dataset.json": b"{}"})
            run_result = EvaluationRunResult(
                run_id="extract_run_20260711_120000_a1b2c3",
                case_id="chapter_001",
                eligibility_level="full",
                generation_model_identity=LLMModelIdentity.unknown(
                    "测试运行未提供模型身份。"
                ),
            )

            await store.write_run_result(record.evaluation_id, run_result)
            loaded = await store.get_run_result(
                record.evaluation_id,
                run_result.run_id,
            )

            self.assertEqual(loaded, run_result)

    async def test_mutation_honors_status_and_execution_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))
            record = _record("knowledge_eval_20260711_120000_a1b2c3")
            await store.publish_pending(record, {"dataset.json": b"{}"})
            running = await store.mutate_record(
                record.evaluation_id,
                {
                    "status": EvaluationStatus.RUNNING,
                    "phase": EvaluationPhase.DETERMINISTIC,
                    "execution_token": "worker-token",
                },
                expected_status="pending",
            )

            with self.assertRaises(EvaluationResultStoreError):
                await store.mutate_record(
                    record.evaluation_id,
                    {"heartbeat_at": _now()},
                    expected_status="running",
                    expected_execution_token="wrong-token",
                )

            self.assertEqual(running.execution_token, "worker-token")

    async def test_rejected_records_are_hidden_from_default_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))
            record = _record("knowledge_eval_20260711_120000_a1b2c3")
            await store.publish_pending(record, {"dataset.json": b"{}"})
            await store.mutate_record(
                record.evaluation_id,
                {"lifecycle": EvaluationLifecycle.REJECTED},
                expected_status="pending",
            )

            records, total = await store.list_records(
                page=1,
                page_size=20,
                status="all",
            )

            self.assertEqual(records, [])
            self.assertEqual(total, 0)

    async def test_rejects_invalid_evaluation_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonEvaluationResultStore(Path(directory))

            with self.assertRaises(EvaluationResultStoreError) as context:
                await store.get_record("../summary")

            self.assertEqual(context.exception.code, "EVALUATION_ID_INVALID")

    async def test_detects_snapshot_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            assets_root = Path(directory)
            store = JsonEvaluationResultStore(assets_root)
            record = _record("knowledge_eval_20260711_120000_a1b2c3")
            await store.publish_pending(record, {"dataset.json": b"{}"})
            snapshot_path = (
                assets_root
                / "derived"
                / "agent_evaluations"
                / "knowledge_extraction"
                / record.evaluation_id
                / "input_snapshot"
                / "dataset.json"
            )
            snapshot_path.write_bytes(b"changed")

            with self.assertRaises(EvaluationResultStoreError) as context:
                await store.read_snapshot_files(record.evaluation_id)

            self.assertEqual(context.exception.code, "EVALUATION_SNAPSHOT_CORRUPTED")

    def test_atomic_write_retries_transient_windows_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "summary.json"
            original_replace = Path.replace
            attempts = 0

            def flaky_replace(source: Path, destination: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("transient sharing violation")
                return original_replace(source, destination)

            with (
                patch.object(Path, "replace", new=flaky_replace),
                patch(
                    "taichu.infrastructure.evaluations.json_result_store.sleep"
                ) as mocked_sleep,
            ):
                _write_json(target, {"status": "completed"})

            self.assertEqual(attempts, 3)
            self.assertEqual(mocked_sleep.call_count, 2)
            self.assertIn('"completed"', target.read_text(encoding="utf-8"))


def _record(evaluation_id: str) -> KnowledgeEvaluationRecord:
    now = _now()
    return KnowledgeEvaluationRecord(
        evaluation_id=evaluation_id,
        request_fingerprint="same-fingerprint",
        evaluation_mode=EvaluationMode.DETERMINISTIC_ONLY,
        dataset_id="demo_dataset",
        dataset_label="演示评测集",
        dataset_checksum="dataset-checksum",
        judge=JudgeSummary(enabled=False),
        progress=EvaluationProgress(run_total=1),
        run_ids=["extract_run_20260711_120000_a1b2c3"],
        created_at=now,
        updated_at=now,
        heartbeat_at=now,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
