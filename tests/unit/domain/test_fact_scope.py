"""Fact-scope pollution guard tests."""

import unittest

from taichu.domain.exceptions import FactScopeViolationError
from taichu.domain.models import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
    Chapter,
    ChapterStatus,
    ChapterSummary,
    ChapterSummaryStatus,
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
)
from taichu.domain.rules import (
    FactScopeSource,
    assert_allowed_in_fact_scope,
    is_allowed_in_fact_scope,
    resolve_retrieval_scope,
)


class FactScopeContractTest(unittest.TestCase):
    """Verify default fact_scope includes only manuscript and knowledge facts."""

    def test_default_fact_scope_sources(self) -> None:
        self.assertEqual(
            resolve_retrieval_scope(),
            frozenset(
                {
                    FactScopeSource.CHAPTERS,
                    FactScopeSource.CONFIRMED_KNOWLEDGE,
                }
            ),
        )

    def test_chapter_and_confirmed_knowledge_are_fact_scope_allowed(
        self,
    ) -> None:
        chapter = Chapter(
            id="chapter_001",
            title="第一章",
            order=0,
            markdown_path=(
                "project_assets/source/manuscripts/chapters/chapter_001.md"
            ),
            status=ChapterStatus.ACTIVE,
            word_count=10,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        knowledge = KnowledgeCard(
            id="knowledge_001",
            type=KnowledgeCardType.RULE,
            name="天道规则",
            summary="作者确认的设定",
            status=KnowledgeCardStatus.CONFIRMED,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )

        self.assertTrue(is_allowed_in_fact_scope(chapter))
        self.assertTrue(is_allowed_in_fact_scope(knowledge))
        assert_allowed_in_fact_scope(chapter)
        assert_allowed_in_fact_scope(knowledge)

    def test_workspace_assets_are_excluded_from_fact_scope(self) -> None:
        non_fact_items = [
            PendingFact(
                id="pending_001",
                fact_type=PendingFactType.RULE,
                title="候选设定",
                content="AI 还没被作者确认的设定",
                proposed_by=ProposedBy.AI,
                status=PendingFactStatus.PENDING,
                created_at="2026-06-27T00:00:00Z",
            ),
            IdeaCard(
                id="idea_001",
                content="灵感不是事实",
                source=IdeaCardSource.AUTHOR,
                status=IdeaCardStatus.OPEN,
                created_at="2026-06-27T00:00:00Z",
                updated_at="2026-06-27T00:00:00Z",
            ),
            AIResultCard(
                id="card_001",
                type=AIResultCardType.SUGGESTION,
                workflow=AIWorkflow.ASK_SELECTION,
                status=AIResultCardStatus.GENERATED,
                input_context={},
                content="AI 建议不是事实",
                created_at="2026-06-27T00:00:00Z",
                updated_at="2026-06-27T00:00:00Z",
            ),
            ChapterSummary(
                id="summary_001",
                chapter_id="chapter_001",
                status=ChapterSummaryStatus.CONFIRMED,
                summary="摘要也必须回指正文",
                created_at="2026-06-27T00:00:00Z",
                updated_at="2026-06-27T00:00:00Z",
            ),
        ]

        for item in non_fact_items:
            with self.subTest(type=type(item).__name__):
                self.assertFalse(is_allowed_in_fact_scope(item))
                with self.assertRaises(FactScopeViolationError):
                    assert_allowed_in_fact_scope(item)

    def test_discarded_ai_result_card_is_not_fact_scope_allowed(self) -> None:
        card = AIResultCard(
            id="card_discarded",
            type=AIResultCardType.SUGGESTION,
            workflow=AIWorkflow.ASK_SELECTION,
            status=AIResultCardStatus.DISCARDED,
            input_context={},
            content="已丢弃的 AI 建议不是事实",
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )

        self.assertFalse(is_allowed_in_fact_scope(card))
        with self.assertRaises(FactScopeViolationError):
            assert_allowed_in_fact_scope(card)
