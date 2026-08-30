"""运行太初 Graph RAG 确定性回归与 DeepEval 语义评测。"""

from __future__ import annotations

import argparse
import asyncio
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from taichu.application.evaluations.rag.dataset import (
    load_golden_suite,
    validate_core_golden_suite,
)
from taichu.application.evaluations.rag.gates import (
    evaluate_regression_gate,
    select_pr_semantic_cases,
)
from taichu.application.evaluations.rag.models import (
    RAGInfrastructureFailureReport,
    RAGRunReport,
)
from taichu.application.evaluations.rag.runner import run_deterministic_evaluation
from taichu.config import settings
from taichu.infrastructure.evaluations.rag.answer_generator import RAGAnswerGenerator
from taichu.infrastructure.evaluations.rag.deepeval_adapter import (
    TaichuDeepEvalLLM,
    evaluate_semantic_case,
)
from taichu.infrastructure.evaluations.rag.result_repository import (
    RAGEvaluationResultRepository,
)
from taichu.infrastructure.vector_graph.llm_adapter import (
    vector_graph_llm_run_context,
)
from taichu.main import create_app


DEFAULT_SUITE = Path("tests/fixtures/evaluations/rag_graph_core/suite.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="太初 Graph RAG 质量评测")
    parser.add_argument("mode", choices=("smoke", "rag-pr", "full"))
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--no-gate", action="store_true", help="只产出报告，不阻断")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    suite = load_golden_suite(args.suite)
    validate_core_golden_suite(suite)
    application = create_app(settings)
    gateway = application.state.llm_gateway
    chat_model = application.state.chat_model
    active_provider = getattr(gateway, "active_provider", "unknown")
    provider_label = {
        "rightcode": "RightCode",
        "deepseek_official": "DeepSeek 官方",
    }.get(active_provider, "未知供应商")
    print(
        f"本次评测供应商：{provider_label}；"
        f"Graph 模型：{settings.vector_graph_llm_model}"
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{args.mode}"
    repository = RAGEvaluationResultRepository(
        settings.project_assets_dir / "derived" / "rag_evaluations"
    )
    try:
        with vector_graph_llm_run_context(run_id):
            deterministic = await run_deterministic_evaluation(
                suite,
                application.state.vector_graph_rag_service,
                smoke_only=args.mode == "smoke",
                continue_on_error=True,
            )
        semantic_scores: list[dict[str, object]] = []
        if args.mode in ("smoke", "rag-pr", "full"):
            default_model_id = next(
                profile.id for profile in gateway.list_models() if profile.is_default
            )
            judge_model_id = (
                settings.evaluation_judge_model.strip() or default_model_id
            )
            generator = RAGAnswerGenerator(chat_model, model_id=default_model_id)
            judge = TaichuDeepEvalLLM(chat_model, judge_model_id)
            semantic_cases = (
                [case for case in suite.cases if case.smoke]
                if args.mode == "smoke"
                else (
                    list(suite.cases)
                    if args.mode == "full"
                    else list(select_pr_semantic_cases(suite.cases))
                )
            )
            with vector_graph_llm_run_context(run_id):
                for case in semantic_cases:
                    try:
                        retrieval = (
                            await application.state.vector_graph_rag_service.retrieve(
                                case.query,
                                top_k=10,
                            )
                        )
                        answer = await generator.generate(case.query, retrieval)
                        score = await evaluate_semantic_case(
                            case,
                            actual_answer=answer,
                            retrieval=retrieval,
                            judge=judge,
                        )
                        semantic_scores.append(score.model_dump(mode="json"))
                    except Exception as error:
                        semantic_scores.append(
                            {
                                "case_id": case.case_id,
                                "status": "failed",
                                "error_type": type(error).__name__,
                                "error_message": str(error)[:2_000],
                            }
                        )

        gate = evaluate_regression_gate(deterministic, semantic_scores)
        report = RAGRunReport(
            deterministic=deterministic,
            semantic_scores=semantic_scores,
            runtime_identity={
                "llm_provider": active_provider,
                "embedding_model": settings.embedding_model_id,
                "reranker_model": settings.reranker_model_id,
                "graph_llm_model": settings.vector_graph_llm_model,
                "generator_model": (
                    default_model_id
                ),
                "judge_model": (
                    judge_model_id
                ),
            },
            gate=gate,
        )
        output = repository.save(report, run_id=run_id)
        print(f"RAG 评测报告：{output.resolve()}")
        print(report.deterministic.summary.model_dump_json(indent=2))
        if gate.failures:
            print("门禁失败：")
            for gate_failure in gate.failures:
                print(f"- {gate_failure}")
        else:
            print("门禁通过。")
        return 0 if args.no_gate or gate.passed else 1
    except Exception as error:
        infrastructure_failure = RAGInfrastructureFailureReport(
            mode=args.mode,
            created_at=datetime.now(UTC).isoformat(),
            error_type=type(error).__name__,
            error_message=str(error)[:2_000],
        )
        output = repository.save(infrastructure_failure, run_id=run_id)
        print(f"RAG 评测基础设施失败：{type(error).__name__}: {error}")
        print(f"失败报告：{output.resolve()}")
        return 2
    finally:
        await _close_state(application.state)


async def _close_state(state: Any) -> None:
    for name in (
        "vector_graph_backend",
        "knowledge_repository",
        "sedimentation_progress_repository",
    ):
        resource = getattr(state, name, None)
        close = getattr(resource, "close", None)
        if close is None:
            continue
        result = close()
        if inspect.isawaitable(result):
            await result


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
