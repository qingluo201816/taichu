"""API contract tests for knowledge-extraction effect evaluation."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest.mock import AsyncMock, Mock, patch

from httpx import ASGITransport, AsyncClient

from taichu.api.deps import provide_knowledge_extraction_evaluation_service
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationResult,
    EvaluationDatasetSummary,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationComparison,
    EvaluationMode,
    EvaluationProgress,
    IndependenceLevel,
    JudgeCallRecord,
    JudgeSummary,
    KnowledgeEvaluationRecord,
)
from taichu.application.services.knowledge_extraction_evaluation_service import (
    EvaluationServiceError,
)
from taichu.config import Settings
from taichu.infrastructure.llm.unavailable import UnavailableLLMChatModel
from taichu.main import create_app


_PREFIX = "/api/agent-evaluations/knowledge-extraction"
_DATASET_ID = "demo_evaluation_dataset"
_RUN_ID = "extract_run_20260711_120000_a1b2c3"
_EVALUATION_ID = "knowledge_eval_20260711_120100_d4e5f6"
_RETRY_ID = "knowledge_eval_20260711_120200_aabbcc"
_CALL_ID = "judge_call_a1b2c3d4e5f6"
_IDENTITY = LLMModelIdentity(
    provider="test",
    model_id="judge-model",
    family="judge-family",
    endpoint_kind="test",
    known=True,
)


class AgentEvaluationsApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self._temporary_directory.name)
        self.service = _FakeEvaluationService()
        self.app = create_app(
            _settings(
                project_assets_dir=root / "assets",
                evaluation_datasets_dir=root / "datasets",
            ),
            llm=UnavailableLLMChatModel(),
            llm_model_identity=_IDENTITY,
        )
        self.app.dependency_overrides[
            provide_knowledge_extraction_evaluation_service
        ] = lambda: self.service
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_dataset_validation_and_eligible_run_contracts(self) -> None:
        datasets = await self.client.get(f"{_PREFIX}/datasets")
        detail = await self.client.get(f"{_PREFIX}/datasets/{_DATASET_ID}")
        validation = await self.client.post(
            f"{_PREFIX}/datasets/{_DATASET_ID}/validate"
        )
        eligible = await self.client.get(
            f"{_PREFIX}/eligible-runs",
            params={"dataset_id": _DATASET_ID, "page": 1, "page_size": 50},
        )

        self.assertEqual(datasets.status_code, 200)
        self.assertEqual(datasets.json()["datasets"][0]["dataset_id"], _DATASET_ID)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(validation.json()["validation"]["valid"])
        self.assertEqual(eligible.status_code, 200)
        self.assertEqual(eligible.json()["runs"][0]["run_id"], _RUN_ID)
        self.assertEqual(
            eligible.json()["runs"][0]["generation_model_identity"]["model_id"],
            "judge-model",
        )

    async def test_preview_does_not_persist_and_preserves_judge_contract(self) -> None:
        response = await self.client.post(
            f"{_PREFIX}/preview",
            json=_request_payload(judge_enabled=False),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["can_create"])
        self.assertEqual(payload["evaluation_mode"], "deterministic_only")
        self.assertFalse(payload["judge"]["requested"])
        self.assertIsNone(payload["judge"]["available"])
        self.assertIsNone(payload["judge"]["model_identity"])
        self.assertEqual(payload["estimate"]["judge_card_count"], 0)
        self.assertEqual(self.service.created_count, 0)

    async def test_create_returns_202_rounds_floats_and_hides_execution_token(
        self,
    ) -> None:
        response = await self.client.post(
            f"{_PREFIX}/evaluations",
            json=_request_payload(),
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["evaluation_id"], _EVALUATION_ID)
        self.assertNotIn("execution_token", payload)
        self.assertEqual(payload["aggregate_metrics"]["candidate_f1_micro"], 0.1235)
        self.assertEqual(
            payload["poll_url"],
            f"{_PREFIX}/evaluations/{_EVALUATION_ID}",
        )
        self.assertEqual(payload["dataset"]["dataset_id"], _DATASET_ID)

    async def test_request_cannot_inject_json_path_or_more_than_ten_runs(self) -> None:
        injected = {**_request_payload(), "expected_json_path": "../secret.json"}
        injection_response = await self.client.post(
            f"{_PREFIX}/evaluations",
            json=injected,
        )
        too_many_response = await self.client.post(
            f"{_PREFIX}/evaluations",
            json={
                **_request_payload(),
                "run_ids": [
                    f"extract_run_20260711_12{index:04d}_a1b2c3" for index in range(11)
                ],
            },
        )

        self.assertEqual(injection_response.status_code, 422)
        self.assertEqual(
            injection_response.json()["error"]["code"],
            "VALIDATION_ERROR",
        )
        self.assertEqual(too_many_response.status_code, 422)
        self.assertIn("请求内容", too_many_response.json()["error"]["message"])

    async def test_history_detail_comparisons_and_judge_call(self) -> None:
        history = await self.client.get(f"{_PREFIX}/evaluations")
        detail = await self.client.get(f"{_PREFIX}/evaluations/{_EVALUATION_ID}")
        comparisons = await self.client.get(
            f"{_PREFIX}/evaluations/{_EVALUATION_ID}/comparisons",
            params={"run_id": _RUN_ID},
        )
        judge_call = await self.client.get(
            f"{_PREFIX}/evaluations/{_EVALUATION_ID}/judge-calls/{_CALL_ID}"
        )

        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 1)
        self.assertNotIn("execution_token", detail.json()["evaluation"])
        comparison = comparisons.json()["comparisons"][0]
        self.assertEqual(comparison["display_title"], "秦浩轩")
        self.assertEqual(comparison["actual_review_item_id"], "review-1")
        self.assertEqual(comparison["judge_result"]["confidence"], 0.9877)
        self.assertEqual(judge_call.status_code, 200)
        self.assertEqual(judge_call.json()["judge_call"]["call_id"], _CALL_ID)

    async def test_retry_confirm_and_soft_delete(self) -> None:
        retry = await self.client.post(f"{_PREFIX}/evaluations/{_EVALUATION_ID}/retry")
        confirm = await self.client.post(
            f"{_PREFIX}/evaluations/{_EVALUATION_ID}/confirm"
        )
        reject = await self.client.delete(f"{_PREFIX}/evaluations/{_EVALUATION_ID}")

        self.assertEqual(retry.status_code, 202)
        self.assertEqual(retry.json()["evaluation_id"], _RETRY_ID)
        self.assertEqual(retry.json()["parent_evaluation_id"], _EVALUATION_ID)
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()["lifecycle"], "confirmed")
        self.assertEqual(reject.status_code, 200)
        self.assertEqual(reject.json()["lifecycle"], "rejected")
        self.assertTrue(self.service.rejected)

    async def test_service_errors_use_stable_http_status_and_chinese_message(
        self,
    ) -> None:
        self.service.create_error = EvaluationServiceError(
            "EVALUATION_JUDGE_UNAVAILABLE",
            "语义裁判当前不可用。",
        )

        response = await self.client.post(
            f"{_PREFIX}/evaluations",
            json=_request_payload(),
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "EVALUATION_JUDGE_UNAVAILABLE",
                    "message": "语义裁判当前不可用。",
                }
            },
        )

    async def test_invalid_and_encoded_path_ids_fail_closed(self) -> None:
        invalid = await self.client.get(f"{_PREFIX}/evaluations/not-an-id")
        double_encoded = await self.client.get(
            f"{_PREFIX}/evaluations/%252e%252e%252fsecret"
        )
        invalid_call = await self.client.get(
            f"{_PREFIX}/evaluations/{_EVALUATION_ID}/judge-calls/%252e%252e"
        )
        invalid_dataset = await self.client.get(f"{_PREFIX}/datasets/%252e%252e")

        for response in (
            invalid,
            double_encoded,
            invalid_call,
            invalid_dataset,
        ):
            self.assertEqual(response.status_code, 422)
            self.assertEqual(
                response.json()["error"]["code"],
                "EVALUATION_ID_INVALID",
            )

    async def test_application_lifespan_recovers_and_stops_evaluation_workers(
        self,
    ) -> None:
        evaluation_service = self.app.state.knowledge_extraction_evaluation_service
        with (
            patch.object(
                evaluation_service,
                "recover_interrupted",
                new=AsyncMock(),
            ) as recover,
            patch.object(
                evaluation_service,
                "start_watchdog",
                new=Mock(),
            ) as start_watchdog,
            patch.object(
                evaluation_service,
                "shutdown",
                new=AsyncMock(),
            ) as shutdown,
        ):
            async with self.app.router.lifespan_context(self.app):
                recover.assert_awaited_once_with()
                start_watchdog.assert_called_once_with()
            shutdown.assert_awaited_once_with()


class _FakeEvaluationService:
    def __init__(self) -> None:
        self.record = _record()
        self.created_count = 0
        self.create_error: EvaluationServiceError | None = None
        self.rejected = False

    async def list_datasets(self) -> list[EvaluationDatasetSummary]:
        return [_dataset_summary()]

    async def get_dataset(self, dataset_id: str) -> EvaluationDatasetSummary:
        return _dataset_summary()

    async def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        return DatasetValidationResult(
            dataset_id=dataset_id,
            valid=True,
            lifecycle=EvaluationLifecycle.CONFIRMED,
            checksum="a" * 64,
        )

    async def list_eligible_runs(
        self,
        *,
        dataset_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, object]], int]:
        return [
            {
                "run_id": _RUN_ID,
                "case_id": "chapter_001",
                "status": "completed",
                "scope_type": "chapter",
                "chapter_id": "chapter-demo001",
                "chapter_title": "第一章",
                "chapter_ids": ["chapter-demo001"],
                "chapter_titles": ["第一章"],
                "total_chapter_count": 1,
                "started_at": "2026-07-11T12:00:00Z",
                "requested_model_name": None,
                "model_name": "generation-model",
                "generation_model_identity": _IDENTITY,
                "prompt_version": "knowledge_extraction_prompt_v2",
                "schema_version": "knowledge_fields_v2",
                "eligibility_level": "full",
                "reason": None,
                "suggested_card_available": True,
                "latest_evaluation": None,
            }
        ], 1

    async def preview(self, **request: object) -> dict[str, object]:
        judge_enabled = bool(request["judge_enabled"])
        return {
            "can_create": True,
            "evaluation_mode": (
                "deterministic_and_judge" if judge_enabled else "deterministic_only"
            ),
            "has_diagnostic_runs": False,
            "dataset": {"dataset_id": _DATASET_ID, "checksum": "a" * 64},
            "runs": [
                {
                    "run_id": _RUN_ID,
                    "case_id": "chapter_001",
                    "eligibility_level": "full",
                    "reason": None,
                    "generation_model_identity": _IDENTITY,
                    "independence_level": (
                        IndependenceLevel.SAME_MODEL if judge_enabled else None
                    ),
                    "expected_card_count": 1,
                    "estimated_matched_card_count": 1,
                    "estimated_judge_card_count": 1 if judge_enabled else 0,
                }
            ],
            "judge": {
                "requested": judge_enabled,
                "available": True if judge_enabled else None,
                "model_identity": _IDENTITY if judge_enabled else None,
                "unavailable_reason": None,
            },
            "estimate": {
                "run_count": 1,
                "expected_card_count": 1,
                "matched_card_count": 1,
                "judge_card_count": 1 if judge_enabled else 0,
                "judge_batch_count": 1 if judge_enabled else 0,
            },
            "warnings": [],
            "blocking_errors": [],
        }

    async def create_evaluation(self, **request: object) -> KnowledgeEvaluationRecord:
        if self.create_error:
            raise self.create_error
        self.created_count += 1
        return self.record

    async def list_evaluations(
        self,
        *,
        page: int,
        page_size: int,
        status: str,
    ) -> tuple[list[KnowledgeEvaluationRecord], int]:
        return [self.record], 1

    async def get_evaluation(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord:
        return self.record

    async def list_comparisons(
        self,
        evaluation_id: str,
        *,
        page: int,
        page_size: int,
        run_id: str | None,
        knowledge_type: str | None,
        issue_type: str | None,
    ) -> tuple[list[EvaluationComparison], int]:
        return [
            EvaluationComparison(
                run_id=_RUN_ID,
                case_id="chapter_001",
                knowledge_type="character",
                issue_type="field_difference",
                expected_card_id="character_qin",
                actual_candidate_id="review-1",
                expected_card={"name": "秦浩轩"},
                actual_card={"name": "秦浩轩"},
                match_kind="exact_name",
                judge_result={"confidence": 0.987654},
            )
        ], 1

    async def get_judge_call(
        self,
        evaluation_id: str,
        call_id: str,
    ) -> JudgeCallRecord:
        return JudgeCallRecord(
            call_id=call_id,
            evaluation_id=evaluation_id,
            run_ids=[_RUN_ID],
            judge_model_identity=_IDENTITY,
            independence_level=IndependenceLevel.SAME_MODEL,
            prompt_contract_id="knowledge_extraction_judge",
            prompt_hash="a" * 64,
            input_snapshot_hash="b" * 64,
            input_prompt="裁判输入",
            raw_response="{}",
            parsed_output={},
            started_at="2026-07-11T12:00:00Z",
            finished_at="2026-07-11T12:00:01Z",
            duration_ms=1000,
        )

    async def retry_evaluation(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord:
        return self.record.model_copy(
            update={
                "evaluation_id": _RETRY_ID,
                "parent_evaluation_id": evaluation_id,
            }
        )

    async def confirm_evaluation(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord:
        return self.record.model_copy(
            update={"lifecycle": EvaluationLifecycle.CONFIRMED}
        )

    async def reject_evaluation(self, evaluation_id: str) -> None:
        self.rejected = True


def _dataset_summary() -> EvaluationDatasetSummary:
    return EvaluationDatasetSummary(
        dataset_id=_DATASET_ID,
        label="演示评测集",
        lifecycle=EvaluationLifecycle.CONFIRMED,
        case_count=1,
        valid=True,
        checksum="a" * 64,
    )


def _record() -> KnowledgeEvaluationRecord:
    return KnowledgeEvaluationRecord(
        evaluation_id=_EVALUATION_ID,
        request_fingerprint="f" * 64,
        snapshot_root_hash="s" * 64,
        evaluation_mode=EvaluationMode.DETERMINISTIC_AND_JUDGE,
        dataset_id=_DATASET_ID,
        dataset_label="演示评测集",
        dataset_checksum="a" * 64,
        judge=JudgeSummary(
            enabled=True,
            model_identity=_IDENTITY,
            self_judge=True,
            independence_by_run={_RUN_ID: IndependenceLevel.SAME_MODEL},
        ),
        progress=EvaluationProgress(run_total=1, judge_card_total=1),
        run_ids=[_RUN_ID],
        aggregate_metrics={"candidate_f1_micro": 0.123456},
        created_at="2026-07-11T12:01:00Z",
        updated_at="2026-07-11T12:01:00Z",
        heartbeat_at="2026-07-11T12:01:00Z",
        execution_token="backend-secret-token",
    )


def _request_payload(*, judge_enabled: bool = True) -> dict[str, object]:
    return {
        "dataset_id": _DATASET_ID,
        "run_ids": [_RUN_ID],
        "judge_enabled": judge_enabled,
        "metric_profile_id": "knowledge_extraction_balanced",
    }


def _settings(**values: Any) -> Settings:
    return Settings(**{"_env_file": None, **values})


if __name__ == "__main__":
    unittest.main()
