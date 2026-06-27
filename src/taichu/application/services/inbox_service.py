"""Creative inbox use cases."""

from __future__ import annotations

from dataclasses import dataclass

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.ai_card_service import (
    AI_CARDS_FILE,
    IDEAS_FILE,
    PENDING_FACTS_FILE,
    AICardService,
    ConvertPendingFactResult,
    SaveIdeaResult,
)
from taichu.domain.models.ai_card import AIResultCard, AIResultCardStatus
from taichu.domain.models.inbox import ChapterIssue, ChapterIssueStatus, IdeaCard
from taichu.domain.models.pending_fact import PendingFact, PendingFactStatus
from taichu.domain.rules.card_state import assert_pending_fact_transition_allowed

CHAPTER_ISSUES_FILE = "chapter_issues.jsonl"


@dataclass(frozen=True)
class InboxSnapshot:
    """The four lightweight creative inbox lanes."""

    ideas: list[IdeaCard]
    pending_facts: list[PendingFact]
    saved_ai_cards: list[AIResultCard]
    chapter_issues: list[ChapterIssue]


class InboxService:
    """Application service for non-fact workspace inbox assets."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        ai_card_service: AICardService,
    ) -> None:
        self._storage = storage
        self._ai_card_service = ai_card_service

    async def list_inbox(self) -> InboxSnapshot:
        """Return the current non-fact creative inbox lanes."""
        ideas = [
            IdeaCard.model_validate(record)
            for record in await self._storage.list_workspace_records(
                IDEAS_FILE
            )
        ]
        pending_facts = [
            fact
            for fact in [
                PendingFact.model_validate(record)
                for record in await self._storage.list_workspace_records(
                    PENDING_FACTS_FILE
                )
            ]
            if fact.status is PendingFactStatus.PENDING
        ]
        saved_ai_cards = [
            card
            for card in [
                AIResultCard.model_validate(record)
                for record in await self._storage.list_workspace_records(
                    AI_CARDS_FILE
                )
            ]
            if card.status is AIResultCardStatus.SAVED_TO_INBOX
        ]
        chapter_issues = [
            issue
            for issue in [
                ChapterIssue.model_validate(record)
                for record in await self._storage.list_workspace_records(
                    CHAPTER_ISSUES_FILE
                )
            ]
            if issue.status is ChapterIssueStatus.OPEN
        ]
        return InboxSnapshot(
            ideas=ideas,
            pending_facts=pending_facts,
            saved_ai_cards=saved_ai_cards,
            chapter_issues=chapter_issues,
        )

    async def save_card_as_idea(self, card_id: str) -> SaveIdeaResult:
        """Save a SuggestionCard into ideas without creating facts."""
        return await self._ai_card_service.save_suggestion_as_idea(card_id)

    async def convert_card_to_pending_fact(
        self,
        card_id: str,
    ) -> ConvertPendingFactResult:
        """Move a PendingFactCard into pending_facts without confirming it."""
        return await self._ai_card_service.convert_card_to_pending_fact(
            card_id
        )

    async def ignore_pending_fact(self, pending_fact_id: str) -> PendingFact:
        """Ignore a pending fact so it leaves the active inbox lane."""
        records = await self._storage.list_workspace_records(PENDING_FACTS_FILE)
        rewritten: list[dict[str, object]] = []
        ignored: PendingFact | None = None
        for record in records:
            pending_fact = PendingFact.model_validate(record)
            if pending_fact.id == pending_fact_id:
                assert_pending_fact_transition_allowed(
                    pending_fact.status,
                    PendingFactStatus.IGNORED,
                )
                pending_fact = pending_fact.model_copy(
                    update={"status": PendingFactStatus.IGNORED}
                )
                ignored = pending_fact
            rewritten.append(pending_fact.model_dump(mode="json"))

        if ignored is None:
            raise PendingFactNotFoundError(pending_fact_id)

        await self._storage.rewrite_workspace_records(
            PENDING_FACTS_FILE,
            rewritten,
        )
        return ignored


class PendingFactNotFoundError(LookupError):
    """Raised when a pending fact id is absent from the inbox."""

    def __init__(self, pending_fact_id: str) -> None:
        super().__init__(f"待确认设定“{pending_fact_id}”不存在")
