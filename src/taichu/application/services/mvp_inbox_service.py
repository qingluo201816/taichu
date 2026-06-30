"""MVP Inbox use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.mvp_knowledge_service import MVPKnowledgeService
from taichu.domain.models import (
    MVPInboxIdea,
    MVPInboxIssue,
    MVPInboxPendingFact,
    MVPInboxStatus,
    StructuredKnowledgeCard,
    StructuredKnowledgeType,
)

INBOX_IDEAS_FILE = "inbox_ideas.jsonl"
INBOX_PENDING_FACTS_FILE = "inbox_pending_facts.jsonl"
INBOX_ISSUES_FILE = "inbox_issues.jsonl"


@dataclass(frozen=True)
class PendingFactConfirmResult:
    """Result of confirming a pending fact into a knowledge card."""

    pending_fact: MVPInboxPendingFact
    knowledge_card: StructuredKnowledgeCard


class MVPInboxService:
    """Manage the three MVP Inbox tabs."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        knowledge_service: MVPKnowledgeService,
    ) -> None:
        self._storage = storage
        self._knowledge_service = knowledge_service

    async def list_items(self, tab: str) -> list[MVPInboxIdea | MVPInboxPendingFact | MVPInboxIssue]:
        """List active items for one Inbox tab."""
        if tab == "ideas":
            return [
                item
                for item in await self._list_ideas()
                if item.status is MVPInboxStatus.TODO
            ]
        if tab == "pending-facts":
            return [
                item
                for item in await self._list_pending_facts()
                if item.status is MVPInboxStatus.TODO
            ]
        if tab == "issues":
            return [
                item
                for item in await self._list_issues()
                if item.status is MVPInboxStatus.TODO
            ]
        raise InboxValidationError("未知的 Inbox 分类")

    async def create_idea(self, data: dict[str, Any]) -> MVPInboxIdea:
        """Create a manual inspiration item."""
        now = _now_iso()
        item = MVPInboxIdea.model_validate(
            {
                "id": data.get("id") or f"idea-{uuid4().hex}",
                "content": data.get("content", ""),
                "source_chapter_id": data.get("source_chapter_id"),
                "priority": data.get("priority", "normal"),
                "status": "todo",
                "created_at": data.get("created_at", now),
                "updated_at": now,
            }
        )
        await self._storage.append_workspace_record(
            INBOX_IDEAS_FILE,
            item.model_dump(mode="json"),
        )
        return item

    async def create_pending_fact(self, data: dict[str, Any]) -> MVPInboxPendingFact:
        """Create a manual pending fact item."""
        now = _now_iso()
        item = MVPInboxPendingFact.model_validate(
            {
                "id": data.get("id") or f"pending-fact-{uuid4().hex}",
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "source_chapter_id": data.get("source_chapter_id"),
                "origin": data.get("origin", data.get("出处", "")),
                "priority": data.get("priority", "normal"),
                "status": "todo",
                "confirmed_knowledge_card_id": None,
                "created_at": data.get("created_at", now),
                "updated_at": now,
            }
        )
        await self._storage.append_workspace_record(
            INBOX_PENDING_FACTS_FILE,
            item.model_dump(mode="json"),
        )
        return item

    async def create_issue(self, data: dict[str, Any]) -> MVPInboxIssue:
        """Create a manual issue item."""
        now = _now_iso()
        item = MVPInboxIssue.model_validate(
            {
                "id": data.get("id") or f"issue-{uuid4().hex}",
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "source_chapter_id": data.get("source_chapter_id"),
                "priority": data.get("priority", "normal"),
                "status": "todo",
                "created_at": data.get("created_at", now),
                "updated_at": now,
            }
        )
        await self._storage.append_workspace_record(
            INBOX_ISSUES_FILE,
            item.model_dump(mode="json"),
        )
        return item

    async def patch_idea(self, item_id: str, updates: dict[str, Any]) -> MVPInboxIdea:
        """Patch one idea item."""
        return await self._patch_jsonl_item(
            INBOX_IDEAS_FILE,
            item_id,
            updates,
            MVPInboxIdea,
        )

    async def patch_pending_fact(
        self,
        item_id: str,
        updates: dict[str, Any],
    ) -> MVPInboxPendingFact:
        """Patch one pending fact item."""
        return await self._patch_jsonl_item(
            INBOX_PENDING_FACTS_FILE,
            item_id,
            updates,
            MVPInboxPendingFact,
        )

    async def patch_issue(self, item_id: str, updates: dict[str, Any]) -> MVPInboxIssue:
        """Patch one issue item."""
        return await self._patch_jsonl_item(
            INBOX_ISSUES_FILE,
            item_id,
            updates,
            MVPInboxIssue,
        )

    async def confirm_pending_fact(
        self,
        item_id: str,
        knowledge_type: StructuredKnowledgeType,
        card_preview: dict[str, Any],
    ) -> PendingFactConfirmResult:
        """Confirm a pending fact into structured knowledge and keep the item."""
        pending_fact = await self._find_pending_fact(item_id)
        payload = dict(card_preview)
        payload.setdefault("name", pending_fact.title or pending_fact.content[:20])
        payload.setdefault("summary", pending_fact.content[:80])
        payload.setdefault("body", pending_fact.content)
        payload.setdefault("status", "draft")
        card = await self._knowledge_service.create_card(knowledge_type, payload)
        processed = await self.patch_pending_fact(
            pending_fact.id,
            {
                "status": "processed",
                "confirmed_knowledge_card_id": card.id,
            },
        )
        return PendingFactConfirmResult(
            pending_fact=processed,
            knowledge_card=card,
        )

    async def _list_ideas(self) -> list[MVPInboxIdea]:
        return [
            MVPInboxIdea.model_validate(record)
            for record in await self._storage.list_workspace_records(
                INBOX_IDEAS_FILE
            )
        ]

    async def _list_pending_facts(self) -> list[MVPInboxPendingFact]:
        return [
            MVPInboxPendingFact.model_validate(record)
            for record in await self._storage.list_workspace_records(
                INBOX_PENDING_FACTS_FILE
            )
        ]

    async def _list_issues(self) -> list[MVPInboxIssue]:
        return [
            MVPInboxIssue.model_validate(record)
            for record in await self._storage.list_workspace_records(INBOX_ISSUES_FILE)
        ]

    async def _find_pending_fact(self, item_id: str) -> MVPInboxPendingFact:
        for item in await self._list_pending_facts():
            if item.id == item_id:
                return item
        raise InboxItemNotFoundError(f"待确认事实“{item_id}”不存在")

    async def _patch_jsonl_item(
        self,
        filename: str,
        item_id: str,
        updates: dict[str, Any],
        model_type: type[MVPInboxIdea] | type[MVPInboxPendingFact] | type[MVPInboxIssue],
    ) -> Any:
        records = await self._storage.list_workspace_records(filename)
        rewritten: list[dict[str, object]] = []
        updated_item: Any | None = None
        for record in records:
            item = model_type.model_validate(record)
            if item.id == item_id:
                payload = item.model_dump(mode="json")
                for key, value in updates.items():
                    if key in payload:
                        payload[key] = value
                payload["updated_at"] = _now_iso()
                item = model_type.model_validate(payload)
                updated_item = item
            rewritten.append(item.model_dump(mode="json"))
        if updated_item is None:
            raise InboxItemNotFoundError(f"Inbox 项“{item_id}”不存在")
        await self._storage.rewrite_workspace_records(filename, rewritten)
        return updated_item


class InboxItemNotFoundError(LookupError):
    """Raised when an Inbox item does not exist."""


class InboxValidationError(ValueError):
    """Raised when an Inbox request is invalid."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
