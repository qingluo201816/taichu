import asyncio

import pytest

from taichu.application.evaluations.rag.models import (
    RAGExpectedRelation,
    RAGGoldenCase,
    RAGGoldenCategory,
    RAGGoldenSuite,
)
from taichu.application.evaluations.rag.runner import (
    RAGEvaluationExecutionError,
    run_deterministic_evaluation,
)
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


def test_runner_executes_graph_cases_as_paired_ablation() -> None:
    relation = RAGExpectedRelation(subject="甲", predicate="师从", object="乙")
    suite = RAGGoldenSuite(
        suite_id="test-suite",
        cases=[
            RAGGoldenCase(
                case_id="graph-001",
                query="问题",
                category=RAGGoldenCategory.GRAPH_MULTI_HOP,
                graph_required=True,
                expected_source_ids=["source-a"],
                expected_relations=[relation],
                expected_path=[relation.relation_id],
                expected_claims=["事实"],
                reference_answer="答案",
            )
        ],
    )

    class ServiceFake:
        calls: list[bool] = []

        async def retrieve(
            self, query: str, *, top_k: int, graph_enabled: bool
        ) -> VectorGraphRetrievalResult:
            self.calls.append(graph_enabled)
            return VectorGraphRetrievalResult(
                query=query,
                reranked_relations=[relation.text] if graph_enabled else [],
            )

    service = ServiceFake()
    report = asyncio.run(
        run_deterministic_evaluation(suite, service, include_ablation=True)  # type: ignore[arg-type]
    )

    assert service.calls == [True, False]
    assert len(report.case_scores) == 1
    assert len(report.ablation_scores) == 1
    assert report.ablation_scores[0].complete_path_delta == 1.0
    assert report.summary.graph_case_count == 1


def test_smoke_mode_only_runs_marked_cases() -> None:
    cases = [
        RAGGoldenCase(
            case_id=f"single-{index:03d}",
            query="问题",
            category=RAGGoldenCategory.SINGLE_FACT,
            smoke=index == 1,
            expected_source_ids=[],
            expected_claims=["事实"],
            reference_answer="答案",
        )
        for index in range(1, 3)
    ]

    class ServiceFake:
        calls = 0

        async def retrieve(
            self, query: str, *, top_k: int, graph_enabled: bool
        ) -> VectorGraphRetrievalResult:
            self.calls += 1
            return VectorGraphRetrievalResult(query=query)

    service = ServiceFake()
    report = asyncio.run(
        run_deterministic_evaluation(
            RAGGoldenSuite(suite_id="suite", cases=cases),
            service,  # type: ignore[arg-type]
            smoke_only=True,
            include_ablation=False,
        )
    )

    assert service.calls == 1
    assert report.summary.case_count == 1


def test_runner_reports_case_and_phase_for_infrastructure_failure() -> None:
    case = RAGGoldenCase(
        case_id="single-001",
        query="问题",
        category=RAGGoldenCategory.SINGLE_FACT,
        expected_source_ids=["source-a"],
        expected_claims=["事实"],
        reference_answer="答案",
    )

    class ServiceFake:
        async def retrieve(
            self, query: str, *, top_k: int, graph_enabled: bool
        ) -> VectorGraphRetrievalResult:
            raise TimeoutError("重排超时")

    with pytest.raises(
        RAGEvaluationExecutionError,
        match="single-001.*Graph ON.*重排超时",
    ):
        asyncio.run(
            run_deterministic_evaluation(
                RAGGoldenSuite(suite_id="suite", cases=[case]),
                ServiceFake(),  # type: ignore[arg-type]
            )
        )
