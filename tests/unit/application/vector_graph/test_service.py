import asyncio
import unittest

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildProgress,
    VectorGraphBuildResult,
    VectorGraphBuildStage,
    VectorGraphIndexState,
    VectorGraphIndexStatus,
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)
from taichu.application.vector_graph.models import VectorGraphExtractedTriplets
from taichu.application.vector_graph.service import VectorGraphRAGService


class _ControlledBackend:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.update_calls = 0
        self.received_documents: list[VectorGraphSourceDocument] | None = None
        self.received_plan: VectorGraphBuildPlan | None = None

    async def inspect(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        return VectorGraphIndexStatus(
            state=VectorGraphIndexState.NOT_BUILT,
            current_plan=plan,
            message="尚未建立向量图谱索引。",
        )

    async def update(
        self,
        documents: list[VectorGraphSourceDocument],
        *,
        plan: VectorGraphBuildPlan,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult:
        del extracted_triplets
        self.update_calls += 1
        self.received_documents = documents
        self.received_plan = plan
        self.started.set()
        await self.release.wait()
        return VectorGraphBuildResult(
            status="completed",
            plan=plan,
            passage_count=len(documents),
        )


class _PersistedBuildingBackend(_ControlledBackend):
    async def inspect(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        return VectorGraphIndexStatus(
            state=VectorGraphIndexState.BUILDING,
            current_plan=plan,
            progress=VectorGraphBuildProgress(
                stage=VectorGraphBuildStage.EXTRACTING,
                snapshot_sha256=plan.snapshot_sha256,
                processed_documents=1,
                total_documents=plan.document_count,
                processed_sources=1,
                total_sources=plan.manuscript_count + plan.knowledge_card_count,
                current_source_key="knowledge_card:test",
                started_at="2026-08-16T00:00:00Z",
                updated_at="2026-08-16T00:01:00Z",
            ),
            message="正在更新索引。",
        )


class _ControlledService(VectorGraphRAGService):
    def __init__(
        self,
        backend: _ControlledBackend,
        documents: list[VectorGraphSourceDocument] | None = None,
    ) -> None:
        self._backend = backend
        self._documents = documents if documents is not None else [_document()]
        self._build_lock = asyncio.Lock()
        self._background_task = None
        self._background_started_at = None
        self._background_finished_at = None
        self._background_error = None

    async def plan(
        self,
    ) -> tuple[VectorGraphBuildPlan, list[VectorGraphSourceDocument]]:
        return _plan(len(self._documents)), self._documents


def _document() -> VectorGraphSourceDocument:
    return VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id="test",
        source_ref="knowledge-card:test",
        title="测试知识卡",
        content="测试内容",
        content_sha256="b" * 64,
        updated_at="2026-08-16T00:00:00Z",
    )


def _plan(document_count: int = 1) -> VectorGraphBuildPlan:
    return VectorGraphBuildPlan(
        snapshot_sha256="a" * 64,
        manuscript_count=0,
        manuscript_chunk_count=0,
        knowledge_card_count=document_count,
        document_count=document_count,
        total_content_chars=4 * document_count,
    )


class VectorGraphServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_persisted_building_without_live_task_is_retryable_after_restart(
        self,
    ) -> None:
        backend = _PersistedBuildingBackend()
        service = _ControlledService(backend)

        interrupted = await service.status()
        restarted = await service.start_update()

        self.assertIs(interrupted.state, VectorGraphIndexState.FAILED)
        self.assertIsNotNone(interrupted.progress)
        self.assertIs(interrupted.progress.stage, VectorGraphBuildStage.FAILED)
        self.assertEqual(interrupted.progress.processed_sources, 1)
        self.assertEqual(
            interrupted.progress.error_message,
            "上次索引同步因服务中断，未完成来源会在重试时继续处理。",
        )
        self.assertEqual(
            interrupted.message,
            "上次索引同步因服务中断，未完成来源会在重试时继续处理。",
        )
        self.assertTrue(restarted.accepted)

        await asyncio.wait_for(backend.started.wait(), timeout=1)
        while_running = await service.status()
        duplicate = await service.start_update()

        self.assertIs(while_running.state, VectorGraphIndexState.BUILDING)
        self.assertFalse(duplicate.accepted)
        self.assertEqual(backend.update_calls, 1)

        backend.release.set()
        self.assertIsNotNone(service._background_task)
        await service._background_task

    async def test_start_update_runs_in_background_and_rejects_duplicate(
        self,
    ) -> None:
        backend = _ControlledBackend()
        service = _ControlledService(backend)

        first = await service.start_update()
        await backend.started.wait()
        while_running = await service.status()
        duplicate = await service.start_update()

        self.assertTrue(first.accepted)
        self.assertEqual(first.message, "RAG 索引同步已开始。")
        self.assertIs(while_running.state, VectorGraphIndexState.BUILDING)
        self.assertEqual(while_running.progress.total_sources, 1)
        self.assertFalse(duplicate.accepted)
        self.assertEqual(duplicate.message, "已有 RAG 索引同步正在运行。")
        self.assertEqual(backend.update_calls, 1)

        backend.release.set()
        self.assertIsNotNone(service._background_task)
        await service._background_task

    async def test_empty_corpus_still_runs_update_to_remove_stale_sources(
        self,
    ) -> None:
        backend = _ControlledBackend()
        service = _ControlledService(backend, documents=[])

        result = await service.start_update()
        await backend.started.wait()

        self.assertTrue(result.accepted)
        self.assertEqual(result.plan.document_count, 0)
        self.assertEqual(backend.received_documents, [])
        self.assertEqual(backend.received_plan, _plan(0))

        backend.release.set()
        self.assertIsNotNone(service._background_task)
        await service._background_task
