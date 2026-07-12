"""从应用状态提供 FastAPI 依赖。"""

from fastapi import Request

from taichu.application.agents.registry import AgentRegistry
from taichu.application.contracts.storage import StorageBackend
from taichu.application.contracts.llm import LLMGatewayContract
from taichu.application.contracts.llm_usage import LLMUsageRepository
from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.chapter_summary_service import (
    ChapterSummaryService,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.export_service import ExportService
from taichu.application.services.inbox_service import InboxService
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.services.knowledge_extraction_service import (
    KnowledgeExtractionService,
)
from taichu.application.services.knowledge_extraction_evaluation_service import (
    KnowledgeExtractionEvaluationService,
)
from taichu.application.services.agent_task_event_service import AgentTaskEventCenter
from taichu.application.services.mvp_inbox_service import MVPInboxService
from taichu.application.services.outline_service import OutlineService
from taichu.application.services.selection_ai_service import SelectionAIService
from taichu.application.services.settings_service import SettingsPreferenceService
from taichu.application.services.writing_ai_service import WritingAIService


def provide_agent_registry(request: Request) -> AgentRegistry:
    """返回应用启动时创建的 Agent 注册中心。"""
    return request.app.state.agent_registry


def provide_storage(request: Request) -> StorageBackend:
    """返回应用启动时创建的存储实现。"""
    return request.app.state.storage


def provide_chapter_service(request: Request) -> ChapterService:
    """返回章节应用服务。"""
    return request.app.state.chapter_service


def provide_outline_service(request: Request) -> OutlineService:
    """Return the MVP writing outline application service."""
    return request.app.state.outline_service


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


def provide_mvp_inbox_service(request: Request) -> MVPInboxService:
    """Return the MVP Inbox application service."""
    return request.app.state.mvp_inbox_service


def provide_export_service(request: Request) -> ExportService:
    """Return the readable export application service."""
    return request.app.state.export_service


def provide_knowledge_service(request: Request) -> KnowledgeService:
    """Return the minimal Knowledge application service."""
    return request.app.state.knowledge_service


def provide_knowledge_extraction_service(
    request: Request,
) -> KnowledgeExtractionService:
    """Return the knowledge extraction Agent workbench service."""
    return request.app.state.knowledge_extraction_service


def provide_knowledge_extraction_evaluation_service(
    request: Request,
) -> KnowledgeExtractionEvaluationService:
    """返回知识沉淀效果评估应用服务。"""

    return request.app.state.knowledge_extraction_evaluation_service


def provide_agent_task_event_center(request: Request) -> AgentTaskEventCenter:
    """Return the Agent task event center."""
    return request.app.state.agent_task_events


def provide_settings_preference_service(request: Request) -> SettingsPreferenceService:
    """Return the MVP settings preference service."""
    return request.app.state.settings_preference_service


def provide_writing_ai_service(request: Request) -> WritingAIService:
    """Return the writing-page real AI run service."""
    return request.app.state.writing_ai_service


def provide_llm_gateway(request: Request) -> LLMGatewayContract:
    """返回应用唯一模型网关。"""
    return request.app.state.llm_gateway


def provide_llm_usage_repository(request: Request) -> LLMUsageRepository:
    """返回模型调用遥测仓储。"""
    return request.app.state.llm_usage_repository
