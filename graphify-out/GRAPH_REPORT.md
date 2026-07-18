# Graph Report - src  (2026-07-18)

## Corpus Check
- 246 files · ~88,682 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3458 nodes · 11030 edges · 113 communities (108 shown, 5 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 1737 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- 知识抽取评测指标
- 章节与大纲管理
- 通用智能体评测
- 知识抽取工作流
- 知识抽取工作台接口
- 知识抽取评测接口
- 领域事实模型
- 知识抽取评测服务
- 评测差异解释
- Markdown项目存储
- 能力与工具契约
- 章节来源接口模型
- 章节摘要服务
- 通用智能体运行时
- AI结果与待处理事实
- 知识抽取批次执行
- 子智能体模型与契约
- 知识抽取任务状态
- MongoDB知识仓储
- 评测数据集仓储
- 收件箱服务接口
- 子智能体注册与追踪
- 智能体运行记录存储
- 工具领域类型
- 大模型调用契约
- 项目资产存储契约
- 评测结果存储
- AI结果卡服务
- 子智能体执行器
- 知识卡业务服务
- 知识候选匹配
- 外部资料研究
- MVP收件箱
- RightCode模型网关
- 知识评测裁判
- 智能体插件注册
- 章节结构工具
- 大纲API接口
- 通用智能体编排器
- 检索执行服务
- 模型目录与配置
- 知识卡API接口
- 检索上下文模型
- 检索评测模型
- 收件箱写操作接口
- 写作助手运行服务
- 模型用量审计
- 动态任务图执行
- 模型API与用量接口
- 知识查询服务
- 通用智能体API
- 小说导出服务
- 知识抽取图契约
- API依赖注入
- 写作助手API
- 通用智能体运行仓储
- 检索评测仓储
- 调用授权策略
- 检索评测API
- 写作检索上下文
- 知识沉淀进度
- 工具调用封装
- 知识类型模式
- 正文补丁工具
- JSON通用存储
- MongoDB沉淀进度
- 结构化知识仓储契约
- 写作提示词
- MongoDB词法检索
- 用户偏好设置
- FastAPI应用入口
- 检索评测命令行
- 来源引用校验
- 能力评测档案
- 确定性模拟模型
- 不可用模型占位
- 评测数据集契约
- 知识类型中文标签
- 能力依赖校验
- 知识抽取模型选择
- 知识模式API
- 写作流式响应
- 写作运行异常
- 智能体事件流
- 知识抽取插件包
- 评测引擎包
- 工作流契约包
- 大模型基础设施包

## God Nodes (most connected - your core abstractions)
1. `StructuredKnowledgeType` - 233 edges
2. `StructuredKnowledgeCard` - 131 edges
3. `CapabilityContext` - 109 edges
4. `KnowledgeExtractionService` - 92 edges
5. `KnowledgeExtractionEvaluationService` - 86 edges
6. `AgentRun` - 84 edges
7. `ChapterService` - 82 edges
8. `InvocationContext` - 81 edges
9. `SourceRef` - 81 edges
10. `DomainModel` - 77 edges

## Surprising Connections (you probably didn't know these)
- `api_get_agent_task()` --indirect_call--> `KnowledgeExtractionNotFoundError`  [INFERRED]
  taichu/api/routes/agent_tasks.py → taichu/application/services/knowledge_extraction_service.py
- `api_delete_agent_task()` --indirect_call--> `KnowledgeExtractionNotFoundError`  [INFERRED]
  taichu/api/routes/agent_tasks.py → taichu/application/services/knowledge_extraction_service.py
- `api_get_knowledge_extraction_run()` --indirect_call--> `KnowledgeExtractionNotFoundError`  [INFERRED]
  taichu/api/routes/agent_workbench.py → taichu/application/services/knowledge_extraction_service.py
- `_confirm_candidate()` --indirect_call--> `KnowledgeExtractionNotFoundError`  [INFERRED]
  taichu/api/routes/agent_workbench.py → taichu/application/services/knowledge_extraction_service.py
- `_confirm_candidate()` --indirect_call--> `KnowledgeCardNotFoundError`  [INFERRED]
  taichu/api/routes/agent_workbench.py → taichu/application/services/knowledge_service.py

## Import Cycles
- None detected.

## Communities (113 total, 5 thin omitted)

### Community 0 - "知识抽取评测指标"
Cohesion: 0.03
Nodes (118): Deterministic and judge-ready knowledge-extraction evaluation contracts., assemble_deterministic_metrics(), _candidate_metrics(), _checked_rate(), compare_source_hashes(), compare_structured_fields(), compute_batch_diagnostic_metrics(), compute_candidate_identification_metrics() (+110 more)

### Community 1 - "章节与大纲管理"
Cohesion: 0.05
Nodes (80): ChapterContent, ChapterNotFoundError, _count_non_space(), _now_iso(), LookupError, A chapter record with its Markdown body., Return the current chapter manifest., List chapters in manifest order. (+72 more)

### Community 2 - "通用智能体评测"
Cohesion: 0.05
Nodes (56): provide_general_agent_evaluation_service(), create_general_agent_evaluation(), delete_general_agent_evaluation(), get_general_agent_evaluation(), get_general_agent_evaluation_dataset(), list_general_agent_evaluation_datasets(), list_general_agent_evaluations(), HTTPException (+48 more)

### Community 3 - "知识抽取工作流"
Cohesion: 0.06
Nodes (85): Fixed prompt templates for the knowledge extraction Agent., _accepted_entity_groups(), _additive_baselines(), _aggregate_entities(), _append_state_list(), build_knowledge_extraction_branch_graph(), build_knowledge_extraction_graph(), _build_review_items() (+77 more)

### Community 4 - "知识抽取工作台接口"
Cohesion: 0.05
Nodes (88): provide_knowledge_extraction_service(), Return the knowledge extraction Agent workbench service., api_delete_agent_task(), api_get_agent_task(), api_list_agent_tasks(), Agent task monitoring endpoints., Delete one persisted or in-memory Agent task., List active and persisted Agent tasks. (+80 more)

### Community 5 - "知识抽取评测接口"
Cohesion: 0.11
Nodes (89): _comparison_response(), confirm_knowledge_evaluation(), create_knowledge_evaluation(), get_evaluation_dataset(), get_knowledge_evaluation(), get_knowledge_evaluation_judge_call(), _http_error(), _id_error() (+81 more)

### Community 6 - "领域事实模型"
Cohesion: 0.04
Nodes (72): Persist one summary candidate as a non-fact PendingFact., DomainModel, BaseModel, Shared helpers for immutable domain data contracts., Base model for Phase 0 data contracts., Readable export bundle contracts., Corpus import batch contract., ChapterIssue (+64 more)

### Community 7 - "知识抽取评测服务"
Cohesion: 0.04
Nodes (42): provide_knowledge_extraction_evaluation_service(), EvaluationJudge, Protocol, One isolated text-to-JSON semantic judge capability., Whether the runtime is configured before a task is accepted., EvaluationResultRepository, Any, Protocol (+34 more)

### Community 8 - "评测差异解释"
Cohesion: 0.05
Nodes (75): build_difference_explanation_prompt(), _comparison_title(), difference_explanation_prompt_contract_hash(), DifferenceExplanationBatchOutput, DifferenceExplanationInput, DifferenceExplanationOutputItem, _display_value(), _extract_json_object() (+67 more)

### Community 9 - "Markdown项目存储"
Cohesion: 0.05
Nodes (27): Lock, Path, _format_scalar(), _is_safe_manuscript_segment(), _now_iso(), _parse_scalar(), ProjectAssetStorageBackend, Any (+19 more)

### Community 10 - "能力与工具契约"
Cohesion: 0.06
Nodes (60): CapabilityContext, 保存 Agent 和 Tool 可按名称取得的运行能力。, InvocationContext, 关联调用树、权限和业务范围，但不替代业务运行状态。, 关联业务运行但不统一业务日志的最小上下文。, RetrievalConsumerContext, BaseModel, run() (+52 more)

### Community 11 - "章节来源接口模型"
Cohesion: 0.06
Nodes (70): api_apply_summary_action(), api_convert_summary_candidate(), api_list_chapter_summaries(), api_list_chapters(), api_read_chapter(), api_save_chapter(), api_summarize_chapter(), _card_info() (+62 more)

### Community 12 - "章节摘要服务"
Cohesion: 0.06
Nodes (61): KnowledgeCard, provide_chapter_summary_service(), Return the chapter summary application service., _candidate_data(), _candidate_key(), _candidate_pending_facts(), _chapter_segments(), _chapter_source_ref() (+53 more)

### Community 13 - "通用智能体运行时"
Cohesion: 0.07
Nodes (33): GeneralAgentRunRepository, Protocol, 通用写作助手 Runtime 检查点仓储契约。, GeneralAgentEventCenter, Any, 广播通用 Runtime 事件，不混入知识沉淀 Workflow 业务日志。, GeneralAgentHumanRequest, GeneralAgentLifecycleEvent (+25 more)

### Community 14 - "AI结果与待处理事实"
Cohesion: 0.06
Nodes (59): ConvertPendingFactResult, AIResultCard persistence and lifecycle use cases., Result of saving a suggestion card to the creative inbox., Result of moving a pending-fact card into the creative inbox., SaveIdeaResult, InboxSnapshot, PendingFactNotFoundError, LookupError (+51 more)

### Community 15 - "知识抽取批次执行"
Cohesion: 0.07
Nodes (58): _action_label(), _candidate_action(), _candidate_validation_errors(), _count_actions(), _count_items(), _count_status(), _iso_duration_ms(), _metrics() (+50 more)

### Community 16 - "子智能体模型与契约"
Cohesion: 0.08
Nodes (51): BaseModel, run(), BaseModel, run(), BaseModel, 独立于知识沉淀 Workflow Graph 的专业子 Agent 协议。, 一个稳定专业能力的注册、权限、模型和校验契约。, SubagentManifest (+43 more)

### Community 17 - "知识抽取任务状态"
Cohesion: 0.07
Nodes (52): AgentBatchChapterProgress, AgentEntityGroup, AgentIgnoredExtraction, AgentLLMCall, AgentMetrics, AgentModel, AgentRawMention, AgentReviewCandidateAction (+44 more)

### Community 18 - "MongoDB知识仓储"
Cohesion: 0.06
Nodes (47): NoReturn, PyMongoError, KnowledgeRepositoryConcurrentUpdateError, KnowledgeRepositoryConflictError, KnowledgeRepositoryNotFoundError, KnowledgeRepositoryValidationError, Repository boundary for MongoDB-backed structured knowledge cards., Raised when the requested knowledge card does not exist. (+39 more)

### Community 19 - "评测数据集仓储"
Cohesion: 0.07
Nodes (45): Evaluation dataset repository boundary., DatasetValidationIssue, LoadedEvaluationCase, LoadedEvaluationDataset, EvaluationModel, Loaded dataset models for knowledge-extraction evaluation., One fully loaded and validated evaluation case., One immutable dataset ready for preview or snapshotting. (+37 more)

### Community 20 - "收件箱服务接口"
Cohesion: 0.07
Nodes (50): api_convert_card_to_pending_fact(), api_ignore_pending_fact(), api_read_inbox(), api_save_card_as_idea(), _chapter_id_from_pending_fact(), _chapter_issue_info(), _conflict(), _editor_href() (+42 more)

### Community 21 - "子智能体注册与追踪"
Cohesion: 0.07
Nodes (29): IntermediateArtifactRecord, BaseModel, 可供下游专业子 Agent 复用的有类型草稿产物。, JSON 中间态，不是正文或结构化知识事实。, IntermediateArtifactRepository, Protocol, InvocationTraceRepository, SubagentPlugin (+21 more)

### Community 22 - "智能体运行记录存储"
Cohesion: 0.06
Nodes (26): AgentRun, Any, A complete JSON intermediate state for one knowledge extraction run., Load historical JSON without claiming its display name is verified., Return in-memory tasks, newest first., Return one in-memory task snapshot., _consume_background_task_exception(), AuthorMergeMode (+18 more)

### Community 23 - "工具领域类型"
Cohesion: 0.12
Nodes (51): ApplyManuscriptPatchInput, ApplyManuscriptPatchOutput, CreateConfirmedKnowledgeInput, CreateConfirmedKnowledgeOutput, CreateNovelStructureItemsInput, CreateStructureItem, DeleteNovelStructureItemsInput, DeleteStructureTarget (+43 more)

### Community 24 - "大模型调用契约"
Cohesion: 0.07
Nodes (30): EvaluationJudgeResponse, BaseModel, Semantic evaluation judge boundary., Raw response plus metadata returned by one judge transport call., Return the actual runtime identity., Execute one judge request without mutating application state., LLMCost, LLMMessage (+22 more)

### Community 25 - "项目资产存储契约"
Cohesion: 0.05
Nodes (25): ProjectAssetStorageContract, Protocol, StorageData, 读取 source/workspace 下的 JSONL 主记录。, 原子重写 source/workspace 下的 JSONL 主记录。, 读取 source/workspace/settings_preferences.json。, 写入 source/workspace/settings_preferences.json。, 单本小说 project_assets 文件资产访问契约。 (+17 more)

### Community 26 - "评测结果存储"
Cohesion: 0.08
Nodes (25): EvaluationResultStoreError, JsonEvaluationResultStore, Any, Path, ValueError, Atomic file-backed store for knowledge-extraction evaluation reports., Write one complete run result atomically., Read one complete run result. (+17 more)

### Community 27 - "AI结果卡服务"
Cohesion: 0.08
Nodes (33): SelectionAIRequest, api_apply_ai_card_action(), api_create_selection_ai_card(), api_list_ai_cards(), _card_info(), List persisted AI cards for the editor side panel., Run Selection AI and persist the resulting AIResultCard., Apply a persisted card lifecycle action. (+25 more)

### Community 28 - "子智能体执行器"
Cohesion: 0.08
Nodes (28): 读取响应正文，并兼容仅存在于测试替身中的字符串返回值。, response_text(), InvocationTraceRecord, ModelRoleRouter, 把专业子 Agent 的逻辑模型角色映射到具体模型。, 保持 Agent 业务代码与具体模型 ID 解耦。, _append_llm_failure_trace(), _append_llm_trace() (+20 more)

### Community 29 - "知识卡业务服务"
Cohesion: 0.11
Nodes (31): _card_from_payload(), KnowledgeCardValidationError, KnowledgeIdentityConflictError, KnowledgeService, _now_iso(), Any, AuthorMergeMode, ValueError (+23 more)

### Community 30 - "知识候选匹配"
Cohesion: 0.09
Nodes (35): _candidate_ref(), _card_chapter_ids(), _chapter_scopes_overlap(), _component_is_ambiguous(), _connected_components(), _Edge, _event_semantic_edge(), _evidence_edge() (+27 more)

### Community 31 - "外部资料研究"
Cohesion: 0.08
Nodes (20): HTMLParser, ExternalResearchBackend, Protocol, ExternalDocument, ExternalResearchModel, ExternalSearchResult, BaseModel, ExternalResearchService (+12 more)

### Community 32 - "MVP收件箱"
Cohesion: 0.10
Nodes (28): MVPInboxItem, _filter_items(), InboxItemNotFoundError, InboxValidationError, MVPInboxService, _now_iso(), PendingFactConfirmResult, Any (+20 more)

### Community 33 - "RightCode模型网关"
Cohesion: 0.15
Nodes (33): Response, LLMModelProfile, LLMResponse, LLMUsage, calculate_cost(), 实际费用优先，否则仅在所需价格齐全时进行 Decimal 预估。, _anthropic_payload(), _call_record() (+25 more)

### Community 34 - "知识评测裁判"
Cohesion: 0.09
Nodes (37): aggregate_judge_samples(), build_judge_prompt(), _extract_json_object(), JudgeBatchOutput, JudgeCriticalFlag, JudgeDimensionResult, JudgeFinding, JudgeInputCase (+29 more)

### Community 35 - "智能体插件注册"
Cohesion: 0.10
Nodes (26): provide_agent_registry(), 返回应用启动时创建的 Agent 注册中心。, api_list_agents(), AgentInfo, AgentListResponse, BaseModel, 可供 API 和前端展示的 Agent 信息。, AgentManifest (+18 more)

### Community 36 - "章节结构工具"
Cohesion: 0.14
Nodes (28): ChapterService, Chapter manifest and manuscript read use cases., Application use cases for manuscript chapters., Ensure source/generated skeleton files exist for active root., BaseModel, run(), BaseModel, run() (+20 more)

### Community 37 - "大纲API接口"
Cohesion: 0.10
Nodes (35): api_create_chapter(), api_create_volume(), api_delete_chapter(), api_delete_volume(), api_get_outline(), api_rename_chapter(), api_rename_volume(), _not_found() (+27 more)

### Community 38 - "通用智能体编排器"
Cohesion: 0.10
Nodes (26): _OutputModel, _ensure_acyclic(), GeneralAgentExecutionPlan, GeneralAgentInputBinding, GeneralAgentNodeKind, GeneralAgentNodeStatus, GeneralAgentPlanDraft, GeneralAgentVerification (+18 more)

### Community 39 - "检索执行服务"
Cohesion: 0.11
Nodes (22): Protocol, RetrievalBackend, RetrievalTraceRepository, 把消费者策略冻结为一次可观测、可执行的召回计划。, RetrievalExecutionPlan, RetrievalRequest, BaseModel, RetrievalPolicyProfile (+14 more)

### Community 40 - "模型目录与配置"
Cohesion: 0.10
Nodes (17): AsyncClient, BaseSettings, Settings, create_evaluation_judge(), 从统一 Right Code 网关创建语义评估裁判。, 显式裁判模型和默认模型都复用同一产品级供应商网关。, LLMModelCatalog, LLMModelSelectionError (+9 more)

### Community 41 - "知识卡API接口"
Cohesion: 0.12
Nodes (34): provide_knowledge_service(), Return the minimal Knowledge application service., api_confirm_knowledge_card(), api_create_knowledge_card(), api_get_knowledge_card(), api_get_knowledge_schema(), api_list_knowledge_cards(), api_patch_knowledge_card() (+26 more)

### Community 42 - "检索上下文模型"
Cohesion: 0.17
Nodes (31): BaseModel, StrEnum, 统一知识召回的稳定输入、输出与技术观测模型。, 交给写作任务、Workflow 或 Tool 的标准知识条目。, RetrievalBackendCandidate, RetrievalBackendResult, RetrievalBranchStatus, RetrievalFallbackReasonCode (+23 more)

### Community 43 - "检索评测模型"
Cohesion: 0.13
Nodes (22): Protocol, RetrievalEvaluationDatasetRepository, RetrievalEvaluationResultRepository, BaseModel, StrEnum, RetrievalAtKMetric, RetrievalEvaluationCase, RetrievalEvaluationCaseResult (+14 more)

### Community 44 - "收件箱写操作接口"
Cohesion: 0.09
Nodes (34): api_confirm_mvp_pending_fact(), api_create_mvp_idea(), api_create_mvp_issue(), api_create_mvp_pending_fact(), api_list_mvp_issues(), api_list_mvp_pending_facts(), api_patch_mvp_idea(), api_patch_mvp_issue() (+26 more)

### Community 45 - "写作助手运行服务"
Cohesion: 0.14
Nodes (21): _new_run_id(), _now_iso(), _parse_structured_output(), ValueError, Create, persist, list and replay writing-page AI runs., Run the complete writing AI workflow and persist the trace., 执行写作任务并输出 NDJSON 所需的增量事件。, List saved writing AI runs newest first. (+13 more)

### Community 46 - "模型用量审计"
Cohesion: 0.18
Nodes (15): LLMCallRecord, LLMTokenTrendPoint, LLMUsageGroup, LLMUsagePage, LLMUsageQuery, LLMUsageSummary, BaseModel, 一个小时或一天内的 Token 使用聚合点。 (+7 more)

### Community 47 - "动态任务图执行"
Cohesion: 0.17
Nodes (17): CheckpointCallback, _current_runs(), DynamicDagExecutionError, DynamicDagExecutor, Any, RuntimeError, 按依赖和并发上限执行一次动态能力 DAG。, 仅调度注册表中的真实 Tool 与专业子 Agent。 (+9 more)

### Community 48 - "模型API与用量接口"
Cohesion: 0.15
Nodes (23): provide_llm_usage_repository(), api_get_llm_call(), api_get_llm_token_trend(), api_get_llm_usage_summary(), api_list_llm_calls(), api_list_llm_models(), api_probe_llm_model(), _llm_error() (+15 more)

### Community 49 - "知识查询服务"
Cohesion: 0.11
Nodes (24): KnowledgeCardPage, KnowledgeCardQuery, KnowledgeRepositoryError, RuntimeError, Storage-level filters for one deterministic page of knowledge cards., One page of knowledge cards and its total matching record count., Base error exposed by the structured knowledge storage boundary., Return one filtered and deterministically ordered card page. (+16 more)

### Community 50 - "通用智能体API"
Cohesion: 0.17
Nodes (26): api_cancel_general_agent_run(), api_delete_general_agent_run(), api_get_general_agent_run(), api_list_general_agent_runs(), api_list_general_agent_traces(), api_resume_general_agent_run(), api_run_general_agent(), api_start_general_agent() (+18 more)

### Community 51 - "小说导出服务"
Cohesion: 0.13
Nodes (21): api_export_bundle(), _bundle_response(), Build a readable source asset export bundle., ExportBundleResponse, ExportFileInfo, BaseModel, Source asset export bundle response., One readable file in an export bundle. (+13 more)

### Community 52 - "知识抽取图契约"
Cohesion: 0.09
Nodes (19): build_graph(), CompiledStateGraph, Agent plugin entry for knowledge extraction., Build the product graph from registered runtime capabilities., KnowledgeExtractionAgentInput, KnowledgeExtractionAgentOutput, BaseModel, Input and output schemas for the knowledge extraction Agent manifest. (+11 more)

### Community 53 - "API依赖注入"
Cohesion: 0.12
Nodes (24): StorageBackend, provide_agent_task_event_center(), provide_ai_card_service(), provide_chapter_service(), provide_export_service(), provide_general_agent_event_center(), provide_general_agent_runtime_service(), provide_inbox_service() (+16 more)

### Community 54 - "写作助手API"
Cohesion: 0.13
Nodes (23): api_create_writing_ai_run(), api_get_writing_ai_run(), api_list_writing_ai_runs(), api_replay_writing_ai_run(), _bad_request(), _filter_by_chapter_name(), _not_found(), _paginate() (+15 more)

### Community 55 - "通用智能体运行仓储"
Cohesion: 0.13
Nodes (12): 通用写作助手 Agent 的高层编排运行时。, GeneralAgentRunStatus, 通用写作助手 Runtime 检查点持久化。, GeneralAgentRunStoreError, JsonGeneralAgentRunRepository, _load(), Path, ValueError (+4 more)

### Community 56 - "检索评测仓储"
Cohesion: 0.19
Nodes (10): RetrievalEvaluationRecord, File-backed effect-evaluation infrastructure., JsonRetrievalEvaluationDatasetRepository, JsonRetrievalEvaluationResultRepository, _load_record(), Path, ValueError, RetrievalEvaluationStoreError (+2 more)

### Community 57 - "调用授权策略"
Cohesion: 0.16
Nodes (17): _as_iso(), _AuthorGrant, canonical_input_hash(), _ensure_not_expired(), _ExternalGrant, GrantReference, IdempotencyConflictError, _IdempotencyRecord (+9 more)

### Community 58 - "检索评测API"
Cohesion: 0.18
Nodes (17): provide_retrieval_evaluation_service(), get_retrieval_evaluation(), get_retrieval_evaluation_dataset(), list_retrieval_evaluations(), HTTPException, _service_error(), _unprocessable(), BaseModel (+9 more)

### Community 59 - "写作检索上下文"
Cohesion: 0.15
Nodes (20): _chapter_evidence_context(), _chapter_evidence_item(), _chapter_excerpt(), _evidence_context(), _evidence_item(), _knowledge_context_block(), _llm_request(), Unified real LLM workflow for writing-page AI buttons. (+12 more)

### Community 60 - "知识沉淀进度"
Cohesion: 0.13
Nodes (10): InMemoryKnowledgeSedimentationProgressRepository, KnowledgeSedimentationProgress, KnowledgeSedimentationProgressRepository, Protocol, Persistence boundary for the single-novel knowledge sedimentation frontier., The latest chapter whose review range the author has accepted., Storage contract for the one global, monotonically advancing frontier., Small non-persistent adapter for isolated application tests. (+2 more)

### Community 61 - "工具调用封装"
Cohesion: 0.14
Nodes (15): InvocationBudget, InvocationEnvelope, InvocationModel, InvocationStatus, BaseModel, StrEnum, Tool 与专业子 Agent 共用的最小技术调用模型。, 统一技术结果信封，领域输出仍保留具体 Schema。 (+7 more)

### Community 62 - "知识类型模式"
Cohesion: 0.12
Nodes (18): Return backend schema definitions for all knowledge types., Return one backend knowledge schema., all_knowledge_card_field_keys(), all_knowledge_type_schemas(), _field(), KnowledgeFieldOption, KnowledgeFieldSchema, KnowledgeSchemaFieldType (+10 more)

### Community 63 - "正文补丁工具"
Cohesion: 0.21
Nodes (11): BaseModel, run(), manuscript_diff(), ManuscriptPatchConflictError, normalize_and_apply_patch(), patch_id(), ValueError, ManuscriptPatchOperation (+3 more)

### Community 64 - "JSON通用存储"
Cohesion: 0.23
Nodes (4): JsonStorageBackend, Path, StorageData, 将集合和记录保存为 UTF-8 JSON 文件。

### Community 65 - "MongoDB沉淀进度"
Cohesion: 0.19
Nodes (9): KnowledgeRepositoryUnavailableError, Raised when MongoDB cannot serve a knowledge repository operation., MongoDB-backed structured knowledge infrastructure., _iso(), MongoKnowledgeSedimentationProgressRepository, Any, datetime, MongoDB storage for the single knowledge-sedimentation frontier. (+1 more)

### Community 66 - "结构化知识仓储契约"
Cohesion: 0.12
Nodes (9): Protocol, Replace one card, optionally using updated_at compare-and-set., Transition one card lifecycle, optionally using compare-and-set., Find confirmed cards sharing normalized names or aliases., Technology-independent persistence contract for structured knowledge., Return confirmed cards that are eligible for factual context., Return one card by its stable business identifier., Create one card without changing its application-approved lifecycle. (+1 more)

### Community 67 - "写作提示词"
Cohesion: 0.17
Nodes (10): Fixed prompt registry for writing-page AI buttons., One fixed prompt template bound to a writing-page button., Lookup and render taskpack-fixed writing AI prompts., Return the fixed template for a button., Render one fixed user prompt by replacing taskpack placeholders., _templates(), WritingAIPromptRegistry, WritingAIPromptTemplate (+2 more)

### Community 68 - "MongoDB词法检索"
Cohesion: 0.23
Nodes (12): _append_reason(), _descending_timestamp_key(), _estimated_content_chars(), MongoLexicalRetrievalBackend, _normalize_compact(), _normalize_search_text(), _query_terms(), 基于 MongoDB 知识事实源的确定性词法召回后端。 (+4 more)

### Community 69 - "用户偏好设置"
Cohesion: 0.19
Nodes (13): provide_settings_preference_service(), Return the MVP settings preference service., api_get_preferences(), api_patch_preferences(), _bad_request(), HTTPException, MVP settings preference endpoints., Return basic editor preferences without real model configuration. (+5 more)

### Community 70 - "FastAPI应用入口"
Cohesion: 0.26
Nodes (12): JSONResponse, FastAPI, 向 FastAPI 应用注册所有功能路由。, register_routes(), create_app(), _http_exception_handler(), _knowledge_unavailable_exception_handler(), BaseChatModel (+4 more)

### Community 71 - "检索评测命令行"
Cohesion: 0.19
Nodes (7): main(), _recall_at_k(), _run(), 读取可选覆盖；任何无效值都以中文安全错误阻止启动。, JsonlRetrievalTraceRepository, Path, 将完成、空结果和失败召回保存为轻量技术记录。

### Community 72 - "来源引用校验"
Cohesion: 0.21
Nodes (11): Raised when a SourceRef violates the v1 evidence contract., SourceRefValidationError, Protocol, SourceRef validation interface and local contract checks., Result returned by storage-aware SourceRef validators., Storage-aware validator implemented outside the domain layer., Validate freshness and optionally return a relocated reference., Run local v1 checks already encoded by the SourceRef model. (+3 more)

### Community 73 - "能力评测档案"
Cohesion: 0.31
Nodes (10): MetricDefinition, all_capability_evaluation_profiles(), capability_evaluation_profile(), CapabilityEvaluationMetric, CapabilityEvaluationProfile, _profile(), BaseModel, 第一版 Tool 与专业子 Agent 的独立评测口径注册表。 (+2 more)

### Community 74 - "确定性模拟模型"
Cohesion: 0.18
Nodes (8): MVPNoRealLLMChatModel, Any, BaseChatModel, BaseMessage, CallbackManagerForLLMRun, ChatResult, Local mock chat model used by the MVP instead of a real LLM., A deterministic chat model that never calls an external service.

### Community 75 - "不可用模型占位"
Cohesion: 0.18
Nodes (8): Any, BaseChatModel, BaseMessage, CallbackManagerForLLMRun, ChatResult, Failure-only chat model used when no real LLM is configured., A chat model placeholder that never generates synthetic content., UnavailableLLMChatModel

### Community 76 - "评测数据集契约"
Cohesion: 0.22
Nodes (6): EvaluationDatasetRepository, Protocol, Discover and load immutable knowledge-extraction evaluation data., List datasets without exposing filesystem paths., Validate one dataset and return all discoverable issues., Return one confirmed and fully validated dataset.

### Community 77 - "知识类型中文标签"
Cohesion: 0.25
Nodes (8): api_list_knowledge_types(), Return structured knowledge types with Chinese labels., KnowledgeTypeInfo, KnowledgeTypesResponse, Knowledge type with Chinese label., Supported knowledge types., knowledge_type_label(), Return the Chinese label for one knowledge type.

### Community 78 - "能力依赖校验"
Cohesion: 0.29
Nodes (5): CapabilityTypeError, MissingCapabilityError, RuntimeError, T, TypeError

### Community 80 - "知识模式API"
Cohesion: 0.50
Nodes (4): api_list_knowledge_schemas(), Return all structured knowledge schemas., KnowledgeSchemasResponse, Supported knowledge type schemas.

### Community 81 - "写作流式响应"
Cohesion: 0.50
Nodes (4): api_stream_writing_ai_run(), Request, StreamingResponse, 以 NDJSON 输出真实模型增量，同时保存最终完整运行记录。

### Community 82 - "写作运行异常"
Cohesion: 0.50
Nodes (3): LookupError, Raised when a writing AI run id is not found., WritingAIRunNotFoundError

### Community 83 - "智能体事件流"
Cohesion: 0.67
Nodes (3): api_stream_agent_task_events(), StreamingResponse, Stream future Agent task events as NDJSON.

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StructuredKnowledgeType` connect `工具领域类型` to `知识抽取评测指标`, `知识抽取工作流`, `知识抽取工作台接口`, `领域事实模型`, `评测差异解释`, `能力与工具契约`, `知识抽取批次执行`, `子智能体模型与契约`, `知识抽取任务状态`, `MongoDB知识仓储`, `评测数据集仓储`, `收件箱服务接口`, `智能体运行记录存储`, `知识卡业务服务`, `知识候选匹配`, `MVP收件箱`, `章节结构工具`, `检索执行服务`, `知识卡API接口`, `检索上下文模型`, `检索评测模型`, `收件箱写操作接口`, `知识查询服务`, `检索评测仓储`, `知识类型模式`, `正文补丁工具`, `MongoDB沉淀进度`, `结构化知识仓储契约`, `知识类型中文标签`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `create_app()` connect `FastAPI应用入口` to `章节与大纲管理`, `通用智能体评测`, `知识抽取工作流`, `知识抽取工作台接口`, `知识抽取评测服务`, `Markdown项目存储`, `能力与工具契约`, `章节摘要服务`, `通用智能体运行时`, `AI结果与待处理事实`, `知识抽取任务状态`, `MongoDB知识仓储`, `评测数据集仓储`, `收件箱服务接口`, `子智能体注册与追踪`, `智能体运行记录存储`, `大模型调用契约`, `评测结果存储`, `AI结果卡服务`, `子智能体执行器`, `知识卡业务服务`, `外部资料研究`, `MVP收件箱`, `智能体插件注册`, `章节结构工具`, `通用智能体编排器`, `检索执行服务`, `模型目录与配置`, `写作助手运行服务`, `模型用量审计`, `动态任务图执行`, `模型API与用量接口`, `知识查询服务`, `小说导出服务`, `通用智能体运行仓储`, `检索评测仓储`, `检索评测API`, `知识沉淀进度`, `JSON通用存储`, `MongoDB沉淀进度`, `结构化知识仓储契约`, `MongoDB词法检索`, `用户偏好设置`, `检索评测命令行`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `ChapterService` connect `章节结构工具` to `章节与大纲管理`, `知识抽取工作流`, `知识抽取工作台接口`, `知识抽取评测接口`, `知识抽取评测服务`, `评测差异解释`, `章节来源接口模型`, `章节摘要服务`, `知识抽取批次执行`, `知识抽取任务状态`, `工具领域类型`, `项目资产存储契约`, `写作助手运行服务`, `知识抽取图契约`, `API依赖注入`, `写作助手API`, `写作检索上下文`, `正文补丁工具`, `写作提示词`, `FastAPI应用入口`, `写作运行异常`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 177 inferred relationships involving `StructuredKnowledgeType` (e.g. with `KnowledgeExtractionDependencies` and `KnowledgeExtractionState`) actually correct?**
  _`StructuredKnowledgeType` has 177 INFERRED edges - model-reasoned connections that need verification._
- **Are the 76 inferred relationships involving `StructuredKnowledgeCard` (e.g. with `KnowledgeExtractionDependencies` and `KnowledgeExtractionState`) actually correct?**
  _`StructuredKnowledgeCard` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `CapabilityContext` (e.g. with `AgentManifest` and `AgentPlugin`) actually correct?**
  _`CapabilityContext` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `KnowledgeExtractionService` (e.g. with `KnowledgeExtractionDependencies` and `AgentBatchChapterProgress`) actually correct?**
  _`KnowledgeExtractionService` has 28 INFERRED edges - model-reasoned connections that need verification._