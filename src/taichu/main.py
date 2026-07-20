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
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.capabilities import CapabilityContext
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.context import (
    ContextAssembler,
    GeneralAgentContextPolicy,
)
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.memory_policy import AgentMemoryPolicy
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.evaluations.general_agent.service import (
    GeneralAgentEvaluationService,
)
from taichu.application.evaluations.retrieval.service import (
    RetrievalEvaluationService,
)
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
from taichu.application.services.agent_memory_service import AgentMemoryService
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
from taichu.application.services.knowledge_vector_index_service import (
    KnowledgeVectorIndexService,
)
from taichu.application.retrieval.policy import RetrievalPolicyResolver
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.external_research.service import ExternalResearchService
from taichu.application.tools.registry import ToolRegistry
from taichu.config import Settings, settings
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.catalog import LLMModelCatalog
from taichu.infrastructure.llm.rightcode import RightCodeLLMGateway
from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository
from taichu.infrastructure.embedding import (
    JsonlEmbeddingUsageRepository,
    LlamaCppEmbeddingGateway,
)
from taichu.infrastructure.evaluations import (
    JsonGeneralAgentEvaluationDatasetRepository,
    JsonGeneralAgentEvaluationResultRepository,
    JsonEvaluationDatasetRepository,
    JsonEvaluationResultStore,
    JsonRetrievalEvaluationDatasetRepository,
    JsonRetrievalEvaluationResultRepository,
    create_evaluation_judge,
)
from taichu.infrastructure.plugin_discovery import (
    discover_agents,
    discover_subagents,
    discover_tools,
)
from taichu.infrastructure.agent_runs import JsonAgentRunStore
from taichu.infrastructure.knowledge import (
    MongoKnowledgeRepository,
    MongoKnowledgeSedimentationProgressRepository,
)
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    KnowledgeVectorRetrievalBackend,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.retrieval.vector_index import (
    JsonVectorIndexManifestRepository,
    QdrantVectorIndexBackend,
)
from taichu.infrastructure.storage.json_backend import JsonStorageBackend
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.infrastructure.external_research import (
    DuckDuckGoExternalResearchBackend,
)
from taichu.infrastructure.invocations import JsonlInvocationTraceRepository
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
    JsonGeneralAgentRunRepository,
    JsonLangGraphCheckpointSaver,
)
from taichu.infrastructure.agent_memory import (
    JsonAgentMemoryLexicalIndex,
    JsonAgentMemoryRepository,
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
    retrieval_policy_resolver = RetrievalPolicyResolver.from_json(
        app_settings.retrieval_policies_json,
        default_relevance_strategy=(app_settings.retrieval_default_relevance_strategy),
    )
    retrieval_service = RetrievalService(
        MongoLexicalRetrievalBackend(knowledge_repository),
        retrieval_trace_repository,
        policy_resolver=retrieval_policy_resolver,
    )
    embedding_gateway = LlamaCppEmbeddingGateway(
        base_url=app_settings.embedding_base_url,
        model_id=app_settings.embedding_model_id,
        dimensions=app_settings.embedding_dimensions,
        timeout_seconds=app_settings.embedding_request_timeout_seconds,
        usage_repository=JsonlEmbeddingUsageRepository(app_settings.project_assets_dir),
        max_input_tokens=app_settings.embedding_max_input_tokens,
    )
    vector_index_backend = QdrantVectorIndexBackend(
        url=app_settings.qdrant_url,
        api_key=app_settings.qdrant_api_key.get_secret_value(),
    )
    vector_manifest_repository = JsonVectorIndexManifestRepository(
        app_settings.project_assets_dir
    )
    knowledge_vector_index_service = KnowledgeVectorIndexService(
        knowledge_repository=knowledge_repository,
        embedding_gateway=embedding_gateway,
        vector_index=vector_index_backend,
        manifests=vector_manifest_repository,
        active_alias=app_settings.qdrant_collection,
        document_batch_size=app_settings.vector_document_batch_size,
        embedding_input_char_budget=(app_settings.vector_embedding_input_char_budget),
    )
    knowledge_vector_backend = KnowledgeVectorRetrievalBackend(
        knowledge_repository=knowledge_repository,
        embedding_gateway=embedding_gateway,
        vector_index=vector_index_backend,
        manifests=vector_manifest_repository,
        query_char_budget=app_settings.vector_query_char_budget,
        candidate_multiplier=app_settings.vector_candidate_multiplier,
        score_threshold=app_settings.vector_score_threshold,
        coverage_bonus=app_settings.vector_coverage_bonus,
    )
    retrieval_evaluation_runtime = RetrievalService(
        MongoLexicalRetrievalBackend(knowledge_repository),
        retrieval_trace_repository,
        policy_resolver=retrieval_policy_resolver,
        additional_backends={
            knowledge_vector_backend.strategy_name: knowledge_vector_backend
        },
    )
    invocation_trace_repository = JsonlInvocationTraceRepository(
        app_settings.project_assets_dir
    )
    artifact_repository = JsonIntermediateArtifactRepository(
        app_settings.project_assets_dir
    )
    general_agent_run_repository = JsonGeneralAgentRunRepository(
        app_settings.project_assets_dir
    )
    general_agent_graph_checkpointer = JsonLangGraphCheckpointSaver(
        app_settings.project_assets_dir
    )
    general_agent_effect_repository = JsonGeneralAgentEffectRepository(
        app_settings.project_assets_dir
    )
    agent_memory_repository = JsonAgentMemoryRepository(app_settings.project_assets_dir)
    agent_memory_lexical_index = JsonAgentMemoryLexicalIndex(
        app_settings.project_assets_dir
    )
    agent_memory_service = AgentMemoryService(
        repository=agent_memory_repository,
        lexical_index=agent_memory_lexical_index,
        policy=AgentMemoryPolicy(
            top_k=app_settings.general_agent_related_memory_top_k,
            char_budget=app_settings.general_agent_related_memory_char_budget,
            age_decay_days=app_settings.general_agent_memory_age_decay_days,
            minimum_relevance=(app_settings.general_agent_memory_minimum_relevance),
        ),
    )
    general_agent_context_assembler = ContextAssembler(
        memory_service=agent_memory_service,
        policy=GeneralAgentContextPolicy(
            total_char_budget=app_settings.general_agent_context_char_budget,
            related_memory_top_k=(app_settings.general_agent_related_memory_top_k),
            related_memory_char_budget=(
                app_settings.general_agent_related_memory_char_budget
            ),
            working_memory_char_budget=(
                app_settings.general_agent_working_memory_char_budget
            ),
            process_history_limit=(app_settings.general_agent_process_history_limit),
            process_history_char_budget=(
                app_settings.general_agent_process_history_char_budget
            ),
            node_summary_char_budget=(
                app_settings.general_agent_node_summary_char_budget
            ),
            plan_summary_char_budget=(
                app_settings.general_agent_plan_summary_char_budget
            ),
            message_compaction_threshold=(
                app_settings.general_agent_message_compaction_threshold
            ),
            node_output_compaction_threshold=(
                app_settings.general_agent_node_output_compaction_threshold
            ),
        ),
    )
    general_agent_event_center = GeneralAgentEventCenter()
    invocation_policy_service = InvocationPolicyService()
    external_research_service = ExternalResearchService(
        DuckDuckGoExternalResearchBackend()
    )
    model_role_router = ModelRoleRouter.from_json(
        active_default_model,
        app_settings.agent_model_roles_json,
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
            "outline_service": outline_service,
            "knowledge_service": knowledge_service,
            "knowledge_repository": knowledge_repository,
            "retrieval_service": retrieval_service,
            "external_research_service": external_research_service,
            "invocation_policy_service": invocation_policy_service,
            "invocation_trace_repository": invocation_trace_repository,
            "artifact_repository": artifact_repository,
            "model_role_router": model_role_router,
            "knowledge_run_store": knowledge_run_store,
            "storage": storage,
        }
    )
    agent_registry = AgentRegistry(capability_context)
    agent_registry.register_all(discover_agents("taichu.application.agents"))
    tool_registry = ToolRegistry(
        capability_context,
        invocation_trace_repository,
    )
    tool_registry.register_all(discover_tools("taichu.application.tools"))
    subagent_context = CapabilityContext(
        capabilities={
            **capability_context.capabilities,
            "tool_registry": tool_registry,
        }
    )
    subagent_registry = SubagentRegistry(
        subagent_context,
        invocation_trace_repository,
    )
    subagent_registry.register_all(discover_subagents("taichu.application.subagents"))
    orchestrator_agent = OrchestratorAgent(
        llm=llm_service,
        model_router=model_role_router,
        tool_registry=tool_registry,
        subagent_registry=subagent_registry,
        trace_repository=invocation_trace_repository,
        capability_catalog_char_budget=(
            app_settings.general_agent_capability_catalog_char_budget
        ),
    )
    dynamic_dag_executor = DynamicDagExecutor(
        tool_registry=tool_registry,
        subagent_registry=subagent_registry,
        policy_service=invocation_policy_service,
        graph_checkpointer=general_agent_graph_checkpointer,
        effect_repository=general_agent_effect_repository,
    )
    general_agent_runtime_service = GeneralAgentRuntimeService(
        repository=general_agent_run_repository,
        event_center=general_agent_event_center,
        orchestrator=orchestrator_agent,
        executor=dynamic_dag_executor,
        policy_service=invocation_policy_service,
        memory_service=agent_memory_service,
        context_assembler=general_agent_context_assembler,
        graph_checkpointer=general_agent_graph_checkpointer,
        effect_repository=general_agent_effect_repository,
    )
    general_agent_evaluation_service = GeneralAgentEvaluationService(
        datasets=JsonGeneralAgentEvaluationDatasetRepository(
            app_settings.evaluation_datasets_dir
        ),
        results=JsonGeneralAgentEvaluationResultRepository(
            app_settings.project_assets_dir
        ),
        runs=general_agent_run_repository,
        traces=invocation_trace_repository,
    )
    retrieval_evaluation_service = RetrievalEvaluationService(
        datasets=JsonRetrievalEvaluationDatasetRepository(
            app_settings.evaluation_datasets_dir
        ),
        results=JsonRetrievalEvaluationResultRepository(
            app_settings.project_assets_dir
        ),
        retrieval=retrieval_evaluation_runtime,
    )

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
                await embedding_gateway.close()
                await vector_index_backend.close()
                await cast(MongoKnowledgeRepository, knowledge_repository).close()
                await cast(
                    MongoKnowledgeSedimentationProgressRepository,
                    sedimentation_progress_repository,
                ).close()
                raise RuntimeError(
                    f"MongoDB 知识库初始化失败，后端已停止启动：{error}"
                ) from error
        await knowledge_extraction_evaluation_service.recover_interrupted()
        await general_agent_runtime_service.recover_interrupted()
        knowledge_extraction_evaluation_service.start_watchdog()
        try:
            yield
        finally:
            await general_agent_runtime_service.shutdown()
            await knowledge_extraction_evaluation_service.shutdown()
            await embedding_gateway.close()
            await vector_index_backend.close()
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
    application.state.subagent_registry = subagent_registry
    application.state.general_agent_run_repository = general_agent_run_repository
    application.state.general_agent_event_center = general_agent_event_center
    application.state.general_agent_runtime_service = general_agent_runtime_service
    application.state.agent_memory_service = agent_memory_service
    application.state.agent_memory_repository = agent_memory_repository
    application.state.agent_memory_lexical_index = agent_memory_lexical_index
    application.state.general_agent_evaluation_service = (
        general_agent_evaluation_service
    )
    application.state.retrieval_evaluation_service = retrieval_evaluation_service
    application.state.invocation_policy_service = invocation_policy_service
    application.state.invocation_trace_repository = invocation_trace_repository
    application.state.artifact_repository = artifact_repository
    application.state.external_research_service = external_research_service
    application.state.model_role_router = model_role_router
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
    application.state.retrieval_evaluation_runtime = retrieval_evaluation_runtime
    application.state.embedding_gateway = embedding_gateway
    application.state.vector_index_backend = vector_index_backend
    application.state.vector_manifest_repository = vector_manifest_repository
    application.state.knowledge_vector_index_service = knowledge_vector_index_service
    application.state.knowledge_vector_backend = knowledge_vector_backend
    application.state.retrieval_trace_repository = retrieval_trace_repository
    application.state.sedimentation_progress_repository = (
        sedimentation_progress_repository
    )
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
