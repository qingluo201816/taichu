"""MVP creative inbox contracts."""

from enum import StrEnum
from typing import Literal

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


class MVPInboxEntryType(StrEnum):
    """Stable discriminator for the Inbox record shapes."""

    IDEA = "idea"
    PENDING_FACT = "pending_fact"
    ISSUE = "issue"
    DECISION = "decision"


class MVPInboxIssueRelationKind(StrEnum):
    """通用问题记录与外部冻结对象之间的关系。"""

    DOCUMENTS = "documents"
    CAUSED_BY = "caused_by"
    OBSERVED_IN = "observed_in"
    CLOSES = "closes"


class MVPInboxIssueLink(DomainModel):
    """不复制外部对象内容的稳定类型化关联。"""

    namespace: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    relation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    subject_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    relation_kind: MVPInboxIssueRelationKind
    subject_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MVPInboxIdea(DomainModel):
    """Manual inspiration item."""

    id: str = Field(min_length=1)
    entry_type: Literal[MVPInboxEntryType.IDEA] = MVPInboxEntryType.IDEA
    title: str = ""
    content: str = Field(min_length=1)
    source_chapter_id: str | None = None
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class MVPInboxPendingFact(DomainModel):
    """Manual fact candidate waiting for author confirmation."""

    id: str = Field(min_length=1)
    entry_type: Literal[MVPInboxEntryType.PENDING_FACT] = (
        MVPInboxEntryType.PENDING_FACT
    )
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
    entry_type: Literal[MVPInboxEntryType.ISSUE] = MVPInboxEntryType.ISSUE
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_chapter_id: str | None = None
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    revision: int = Field(default=0, ge=0)
    links: tuple[MVPInboxIssueLink, ...] = ()
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class MVPInboxDecision(DomainModel):
    """Manual decision item."""

    id: str = Field(min_length=1)
    entry_type: Literal[MVPInboxEntryType.DECISION] = MVPInboxEntryType.DECISION
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_chapter_id: str | None = None
    priority: MVPInboxPriority = MVPInboxPriority.NORMAL
    status: MVPInboxStatus = MVPInboxStatus.TODO
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
