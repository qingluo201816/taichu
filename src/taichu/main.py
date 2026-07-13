"""组装并启动太初 FastAPI 应用。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import uvicorn
from typing import cast
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.language_models.chat_models import BaseChatModel

from taichu.api.router import register_routes
from taichu.application.agents.registry import AgentRegistry
from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMModelIdentity,
)
from taichu.application.contracts.knowledge_repository import (
    KnowledgeRepositoryUnavailableError,
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.knowledge_sedimentation_progress_repository import (
    InMemoryKnowledgeSedimentationProgressRepository,
)
from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.chapter_summary_service import (
    ChapterSummaryService,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.export_service import ExportService
from taichu.application.services.inbox_service import InboxService
from taichu.application.services.knowledge_service import (
    KnowledgeService,
    KnowledgeUnavailableError,
)
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
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools.registry import ToolRegistry
from taichu.config import Settings, settings
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.catalog import LLMModelCatalog
from taichu.infrastructure.llm.rightcode import RightCodeLLMGateway
from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository
from taichu.infrastructure.evaluations import (
    JsonEvaluationDatasetRepository,
    JsonEvaluationResultStore,
    create_evaluation_judge,
)
from taichu.infrastructure.plugin_discovery import (
    discover_agents,
    discover_tools,
)
from taichu.infrastructure.agent_runs import JsonAgentRunStore
from taichu.infrastructure.knowledge import (
    MongoKnowledgeRepository,
    MongoKnowledgeSedimentationProgressRepository,
)
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.storage.json_backend import JsonStorageBackend
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)


def create_app(
    app_settings: Settings = settings,
    *,
    llm: BaseChatModel | None = None,
    llm_model_identity: LLMModelIdentity | None = None,
    llm_gateway: LLMGatewayContract | None = None,
    knowledge_repository: StructuredKnowledgeRepository | None = None,
) -> FastAPI:
    """创建并组装 FastAPI 应用。"""
    storage = JsonStorageBackend(app_settings.project_assets_dir / "source")
    project_storage = ProjectAssetStorageBackend(app_settings.project_assets_dir)
    chapter_service = ChapterService(project_storage)
    outline_service = OutlineService(project_storage)
    settings_preference_service = SettingsPreferenceService(project_storage)
    model_catalog = LLMModelCatalog(app_settings)
    llm_usage_repository = JsonlLLMUsageRepository(app_settings.project_assets_dir)
    if llm_gateway is not None:
        llm_service = llm_gateway
        llm_configured = True
    elif llm is not None:
        llm_service = LangChainLLMAdapter(
            llm,
            llm_model_identity
            or LLMModelIdentity.unknown(
                "注入模型未提供身份。",
                model_id=app_settings.rightcode_default_model_id,
            ),
            default_model_id=app_settings.rightcode_default_model_id,
        )
        llm_configured = True
    else:
        rightcode_gateway = RightCodeLLMGateway(
            app_settings,
            model_catalog,
            llm_usage_repository,
        )
        llm_service = rightcode_gateway
        llm_configured = rightcode_gateway.configured
    active_default_model = next(
        (profile.id for profile in llm_service.list_models() if profile.is_default),
        app_settings.rightcode_default_model_id,
    )
    ai_card_service = AICardService(project_storage)
    inbox_service = InboxService(project_storage, ai_card_service)
    managed_knowledge_repository = knowledge_repository is None
    if knowledge_repository is None:
        knowledge_repository = MongoKnowledgeRepository(
            app_settings.mongodb_uri,
            app_settings.mongodb_database,
        )
    knowledge_service = KnowledgeService(knowledge_repository)
    retrieval_trace_repository = JsonlRetrievalTraceRepository(
        app_settings.project_assets_dir
    )
    retrieval_service = RetrievalService(
        MongoLexicalRetrievalBackend(knowledge_repository),
        retrieval_trace_repository,
    )
    sedimentation_progress_repository = (
        MongoKnowledgeSedimentationProgressRepository(
            app_settings.mongodb_uri,
            app_settings.mongodb_database,
        )
        if managed_knowledge_repository
        else InMemoryKnowledgeSedimentationProgressRepository()
    )
    mvp_inbox_service = MVPInboxService(project_storage, knowledge_service)
    knowledge_run_store = JsonAgentRunStore(app_settings.project_assets_dir)
    agent_task_events = AgentTaskEventCenter()
    knowledge_extraction_service = KnowledgeExtractionService(
        chapter_service=chapter_service,
        llm=llm_service,
        retrieval_service=retrieval_service,
        knowledge_service=knowledge_service,
        run_store=knowledge_run_store,
        sedimentation_progress_repository=sedimentation_progress_repository,
        task_events=agent_task_events,
        default_model_id=active_default_model,
    )
    evaluation_dataset_repository = JsonEvaluationDatasetRepository(
        app_settings.evaluation_datasets_dir,
        app_settings.project_assets_dir / "source",
    )
    evaluation_result_repository = JsonEvaluationResultStore(
        app_settings.project_assets_dir
    )
    evaluation_judge = create_evaluation_judge(
        app_settings,
        llm_service,
        configured=llm_configured,
    )
    knowledge_extraction_evaluation_service = KnowledgeExtractionEvaluationService(
        dataset_repository=evaluation_dataset_repository,
        result_repository=evaluation_result_repository,
        run_store=knowledge_run_store,
        chapter_service=chapter_service,
        judge=evaluation_judge,
    )
    writing_ai_service = WritingAIService(
        storage=project_storage,
        chapter_service=chapter_service,
        retrieval_service=retrieval_service,
        llm=llm_service,
        default_model_id=active_default_model,
        llm_configured=llm_configured,
    )
    selection_ai_service = SelectionAIService(
        llm_service,
        ai_card_service,
        default_model_id=active_default_model,
    )
    export_service = ExportService(project_storage, knowledge_repository)
    chapter_summary_service = ChapterSummaryService(
        storage=project_storage,
        chapter_service=chapter_service,
        retrieval_service=retrieval_service,
        llm=llm_service,
        ai_card_service=ai_card_service,
        default_model_id=active_default_model,
    )
    capability_context = CapabilityContext(
        capabilities={
            "llm": llm_service,
            "chapter_service": chapter_service,
            "knowledge_repository": knowledge_repository,
            "retrieval_service": retrieval_service,
            "knowledge_run_store": knowledge_run_store,
            "storage": storage,
        }
    )
    agent_registry = AgentRegistry(capability_context)
    agent_registry.register_all(discover_agents("taichu.application.agents"))
    tool_registry = ToolRegistry(capability_context)
    tool_registry.register_all(discover_tools("taichu.application.tools"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if managed_knowledge_repository:
            try:
                await cast(MongoKnowledgeRepository, knowledge_repository).initialize()
                await cast(
                    MongoKnowledgeSedimentationProgressRepository,
                    sedimentation_progress_repository,
                ).initialize()
            except Exception as error:
                await cast(MongoKnowledgeRepository, knowledge_repository).close()
                await cast(
                    MongoKnowledgeSedimentationProgressRepository,
                    sedimentation_progress_repository,
                ).close()
                raise RuntimeError(
                    f"MongoDB 知识库初始化失败，后端已停止启动：{error}"
                ) from error
        await knowledge_extraction_evaluation_service.recover_interrupted()
        knowledge_extraction_evaluation_service.start_watchdog()
        try:
            yield
        finally:
            await knowledge_extraction_evaluation_service.shutdown()
            if managed_knowledge_repository:
                await cast(MongoKnowledgeRepository, knowledge_repository).close()
                await cast(
                    MongoKnowledgeSedimentationProgressRepository,
                    sedimentation_progress_repository,
                ).close()

    application = FastAPI(
        title="Taichu",
        description="太初 - 单本玄幻小说个人写作助手",
        lifespan=lifespan,
    )
    application.state.agent_registry = agent_registry
    application.state.tool_registry = tool_registry
    application.state.storage = storage
    application.state.project_storage = project_storage
    application.state.chapter_service = chapter_service
    application.state.outline_service = outline_service
    application.state.ai_card_service = ai_card_service
    application.state.inbox_service = inbox_service
    application.state.mvp_inbox_service = mvp_inbox_service
    application.state.export_service = export_service
    application.state.knowledge_service = knowledge_service
    application.state.knowledge_repository = knowledge_repository
    application.state.retrieval_service = retrieval_service
    application.state.retrieval_trace_repository = retrieval_trace_repository
    application.state.sedimentation_progress_repository = sedimentation_progress_repository
    application.state.knowledge_run_store = knowledge_run_store
    application.state.agent_task_events = agent_task_events
    application.state.knowledge_extraction_service = knowledge_extraction_service
    application.state.knowledge_extraction_evaluation_service = (
        knowledge_extraction_evaluation_service
    )
    application.state.evaluation_dataset_repository = evaluation_dataset_repository
    application.state.evaluation_result_repository = evaluation_result_repository
    application.state.evaluation_judge = evaluation_judge
    application.state.selection_ai_service = selection_ai_service
    application.state.chapter_summary_service = chapter_summary_service
    application.state.settings_preference_service = settings_preference_service
    application.state.writing_ai_service = writing_ai_service
    application.state.llm_gateway = llm_service
    application.state.llm_model_catalog = model_catalog
    application.state.llm_usage_repository = llm_usage_repository
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_routes(application)
    application.add_exception_handler(HTTPException, _http_exception_handler)
    application.add_exception_handler(
        RequestValidationError,
        _validation_exception_handler,
    )
    application.add_exception_handler(
        KnowledgeUnavailableError,
        _knowledge_unavailable_exception_handler,
    )
    application.add_exception_handler(
        KnowledgeRepositoryUnavailableError,
        _knowledge_unavailable_exception_handler,
    )
    return application


async def _http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    http_error = cast(HTTPException, exc)
    if isinstance(http_error.detail, dict) and "error" in http_error.detail:
        return JSONResponse(
            status_code=http_error.status_code,
            content=http_error.detail,
        )
    return JSONResponse(
        status_code=http_error.status_code,
        content={"detail": http_error.detail},
    )


async def _validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    cast(RequestValidationError, exc)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求内容不完整或格式不正确，请检查后再试。",
            }
        },
    )


async def _knowledge_unavailable_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    message = str(exc).strip() or "MongoDB 知识库暂时不可用，请稍后重试。"
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "KNOWLEDGE_UNAVAILABLE",
                "message": message,
            }
        },
    )


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
