"""Reusable in-memory test doubles."""

from tests.fakes.general_agent_tool_budget import (
    InMemoryGeneralAgentToolBudgetRepository,
)
from tests.fakes.general_agent_effects import (
    InMemoryGeneralAgentEffectRepository,
)
from tests.fakes.knowledge_repository import InMemoryKnowledgeRepository
from tests.fakes.llm import (
    LangChainTestGateway,
    MVPNoRealLLMChatModel,
    make_test_llm_gateway,
)
from tests.fakes.native_tool_chat_model import NativeToolCallSequenceChatModel

__all__ = [
    "InMemoryGeneralAgentToolBudgetRepository",
    "InMemoryGeneralAgentEffectRepository",
    "InMemoryKnowledgeRepository",
    "LangChainTestGateway",
    "MVPNoRealLLMChatModel",
    "NativeToolCallSequenceChatModel",
    "make_test_llm_gateway",
]
