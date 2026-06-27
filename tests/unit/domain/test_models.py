"""Schema validation tests for Phase 0 domain models."""

import unittest
from typing import Any, cast

from pydantic import ValidationError

from taichu.domain.models import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
    Chapter,
    ChapterManifest,
    ChapterStatus,
    ChapterSummary,
    ChapterSummaryStatus,
    CharacterCard,
    CharacterImportance,
    EmbeddingChunk,
    IdeaCard,
    IdeaCardSource,
    IdeaCardStatus,
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
    Volume,
)


def create_source_ref() -> SourceRef:
    """Create a valid chapter paragraph SourceRef."""
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="开篇第一段",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )


class DomainModelContractTest(unittest.TestCase):
    """Verify all Phase 0 data contracts can be imported and validated."""

    def test_core_models_can_be_constructed(self) -> None:
        source_ref = create_source_ref()
        chapter = Chapter(
            id="chapter_001",
            volume_id="volume_001",
            title="第一章",
            order=0,
            markdown_path=(
                "project_assets/source/manuscripts/chapters/chapter_001.md"
            ),
            status=ChapterStatus.ACTIVE,
            word_count=1200,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        manifest = ChapterManifest(
            schema_version="1",
            current_chapter_id=chapter.id,
            volumes=[Volume(id="volume_001", title="第一卷", order=0)],
            chapters=[chapter],
            updated_at="2026-06-27T00:00:00Z",
        )
        ai_card = AIResultCard(
            id="card_001",
            type=AIResultCardType.TEXT_CANDIDATE,
            workflow=AIWorkflow.CONTINUE_TEXT,
            status=AIResultCardStatus.GENERATED,
            chapter_id=chapter.id,
            input_context={"selection": "开篇"},
            content="续写正文候选",
            source_refs=[source_ref],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        pending_fact = PendingFact(
            id="pending_001",
            fact_type=PendingFactType.CHARACTER,
            title="主角境界",
            content={"realm": "炼气"},
            proposed_by=ProposedBy.AI,
            source_refs=[source_ref],
            status=PendingFactStatus.PENDING,
            created_at="2026-06-27T00:00:00Z",
        )
        knowledge = KnowledgeCard(
            id="knowledge_001",
            type=KnowledgeCardType.CHARACTER,
            name="主角",
            aliases=["少年"],
            summary="作者确认的角色设定",
            fields={"cultivation": {"current_realm": "炼气"}},
            source_refs=[source_ref],
            status=KnowledgeCardStatus.CONFIRMED,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        character = CharacterCard(
            knowledge_base=knowledge,
            current_realm="炼气",
            importance=CharacterImportance.CORE,
        )
        idea = IdeaCard(
            id="idea_001",
            content="一个尚未确认的灵感",
            source=IdeaCardSource.AI,
            status=IdeaCardStatus.OPEN,
            source_card_id=ai_card.id,
            tags=["伏笔"],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        summary = ChapterSummary(
            id="summary_001",
            chapter_id=chapter.id,
            status=ChapterSummaryStatus.DRAFT,
            summary="本章摘要草稿",
            new_setting_candidates=[pending_fact],
            source_refs=[source_ref],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        retrieval_hit = RetrievalHit(
            source_type=RetrievalSourceType.CHAPTER,
            source_id=chapter.id,
            excerpt="开篇第一段",
            score=1.0,
            reason=RetrievalReason.EXACT,
            source_ref=source_ref,
        )
        embedding_chunk = EmbeddingChunk(
            id="chunk_001",
            source_type=RetrievalSourceType.CHAPTER,
            source_id=chapter.id,
            text="开篇第一段",
            source_ref=source_ref,
            embedding=[0.1, 0.2],
            updated_at="2026-06-27T00:00:00Z",
        )

        self.assertEqual(manifest.chapters[0].id, "chapter_001")
        self.assertEqual(character.knowledge_base.id, knowledge.id)
        self.assertEqual(idea.source_card_id, ai_card.id)
        self.assertEqual(summary.new_setting_candidates[0].id, pending_fact.id)
        self.assertEqual(retrieval_hit.source_ref, source_ref)
        self.assertEqual(embedding_chunk.source_ref, source_ref)

    def test_invalid_enum_value_fails_schema_validation(self) -> None:
        with self.assertRaises(ValidationError):
            AIResultCard(
                id="card_001",
                type=cast(Any, "plain_text"),
                workflow=AIWorkflow.CHAT,
                status=AIResultCardStatus.GENERATED,
                input_context={},
                content="裸字符串不能绕过卡片，但非法 type 也不能通过",
                created_at="2026-06-27T00:00:00Z",
                updated_at="2026-06-27T00:00:00Z",
            )
