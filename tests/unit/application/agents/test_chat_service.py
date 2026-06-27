"""Basic Agent Chat service tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.agents.chat.service import (
    ChatAgentRequest,
    ChatAgentService,
)
from taichu.application.contracts.retrieval import RetrievalQuery
from taichu.application.services.ai_card_service import (
    AICardService,
    PENDING_FACTS_FILE,
)
from taichu.application.services.chapter_service import ChapterService
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
from taichu.domain.models.pending_fact import (
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
)
from taichu.domain.models.retrieval import (
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.rules.fact_scope import RetrievalScopeName
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class FakeLLM:
    """Capture prompts and return a fixed answer."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "可以强化角色选择。[S1]"


class FakeRetrieval:
    """Capture retrieval queries without returning generated data."""

    def __init__(self) -> None:
        self.queries: list[RetrievalQuery] = []
        self.hits: list[RetrievalHit] = []

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        self.queries.append(query)
        return self.hits


class ChatAgentServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify chat context stays inside the MVP fact boundary."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            "第一章 初临\n秦浩轩发现太初古卷。",
            source_name="chat_service.txt",
        )
        self.llm = FakeLLM()
        self.retrieval = FakeRetrieval()
        self.service = ChatAgentService(
            chapter_service=ChapterService(self.storage),
            knowledge_service=KnowledgeService(self.storage),
            retrieval=self.retrieval,
            llm=self.llm,
            ai_card_service=AICardService(self.storage),
        )

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_chat_uses_confirmed_facts_without_workspace_pollution(
        self,
    ) -> None:
        await self._write_knowledge(
            _knowledge_card(
                knowledge_id="knowledge_confirmed",
                name="Confirmed lotus",
                status=KnowledgeCardStatus.CONFIRMED,
            )
        )
        await self._write_knowledge(
            _knowledge_card(
                knowledge_id="knowledge_archived",
                name="Archived lotus",
                status=KnowledgeCardStatus.ARCHIVED,
            )
        )
        await self.storage.append_workspace_record(
            PENDING_FACTS_FILE,
            _pending_fact().model_dump(mode="json"),
        )

        result = await self.service.run(
            ChatAgentRequest(
                message="这一章怎么推进？",
                chapter_id="chapter_001",
            )
        )

        self.assertEqual(result.card.workflow.value, "chat")
        self.assertEqual(result.card.type.value, "suggestion")
        self.assertIn("Confirmed lotus", self.llm.prompts[0])
        self.assertNotIn("Archived lotus", self.llm.prompts[0])
        self.assertNotIn("Unconfirmed seed", self.llm.prompts[0])
        self.assertEqual(
            self.retrieval.queries[0].scopes,
            frozenset({RetrievalScopeName.FACT.value}),
        )
        self.assertGreaterEqual(len(result.card.source_refs), 1)
        for source_ref in result.card.source_refs:
            self.assertNotIn("generated", source_ref.path)
            self.assertNotIn("sqlite", source_ref.path.lower())

    async def test_chat_citation_labels_match_deduped_source_order(self) -> None:
        await self._write_knowledge(
            _knowledge_card(
                knowledge_id="knowledge_confirmed",
                name="Confirmed lotus",
                status=KnowledgeCardStatus.CONFIRMED,
            )
        )
        self.retrieval.hits = [
            _retrieval_hit(
                _knowledge_source_ref(
                    knowledge_id="knowledge_confirmed",
                    path="project_assets/source/knowledge/items/knowledge_confirmed.json",
                )
            )
        ]

        result = await self.service.run(
            ChatAgentRequest(
                message="这一章怎么推进？",
                chapter_id="chapter_001",
            )
        )
        content = result.card.content
        self.assertIsInstance(content, dict)
        assert isinstance(content, dict)
        citations = content["citations"]

        self.assertEqual(len(result.card.source_refs), 2)
        self.assertEqual([citation["label"] for citation in citations], ["S1", "S2"])
        self.assertIn("[S1] 当前章节", self.llm.prompts[0])
        self.assertIn("[S2] confirmed Knowledge", self.llm.prompts[0])
        self.assertNotIn("[S3]", self.llm.prompts[0])

    async def test_chat_without_context_is_marked_speculative(self) -> None:
        result = await self.service.run(
            ChatAgentRequest(
                message="给我一个新的意象",
                include_current_chapter=False,
                include_confirmed_facts=False,
            )
        )

        self.assertEqual(result.card.source_refs, [])
        content = result.card.content
        self.assertIsInstance(content, dict)
        assert isinstance(content, dict)
        self.assertEqual(content["source_status"], "speculative")
        self.assertEqual(self.retrieval.queries, [])

    async def _write_knowledge(self, card: KnowledgeCard) -> None:
        await self.storage.write_knowledge_record(
            knowledge_category_for_type(card.type),
            card.id,
            card.model_dump(mode="json"),
        )


def _knowledge_card(
    *,
    knowledge_id: str,
    name: str,
    status: KnowledgeCardStatus,
) -> KnowledgeCard:
    return KnowledgeCard(
        id=knowledge_id,
        type=KnowledgeCardType.ITEM,
        name=name,
        aliases=[],
        summary=f"{name} summary",
        fields={},
        source_refs=[_source_ref()],
        status=status,
        created_at="2026-06-27T00:00:00Z",
        updated_at="2026-06-27T00:00:00Z",
    )


def _pending_fact() -> PendingFact:
    return PendingFact(
        id="pending_chat_001",
        fact_type=PendingFactType.ITEM,
        title="Unconfirmed seed",
        content="Unconfirmed seed must not enter chat fact context.",
        proposed_by=ProposedBy.AI,
        source_refs=[_source_ref()],
        status=PendingFactStatus.PENDING,
        created_at="2026-06-27T00:00:00Z",
    )


def _source_ref() -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="秦浩轩发现太初古卷。",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )


def _knowledge_source_ref(*, knowledge_id: str, path: str) -> SourceRef:
    return SourceRef(
        source_type=SourceRefSourceType.KNOWLEDGE,
        source_id=knowledge_id,
        path=path,
        anchor_type=SourceAnchorType.KNOWLEDGE_FIELD,
        field_path="summary",
        excerpt="Confirmed lotus summary",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )


def _retrieval_hit(source_ref: SourceRef) -> RetrievalHit:
    return RetrievalHit(
        source_type=RetrievalSourceType(source_ref.source_type.value),
        source_id=source_ref.source_id,
        excerpt=source_ref.excerpt,
        score=1.0,
        reason=RetrievalReason.EXACT,
        source_ref=source_ref,
    )
