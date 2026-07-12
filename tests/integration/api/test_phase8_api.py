"""Agent Chat and export API integration tests."""

import json
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage

from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardLifecycle,
    KnowledgeCardType,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeSourceOrigin
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class Phase8ApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify export and the writing loop compose without source pollution."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 集成\n秦浩轩携太初古卷入山。",
            source_name="phase8.txt",
        )
        self.knowledge_repository = InMemoryKnowledgeRepository([_knowledge_card()])
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[AIMessage(content="可以从古卷代价推进。[S1]")]
            ),
            knowledge_repository=self.knowledge_repository,
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_export_bundle_endpoint_returns_readable_files(self) -> None:
        response = await self.client.get("/api/export/bundle")

        self.assertEqual(response.status_code, 200)
        files = {file["path"]: file for file in response.json()["files"]}
        self.assertIn("source/metadata.yaml", files)
        self.assertIn("source/manuscripts/chapters/chapter_001.md", files)
        self.assertIn("knowledge/knowledge_cards.json", files)
        self.assertIn("source/workspace/ai_cards.jsonl", files)
        snapshot = json.loads(files["knowledge/knowledge_cards.json"]["content"])
        self.assertEqual(snapshot["schema_version"], "taichu_export_v2")
        self.assertEqual(snapshot["cards"][0]["lifecycle"], "confirmed")

    async def test_generated_projection_endpoints_are_removed(self) -> None:
        for path in ("/api/generated/rebuild", "/api/generated/clear"):
            with self.subTest(path=path):
                response = await self.client.post(path)
                self.assertEqual(response.status_code, 404)

    async def test_mvp_writing_loop_smoke(self) -> None:
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[
                    AIMessage(
                        content=json.dumps(
                            {
                                "card_type": "text_candidate",
                                "content": {"text": "他握紧古卷，继续入山。"},
                            },
                            ensure_ascii=False,
                        )
                    ),
                    AIMessage(
                        content=json.dumps(
                            {
                                "card_type": "suggestion",
                                "content": {"body": "可以强化古卷代价。"},
                            },
                            ensure_ascii=False,
                        )
                    ),
                    AIMessage(
                        content=json.dumps(
                            {
                                "card_type": "pending_fact",
                                "content": {
                                    "fact_type": "item",
                                    "title": "灵犀玉",
                                    "content": "灵犀玉会回应心念。",
                                },
                            },
                            ensure_ascii=False,
                        )
                    ),
                    AIMessage(content=_summary_json()),
                ]
            ),
            knowledge_repository=self.knowledge_repository,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            chapter = (await client.get("/api/chapters/chapter_001")).json()
            base_markdown = chapter["markdown"]

            continue_card = (
                await client.post(
                    "/api/ai-cards/selection",
                    json=_selection_payload(
                        mode="continue_text",
                        user_prompt="续写一句",
                        target_words=30,
                    ),
                )
            ).json()["card"]
            await client.post(
                f"/api/ai-cards/{continue_card['id']}/actions",
                json={"action": "inserted"},
            )
            await client.put(
                "/api/chapters/chapter_001",
                json={"markdown": base_markdown + "\n\n" + continue_card["content"]},
            )

            suggestion_card = (
                await client.post(
                    "/api/ai-cards/selection",
                    json=_selection_payload(mode="ask", user_prompt="哪里能更好？"),
                )
            ).json()["card"]
            save_idea = await client.post(
                f"/api/inbox/cards/{suggestion_card['id']}/save-idea"
            )

            pending_card = (
                await client.post(
                    "/api/ai-cards/selection",
                    json=_selection_payload(
                        mode="enrich_setting",
                        user_prompt="补一个法宝设定",
                    ),
                )
            ).json()["card"]
            converted = await client.post(
                f"/api/inbox/cards/{pending_card['id']}/convert-pending-fact"
            )
            pending_fact = await client.post(
                "/api/inbox/pending-facts",
                json={
                    "data": {
                        "title": "灵犀玉",
                        "content": "灵犀玉会回应心念。",
                        "origin": "AI 候选经作者预览",
                    }
                },
            )
            pending_fact_id = pending_fact.json()["item"]["id"]
            confirmed = await client.post(
                f"/api/inbox/pending-facts/{pending_fact_id}/confirm",
                json={
                    "knowledge_type": "item",
                    "card_preview": {
                        "name": "灵犀玉",
                        "summary": "灵犀玉会回应持有者心念。",
                        "source_origin": "inbox_fact",
                        "source_note": "作者在收件箱预览后确认。",
                    },
                },
            )

            summary = await client.post("/api/chapters/chapter_001/summary")
            export_bundle = await client.get("/api/export/bundle")

        self.assertEqual(save_idea.status_code, 200)
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["knowledge_card"]["lifecycle"], "confirmed")
        self.assertEqual(
            confirmed.json()["knowledge_card"]["source_origin"],
            "inbox_fact",
        )
        self.assertEqual(summary.status_code, 200)
        export_paths = {file["path"] for file in export_bundle.json()["files"]}
        self.assertIn("source/workspace/ideas.jsonl", export_paths)
        self.assertIn("source/workspace/pending_facts.jsonl", export_paths)
        self.assertIn("knowledge/knowledge_cards.json", export_paths)
        self.assertFalse(any(path.startswith("generated/") for path in export_paths))


def _knowledge_card() -> KnowledgeCard:
    return KnowledgeCard(
        id="knowledge_phase8_item",
        type=KnowledgeCardType.ITEM,
        name="太初古卷",
        aliases=[],
        summary="太初古卷会映照持有者的选择。",
        lifecycle=KnowledgeCardLifecycle.CONFIRMED,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="作者手动确认。",
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _selection_payload(
    *,
    mode: str,
    user_prompt: str,
    target_words: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "mode": mode,
        "selection_context": {
            "chapter_id": "chapter_001",
            "selected_text": "太初古卷",
            "surrounding_text": "秦浩轩携太初古卷入山。",
            "selection_range": {"from": 1, "to": 5},
            "source_ref": _source_ref().model_dump(mode="json"),
        },
        "user_prompt": user_prompt,
    }
    if target_words is not None:
        payload["target_words"] = target_words
    return payload


def _summary_json() -> str:
    return json.dumps(
        {
            "summary": "秦浩轩携太初古卷入山。",
            "key_events": ["秦浩轩入山"],
            "character_changes": [],
            "new_setting_candidates": [],
            "foreshadow_candidates": [],
            "next_chapter_hooks": ["古卷显露代价"],
        },
        ensure_ascii=False,
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="秦浩轩携太初古卷入山。",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
