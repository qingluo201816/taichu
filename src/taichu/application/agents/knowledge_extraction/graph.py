"""Agent plugin entry for knowledge extraction."""

from typing import cast

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from taichu.application.agents.contract import AgentManifest
from taichu.application.agents.knowledge_extraction.schemas import (
    KnowledgeExtractionAgentInput,
    KnowledgeExtractionAgentOutput,
)
from taichu.application.agents.knowledge_extraction.workflow import (
    KnowledgeExtractionDependencies,
    build_knowledge_extraction_graph,
)
from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.agent_run_repository import AgentRunRepository
from taichu.application.services.chapter_service import ChapterService
from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)

manifest = AgentManifest(
    name="knowledge_extraction",
    label="正文知识沉淀 Agent",
    description="从当前章节正文抽取候选知识卡，写入作者审核中间态。",
    input_schema=KnowledgeExtractionAgentInput,
    output_schema=KnowledgeExtractionAgentOutput,
    required_capabilities=frozenset(
        {
            "chapter_service",
            "llm",
            "knowledge_repository",
            "knowledge_run_store",
        }
    ),
    exposures=frozenset({"agent_workbench"}),
    supports_streaming=False,
)


def build_graph(context: CapabilityContext) -> CompiledStateGraph:
    """Build the product graph from registered runtime capabilities."""
    return build_knowledge_extraction_graph(
        KnowledgeExtractionDependencies(
            chapter_service=context.require("chapter_service", ChapterService),
            llm=context.require("llm", cast(type[BaseChatModel], BaseChatModel)),
            knowledge_repository=context.require(
                "knowledge_repository",
                cast(
                    type[StructuredKnowledgeRepository],
                    StructuredKnowledgeRepository,
                ),
            ),
            run_store=context.require(
                "knowledge_run_store",
                cast(type[AgentRunRepository], AgentRunRepository),
            ),
        )
    )
