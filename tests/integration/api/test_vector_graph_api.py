"""Vector Graph RAG 索引同步与状态 API 测试。"""

from pathlib import Path
import tempfile
import unittest

from httpx import ASGITransport, AsyncClient

from taichu.application.vector_graph import (
    VectorGraphBuildPlan,
    VectorGraphBuildStartResult,
    VectorGraphIndexState,
    VectorGraphIndexStatus,
)
from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class _StatusService:
    def __init__(self) -> None:
        self.start_calls = 0

    async def status(self) -> VectorGraphIndexStatus:
        return VectorGraphIndexStatus(
            state=VectorGraphIndexState.NOT_BUILT,
            current_plan=VectorGraphBuildPlan(
                snapshot_sha256="c" * 64,
                manuscript_count=100,
                manuscript_chunk_count=1753,
                knowledge_card_count=305,
                document_count=2058,
                total_content_chars=570546,
            ),
            message="尚未建立向量图谱索引。",
        )

    async def start_update(self) -> VectorGraphBuildStartResult:
        self.start_calls += 1
        return VectorGraphBuildStartResult(
            accepted=True,
            message="RAG 索引同步已开始。",
            plan=(await self.status()).current_plan,
        )


class VectorGraphApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        app = create_app(
            app_settings=Settings(
                project_assets_dir=Path(self._temporary_directory.name)
            ),
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
        self.service = _StatusService()
        app.state.vector_graph_rag_service = self.service
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_status_is_available_as_read_only_api(self) -> None:
        response = await self.client.get("/api/vector-graph/status")
        mutation = await self.client.post("/api/vector-graph/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "not_built")
        self.assertEqual(payload["current_plan"]["document_count"], 2058)
        self.assertEqual(payload["message"], "尚未建立向量图谱索引。")
        self.assertEqual(mutation.status_code, 405)

    async def test_update_starts_as_background_task_and_rebuild_is_removed(
        self,
    ) -> None:
        response = await self.client.post("/api/vector-graph/update")
        removed_rebuild = await self.client.post("/api/vector-graph/rebuild")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted"], True)
        self.assertEqual(response.json()["message"], "RAG 索引同步已开始。")
        self.assertEqual(response.json()["plan"]["document_count"], 2058)
        self.assertEqual(self.service.start_calls, 1)
        self.assertEqual(removed_rebuild.status_code, 404)
