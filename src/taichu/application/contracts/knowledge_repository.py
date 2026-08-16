"""Repository boundary for MongoDB-backed structured knowledge cards."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
)


class KnowledgeCardSort(StrEnum):
    """Application-selected ordering for a knowledge-card page."""

    RECENT = "recent"
    REALM_LEVEL = "realm_level"
    APPEARANCE_COUNT = "appearance_count"


@dataclass(frozen=True, slots=True)
class KnowledgeCardQuery:
    """Storage-level filters for one deterministic page of knowledge cards."""

    type: StructuredKnowledgeType | None = None
    lifecycles: frozenset[StructuredKnowledgeLifecycle] = field(
        default_factory=lambda: frozenset(
            {
                StructuredKnowledgeLifecycle.DRAFT,
                StructuredKnowledgeLifecycle.CONFIRMED,
            }
        )
    )
    q: str | None = None
    sort: KnowledgeCardSort = KnowledgeCardSort.RECENT
    offset: int = 0
    limit: int = 50

    def __post_init__(self) -> None:
        if not self.lifecycles:
            raise ValueError("知识卡查询必须至少包含一个生命周期。")
        if self.offset < 0:
            raise ValueError("知识卡查询偏移量不能小于零。")
        if self.limit < 1 or self.limit > 200:
            raise ValueError("知识卡单次查询数量必须在 1 到 200 之间。")


@dataclass(frozen=True, slots=True)
class KnowledgeCardPage:
    """One page of knowledge cards and its total matching record count."""

    cards: list[StructuredKnowledgeCard]
    total: int
    offset: int
    limit: int


class KnowledgeRepositoryError(RuntimeError):
    """Base error exposed by the structured knowledge storage boundary."""


class KnowledgeRepositoryNotFoundError(KnowledgeRepositoryError):
    """Raised when the requested knowledge card does not exist."""


class KnowledgeRepositoryConflictError(KnowledgeRepositoryError):
    """Raised for duplicate identifiers or confirmed identity collisions."""


class KnowledgeRepositoryConcurrentUpdateError(KnowledgeRepositoryConflictError):
    """Raised when compare-and-set detects a stale knowledge card update."""


class KnowledgeRepositoryValidationError(KnowledgeRepositoryError):
    """Raised when MongoDB rejects a document that violates its validator."""


class KnowledgeRepositoryUnavailableError(KnowledgeRepositoryError):
    """Raised when MongoDB cannot serve a knowledge repository operation."""


@runtime_checkable
class StructuredKnowledgeRepository(Protocol):
    """Technology-independent persistence contract for structured knowledge."""

    async def list_cards(self, query: KnowledgeCardQuery) -> KnowledgeCardPage:
        """Return one filtered and deterministically ordered card page."""
        ...

    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        """Return confirmed cards that are eligible for factual context."""
        ...

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        """Return one card by its stable business identifier."""
        ...

    async def create_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        """Create one card without changing its application-approved lifecycle."""
        ...

    async def update_card(
        self,
        card: StructuredKnowledgeCard,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        """Replace one card, optionally using updated_at compare-and-set."""
        ...

    async def set_lifecycle(
        self,
        card_id: str,
        lifecycle: StructuredKnowledgeLifecycle,
        *,
        expected_updated_at: str | None = None,
    ) -> StructuredKnowledgeCard:
        """Transition one card lifecycle, optionally using compare-and-set."""
        ...

    async def search_confirmed_identity(
        self,
        type: StructuredKnowledgeType,
        name: str,
        aliases: list[str],
    ) -> list[StructuredKnowledgeCard]:
        """Find confirmed cards sharing normalized names or aliases."""
        ...
