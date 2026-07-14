"""通用写作助手专属评测 API 全链路测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentLifecycleEvent,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class GeneralAgentEvaluationsApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        fixtures = (
            Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "evaluations"
        )
        self.app = create_app(
            app_settings=Settings(
                project_assets_dir=Path(self._temporary_directory.name),
                evaluation_datasets_dir=fixtures,
            ),
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_dataset_evaluate_list_detail_and_delete(self) -> None:
        run = _direct_answer_run()
        await self.app.state.general_agent_run_repository.save(run)

        datasets = await self.client.get(
            "/api/agent-evaluations/general-agent/datasets"
        )
        self.assertEqual(datasets.status_code, 200)
        selected = next(
            item
            for item in datasets.json()["datasets"]
            if item["dataset_id"] == "general_writing_assistant_core"
        )
        self.assertEqual(len(selected["cases"]), 8)
        self.assertEqual(len(selected["checksum"]), 64)

        created = await self.client.post(
            "/api/agent-evaluations/general-agent/evaluations",
            json={
                "dataset_id": "general_writing_assistant_core",
                "case_id": "direct_conflict_advice",
                "run_id": run.run_id,
            },
        )
        self.assertEqual(created.status_code, 200)
        record = created.json()["evaluation"]
        self.assertTrue(record["passed"])
        self.assertEqual(record["overall_score"], 100)
        evaluation_id = record["evaluation_id"]

        listing = await self.client.get(
            "/api/agent-evaluations/general-agent/evaluations"
        )
        detail = await self.client.get(
            f"/api/agent-evaluations/general-agent/evaluations/{evaluation_id}"
        )
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(detail.json()["evaluation"]["case_id"], "direct_conflict_advice")

        deleted = await self.client.delete(
            f"/api/agent-evaluations/general-agent/evaluations/{evaluation_id}"
        )
        missing = await self.client.get(
            f"/api/agent-evaluations/general-agent/evaluations/{evaluation_id}"
        )
        self.assertTrue(deleted.json()["deleted"])
        self.assertEqual(missing.status_code, 404)


def _direct_answer_run() -> GeneralAgentRun:
    timestamp = "2026-07-14T00:00:00Z"
    return GeneralAgentRun(
        run_id="general_run_20260714_000000_abc123",
        task_id="general_task_test",
        user_goal="写冲突场景时应该先明确什么？",
        status=GeneralAgentRunStatus.COMPLETED,
        plan=GeneralAgentExecutionPlan(
            rationale="通用写作方法问题可以直接回答。",
            direct_response="先明确场景目标。",
        ),
        plan_revision=1,
        final_answer=(
            "先明确双方的场景目标和冲突来源，再控制信息释放，"
            "让阻力升级并以选择收束场景。"
        ),
        lifecycle_events=[
            GeneralAgentLifecycleEvent(
                status=GeneralAgentRunStatus.COMPLETED,
                reason="任务结果已收敛。",
                created_at=timestamp,
            )
        ],
        resumable=False,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
        finished_at=timestamp,
    )
