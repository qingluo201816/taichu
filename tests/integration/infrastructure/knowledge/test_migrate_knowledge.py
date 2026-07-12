"""End-to-end migration test against an isolated real Mongo database."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from taichu.cli.migrate_knowledge import (
    EXPECTED_ACTIVE_TYPE_COUNTS,
    KnowledgeMigrationError,
    apply,
    finalize,
    preflight,
)
from taichu.config import settings


class KnowledgeMigrationIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """Prove backup, stage/rename, reconciliation, and guarded finalize."""

    async def asyncSetUp(self) -> None:
        self.database_name = f"taichu_test_{uuid4().hex}"
        self.client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            settings.mongodb_uri,
            tz_aware=True,
            serverSelectionTimeoutMS=1_000,
        )
        try:
            await self.client.admin.command("ping")
        except PyMongoError as error:
            await self.client.close()
            raise unittest.SkipTest(f"本地 MongoDB 不可用：{error}") from error
        self.temp_dir = tempfile.TemporaryDirectory()

    async def asyncTearDown(self) -> None:
        if not self.database_name.startswith("taichu_test_"):
            raise AssertionError("测试数据库前缀校验失败")
        await self.client.drop_database(self.database_name)
        await self.client.close()
        self.temp_dir.cleanup()

    async def test_apply_and_finalize_use_backup_before_deleting_source(self) -> None:
        root = Path(self.temp_dir.name)
        source_dir, chapter_manifest = _write_baseline(root)
        inventory = preflight(source_dir, chapter_manifest)

        result = await apply(
            inventory,
            mongodb_uri=settings.mongodb_uri,
            database_name=self.database_name,
            backup_root=root / "backup",
            client=self.client,
            timestamp=datetime(2026, 7, 11, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result.imported, 58)
        self.assertEqual(result.skipped, 30)
        self.assertEqual(
            len(list((result.backup_dir / "cards").rglob("*.json"))),
            88,
        )
        collection = self.client[self.database_name]["knowledge_cards"]
        self.assertEqual(await collection.count_documents({}), 58)
        self.assertEqual(
            await collection.count_documents({"status": {"$exists": True}}),
            0,
        )

        repeated = await apply(
            inventory,
            mongodb_uri=settings.mongodb_uri,
            database_name=self.database_name,
            backup_root=root / "backup",
            client=self.client,
            timestamp=datetime(2026, 7, 11, 0, 1, tzinfo=UTC),
        )
        self.assertTrue(repeated.already_current)

        await finalize(
            result.backup_dir,
            mongodb_uri=settings.mongodb_uri,
            database_name=self.database_name,
            client=self.client,
        )

        self.assertFalse(source_dir.exists())
        self.assertEqual(await collection.count_documents({}), 58)

    async def test_apply_never_overwrites_nonmatching_nonempty_target(self) -> None:
        root = Path(self.temp_dir.name)
        source_dir, chapter_manifest = _write_baseline(root)
        inventory = preflight(source_dir, chapter_manifest)
        target = self.client[self.database_name]["knowledge_cards"]
        await target.insert_one({"_id": "existing", "sentinel": True})

        with self.assertRaisesRegex(KnowledgeMigrationError, "拒绝覆盖"):
            await apply(
                inventory,
                mongodb_uri=settings.mongodb_uri,
                database_name=self.database_name,
                backup_root=root / "backup",
                client=self.client,
                timestamp=datetime(2026, 7, 11, 0, 2, tzinfo=UTC),
            )

        self.assertEqual(await target.find_one({"_id": "existing"}), {
            "_id": "existing",
            "sentinel": True,
        })
        names = await self.client[self.database_name].list_collection_names()
        self.assertFalse(
            any(name.startswith("knowledge_cards_migration_") for name in names)
        )


def _write_baseline(root: Path) -> tuple[Path, Path]:
    source_dir = root / "knowledge"
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"chapters": [{"id": "chapter-1"}]}),
        encoding="utf-8",
    )
    serial = 0
    for type_name, count in EXPECTED_ACTIVE_TYPE_COUNTS.items():
        for _ in range(count):
            serial += 1
            _write_card(source_dir, type_name, serial, "active")
    for _ in range(30):
        serial += 1
        _write_card(source_dir, "character", serial, "deprecated")
    return source_dir, manifest_path


def _write_card(
    source_dir: Path,
    type_name: str,
    serial: int,
    status: str,
) -> None:
    card_id = f"{type_name}-{serial:03d}"
    payload = {
        "id": card_id,
        "type": type_name,
        "name": f"{type_name}名称{serial}",
        "aliases": [f"别名{serial}"],
        "summary": f"摘要{serial}",
        "importance": "normal",
        "status": status,
        "source_origin": "agent_extract",
        "source_note": "第一章",
        "first_seen_chapter_id": "chapter-1" if type_name == "character" else None,
        "created_at": "2026-07-11T00:00:00.123456Z",
        "updated_at": "2026-07-11T00:00:00.123456Z",
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    target_dir = source_dir / type_name
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{card_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
