"""MVP creative inbox contracts."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel


class MVPInboxStatus(StrEnum):
    """Common lifecycle states for the three MVP Inbox tabs."""

    TODO = "todo"
    PROCESSED = "processed"
    DEPRECATED = "deprecated"


class MVPInboxPriority(StrEnum):
    """Author-facing priority levels for Inbox items."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class MVPInboxIdea(DomainModel):
    """Manual inspiration item."""

    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_chapter_id: str | None = None
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class MVPInboxPendingFact(DomainModel):
    """Manual fact candidate waiting for author confirmation."""

    id: str = Field(min_length=1)
    title: str = ""
    content: str = Field(min_length=1)
    source_chapter_id: str | None = None
    origin: str = ""
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    confirmed_knowledge_card_id: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class MVPInboxIssue(DomainModel):
    """Manual writing issue item."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = ""
    source_chapter_id: str | None = None
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
