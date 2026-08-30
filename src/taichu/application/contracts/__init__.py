"""应用层依赖的稳定契约。"""

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
    CapabilityResultRecord,
    DeleteRunOutcome,
    GeneralAgentCapabilityResultRepository,
    ResultIdentityPayload,
)
from taichu.application.contracts.general_agent_tool_budget import (
    GeneralAgentToolBudgetClaim,
    GeneralAgentToolBudgetOwner,
    GeneralAgentToolBudgetRepository,
    GeneralAgentToolBudgetSnapshot,
)
from taichu.application.contracts.llm import (
    LLMModelCatalogContract,
    LLMModelIdentity,
    LLMModelProfile,
)
from taichu.application.contracts.storage import (
    ProjectAssetStorageContract,
    StorageBackend,
    StorageContract,
    StorageData,
)

__all__ = [
    "CapabilityResultOwner",
    "CapabilityResultRecord",
    "DeleteRunOutcome",
    "GeneralAgentCapabilityResultRepository",
    "GeneralAgentToolBudgetClaim",
    "GeneralAgentToolBudgetOwner",
    "GeneralAgentToolBudgetRepository",
    "GeneralAgentToolBudgetSnapshot",
    "LLMModelCatalogContract",
    "LLMModelIdentity",
    "LLMModelProfile",
    "ProjectAssetStorageContract",
    "ResultIdentityPayload",
    "StorageBackend",
    "StorageContract",
    "StorageData",
]
