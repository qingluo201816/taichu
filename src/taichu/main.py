"""组装并启动太初 FastAPI 应用。"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from taichu.api.router import register_routes
from taichu.application.agents.chat.service import ChatAgentService
from taichu.application.agents.registry import AgentRegistry
from taichu.application.capabilities import CapabilityContext
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
from taichu.application.tools.registry import ToolRegistry
from taichu.config import Settings, settings
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.factory import create_llm
from taichu.infrastructure.plugin_discovery import (
    discover_agents,
    discover_tools,
)
from taichu.infrastructure.indexing import SqliteProjectionRebuilder
from taichu.infrastructure.retrieval import SqliteFTSRetrievalBackend
from taichu.infrastructure.storage.json_backend import JsonStorageBackend
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


def create_app(
    app_settings: Settings = settings,
    *,
    llm: BaseChatModel | None = None,
) -> FastAPI:
    """创建并组装 FastAPI 应用。"""
    storage = JsonStorageBackend(app_settings.project_assets_dir / "source")
    project_storage = ProjectAssetStorageBackend(app_settings.project_assets_dir)
    chapter_service = ChapterService(project_storage)
    chat_model = llm or create_llm(app_settings)
    llm_service = LangChainLLMAdapter(chat_model)
    ai_card_service = AICardService(project_storage)
    inbox_service = InboxService(project_storage, ai_card_service)
    knowledge_service = KnowledgeService(project_storage)
    pending_fact_confirmation_service = PendingFactConfirmationService(
        project_storage,
        knowledge_service,
    )
    selection_ai_service = SelectionAIService(llm_service, ai_card_service)
    retrieval_backend = SqliteFTSRetrievalBackend(app_settings.project_assets_dir)
    projection_rebuilder = SqliteProjectionRebuilder(app_settings.project_assets_dir)
    index_service = IndexService(project_storage, projection_rebuilder)
    export_service = ExportService(project_storage)
    chat_agent_service = ChatAgentService(
        chapter_service=chapter_service,
        knowledge_service=knowledge_service,
        retrieval=retrieval_backend,
        llm=llm_service,
        ai_card_service=ai_card_service,
    )
    chapter_summary_service = ChapterSummaryService(
        storage=project_storage,
        chapter_service=chapter_service,
        knowledge_service=knowledge_service,
        retrieval=retrieval_backend,
        llm=llm_service,
        ai_card_service=ai_card_service,
    )
    capability_context = CapabilityContext(
        capabilities={
            "llm": chat_model,
            "retrieval": retrieval_backend,
            "storage": storage,
        }
    )
    agent_registry = AgentRegistry(capability_context)
    agent_registry.register_all(discover_agents("taichu.application.agents"))
    tool_registry = ToolRegistry(capability_context)
    tool_registry.register_all(discover_tools("taichu.application.tools"))

    application = FastAPI(
        title="Taichu",
        description="太初 - 单本玄幻小说个人写作助手",
    )
    application.state.agent_registry = agent_registry
    application.state.tool_registry = tool_registry
    application.state.storage = storage
    application.state.project_storage = project_storage
    application.state.chat_agent_service = chat_agent_service
    application.state.chapter_service = chapter_service
    application.state.ai_card_service = ai_card_service
    application.state.inbox_service = inbox_service
    application.state.export_service = export_service
    application.state.index_service = index_service
    application.state.knowledge_service = knowledge_service
    application.state.pending_fact_confirmation_service = (
        pending_fact_confirmation_service
    )
    application.state.selection_ai_service = selection_ai_service
    application.state.chapter_summary_service = chapter_summary_service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_routes(application)
    return application


app = create_app()


def main() -> None:
    """启动开发服务器。"""
    uvicorn.run(
        "taichu.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
