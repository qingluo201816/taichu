"""Chapter summary service tests."""

import json
import tempfile
import unittest
from pathlib import Path

from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.chapter_summary_service import (
    CHAPTER_SUMMARIES_FILE,
    ChapterSummaryEdit,
    ChapterSummaryService,
)
from taichu.application.services.import_service import ImportService
from taichu.application.services.knowledge_service import (
    KnowledgeService,
    knowledge_category_for_type,
)
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)
from taichu.domain.models import (
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.models.ai_card import AIResultCardType
from taichu.domain.models.pending_fact import PendingFactStatus
from taichu.domain.models.summary import ChapterSummaryStatus
from taichu.domain.rules.fact_scope import is_allowed_in_fact_scope
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class FakeLLM:
    """Record prompts and return queued completions."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeRetrieval:
    """Return canned retrieval hits."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: object) -> list[RetrievalHit]:
        text = getattr(query, "text")
        self.queries.append(text)
        return [
            RetrievalHit(
                source_type=RetrievalSourceType.CHAPTER,
                source_id="chapter_001",
                excerpt="检索证据",
                score=1.0,
                reason=RetrievalReason.EXACT,
                source_ref=_source_ref(),
            )
        ]


class ChapterSummaryServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 7 summary draft and candidate behavior."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.chapter_service = ChapterService(self.storage)
        self.knowledge_service = KnowledgeService(self.storage)
        self.ai_card_service = AICardService(self.storage)
        self.retrieval = FakeRetrieval()

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_empty_chapter_creates_draft_without_llm_call(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 空白",
            source_name="empty.txt",
        )
        llm = FakeLLM([])
        service = self._service(llm)

        result = await service.summarize_chapter("chapter_001")

        self.assertEqual(result.summary.status, ChapterSummaryStatus.DRAFT)
        self.assertIn("暂无可整理正文", result.summary.summary)
        self.assertEqual(llm.prompts, [])
        self.assertEqual(result.card.type, AIResultCardType.CHAPTER_SUMMARY)

    async def test_long_chapter_is_split_into_prompt_segments(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 长文\n" + ("甲" * 1700) + "\n\n" + ("乙" * 1700),
            source_name="long.txt",
        )
        llm = FakeLLM([_summary_json(summary="长章节整理完成")])
        service = self._service(llm)

        await service.summarize_chapter("chapter_001")

        self.assertIn("分段 1/2", llm.prompts[0])
        self.assertIn("分段 2/2", llm.prompts[0])
        self.assertIn("检索证据", llm.prompts[0])

    async def test_summary_prompt_uses_confirmed_knowledge_only(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 事实边界\n秦浩轩修行剑意。",
            source_name="fact_scope.txt",
        )
        confirmed = _knowledge_card(
            knowledge_id="knowledge_confirmed",
            name="Confirmed sword intent",
            status=KnowledgeCardStatus.CONFIRMED,
        )
        archived = _knowledge_card(
            knowledge_id="knowledge_archived",
            name="Archived sword intent",
            status=KnowledgeCardStatus.ARCHIVED,
        )
        await self._write_knowledge_card(confirmed)
        await self._write_knowledge_card(archived)
        llm = FakeLLM([_summary_json()])
        service = self._service(llm)

        await service.summarize_chapter("chapter_001")

        self.assertIn("Confirmed sword intent", llm.prompts[0])
        self.assertNotIn("Archived sword intent", llm.prompts[0])

    async def test_duplicate_setting_candidates_are_deduped(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 设定\n秦浩轩得到太初古卷。",
            source_name="candidate.txt",
        )
        llm = FakeLLM(
            [
                _summary_json(
                    candidates=[
                        {
                            "fact_type": "item",
                            "title": "太初古卷",
                            "content": {"rule": "可映照本心"},
                        },
                        {
                            "fact_type": "item",
                            "title": "太初古卷",
                            "content": {"rule": "可映照本心"},
                        },
                    ]
                )
            ]
        )
        service = self._service(llm)

        result = await service.summarize_chapter("chapter_001")
        pending_records = await self.storage.list_workspace_records(
            "pending_facts.jsonl"
        )

        self.assertEqual(len(result.summary.new_setting_candidates), 1)
        self.assertEqual(pending_records, [])
        self.assertFalse(
            is_allowed_in_fact_scope(result.summary.new_setting_candidates[0])
        )

    async def test_confirm_and_ignore_summary_never_write_knowledge(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 整理\n本章发生了一件事。",
            source_name="summary.txt",
        )
        service = self._service(FakeLLM([_summary_json(), _summary_json()]))

        first = await service.summarize_chapter("chapter_001")
        confirmed = await service.confirm_summary(
            first.summary.id,
            ChapterSummaryEdit(summary="作者编辑后的摘要"),
        )
        second = await service.summarize_chapter("chapter_001")
        ignored = await service.ignore_summary(second.summary.id)

        self.assertEqual(confirmed.status, ChapterSummaryStatus.CONFIRMED)
        self.assertEqual(confirmed.summary, "作者编辑后的摘要")
        self.assertEqual(ignored.status, ChapterSummaryStatus.IGNORED)
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def test_candidate_can_convert_to_pending_fact_idempotently(
        self,
    ) -> None:
        await ImportService(self.storage).import_text(
            "第一章 候选\n秦浩轩得到太初古卷。",
            source_name="candidate.txt",
        )
        service = self._service(
            FakeLLM(
                [
                    _summary_json(
                        candidates=[
                            {
                                "fact_type": "item",
                                "title": "太初古卷",
                                "content": "太初古卷是待确认设定。",
                            }
                        ]
                    )
                ]
            )
        )
        result = await service.summarize_chapter("chapter_001")
        candidate = result.summary.new_setting_candidates[0]

        first = await service.convert_candidate_to_pending_fact(
            result.summary.id,
            candidate.id,
        )
        second = await service.convert_candidate_to_pending_fact(
            result.summary.id,
            candidate.id,
        )
        records = await self.storage.list_workspace_records("pending_facts.jsonl")

        self.assertEqual(first.id, candidate.id)
        self.assertEqual(second.id, candidate.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(first.status, PendingFactStatus.PENDING)
        self.assertFalse(is_allowed_in_fact_scope(first))

    async def test_summary_records_are_workspace_assets(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 记录\n正文。",
            source_name="records.txt",
        )
        service = self._service(FakeLLM([_summary_json()]))

        result = await service.summarize_chapter("chapter_001")
        records = await self.storage.list_workspace_records(CHAPTER_SUMMARIES_FILE)

        self.assertEqual(records[0]["id"], result.summary.id)
        self.assertFalse(is_allowed_in_fact_scope(result.summary))

    def _service(self, llm: FakeLLM) -> ChapterSummaryService:
        return ChapterSummaryService(
            storage=self.storage,
            chapter_service=self.chapter_service,
            knowledge_service=self.knowledge_service,
            retrieval=self.retrieval,
            llm=llm,
            ai_card_service=self.ai_card_service,
        )

    async def _write_knowledge_card(self, card: KnowledgeCard) -> None:
        await self.storage.write_knowledge_record(
            knowledge_category_for_type(card.type),
            card.id,
            card.model_dump(mode="json"),
        )


def _summary_json(
    *,
    summary: str = "本章摘要草稿",
    candidates: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "summary": summary,
            "key_events": ["事件一"],
            "character_changes": [{"character": "秦浩轩", "change": "获得古卷"}],
            "new_setting_candidates": candidates or [],
            "foreshadow_candidates": [{"title": "伏笔", "description": "后续回收"}],
            "next_chapter_hooks": ["继续探索"],
        },
        ensure_ascii=False,
    )


def _knowledge_card(
    *,
    knowledge_id: str,
    name: str,
    status: KnowledgeCardStatus,
) -> KnowledgeCard:
    return KnowledgeCard(
        id=knowledge_id,
        type=KnowledgeCardType.TECHNIQUE,
        name=name,
        aliases=[],
        summary=f"{name} summary",
        fields={},
        source_refs=[_source_ref()],
        status=status,
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="检索证据",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
