"""Phase 8 Agent Chat, export, and rebuild API integration tests."""

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
from taichu.application.services.knowledge_service import knowledge_category_for_type
from taichu.config import Settings
from taichu.domain.models.knowledge import (
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)
from taichu.domain.models.indexing import (
    IndexBuildJob,
    IndexBuildJobAction,
    IndexBuildJobStatus,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.main import create_app


class Phase8ApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 8 API endpoints compose without source pollution."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 集成\n秦浩轩携太初古卷入山。",
            source_name="phase8.txt",
        )
        await self.storage.write_knowledge_record(
            knowledge_category_for_type(KnowledgeCardType.ITEM),
            "knowledge_phase8_item",
            _knowledge_card().model_dump(mode="json"),
        )
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(
                responses=[AIMessage(content="可以从古卷代价推进。[S1]")]
            ),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_agent_chat_returns_and_persists_ai_result_card(self) -> None:
        response = await self.client.post(
            "/api/agents/chat",
            json={
                "message": "下一场戏怎么推进？",
                "chapter_id": "chapter_001",
                "include_current_chapter": True,
                "include_confirmed_facts": True,
            },
        )
        cards_response = await self.client.get("/api/ai-cards")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["card"]["workflow"], "chat")
        self.assertEqual(payload["card"]["type"], "suggestion")
        self.assertGreaterEqual(len(payload["card"]["source_refs"]), 1)
        self.assertEqual(
            cards_response.json()["cards"][0]["id"],
            payload["card"]["id"],
        )

    async def test_export_bundle_endpoint_returns_readable_files(self) -> None:
        response = await self.client.get("/api/export/bundle")

        self.assertEqual(response.status_code, 200)
        files = {file["path"]: file for file in response.json()["files"]}
        self.assertIn("source/metadata.yaml", files)
        self.assertIn("source/manuscripts/chapters/chapter_001.md", files)
        self.assertIn("source/knowledge/items/knowledge_phase8_item.json", files)
        self.assertIn("source/workspace/ai_cards.jsonl", files)

    async def test_generated_rebuild_endpoint_preserves_source(self) -> None:
        chapter_path = (
            self.assets_root / "source" / "manuscripts" / "chapters" / "chapter_001.md"
        )
        chapter_before = chapter_path.read_text(encoding="utf-8")
        junk_path = self.assets_root / "generated" / "temp" / "junk.tmp"
        junk_path.parent.mkdir(parents=True, exist_ok=True)
        junk_path.write_text("junk", encoding="utf-8")

        response = await self.client.post("/api/generated/rebuild")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["status"], "completed")
        self.assertFalse(junk_path.exists())
        self.assertTrue(
            (self.assets_root / "generated" / "sqlite" / "taichu.db").exists()
        )
        self.assertEqual(chapter_path.read_text(encoding="utf-8"), chapter_before)

    async def test_generated_rebuild_endpoint_can_return_failed_job(self) -> None:
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(responses=[AIMessage(content="unused")]),
        )
        app.state.index_service = FailingIndexService()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/generated/rebuild")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["status"], "failed")
        self.assertIn("forced failure", response.json()["job"]["message"])

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
                    AIMessage(content="可以从古卷代价推进。[S1]"),
                ]
            ),
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
            pending_fact_id = converted.json()["pending_fact"]["id"]
            confirmed = await client.post(
                f"/api/pending-facts/{pending_fact_id}/confirm"
            )

            summary = await client.post("/api/chapters/chapter_001/summary")
            rebuild = await client.post("/api/generated/rebuild")
            chat = await client.post(
                "/api/agents/chat",
                json={
                    "message": "下一幕怎么推进？",
                    "chapter_id": "chapter_001",
                    "include_current_chapter": True,
                    "include_confirmed_facts": True,
                },
            )
            export_bundle = await client.get("/api/export/bundle")

        self.assertEqual(save_idea.status_code, 200)
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["knowledge_card"]["status"], "confirmed")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(rebuild.json()["job"]["status"], "completed")
        self.assertEqual(chat.json()["card"]["workflow"], "chat")
        export_paths = {file["path"] for file in export_bundle.json()["files"]}
        self.assertIn("source/workspace/ideas.jsonl", export_paths)
        self.assertIn("source/knowledge/items/knowledge_phase8_item.json", export_paths)
        self.assertTrue(
            (self.assets_root / "generated" / "sqlite" / "taichu.db").exists()
        )


class FailingIndexService:
    """Return a failed job from the API dependency seam."""

    async def rebuild_generated_projection(self) -> IndexBuildJob:
        return IndexBuildJob(
            id="index_job_failed",
            action=IndexBuildJobAction.REBUILD,
            status=IndexBuildJobStatus.FAILED,
            created_at="2026-06-27T00:00:00Z",
            completed_at="2026-06-27T00:00:01Z",
            message="forced failure",
        )

    async def clear_generated(self) -> IndexBuildJob:
        return IndexBuildJob(
            id="index_job_clear_failed",
            action=IndexBuildJobAction.CLEAR,
            status=IndexBuildJobStatus.FAILED,
            created_at="2026-06-27T00:00:00Z",
            completed_at="2026-06-27T00:00:01Z",
            message="forced failure",
        )


def _knowledge_card() -> KnowledgeCard:
    return KnowledgeCard(
        id="knowledge_phase8_item",
        type=KnowledgeCardType.ITEM,
        name="太初古卷",
        aliases=[],
        summary="太初古卷会映照持有者的选择。",
        fields={},
        source_refs=[_source_ref()],
        status=KnowledgeCardStatus.CONFIRMED,
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
