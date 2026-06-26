"""JSON 存储实现测试。"""

import tempfile
import unittest
from pathlib import Path

from taichu.application.contracts.storage import StorageBackend
from taichu.infrastructure.storage.json_backend import JsonStorageBackend


class JsonStorageBackendTest(unittest.IsolatedAsyncioTestCase):
    """验证 JSON 实现符合存储契约。"""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.storage = JsonStorageBackend(
            Path(self._temporary_directory.name)
        )

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_backend_satisfies_protocol_and_crud(self) -> None:
        self.assertIsInstance(self.storage, StorageBackend)

        await self.storage.put(
            "characters",
            "character_main",
            {"id": "character_main", "name": "主角"},
        )

        self.assertEqual(
            await self.storage.get("characters", "character_main"),
            {"id": "character_main", "name": "主角"},
        )
        self.assertEqual(len(await self.storage.list("characters")), 1)
        self.assertTrue(
            await self.storage.delete("characters", "character_main")
        )
        self.assertIsNone(
            await self.storage.get("characters", "character_main")
        )

    async def test_rejects_path_segments(self) -> None:
        with self.assertRaises(ValueError):
            await self.storage.get("../characters", "character_main")
