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
                key="production_retrieval",
                order=1,
                name="生产检索链",
                description="BM25 与 HNSW Dense 召回，经 Milvus RRF 融合后进行受控图扩展。",
            ),
            RAGEvaluationPipelineStage(
                key="rerank_context",
                order=2,
                name="重排与上下文重建",
                description="BGE 二阶段精排后回源父级与相邻正文，形成最终证据上下文。",
            ),
            RAGEvaluationPipelineStage(
                key="deterministic",
                order=3,
                name="Golden 确定性回归",
                description="计算 Recall@10、MRR@10、权威回源、关系召回与完整路径召回。",
            ),
            RAGEvaluationPipelineStage(
                key="ablation",
                order=4,
                name="Graph ON/OFF 消融",
                description="对 14 条图用例成对运行，验证图扩展带来的完整路径净增益。",
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
                key="relation_top_k",
                name="关系初始召回",
                value=str(app_settings.vector_graph_relation_top_k),
                description="关系向量检索进入受控扩展前的候选上限。",
            ),
            RAGEvaluationParameter(
                key="graph_hop",
                name="最大图跳数",
                value=str(app_settings.vector_graph_expansion_degree),
                description="受控 Graph Expansion 的最大扩展深度。",
            ),
            RAGEvaluationParameter(
                key="seed_entities",
                name="种子实体上限",
                value=str(app_settings.vector_graph_expansion_max_seed_entities),
                description="避免主角等 Hub 实体同时展开过多入口。",
            ),
            RAGEvaluationParameter(
                key="initial_relations",
                name="单实体初始关系",
                value=str(
                    app_settings.vector_graph_expansion_initial_relations_per_entity
                ),
                description="每个种子实体按 Query 相关性保留的初始邻接关系数。",
            ),
            RAGEvaluationParameter(
                key="relation_budget",
                name="全局关系预算",
                value=str(app_settings.vector_graph_relation_number_threshold),
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
                name="BGE 最终保留",
                value=str(app_settings.vector_graph_reranker_top_k),
                description="二阶段精排后送入上下文组装的证据数量。",
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
                scope="30 条 Golden + 14 条 Graph 消融 + 10 条 DeepEval",
            ),
            RAGEvaluationCIPolicy(
                name="发布前手动评测",
                trigger="workflow_dispatch",
                scope="30 条完整确定性回归 + 14 条 Graph 消融 + 30 条 DeepEval",
            ),
        ],
    )
