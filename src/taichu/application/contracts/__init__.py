"""应用层依赖的稳定契约。"""

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
    CapabilityResultRecord,
    DeleteRunOutcome,
    GeneralAgentCapabilityResultRepository,
    ResultIdentityPayload,
)
from taichu.application.contracts.llm import (
    LLMCost,
    LLMGatewayContract,
    LLMMessage,
    LLMModelIdentity,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    LLMToolDefinition,
    LLMUsage,
)
from taichu.application.contracts.storage import (
    ProjectAssetStorageContract,
    StorageBackend,
    StorageContract,
    StorageData,
)
from taichu.application.contracts.retrieval import (
    RetrievalBackend,
    RetrievalTraceRepository,
)

__all__ = [
    "CapabilityResultOwner",
    "CapabilityResultRecord",
    "DeleteRunOutcome",
    "GeneralAgentCapabilityResultRepository",
    "LLMGatewayContract",
    "LLMCost",
    "LLMMessage",
    "LLMModelIdentity",
    "LLMModelProfile",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamEvent",
    "LLMToolCall",
    "LLMToolDefinition",
    "LLMUsage",
    "ProjectAssetStorageContract",
    "RetrievalBackend",
    "RetrievalTraceRepository",
    "ResultIdentityPayload",
    "StorageBackend",
    "StorageContract",
    "StorageData",
]
