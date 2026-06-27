"""SQLite retrieval projection integration tests."""

import tempfile
import unittest
from pathlib import Path

from taichu.application.contracts import IndexerContract, RetrievalContract
from taichu.application.services.import_service import ImportService
from taichu.application.services.index_service import IndexService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.domain.models import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
    ChapterIssue,
    ChapterIssueSource,
    ChapterIssueStatus,
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
    RetrievalSourceType,
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.rules.fact_scope import RetrievalScopeName
from taichu.infrastructure.indexing import SqliteProjectionRebuilder
from taichu.infrastructure.retrieval import SqliteFTSRetrievalBackend
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


class SqliteProjectionRetrievalTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 6 generated projection and fact-scope retrieval."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        self.importer = ImportService(self.storage)
        self.indexer = SqliteProjectionRebuilder(self.assets_root)
        self.retrieval_backend = SqliteFTSRetrievalBackend(self.assets_root)
        self.index_service = IndexService(self.storage, self.indexer)
        self.retrieval_service = RetrievalService(self.retrieval_backend)

        self.assertIsInstance(self.indexer, IndexerContract)
        self.assertIsInstance(self.retrieval_backend, RetrievalContract)

        await self._write_source_assets()

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_rebuild_searches_chapters_and_confirmed_knowledge(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()

        self.assertTrue(
            (self.assets_root / "generated" / "sqlite" / "taichu.db").exists()
        )

        chapter_hits = await self.retrieval_service.search("太初古卷")
        knowledge_hits = await self.retrieval_service.search("炼气三层")

        self.assertTrue(
            any(hit.source_type is RetrievalSourceType.CHAPTER for hit in chapter_hits)
        )
        self.assertTrue(
            any(
                hit.source_type is RetrievalSourceType.KNOWLEDGE
                for hit in knowledge_hits
            )
        )
        self.assertTrue(
            all(hit.source_ref is not None for hit in [*chapter_hits, *knowledge_hits])
        )

    async def test_short_alias_exact_search_finds_confirmed_knowledge(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()

        hits = await self.retrieval_service.search("玄引")

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].source_type, RetrievalSourceType.KNOWLEDGE)
        self.assertEqual(hits[0].source_id, "knowledge_qinhaoxuan")
        self.assertEqual(hits[0].source_ref.field_path, "name")

    async def test_generated_can_be_deleted_and_rebuilt_without_source_loss(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()
        source_chapter_path = (
            self.assets_root / "source" / "manuscripts" / "chapters" / "chapter_001.md"
        )
        source_knowledge_path = (
            self.assets_root
            / "source"
            / "knowledge"
            / "characters"
            / "knowledge_qinhaoxuan.json"
        )
        chapter_before = source_chapter_path.read_text(encoding="utf-8")
        knowledge_before = source_knowledge_path.read_text(encoding="utf-8")
        generated_junk = self.assets_root / "generated" / "temp" / "junk.tmp"
        generated_junk.write_text("junk", encoding="utf-8")

        await self.index_service.rebuild_generated_projection()

        self.assertFalse(generated_junk.exists())
        self.assertEqual(
            source_chapter_path.read_text(encoding="utf-8"), chapter_before
        )
        self.assertEqual(
            source_knowledge_path.read_text(encoding="utf-8"),
            knowledge_before,
        )
        hits = await self.retrieval_service.search("玄引")
        self.assertGreaterEqual(len(hits), 1)

    async def test_workspace_and_unconfirmed_assets_are_not_indexed(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()

        excluded_terms = [
            "未确认神脉",
            "灵感浮岛",
            "AI裸候选",
            "章节漏洞",
            "归墟伞",
        ]
        for term in excluded_terms:
            with self.subTest(term=term):
                self.assertEqual(await self.retrieval_service.search(term), [])

    async def test_source_refs_point_to_original_sources_not_sqlite_rows(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()

        chapter_hit = (await self.retrieval_service.search("太初古卷"))[0]
        knowledge_hit = (await self.retrieval_service.search("玄引"))[0]

        self.assertEqual(
            chapter_hit.source_ref.source_type,
            SourceRefSourceType.CHAPTER,
        )
        self.assertEqual(
            knowledge_hit.source_ref.source_type,
            SourceRefSourceType.KNOWLEDGE,
        )
        for hit in [chapter_hit, knowledge_hit]:
            with self.subTest(source_id=hit.source_id):
                self.assertIn("project_assets/source/", hit.source_ref.path)
                self.assertNotIn("project_assets/generated/", hit.source_ref.path)
                self.assertNotIn("sqlite", hit.source_ref.path.lower())

    async def test_non_fact_scope_is_not_searched_by_default_backend(
        self,
    ) -> None:
        await self.index_service.rebuild_generated_projection()

        hits = await self.retrieval_service.search(
            "玄引",
            scopes=frozenset({RetrievalScopeName.WORKSPACE.value}),
        )

        self.assertEqual(hits, [])

    async def _write_source_assets(self) -> None:
        await self.importer.import_text(
            "\n".join(
                [
                    "第一章 初临",
                    "秦浩轩发现太初古卷，玄光在掌心流转。",
                    "",
                    "他以凡骨入山，仍记得师父留下的戒言。",
                ]
            ),
            source_name="phase6_fixture.txt",
        )

        chapter_ref = SourceRef(
            source_type=SourceRefSourceType.CHAPTER,
            source_id="chapter_001",
            path="project_assets/source/manuscripts/chapters/chapter_001.md",
            chapter_id="chapter_001",
            anchor_type=SourceAnchorType.PARAGRAPH,
            paragraph_start=1,
            excerpt="秦浩轩发现太初古卷，玄光在掌心流转。",
            excerpt_hash="excerpt_hash",
            source_hash="source_hash",
            created_at="2026-06-27T00:00:00Z",
        )

        confirmed = KnowledgeCard(
            id="knowledge_qinhaoxuan",
            type=KnowledgeCardType.CHARACTER,
            name="秦浩轩",
            aliases=["玄引"],
            summary="秦浩轩持有太初古卷。",
            fields={"cultivation": {"current_realm": "炼气三层"}},
            source_refs=[chapter_ref],
            status=KnowledgeCardStatus.CONFIRMED,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        archived = KnowledgeCard(
            id="knowledge_archived_item",
            type=KnowledgeCardType.ITEM,
            name="归墟伞",
            aliases=[],
            summary="归墟伞是已归档的旧设定。",
            fields={},
            source_refs=[chapter_ref],
            status=KnowledgeCardStatus.ARCHIVED,
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )

        await self.storage.write_knowledge_record(
            "characters",
            confirmed.id,
            confirmed.model_dump(mode="json"),
        )
        await self.storage.write_knowledge_record(
            "items",
            archived.id,
            archived.model_dump(mode="json"),
        )
        await self._write_workspace_assets(chapter_ref)

    async def _write_workspace_assets(self, source_ref: SourceRef) -> None:
        pending_fact = PendingFact(
            id="pending_001",
            fact_type=PendingFactType.CHARACTER,
            title="未确认神脉",
            content="未确认神脉不能进入默认事实检索。",
            proposed_by=ProposedBy.AI,
            source_refs=[source_ref],
            status=PendingFactStatus.PENDING,
            created_at="2026-06-27T00:00:00Z",
        )
        idea = IdeaCard(
            id="idea_001",
            content="灵感浮岛只是创作灵感。",
            source=IdeaCardSource.AI,
            status=IdeaCardStatus.OPEN,
            tags=[],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        ai_card = AIResultCard(
            id="card_001",
            type=AIResultCardType.SUGGESTION,
            workflow=AIWorkflow.ASK_SELECTION,
            status=AIResultCardStatus.GENERATED,
            input_context={},
            content="AI裸候选不能进入默认事实检索。",
            source_refs=[source_ref],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )
        chapter_issue = ChapterIssue(
            id="issue_001",
            title="章节漏洞",
            description="章节漏洞是 workspace 问题，不是小说事实。",
            chapter_id="chapter_001",
            status=ChapterIssueStatus.OPEN,
            source=ChapterIssueSource.AI,
            source_refs=[source_ref],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )

        await self.storage.append_workspace_record(
            "pending_facts.jsonl",
            pending_fact.model_dump(mode="json"),
        )
        await self.storage.append_workspace_record(
            "ideas.jsonl",
            idea.model_dump(mode="json"),
        )
        await self.storage.append_workspace_record(
            "ai_cards.jsonl",
            ai_card.model_dump(mode="json"),
        )
        await self.storage.append_workspace_record(
            "chapter_issues.jsonl",
            chapter_issue.model_dump(mode="json"),
        )
