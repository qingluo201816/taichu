"""Selection AI service tests."""

import json
import tempfile
import unittest
from pathlib import Path

from taichu.application.services.ai_card_service import (
    AI_CARDS_FILE,
    IDEAS_FILE,
    AICardService,
)
from taichu.application.services.selection_ai_service import (
    SelectionAIRequest,
    SelectionAIService,
    SelectionMode,
)
from taichu.domain.models.ai_card import (
    AIResultCardStatus,
    AIResultCardType,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
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


class SelectionAIServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 3 Selection AI without a real LLM."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.ai_card_service = AICardService(self.storage)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_structured_ask_output_returns_suggestion_card(self) -> None:
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "card_type": "suggestion",
                        "content": {
                            "title": "动机建议",
                            "body": "这里可以强化主角迟疑的代价。",
                        },
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = SelectionAIService(llm, self.ai_card_service)

        card = await service.run_selection(_request(SelectionMode.ASK))
        records = await self.storage.list_workspace_records(AI_CARDS_FILE)

        self.assertEqual(card.type, AIResultCardType.SUGGESTION)
        self.assertEqual(card.status, AIResultCardStatus.GENERATED)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], card.id)

    async def test_non_json_llm_output_is_downgraded_to_failure_card(self) -> None:
        llm = FakeLLM(["这不是 JSON，但也不能裸露给前端。"])
        service = SelectionAIService(llm, self.ai_card_service)

        card = await service.run_selection(_request(SelectionMode.ENRICH_SETTING))

        self.assertEqual(card.type, AIResultCardType.SUGGESTION)
        self.assertIsInstance(card.content, dict)
        assert isinstance(card.content, dict)
        self.assertIn("解析失败", card.content["title"])

    async def test_continue_text_returns_text_candidate_and_uses_target_words(
        self,
    ) -> None:
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "card_type": "text_candidate",
                        "content": {"text": "他终于踏进风雪，剑意无声展开。"},
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = SelectionAIService(llm, self.ai_card_service)

        card = await service.run_selection(
            _request(SelectionMode.CONTINUE_TEXT, target_words=200)
        )

        self.assertEqual(card.type, AIResultCardType.TEXT_CANDIDATE)
        self.assertEqual(card.content, "他终于踏进风雪，剑意无声展开。")
        self.assertIn("约 200 字", llm.prompts[0])

    async def test_enrich_setting_can_return_pending_fact_card_only(self) -> None:
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "card_type": "pending_fact",
                        "content": {
                            "fact_type": "technique",
                            "title": "太初剑意",
                            "content": {"rule": "以心火照见剑路。"},
                        },
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = SelectionAIService(llm, self.ai_card_service)

        card = await service.run_selection(
            _request(SelectionMode.ENRICH_SETTING)
        )
        pending_records = await self.storage.list_workspace_records(
            "pending_facts.jsonl"
        )

        self.assertEqual(card.type, AIResultCardType.PENDING_FACT)
        self.assertIsInstance(card.content, dict)
        assert isinstance(card.content, dict)
        self.assertEqual(card.content["status"], "pending")
        self.assertEqual(pending_records, [])

    async def test_save_suggestion_as_idea_is_non_fact_workspace_asset(
        self,
    ) -> None:
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "card_type": "suggestion",
                        "content": {"body": "可以把这里沉淀成灵感。"},
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = SelectionAIService(llm, self.ai_card_service)
        card = await service.run_selection(_request(SelectionMode.ASK))

        result = await self.ai_card_service.save_suggestion_as_idea(card.id)
        idea_records = await self.storage.list_workspace_records(IDEAS_FILE)
        knowledge_files = list(
            (self.assets_root / "source" / "knowledge").rglob("*.json")
        )

        self.assertEqual(result.card.status, AIResultCardStatus.SAVED_TO_INBOX)
        self.assertEqual(idea_records[0]["source_card_id"], card.id)
        self.assertEqual(knowledge_files, [])

    async def test_discarded_card_stays_out_of_fact_assets(self) -> None:
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "card_type": "suggestion",
                        "content": {"body": "这条建议稍后丢弃。"},
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = SelectionAIService(llm, self.ai_card_service)
        card = await service.run_selection(_request(SelectionMode.ASK))

        discarded = await self.ai_card_service.discard_card(card.id)
        idea_records = await self.storage.list_workspace_records(IDEAS_FILE)
        pending_records = await self.storage.list_workspace_records(
            "pending_facts.jsonl"
        )

        self.assertEqual(discarded.status, AIResultCardStatus.DISCARDED)
        self.assertEqual(idea_records, [])
        self.assertEqual(pending_records, [])


def _request(
    mode: SelectionMode,
    *,
    target_words: int | None = None,
) -> SelectionAIRequest:
    return SelectionAIRequest(
        mode=mode,
        chapter_id="chapter_001",
        selected_text="选中的正文",
        surrounding_text="周边上下文",
        selection_ref=_source_ref(),
        user_prompt="帮我看看",
        target_words=target_words,
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        char_start=0,
        char_end=5,
        excerpt="选中的正文",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
