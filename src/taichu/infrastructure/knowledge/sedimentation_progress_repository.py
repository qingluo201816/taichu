"""MongoDB storage for the single knowledge-sedimentation frontier."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from taichu.application.contracts.knowledge_sedimentation_progress_repository import KnowledgeSedimentationProgress
from taichu.application.contracts.knowledge_repository import KnowledgeRepositoryUnavailableError

_COLLECTION = "knowledge_sedimentation_state"
_DOCUMENT_ID = "current"


class MongoKnowledgeSedimentationProgressRepository:
    """Store one application-state document outside the knowledge-card facts."""

    def __init__(self, uri: str, database_name: str, *, client: Any | None = None) -> None:
        self._owns_client = client is None
        self._client = client or AsyncMongoClient(uri, tz_aware=True)
        self._collection = self._client[database_name][_COLLECTION]

    async def initialize(self) -> None:
        try:
            await self._collection.database.command("ping")
        except PyMongoError as error:
            raise KnowledgeRepositoryUnavailableError("MongoDB 当前不可用，无法读取知识沉淀进度。") from error

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def get_progress(self) -> KnowledgeSedimentationProgress:
        try:
            document = await self._collection.find_one({"_id": _DOCUMENT_ID})
        except PyMongoError as error:
            raise KnowledgeRepositoryUnavailableError("MongoDB 当前不可用，无法读取知识沉淀进度。") from error
        if document is None:
            return KnowledgeSedimentationProgress()
        return KnowledgeSedimentationProgress(
            last_accepted_chapter_id=document.get("last_accepted_chapter_id"),
            updated_at=_iso(document.get("updated_at")),
        )

    async def advance_to(self, chapter_id: str) -> KnowledgeSedimentationProgress:
        now = datetime.now(UTC)
        try:
            await self._collection.update_one(
                {"_id": _DOCUMENT_ID},
                {"$set": {"last_accepted_chapter_id": chapter_id, "updated_at": now}},
                upsert=True,
            )
        except PyMongoError as error:
            raise KnowledgeRepositoryUnavailableError("MongoDB 当前不可用，无法更新知识沉淀进度。") from error
        return KnowledgeSedimentationProgress(chapter_id, _iso(now))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
