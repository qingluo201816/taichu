"""Knowledge confirmation API integration tests."""

import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)

from taichu.application.services.ai_card_service import PENDING_FACTS_FILE
from taichu.config import Settings
from taichu.domain.models.pending_fact import (
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
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


class KnowledgeApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify PendingFact confirmation routes preserve fact boundaries."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        app = create_app(
            app_settings=Settings(project_assets_dir=self.assets_root),
            llm=FakeMessagesListChatModel(responses=[]),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    async def test_confirm_pending_fact_writes_knowledge_idempotently(
        self,
    ) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        first = await self.client.post(
            f"/api/pending-facts/{pending_fact.id}/confirm"
        )
        second = await self.client.post(
            f"/api/pending-facts/{pending_fact.id}/confirm"
        )
        knowledge = await self.client.get("/api/knowledge")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(
            first.json()["knowledge_card"]["id"],
            second.json()["knowledge_card"]["id"],
        )
        self.assertEqual(first.json()["pending_fact"]["status"], "confirmed")
        self.assertEqual(len(knowledge.json()["cards"]), 1)
        self.assertEqual(
            knowledge.json()["cards"][0]["status"],
            "confirmed",
        )
        self.assertEqual(
            len(list((self.assets_root / "source" / "knowledge").rglob("*.json"))),
            1,
        )

    async def test_confirm_edited_uses_author_payload_without_full_card_write(
        self,
    ) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        response = await self.client.post(
            f"/api/pending-facts/{pending_fact.id}/confirm-edited",
            json={
                "name": "Edited Name",
                "summary": "Edited summary",
                "aliases": ["Edited Alias"],
                "fields": {"rule": "edited rule"},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pending_fact"]["status"], "edited_confirmed")
        self.assertEqual(body["knowledge_card"]["name"], "Edited Name")
        self.assertEqual(body["knowledge_card"]["aliases"], ["Edited Alias"])
        self.assertEqual(body["knowledge_card"]["fields"], {"rule": "edited rule"})
        self.assertEqual(len(body["knowledge_card"]["source_refs"]), 1)

    async def test_reject_pending_fact_does_not_write_knowledge(self) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        response = await self.client.post(
            f"/api/pending-facts/{pending_fact.id}/reject"
        )
        knowledge = await self.client.get("/api/knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending_fact"]["status"], "ignored")
        self.assertEqual(knowledge.json()["cards"], [])
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def test_invalid_source_ref_payload_is_rejected(self) -> None:
        pending_fact = _pending_fact()
        await self._append_pending_fact(pending_fact)

        response = await self.client.post(
            f"/api/pending-facts/{pending_fact.id}/confirm-edited",
            json={
                "source_refs": [
                    {
                        "source_type": "chapter",
                        "source_id": "bad",
                        "path": "project_assets/generated/sqlite/taichu.db",
                        "anchor_type": "paragraph",
                        "paragraph_start": 0,
                        "excerpt": "bad",
                        "excerpt_hash": "hash_excerpt",
                        "source_hash": "hash_source",
                        "created_at": "2026-06-27T00:00:00Z",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            list((self.assets_root / "source" / "knowledge").rglob("*.json")),
            [],
        )

    async def _append_pending_fact(self, pending_fact: PendingFact) -> None:
        await self.storage.append_workspace_record(
            PENDING_FACTS_FILE,
            pending_fact.model_dump(mode="json"),
        )


def _pending_fact() -> PendingFact:
    return PendingFact(
        id="pending_fact_001",
        fact_type=PendingFactType.TECHNIQUE,
        title="Taichu sword intent",
        content={"rule": "heart fire reveals the sword path"},
        proposed_by=ProposedBy.AI,
        source_refs=[
            SourceRef(
                source_type=SourceRefSourceType.CHAPTER,
                source_id="chapter_001",
                path="manuscripts/chapters/chapter_001.md",
                chapter_id="chapter_001",
                anchor_type=SourceAnchorType.PARAGRAPH,
                paragraph_start=0,
                char_start=0,
                char_end=8,
                excerpt="source text",
                excerpt_hash="hash_excerpt",
                source_hash="hash_source",
                created_at="2026-06-27T00:00:00Z",
            )
        ],
        status=PendingFactStatus.PENDING,
        created_at="2026-06-27T00:00:00Z",
    )
