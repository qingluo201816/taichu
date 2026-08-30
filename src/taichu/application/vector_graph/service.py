"""Vector Graph RAG 索引同步与多跳证据召回用例。"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.vector_graph import VectorGraphBackend
from taichu.application.services.chapter_service import ChapterService
from taichu.application.vector_graph.corpus import (
    compact_knowledge_card_context,
    corpus_snapshot_sha256,
    project_chapter,
    project_knowledge_card,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeLifecycle
from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildProgress,
    VectorGraphBuildResult,
    VectorGraphBuildStage,
    VectorGraphBuildStartResult,
    VectorGraphEvidence,
    VectorGraphExtractedTriplets,
    VectorGraphIndexState,
    VectorGraphIndexStatus,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)


class VectorGraphRAGService:
    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        knowledge_repository: StructuredKnowledgeRepository,
        backend: VectorGraphBackend,
        manuscript_chunk_size: int = 1_000,
        manuscript_chunk_overlap: int = 200,
    ) -> None:
        self._chapter_service = chapter_service
        self._knowledge_repository = knowledge_repository
        self._backend = backend
        self._chunk_size = manuscript_chunk_size
        self._chunk_overlap = manuscript_chunk_overlap
        self._build_lock = asyncio.Lock()
        self._background_task: asyncio.Task[None] | None = None
        self._background_started_at: str | None = None
        self._background_finished_at: str | None = None
        self._background_error: str | None = None

    async def plan(
        self,
    ) -> tuple[VectorGraphBuildPlan, list[VectorGraphSourceDocument]]:
        documents: list[VectorGraphSourceDocument] = []
        chapters = await self._chapter_service.list_chapters()
        for chapter in chapters:
            content = await self._chapter_service.read_chapter(chapter.id)
            documents.extend(
                project_chapter(
                    chapter,
                    content.markdown,
                    chunk_size=self._chunk_size,
                    chunk_overlap=self._chunk_overlap,
                )
            )

        cards = await self._knowledge_repository.list_confirmed_cards()
        card_lookup = {card.id: card for card in cards}
        documents.extend(project_knowledge_card(card, card_lookup) for card in cards)
        snapshot = corpus_snapshot_sha256(documents)
        return (
            VectorGraphBuildPlan(
                snapshot_sha256=snapshot,
                manuscript_count=len(chapters),
                manuscript_chunk_count=sum(
                    document.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
                    for document in documents
                ),
                knowledge_card_count=len(cards),
                document_count=len(documents),
                total_content_chars=sum(len(item.content) for item in documents),
            ),
            documents,
        )

    async def update(
        self,
        *,
        dry_run: bool = False,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult:
        plan, documents = await self.plan()
        if dry_run:
            return VectorGraphBuildResult(status="dry_run", plan=plan)
        return await self._backend.update(
            documents,
            plan=plan,
            extracted_triplets=extracted_triplets,
        )

    async def status(self) -> VectorGraphIndexStatus:
        plan, _documents = await self.plan()
        status = await self._backend.inspect(plan)
        task = self._background_task
        has_live_task = task is not None and not task.done()
        if status.state is VectorGraphIndexState.BUILDING and not has_live_task:
            finished_at = self._background_finished_at or _utc_now()
            error_message = self._background_error or (
                "上次索引同步因服务中断，未完成来源会在重试时继续处理。"
            )
            if status.progress is not None:
                progress = status.progress.model_copy(
                    update={
                        "stage": VectorGraphBuildStage.FAILED,
                        "updated_at": finished_at,
                        "error_message": error_message,
                    }
                )
            else:
                started_at = self._background_started_at or finished_at
                progress = VectorGraphBuildProgress(
                    stage=VectorGraphBuildStage.FAILED,
                    snapshot_sha256=plan.snapshot_sha256,
                    total_documents=plan.document_count,
                    total_sources=(plan.manuscript_count + plan.knowledge_card_count),
                    started_at=started_at,
                    updated_at=finished_at,
                    error_message=error_message,
                )
            return status.model_copy(
                update={
                    "state": VectorGraphIndexState.FAILED,
                    "progress": progress,
                    "message": error_message,
                }
            )
        if has_live_task and status.state is not VectorGraphIndexState.BUILDING:
            started_at = self._background_started_at or _utc_now()
            return status.model_copy(
                update={
                    "state": VectorGraphIndexState.BUILDING,
                    "progress": VectorGraphBuildProgress(
                        stage=VectorGraphBuildStage.PLANNING,
                        snapshot_sha256=plan.snapshot_sha256,
                        total_documents=plan.document_count,
                        total_sources=(
                            plan.manuscript_count + plan.knowledge_card_count
                        ),
                        started_at=started_at,
                        updated_at=started_at,
                    ),
                    "message": "正在扫描正文与知识卡，准备按来源同步索引。",
                }
            )
        if self._background_error and status.state not in {
            VectorGraphIndexState.BUILDING,
            VectorGraphIndexState.FAILED,
        }:
            finished_at = self._background_finished_at or _utc_now()
            started_at = self._background_started_at or finished_at
            return status.model_copy(
                update={
                    "state": VectorGraphIndexState.FAILED,
                    "progress": VectorGraphBuildProgress(
                        stage=VectorGraphBuildStage.FAILED,
                        snapshot_sha256=plan.snapshot_sha256,
                        total_documents=plan.document_count,
                        total_sources=(
                            plan.manuscript_count + plan.knowledge_card_count
                        ),
                        started_at=started_at,
                        updated_at=finished_at,
                        error_message=self._background_error,
                    ),
                    "message": "最近一次索引同步启动后失败。",
                }
            )
        return status

    async def start_update(self) -> VectorGraphBuildStartResult:
        async with self._build_lock:
            status = await self.status()
            if status.state is VectorGraphIndexState.BUILDING:
                return VectorGraphBuildStartResult(
                    accepted=False,
                    message="已有 RAG 索引同步正在运行。",
                    plan=status.current_plan,
                )
            self._background_started_at = _utc_now()
            self._background_finished_at = None
            self._background_error = None
            self._background_task = asyncio.create_task(
                self._run_background_update(),
                name="vector-graph-incremental-update",
            )
            return VectorGraphBuildStartResult(
                accepted=True,
                message="RAG 索引同步已开始。",
                plan=status.current_plan,
            )

    async def _run_background_update(self) -> None:
        try:
            await self.update()
        except asyncio.CancelledError:
            self._background_error = "索引同步任务因服务停止而中断。"
            self._background_finished_at = _utc_now()
            raise
        except Exception as error:
            self._background_error = str(error)[:2_000]
            self._background_finished_at = _utc_now()
        else:
            self._background_finished_at = _utc_now()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
    ) -> VectorGraphRetrievalResult:
        normalized = query.strip()
        if not normalized:
            raise ValueError("多跳召回查询不能为空。")
        indexed = await self._backend.retrieve(normalized, top_k=top_k)
        evidences = []
        confirmed_cards = None
        for evidence in indexed.evidences:
            if evidence.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK:
                try:
                    chapter = await self._chapter_service.read_chapter(
                        evidence.source_id
                    )
                except Exception:
                    continue
                start = evidence.start_char
                end = evidence.end_char
                if start is None or end is None or end > len(chapter.markdown):
                    continue
                content = chapter.markdown[start:end]
                if _sha256(content) != evidence.content_sha256:
                    continue
                context_start = evidence.context_start_char
                context_end = evidence.context_end_char
                context_content = None
                context_ref = None
                if (
                    context_start is not None
                    and context_end is not None
                    and context_start <= start
                    and context_end >= end
                    and context_end <= len(chapter.markdown)
                ):
                    authoritative_context = chapter.markdown[context_start:context_end]
                    context_content = _verified_context_projection(
                        evidence.context_content,
                        authoritative_context,
                    )
                    context_ref = (
                        f"manuscript:{evidence.source_id}:{context_start}-{context_end}"
                    )
                evidences.append(
                    evidence.model_copy(
                        update={
                            "content": content,
                            "context_content": context_content,
                            "context_source_ref": context_ref,
                            "authority_verified": True,
                        }
                    )
                )
                continue

            if confirmed_cards is None:
                confirmed_cards = {
                    card.id: card
                    for card in await self._knowledge_repository.list_confirmed_cards()
                }
            card = confirmed_cards.get(evidence.source_id)
            if (
                card is None
                or card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED
            ):
                continue
            current_document = project_knowledge_card(card, confirmed_cards)
            evidences.append(
                evidence.model_copy(
                    update={
                        "title": current_document.title,
                        "content": compact_knowledge_card_context(
                            current_document.content
                        ),
                        "content_sha256": current_document.content_sha256,
                        "authority_verified": True,
                    }
                )
            )

        verified = [
            _augment_graph_context(evidence.model_copy(update={"rank": rank}))
            for rank, evidence in enumerate(evidences[:top_k], start=1)
        ]
        return indexed.model_copy(
            update={
                "evidences": verified,
                "source_refs": list(
                    dict.fromkeys(item.source_ref for item in verified)
                ),
            }
        )


class VectorGraphBuildError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _augment_graph_context(evidence: VectorGraphEvidence) -> VectorGraphEvidence:
    """把已筛选的图关系放入最终模型上下文，避免只在重排阶段可见。"""

    if not evidence.relation_texts:
        return evidence
    context = evidence.context_content or evidence.content
    if "相关图关系：" in context:
        return evidence
    augmented = "\n".join(
        [
            "相关图关系：" + "；".join(evidence.relation_texts),
            "相关正文：" + context,
        ]
    )
    return evidence.model_copy(update={"context_content": augmented})


def _verified_context_projection(
    projected: str | None,
    authoritative: str,
) -> str:
    """只保留能在权威原文中连续复原的后端上下文投影。"""

    if not projected:
        return authoritative
    compact_projected = "".join(projected.split())
    compact_authoritative = "".join(authoritative.split())
    if compact_projected and compact_projected in compact_authoritative:
        return projected
    return authoritative
