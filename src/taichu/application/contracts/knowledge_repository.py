"""Repository contracts for structured knowledge cards."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from taichu.domain.models.structured_knowledge import StructuredKnowledgeCard


@runtime_checkable
class StructuredKnowledgeRepository(Protocol):
    """Storage boundary used by Agents and APIs, independent of JSON details."""

    async def list_active_cards(
        self,
        type: str | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """List active cards, optionally filtered by type."""
        ...

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        """Return one card across all structured knowledge types."""
        ...

    async def create_active_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        """Persist one active card after author confirmation."""
        ...

    async def patch_active_card(
        self,
        card_id: str,
        updates: dict[str, Any],
    ) -> StructuredKnowledgeCard:
        """Patch one active card without overwriting protected non-empty fields."""
        ...

    async def search_active_identity(
        self,
        type: str,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        """Find active cards with matching names, aliases or clear mentions."""
        ...
