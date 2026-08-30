"""Graph RAG 当前 Golden 集与评测结果只读入口。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import (
    provide_app_settings,
    provide_rag_evaluation_result_repository,
)
from taichu.application.evaluations.rag.dataset import (
    load_golden_suite,
    validate_core_golden_suite,
)
from taichu.application.evaluations.rag.models import (
    RAGEvaluationCIPolicy,
    RAGEvaluationConfiguration,
    RAGEvaluationParameter,
    RAGEvaluationPipelineStage,
    RAGEvaluationResultSummary,
    RAGGoldenSuite,
    RAGInfrastructureFailureReport,
    RAGRunReport,
)
from taichu.config import Settings
from taichu.infrastructure.evaluations.rag.result_repository import (
    RAGEvaluationResultRepository,
)


router = APIRouter(prefix="/api/rag-evaluations", tags=["Graph RAG 质量评测"])


@router.get("/suite", response_model=RAGGoldenSuite)
async def get_current_suite(
    app_settings: Settings = Depends(provide_app_settings),
) -> RAGGoldenSuite:
    suite = load_golden_suite(
        app_settings.evaluation_datasets_dir / "rag_graph_core" / "suite.json"
    )
    validate_core_golden_suite(suite)
    return suite


@router.get("/results", response_model=list[RAGEvaluationResultSummary])
async def list_results(
    limit: int = Query(default=10, ge=1, le=50),
    repository: RAGEvaluationResultRepository = Depends(
        provide_rag_evaluation_result_repository
    ),
) -> list[RAGEvaluationResultSummary]:
    return repository.list_summaries(limit=limit)


@router.get(
    "/results/{run_id}",
    response_model=RAGRunReport | RAGInfrastructureFailureReport,
)
async def get_result(
    run_id: str,
    repository: RAGEvaluationResultRepository = Depends(
        provide_rag_evaluation_result_repository
    ),
) -> RAGRunReport | RAGInfrastructureFailureReport:
    result = repository.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该次 RAG 评测结果。")
    return result


@router.get("/configuration", response_model=RAGEvaluationConfiguration)
async def get_configuration(
    app_settings: Settings = Depends(provide_app_settings),
) -> RAGEvaluationConfiguration:
    return RAGEvaluationConfiguration(
        pipeline=[
            RAGEvaluationPipelineStage(
                key="passage_retrieval",
                order=1,
                name="Passage 双路召回",
                description="BM25 Passage Top 30 与 HNSW Dense Passage Top 30 并行召回。",
            ),
            RAGEvaluationPipelineStage(
                key="rrf_graph_expansion",
                order=2,
                name="RRF 与有界图扩展",
                description="RRF Top 30 提供实体与关系种子，一跳扩图后按 relation.passage_ids 回取并合并 Passage。",
            ),
            RAGEvaluationPipelineStage(
                key="rerank_context",
                order=3,
                name="重排与上下文重建",
                description="全部合并候选只执行一次 BGE 评分；Top 10 作为评测与追踪边界，再选择最多 3 份互补证据并按问题类型重建原文句窗或父级上下文。",
            ),
            RAGEvaluationPipelineStage(
                key="deterministic",
                order=4,
                name="Golden 确定性回归",
                description="计算 Recall@10、MRR@10、权威回源、关系召回与完整路径召回。",
            ),
            RAGEvaluationPipelineStage(
                key="semantic",
                order=5,
                name="DeepEval 语义评测",
                description="对生成答案评估上下文相关性、忠实度与答案相关性。",
            ),
            RAGEvaluationPipelineStage(
                key="gate",
                order=6,
                name="自动回归门禁",
                description="汇总确定性与语义指标，输出可解释失败原因并决定 CI 是否放行。",
            ),
        ],
        parameters=[
            RAGEvaluationParameter(
                key="retrieval_top_k",
                name="评测召回深度",
                value="10",
                description="Recall、MRR 与关系召回统一按前 10 条计算。",
            ),
            RAGEvaluationParameter(
                key="passage_top_k",
                name="RRF Passage 候选",
                value=str(app_settings.vector_graph_passage_top_k),
                description="BM25 与 Dense 各取相同 TopK，并由 RRF 融合为该数量的种子 Passage。",
            ),
            RAGEvaluationParameter(
                key="graph_hop",
                name="最大图跳数",
                value=str(app_settings.vector_graph_expansion_max_hop),
                description="从 RRF Passage 图元数据出发允许继续扩展的最大跳数。",
            ),
            RAGEvaluationParameter(
                key="seed_entities",
                name="种子实体上限",
                value=str(app_settings.vector_graph_expansion_max_seed_entities),
                description="避免主角等 Hub 实体同时展开过多入口。",
            ),
            RAGEvaluationParameter(
                key="seed_relations",
                name="种子关系上限",
                value=str(app_settings.vector_graph_expansion_max_seed_relations),
                description="从 RRF Passage 携带关系中按 Query 与 Passage 支持度保留的上限。",
            ),
            RAGEvaluationParameter(
                key="neighbor_candidate_pool",
                name="邻边候选池倍率",
                value=str(
                    app_settings.vector_graph_expansion_candidate_pool_multiplier
                ),
                description="每个实体先扩大查询相关邻边候选池，再按单实体上限择优准入。",
            ),
            RAGEvaluationParameter(
                key="relation_budget",
                name="全局关系预算",
                value=str(app_settings.vector_graph_expansion_max_total_relations),
                description="图扩展关系总量的硬上限，防止上下文爆炸。",
            ),
            RAGEvaluationParameter(
                key="rrf_k",
                name="Milvus RRF 常数",
                value=str(app_settings.milvus_rrf_k),
                description="BM25 与 Dense 多路候选融合使用的 RRF 参数。",
            ),
            RAGEvaluationParameter(
                key="reranker_top_k",
                name="BGE 评测与追踪边界",
                value=str(app_settings.vector_graph_reranker_top_k),
                description="统一 BGE 排序用于 Recall、MRR、关系召回和检索追踪的前 K 条；上下文装配另按互补性选择最多 3 份证据。",
            ),
        ],
        ci_policies=[
            RAGEvaluationCIPolicy(
                name="普通拉取请求",
                trigger="所有 pull_request",
                scope="5 条生产链冒烟 + 评测契约测试",
            ),
            RAGEvaluationCIPolicy(
                name="RAG 相关拉取请求",
                trigger="检索、评测、语料或配置路径变更",
                scope="30 条 Golden 确定性回归 + 10 条 DeepEval",
            ),
            RAGEvaluationCIPolicy(
                name="发布前手动评测",
                trigger="workflow_dispatch",
                scope="30 条完整确定性回归 + 30 条 DeepEval",
            ),
        ],
    )
