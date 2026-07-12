"""MongoDB implementation of the structured knowledge repository."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Mapping, NoReturn

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, ReturnDocument
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    ExecutionTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardPage,
    KnowledgeCardQuery,
    KnowledgeRepositoryConcurrentUpdateError,
    KnowledgeRepositoryConflictError,
    KnowledgeRepositoryNotFoundError,
    KnowledgeRepositoryUnavailableError,
    KnowledgeRepositoryValidationError,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)

DEFAULT_KNOWLEDGE_COLLECTION = "knowledge_cards"
LIST_INDEX_NAME = "knowledge_type_lifecycle_updated_at"
CONFIRMED_IDENTITY_INDEX_NAME = "confirmed_identity_unique"


class MongoKnowledgeRepository:
    """Persist structured knowledge in one strictly validated Mongo collection."""

    def __init__(
        self,
        uri: str,
        database_name: str,
        *,
        collection_name: str = DEFAULT_KNOWLEDGE_COLLECTION,
        client: Any | None = None,
        server_selection_timeout_ms: int = 5_000,
    ) -> None:
        self._owns_client = client is None
        self._client = client or AsyncMongoClient(
            uri,
            tz_aware=True,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        self._database = self._client[database_name]
        self._collection_name = collection_name
        self._collection = self._database[collection_name]

    @property
    def collection_name(self) -> str:
        """Return the configured MongoDB collection name."""
        return self._collection_name

    async def initialize(self) -> None:
        """Verify MongoDB and enforce the collection validator and indexes."""
        try:
            await self._database.command("ping")
            collection_names = await self._database.list_collection_names()
            if self._collection_name not in collection_names:
                await self._database.create_collection(
                    self._collection_name,
                    validator=knowledge_collection_validator(),
                    validationLevel="strict",
                    validationAction="error",
                )
            else:
                await self._collection.update_many(
                    {"importance": {"$exists": True}},
                    {
                        "$unset": {"importance": ""},
                        "$set": {"appearance_chapter_count": None},
                    },
                )
                await self._database.command(
                    {
                        "collMod": self._collection_name,
                        "validator": knowledge_collection_validator(),
                        "validationLevel": "strict",
                        "validationAction": "error",
                    }
                )
            await ensure_knowledge_indexes(self._collection)
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error

    async def close(self) -> None:
        """Close a client created by this repository."""
        if self._owns_client:
            await self._client.close()

    async def list_cards(self, query: KnowledgeCardQuery) -> KnowledgeCardPage:
        """Return a filtered page ordered by newest update and stable id."""
        mongo_filter = _query_filter(query)
        try:
            total = await self._collection.count_documents(mongo_filter)
            cursor = (
                self._collection.find(mongo_filter)
                .sort([("updated_at", DESCENDING), ("_id", ASCENDING)])
                .skip(query.offset)
                .limit(query.limit)
            )
            documents = await cursor.to_list(length=query.limit)
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        return KnowledgeCardPage(
            cards=[document_to_card(document) for document in documents],
            total=total,
            offset=query.offset,
            limit=query.limit,
        )

    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """Return all confirmed cards eligible for factual context."""
        cards: list[StructuredKnowledgeCard] = []
        offset = 0
        while True:
            page = await self.list_cards(
                KnowledgeCardQuery(
                    type=type,
                    lifecycles=frozenset(
                        {StructuredKnowledgeLifecycle.CONFIRMED}
                    ),
                    offset=offset,
                    limit=200,
                )
            )
            cards.extend(page.cards)
            offset += len(page.cards)
            if offset >= page.total or not page.cards:
                return cards

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        """Return one card by its business id."""
        try:
            document = await self._collection.find_one({"_id": card_id})
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        return document_to_card(document) if document is not None else None

    async def create_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        """Insert one application-validated card."""
        document = card_to_document(card)
        try:
            await self._collection.insert_one(document)
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        return document_to_card(document)

    async def update_card(
        self,
        card: StructuredKnowledgeCard,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        """Replace one card and optionally reject stale writes."""
        document = card_to_document(card)
        mongo_filter: dict[str, Any] = {"_id": card.id}
        if expected_updated_at is not None:
            mongo_filter["updated_at"] = iso_to_bson_datetime(expected_updated_at)
        try:
            replaced = await self._collection.find_one_and_replace(
                mongo_filter,
                document,
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        if replaced is None:
            await self._raise_missing_or_stale(card.id, expected_updated_at)
        return document_to_card(replaced)

    async def set_lifecycle(
        self,
        card_id: str,
        lifecycle: StructuredKnowledgeLifecycle,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        """Set lifecycle and updated time with optional compare-and-set."""
        mongo_filter: dict[str, Any] = {"_id": card_id}
        if expected_updated_at is not None:
            mongo_filter["updated_at"] = iso_to_bson_datetime(expected_updated_at)
        updated_at = datetime.now(UTC)
        try:
            updated = await self._collection.find_one_and_update(
                mongo_filter,
                {"$set": {"lifecycle": lifecycle.value, "updated_at": updated_at}},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        if updated is None:
            await self._raise_missing_or_stale(card_id, expected_updated_at)
        return document_to_card(updated)

    async def search_confirmed_identity(
        self,
        type: StructuredKnowledgeType,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        """Find confirmed cards whose normalized identity intersects the input."""
        terms = identity_keys(name, aliases)
        if not terms:
            return []
        try:
            cursor = self._collection.find(
                {
                    "type": type.value,
                    "lifecycle": StructuredKnowledgeLifecycle.CONFIRMED.value,
                    "identity_keys": {"$in": terms},
                }
            ).sort("_id", ASCENDING)
            documents = await cursor.to_list(length=None)
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        return [document_to_card(document) for document in documents]

    async def _raise_missing_or_stale(
        self,
        card_id: str,
        expected_updated_at: str | None,
    ) -> NoReturn:
        try:
            exists = await self._collection.count_documents(
                {"_id": card_id}, limit=1
            )
        except PyMongoError as error:
            raise _translate_mongo_error(error) from error
        if not exists:
            raise KnowledgeRepositoryNotFoundError(
                f"知识卡“{card_id}”不存在。"
            )
        if expected_updated_at is not None:
            raise KnowledgeRepositoryConcurrentUpdateError(
                "知识卡已被其他操作更新，请刷新后重试。"
            )
        raise KnowledgeRepositoryConflictError("知识卡更新未生效。")


def knowledge_collection_validator() -> dict[str, Any]:
    """Return the strict JSON Schema used by every knowledge collection."""
    nullable_string = {"bsonType": ["string", "null"]}
    properties: dict[str, Any] = {
        "_id": {"bsonType": "string", "minLength": 1},
        "type": {
            "enum": [knowledge_type.value for knowledge_type in StructuredKnowledgeType]
        },
        "name": {"bsonType": "string"},
        "aliases": {
            "bsonType": "array",
            "items": {"bsonType": "string"},
            "uniqueItems": True,
        },
        "summary": {"bsonType": "string"},
        "appearance_chapter_count": {"bsonType": ["int", "long", "null"], "minimum": 0},
        "lifecycle": {
            "enum": [
                lifecycle.value for lifecycle in StructuredKnowledgeLifecycle
            ]
        },
        "source_origin": {
            "enum": [None, "inbox_fact", "agent_extract", "manual"]
        },
        "source_note": {"bsonType": "string"},
        "role_type": nullable_string,
        "identity": nullable_string,
        "relationship_summary": nullable_string,
        "death_chapter_id": nullable_string,
        "current_realm_text": nullable_string,
        "first_seen_chapter_id": nullable_string,
        "last_seen_chapter_id": nullable_string,
        "system": nullable_string,
        "level_order": {
            "bsonType": ["double", "int", "long", "decimal", "null"]
        },
        "technique_type": nullable_string,
        "grade": nullable_string,
        "practice_condition": nullable_string,
        "owner_faction_id": nullable_string,
        "controlling_faction_id": nullable_string,
        "faction_type": nullable_string,
        "leader_id": nullable_string,
        "item_type": nullable_string,
        "current_holder_id": nullable_string,
        "exceptions": nullable_string,
        "chapter_id": nullable_string,
        "description": nullable_string,
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
        "identity_keys": {
            "bsonType": "array",
            "items": {"bsonType": "string", "minLength": 1},
            "uniqueItems": True,
        },
    }
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "_id",
                "type",
                "name",
                "aliases",
                "summary",
                "appearance_chapter_count",
                "lifecycle",
                "source_origin",
                "source_note",
                "created_at",
                "updated_at",
                "identity_keys",
            ],
            "properties": properties,
            "additionalProperties": False,
        }
    }


async def ensure_knowledge_indexes(collection: Any) -> None:
    """Create the deterministic list and confirmed identity indexes."""
    await collection.create_index(
        [("type", ASCENDING), ("lifecycle", ASCENDING), ("updated_at", DESCENDING)],
        name=LIST_INDEX_NAME,
    )
    await collection.create_index(
        [("type", ASCENDING), ("identity_keys", ASCENDING)],
        name=CONFIRMED_IDENTITY_INDEX_NAME,
        unique=True,
        partialFilterExpression={
            "lifecycle": StructuredKnowledgeLifecycle.CONFIRMED.value
        },
    )


def card_to_document(card: StructuredKnowledgeCard) -> dict[str, Any]:
    """Convert an API/domain card into its BSON-ready representation."""
    payload = card.model_dump(mode="json", exclude_none=False)
    card_id = payload.pop("id")
    payload["_id"] = card_id
    payload["created_at"] = iso_to_bson_datetime(card.created_at)
    payload["updated_at"] = iso_to_bson_datetime(card.updated_at)
    payload["identity_keys"] = identity_keys(card.name, card.aliases)
    return payload


def document_to_card(document: Mapping[str, Any]) -> StructuredKnowledgeCard:
    """Convert a MongoDB document into the public domain representation."""
    payload = dict(document)
    payload["id"] = str(payload.pop("_id"))
    payload.pop("identity_keys", None)
    payload["created_at"] = bson_datetime_to_iso(payload["created_at"])
    payload["updated_at"] = bson_datetime_to_iso(payload["updated_at"])
    return StructuredKnowledgeCard.model_validate(payload)


def identity_keys(name: str, aliases: list[str]) -> list[str]:
    """Derive stable, de-duplicated names used by the unique multikey index."""
    normalized = {
        normalized_value
        for value in [name, *aliases]
        if (normalized_value := normalize_identity(value))
    }
    return sorted(normalized)


def normalize_identity(value: str) -> str:
    """Normalize one human identity without applying fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())


def iso_to_bson_datetime(value: str) -> datetime:
    """Parse an ISO timestamp and require an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise KnowledgeRepositoryValidationError(
            f"知识卡时间格式无效：{value}"
        ) from error
    if parsed.tzinfo is None:
        raise KnowledgeRepositoryValidationError("知识卡时间必须包含时区。")
    parsed = parsed.astimezone(UTC)
    return parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)


def bson_datetime_to_iso(value: datetime) -> str:
    """Serialize one BSON UTC datetime as an ISO 8601 API value."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _query_filter(query: KnowledgeCardQuery) -> dict[str, Any]:
    mongo_filter: dict[str, Any] = {
        "lifecycle": {
            "$in": sorted(lifecycle.value for lifecycle in query.lifecycles)
        }
    }
    if query.type is not None:
        mongo_filter["type"] = query.type.value
    if query.q and query.q.strip():
        pattern = re.escape(query.q.strip())
        mongo_filter["$or"] = [
            {"name": {"$regex": pattern, "$options": "i"}},
            {"aliases": {"$regex": pattern, "$options": "i"}},
            {"summary": {"$regex": pattern, "$options": "i"}},
        ]
    return mongo_filter


def _translate_mongo_error(error: PyMongoError) -> Exception:
    if isinstance(error, DuplicateKeyError):
        return KnowledgeRepositoryConflictError(
            "同类型知识卡的名称或别名已存在。"
        )
    if isinstance(error, OperationFailure) and error.code == 121:
        return KnowledgeRepositoryValidationError(
            "知识卡未通过 MongoDB 字段校验。"
        )
    if isinstance(
        error,
        (
            ConnectionFailure,
            ExecutionTimeout,
            ServerSelectionTimeoutError,
        ),
    ):
        return KnowledgeRepositoryUnavailableError(
            "MongoDB 当前不可用，请确认数据库服务已启动。"
        )
    return KnowledgeRepositoryUnavailableError("MongoDB 知识库存储操作失败。")
