"""Application contract Protocol tests."""

import unittest

from taichu.application.contracts import (
    IndexerContract,
    LLMContract,
    RetrievalContract,
    RetrievalQuery,
    StorageContract,
)
from taichu.domain.models import (
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)


def create_hit() -> RetrievalHit:
    """Create a retrieval hit with required SourceRef evidence."""
    ref = SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="正文证据",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )
    return RetrievalHit(
        source_type=RetrievalSourceType.CHAPTER,
        source_id="chapter_001",
        excerpt="正文证据",
        score=1.0,
        reason=RetrievalReason.EXACT,
        source_ref=ref,
    )


class DummyStorage:
    """Storage contract stub."""

    async def get(
        self,
        collection: str,
        key: str,
    ) -> dict[str, object] | None:
        return {"collection": collection, "key": key}

    async def list(self, collection: str) -> list[dict[str, object]]:
        return [{"collection": collection}]

    async def put(
        self,
        collection: str,
        key: str,
        data: dict[str, object],
    ) -> None:
        return None

    async def delete(self, collection: str, key: str) -> bool:
        return True


class DummyRetrieval:
    """Retrieval contract stub."""

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        return [create_hit()]


class DummyLLM:
    """LLM contract stub."""

    async def complete(self, prompt: str) -> str:
        return prompt


class DummyIndexer:
    """Indexer contract stub."""

    async def rebuild(self) -> None:
        return None


class ApplicationContractTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 0 application contract entry points exist."""

    async def test_protocols_accept_minimal_stubs(self) -> None:
        storage = DummyStorage()
        retrieval = DummyRetrieval()
        llm = DummyLLM()
        indexer = DummyIndexer()

        self.assertIsInstance(storage, StorageContract)
        self.assertIsInstance(retrieval, RetrievalContract)
        self.assertIsInstance(llm, LLMContract)
        self.assertIsInstance(indexer, IndexerContract)
        self.assertEqual(
            (await retrieval.search(RetrievalQuery(text="主角")))[0]
            .source_ref.source_id,
            "chapter_001",
        )
