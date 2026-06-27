"""从应用状态提供 FastAPI 依赖。"""

from fastapi import Request

from taichu.application.agents.chat.service import ChatAgentService
from taichu.application.agents.registry import AgentRegistry
from taichu.application.contracts.storage import StorageBackend
from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.chapter_summary_service import (
    ChapterSummaryService,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.export_service import ExportService
from taichu.application.services.index_service import IndexService
from taichu.application.services.inbox_service import InboxService
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.services.pending_fact_confirmation_service import (
    PendingFactConfirmationService,
)
from taichu.application.services.selection_ai_service import SelectionAIService


def provide_agent_registry(request: Request) -> AgentRegistry:
    """返回应用启动时创建的 Agent 注册中心。"""
    return request.app.state.agent_registry


def provide_chat_agent_service(request: Request) -> ChatAgentService:
    """Return the Basic Agent Chat application service."""
    return request.app.state.chat_agent_service


def provide_storage(request: Request) -> StorageBackend:
    """返回应用启动时创建的存储实现。"""
    return request.app.state.storage


def provide_chapter_service(request: Request) -> ChapterService:
    """返回章节应用服务。"""
    return request.app.state.chapter_service


def provide_chapter_summary_service(request: Request) -> ChapterSummaryService:
    """Return the chapter summary application service."""
    return request.app.state.chapter_summary_service


def provide_ai_card_service(request: Request) -> AICardService:
    """返回 AI 卡片应用服务。"""
    return request.app.state.ai_card_service


def provide_selection_ai_service(request: Request) -> SelectionAIService:
    """返回选区 AI 应用服务。"""
    return request.app.state.selection_ai_service


def provide_inbox_service(request: Request) -> InboxService:
    """返回创作收件箱应用服务。"""
    return request.app.state.inbox_service


def provide_export_service(request: Request) -> ExportService:
    """Return the readable export application service."""
    return request.app.state.export_service


def provide_index_service(request: Request) -> IndexService:
    """Return the generated projection maintenance service."""
    return request.app.state.index_service


def provide_knowledge_service(request: Request) -> KnowledgeService:
    """Return the minimal Knowledge application service."""
    return request.app.state.knowledge_service


def provide_pending_fact_confirmation_service(
    request: Request,
) -> PendingFactConfirmationService:
    """Return the PendingFact author confirmation service."""
    return request.app.state.pending_fact_confirmation_service
