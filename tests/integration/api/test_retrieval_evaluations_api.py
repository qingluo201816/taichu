"""统一召回专项评测只读 API 全链路测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class RetrievalEvaluationsApiTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_dataset_list_and_detail_are_read_only_and_content_safe(
        self,
    ) -> None:
        record = await self.app.state.retrieval_evaluation_service.evaluate(
            dataset_id="retrieval_knowledge_core",
            strategy="mongo_lexical",
            environment={"python": "test"},
        )

        dataset_response = await self.client.get(
            "/api/agent-evaluations/retrieval/datasets/retrieval_knowledge_core"
        )
        self.assertEqual(dataset_response.status_code, 200)
        dataset = dataset_response.json()["dataset"]
        self.assertEqual(len(dataset["cases"]), 60)
        self.assertEqual(len(dataset["checksum"]), 64)
        self.assertIn("query_text", dataset["cases"][0])
        self.assertNotIn("knowledge_card", json.dumps(dataset, ensure_ascii=False))

        list_response = await self.client.get(
            "/api/agent-evaluations/retrieval/evaluations?limit=10"
        )
        self.assertEqual(list_response.status_code, 200)
        listing = list_response.json()["evaluations"]
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["evaluation_id"], record.evaluation_id)
        self.assertEqual(listing[0]["summary"]["case_count"], 60)
        self.assertNotIn("cases", listing[0])

        detail_response = await self.client.get(
            f"/api/agent-evaluations/retrieval/evaluations/{record.evaluation_id}"
        )
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()["evaluation"]
        self.assertEqual(len(detail["cases"]), 60)
        serialized = json.dumps(detail, ensure_ascii=False)
        self.assertNotIn("query_text", serialized)
        self.assertNotIn("knowledge_card", serialized)

        post_response = await self.client.post(
            "/api/agent-evaluations/retrieval/evaluations",
            json={},
        )
        self.assertEqual(post_response.status_code, 405)

    async def test_missing_dataset_and_evaluation_return_404(self) -> None:
        dataset_response = await self.client.get(
            "/api/agent-evaluations/retrieval/datasets/missing_dataset"
        )
        evaluation_response = await self.client.get(
            "/api/agent-evaluations/retrieval/evaluations/"
            "retrieval_eval_20260718_000000_abcdef"
        )

        self.assertEqual(dataset_response.status_code, 404)
        self.assertEqual(evaluation_response.status_code, 404)
