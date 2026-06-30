"""Product and data contract models for the single-novel workspace."""

from taichu.domain.models.ai_card import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
)
from taichu.domain.models.ai_workspace import (
    AIReferenceScope,
    AIWorkspaceConversation,
    AIWorkspaceMessage,
    AIWorkspaceMessageRole,
    AIWorkspaceOutputType,
    AIWorkspaceSubtaskType,
    AIWorkspaceTaskType,
    PromptSnapshot,
)
from taichu.domain.models.agent_chat import AgentConversation
from taichu.domain.models.chapter import (
    Chapter,
    ChapterManifest,
    ChapterStatus,
    Volume,
)
from taichu.domain.models.mvp_inbox import (
    MVPInboxIdea,
    MVPInboxIssue,
    MVPInboxPendingFact,
    MVPInboxPriority,
    MVPInboxStatus,
)
from taichu.domain.models.mvp_source_ref import (
    SourceReference,
    SourceReferenceType,
)
from taichu.domain.models.outline import (
    OutlineChapter,
    OutlineVolume,
    WritingOutline,
)
from taichu.domain.models.preferences import (
    EditorBackground,
    EditorFontStyle,
    EditorPreferences,
)
from taichu.domain.models.inbox import (
    ChapterIssue,
    ChapterIssueSource,
    ChapterIssueStatus,
    IdeaCard,
    IdeaCardSource,
    IdeaCardStatus,
)
from taichu.domain.models.import_batch import ImportBatch
from taichu.domain.models.indexing import (
    IndexBuildJob,
    IndexBuildJobAction,
    IndexBuildJobStatus,
)
from taichu.domain.models.knowledge import (
    CharacterCard,
    CharacterImportance,
    KnowledgeCard,
    KnowledgeCardStatus,
    KnowledgeCardType,
)
from taichu.domain.models.structured_knowledge import (
    CharacterKnowledgeFields,
    CharacterStateRecord,
    EventKnowledgeFields,
    FactionKnowledgeFields,
    ForeshadowKnowledgeFields,
    ItemKnowledgeFields,
    LocationKnowledgeFields,
    RealmKnowledgeFields,
    RuleKnowledgeFields,
    StructuredKnowledgeCard,
    StructuredKnowledgeImportance,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
    TechniqueKnowledgeFields,
)
from taichu.domain.models.pending_fact import (
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
)
from taichu.domain.models.retrieval import (
    EmbeddingChunk,
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.models.summary import ChapterSummary, ChapterSummaryStatus
from taichu.domain.models.export import ExportBundle, ExportFile

__all__ = [
    "AIResultCard",
    "AIResultCardStatus",
    "AIResultCardType",
    "AIWorkflow",
    "AIReferenceScope",
    "AIWorkspaceConversation",
    "AIWorkspaceMessage",
    "AIWorkspaceMessageRole",
    "AIWorkspaceOutputType",
    "AIWorkspaceSubtaskType",
    "AIWorkspaceTaskType",
    "PromptSnapshot",
    "AgentConversation",
    "Chapter",
    "ChapterManifest",
    "ChapterStatus",
    "Volume",
    "OutlineChapter",
    "OutlineVolume",
    "WritingOutline",
    "SourceReference",
    "SourceReferenceType",
    "MVPInboxIdea",
    "MVPInboxIssue",
    "MVPInboxPendingFact",
    "MVPInboxPriority",
    "MVPInboxStatus",
    "EditorBackground",
    "EditorFontStyle",
    "EditorPreferences",
    "IdeaCard",
    "IdeaCardSource",
    "IdeaCardStatus",
    "ChapterIssue",
    "ChapterIssueSource",
    "ChapterIssueStatus",
    "ImportBatch",
    "IndexBuildJob",
    "IndexBuildJobAction",
    "IndexBuildJobStatus",
    "CharacterCard",
    "CharacterImportance",
    "KnowledgeCard",
    "KnowledgeCardStatus",
    "KnowledgeCardType",
    "CharacterKnowledgeFields",
    "CharacterStateRecord",
    "EventKnowledgeFields",
    "FactionKnowledgeFields",
    "ForeshadowKnowledgeFields",
    "ItemKnowledgeFields",
    "LocationKnowledgeFields",
    "RealmKnowledgeFields",
    "RuleKnowledgeFields",
    "StructuredKnowledgeCard",
    "StructuredKnowledgeImportance",
    "StructuredKnowledgeStatus",
    "StructuredKnowledgeType",
    "TechniqueKnowledgeFields",
    "PendingFact",
    "PendingFactStatus",
    "PendingFactType",
    "ProposedBy",
    "EmbeddingChunk",
    "RetrievalHit",
    "RetrievalReason",
    "RetrievalSourceType",
    "SourceAnchorType",
    "SourceRef",
    "SourceRefSourceType",
    "ChapterSummary",
    "ChapterSummaryStatus",
    "ExportBundle",
    "ExportFile",
]
