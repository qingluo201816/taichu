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


def test_runner_executes_every_case_through_the_single_production_chain() -> None:
    relation = RAGExpectedRelation(subject="甲", predicate="师从", object="乙")
    suite = RAGGoldenSuite(
        suite_id="test-suite",
        cases=[
            RAGGoldenCase(
                case_id="graph-001",
                query="问题",
                category=RAGGoldenCategory.GRAPH_MULTI_HOP,
                graph_required=True,
            expected_source_ids=[],
                expected_relations=[relation],
                expected_path=[relation.relation_id],
                expected_claims=["事实"],
                reference_answer="答案",
            )
        ],
    )

    class ServiceFake:
        calls = 0

        async def retrieve(
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            self.calls += 1
            return VectorGraphRetrievalResult(
                query=query,
                context_relations=[relation.text],
            )

    service = ServiceFake()
    report = asyncio.run(run_deterministic_evaluation(suite, service))  # type: ignore[arg-type]

    assert service.calls == 1
    assert len(report.case_scores) == 1
    assert report.case_scores[0].complete_path_recall == 1.0
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
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            self.calls += 1
            return VectorGraphRetrievalResult(query=query)

    service = ServiceFake()
    report = asyncio.run(
        run_deterministic_evaluation(
            RAGGoldenSuite(suite_id="suite", cases=cases),
            service,  # type: ignore[arg-type]
            smoke_only=True,
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
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            raise TimeoutError("重排超时")

    with pytest.raises(
        RAGEvaluationExecutionError,
        match="single-001.*生产检索.*重排超时",
    ):
        asyncio.run(
            run_deterministic_evaluation(
                RAGGoldenSuite(suite_id="suite", cases=[case]),
                ServiceFake(),  # type: ignore[arg-type]
            )
        )


def test_runner_can_record_failure_and_continue_remaining_cases() -> None:
    suite = RAGGoldenSuite(
        suite_id="suite",
        cases=[
            RAGGoldenCase(
                case_id=f"single-{index:03d}",
                query=f"问题{index}",
                category=RAGGoldenCategory.SINGLE_FACT,
                expected_source_ids=[],
                expected_claims=["事实"],
                reference_answer="答案",
            )
            for index in range(1, 3)
        ],
    )

    class ServiceFake:
        async def retrieve(
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            if query == "问题1":
                raise TimeoutError("重排超时")
            return VectorGraphRetrievalResult(query=query)

    report = asyncio.run(
        run_deterministic_evaluation(
            suite,
            ServiceFake(),  # type: ignore[arg-type]
            continue_on_error=True,
        )
    )

    assert [item.case_id for item in report.case_scores] == ["single-002"]
    assert len(report.execution_failures) == 1
    assert report.execution_failures[0].case_id == "single-001"
    assert report.execution_failures[0].phase == "生产检索"
