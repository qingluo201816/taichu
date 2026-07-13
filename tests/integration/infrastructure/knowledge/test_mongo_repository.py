"""Real-Mongo integration tests for the structured knowledge repository."""

import unittest
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardQuery,
    KnowledgeRepositoryConcurrentUpdateError,
    KnowledgeRepositoryConflictError,
)
from taichu.config import settings
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
)
from taichu.infrastructure.knowledge.mongo_repository import (
    CONFIRMED_IDENTITY_INDEX_NAME,
    LIST_INDEX_NAME,
    MongoKnowledgeRepository,
)


class MongoKnowledgeRepositoryIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """Exercise validator, indexes, lifecycle filtering, identity, and CAS."""

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
        self.repository = MongoKnowledgeRepository(
            settings.mongodb_uri,
            self.database_name,
            client=self.client,
        )
        await self.repository.initialize()

    async def asyncTearDown(self) -> None:
        if not self.database_name.startswith("taichu_test_"):
            raise AssertionError("测试数据库前缀校验失败")
        await self.client.drop_database(self.database_name)
        await self.client.close()

    async def test_crud_filter_identity_conflict_and_compare_and_set(self) -> None:
        await self.repository.initialize()
        collection = self.client[self.database_name]["knowledge_cards"]
        indexes = await collection.list_indexes()
        index_names = {index["name"] async for index in indexes}
        self.assertIn(LIST_INDEX_NAME, index_names)
        self.assertIn(CONFIRMED_IDENTITY_INDEX_NAME, index_names)

        draft = _card("character-qin", "秦阳", "draft")
        created = await self.repository.create_card(draft)
        self.assertEqual(
            datetime.fromisoformat(
                created.created_at.replace("Z", "+00:00")
            ).microsecond
            % 1000,
            0,
        )
        self.assertEqual((await self.repository.list_cards(KnowledgeCardQuery())).total, 1)
        self.assertEqual(await self.repository.list_confirmed_cards(), [])

        confirmed = await self.repository.set_lifecycle(
            draft.id,
            StructuredKnowledgeLifecycle.CONFIRMED,
            expected_updated_at=created.updated_at,
        )
        self.assertEqual(confirmed.lifecycle.value, "confirmed")
        matches = await self.repository.search_confirmed_identity(
            draft.type,
            "秦阳",
            [],
        )
        self.assertEqual([card.id for card in matches], [draft.id])

        with self.assertRaises(KnowledgeRepositoryConflictError):
            await self.repository.create_card(
                _card("character-other", "其他人", "confirmed", aliases=["秦阳"])
            )

        changed = confirmed.model_copy(
            update={
                "summary": "已更新摘要",
                "updated_at": _now_iso(),
            }
        )
        updated = await self.repository.update_card(
            changed,
            expected_updated_at=confirmed.updated_at,
        )
        self.assertEqual(updated.summary, "已更新摘要")
        with self.assertRaises(KnowledgeRepositoryConcurrentUpdateError):
            await self.repository.update_card(
                changed.model_copy(update={"summary": "过期写入"}),
                expected_updated_at=confirmed.updated_at,
            )

        rejected = await self.repository.set_lifecycle(
            draft.id,
            StructuredKnowledgeLifecycle.REJECTED,
            expected_updated_at=updated.updated_at,
        )
        self.assertEqual(rejected.lifecycle.value, "rejected")
        self.assertEqual((await self.repository.list_cards(KnowledgeCardQuery())).total, 0)

def _card(
    card_id: str,
    name: str,
    lifecycle: str,
    *,
    aliases: list[str] | None = None,
) -> StructuredKnowledgeCard:
    now = _now_iso()
    return StructuredKnowledgeCard.model_validate(
        {
            "id": card_id,
            "type": "character",
            "name": name,
            "aliases": aliases or [],
            "summary": "测试摘要",
            "lifecycle": lifecycle,
            "source_origin": "manual",
            "source_note": "作者确认",
            "created_at": now,
            "updated_at": now,
        }
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
