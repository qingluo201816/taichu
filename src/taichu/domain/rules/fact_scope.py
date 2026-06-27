"""Fact-scope guardrails that prevent AI/workspace pollution."""

from enum import StrEnum
from typing import Any

from taichu.domain.exceptions import FactScopeViolationError
from taichu.domain.models.ai_card import AIResultCard
from taichu.domain.models.chapter import Chapter
from taichu.domain.models.inbox import ChapterIssue, IdeaCard
from taichu.domain.models.knowledge import KnowledgeCard, KnowledgeCardStatus
from taichu.domain.models.pending_fact import PendingFact
from taichu.domain.models.summary import ChapterSummary


class RetrievalScopeName(StrEnum):
    """Named retrieval scopes for product use."""

    FACT = "fact_scope"
    WORKSPACE = "workspace_scope"
    DEBUG = "debug_scope"


class FactScopeSource(StrEnum):
    """Coarse source buckets used by scope definitions."""

    CHAPTERS = "chapters"
    CONFIRMED_KNOWLEDGE = "confirmed_knowledge"
    PENDING_FACTS = "pending_facts"
    IDEAS = "ideas"
    AI_CARDS = "ai_cards"
    SUMMARIES = "summaries"
    GENERATED = "generated"


_SCOPE_DEFINITIONS: dict[RetrievalScopeName, frozenset[FactScopeSource]] = {
    RetrievalScopeName.FACT: frozenset(
        {
            FactScopeSource.CHAPTERS,
            FactScopeSource.CONFIRMED_KNOWLEDGE,
        }
    ),
    RetrievalScopeName.WORKSPACE: frozenset(
        {
            FactScopeSource.PENDING_FACTS,
            FactScopeSource.IDEAS,
            FactScopeSource.AI_CARDS,
            FactScopeSource.SUMMARIES,
        }
    ),
    RetrievalScopeName.DEBUG: frozenset({FactScopeSource.GENERATED}),
}


def resolve_retrieval_scope(
    scope: RetrievalScopeName | str | None = None,
) -> frozenset[FactScopeSource]:
    """Return the configured source buckets, defaulting to fact_scope."""
    if scope is None:
        return _SCOPE_DEFINITIONS[RetrievalScopeName.FACT]
    return _SCOPE_DEFINITIONS[RetrievalScopeName(scope)]


def is_allowed_in_fact_scope(item: Any) -> bool:
    """Return whether an item may be read by default fact_scope."""
    if isinstance(item, Chapter):
        return True
    if isinstance(item, KnowledgeCard):
        return item.status is KnowledgeCardStatus.CONFIRMED
    if isinstance(
        item,
        (PendingFact, IdeaCard, ChapterIssue, AIResultCard, ChapterSummary),
    ):
        return False
    return False


def assert_allowed_in_fact_scope(item: Any) -> None:
    """Raise if an item would pollute default fact_scope retrieval."""
    if not is_allowed_in_fact_scope(item):
        raise FactScopeViolationError(
            f"{type(item).__name__} is not allowed in default fact_scope"
        )
