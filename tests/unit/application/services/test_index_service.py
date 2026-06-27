"""Index service hardening tests."""

import unittest
from typing import cast

from taichu.application.contracts.indexer import IndexerContract
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.index_service import IndexService


class FakeStorage:
    """Minimal generated storage fake."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.clear_calls = 0

    async def clear_generated(self) -> None:
        self.clear_calls += 1
        if self.error is not None:
            raise self.error


class FakeIndexer:
    """Minimal projection indexer fake."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.rebuild_calls = 0

    async def rebuild(self) -> None:
        self.rebuild_calls += 1
        if self.error is not None:
            raise self.error


class IndexServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify generated maintenance jobs report failed states."""

    async def test_rebuild_failure_returns_failed_job(self) -> None:
        storage = FakeStorage()
        indexer = FakeIndexer(RuntimeError("sqlite locked"))
        service = IndexService(
            cast(ProjectAssetStorageContract, storage),
            cast(IndexerContract, indexer),
        )

        job = await service.rebuild_generated_projection()

        self.assertEqual(job.action.value, "rebuild")
        self.assertEqual(job.status.value, "failed")
        self.assertIn("sqlite locked", job.message)
        self.assertEqual(storage.clear_calls, 1)
        self.assertEqual(indexer.rebuild_calls, 1)

    async def test_clear_failure_returns_failed_job(self) -> None:
        storage = FakeStorage(RuntimeError("permission denied"))
        indexer = FakeIndexer()
        service = IndexService(
            cast(ProjectAssetStorageContract, storage),
            cast(IndexerContract, indexer),
        )

        job = await service.clear_generated()

        self.assertEqual(job.action.value, "clear")
        self.assertEqual(job.status.value, "failed")
        self.assertIn("permission denied", job.message)
        self.assertEqual(storage.clear_calls, 1)
        self.assertEqual(indexer.rebuild_calls, 0)
