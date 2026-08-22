"""需求 1.10、2.4、5.8、7.4、7.8、9.1-9.9：新基准资源 API。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
import tempfile
from typing import TypeVar

import httpx
from fastapi import FastAPI

from taichu.api.routes.general_agent_benchmarks import router
from taichu.application.evaluations.general_agent_benchmark.container import (
    build_general_agent_benchmark_services,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    FrozenSubjectSnapshot,
    InboxIssueReadback,
    IssueCorrelationIntent,
    IssueCorrelationRepository,
    IssueCorrelationRelationRevision,
    IssueCorrelationSnapshot,
    IssueRelationManifest,
    IterationCorrelationSnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    InMemorySuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CaseConclusion,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
    CaseResultRow,
    EvidenceAvailability,
    EvidenceBundle,
    EvidenceBundleIdentity,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_authored_suite,
)
from taichu.config import Settings
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


async def _execute_case(run: SuiteRun, case_id: str) -> str:
    return f"row:{run.run_id}:{case_id}"


async def _finalize(run: SuiteRun) -> tuple[SuiteConclusion, str]:
    return SuiteConclusion.PASSED, f"artifact:{run.run_id}"


def _app() -> tuple[FastAPI, object]:
    services = build_general_agent_benchmark_services(
        catalog_entries=(
            BenchmarkCatalogEntry(
                suite_id="general_writing_agent_core",
                name="通用写作智能体固定基准",
                content_hash="a" * 64,
                case_count=37,
            ),
        ),
        suite_run_store=InMemorySuiteRunStore(),
        execute_case=_execute_case,
        finalize_suite=_finalize,
        issue_correlation_repository=IssueCorrelationRepository(),
    )
    app = FastAPI()
    app.state.general_agent_benchmark_services = services
    app.include_router(router)
    return app, services


def _authoritative_app() -> tuple[FastAPI, object, object]:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        Path(
            "tests/fixtures/evaluations/"
            "general_writing_agent_benchmark/suite.json"
        ),
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    services = build_general_agent_benchmark_services(
        catalog_entries=(BenchmarkCatalogEntry.from_suite(suite),),
        authored_suites=(suite,),
        suite_run_store=InMemorySuiteRunStore(),
        execute_case=_execute_case,
        finalize_suite=_finalize,
        issue_correlation_repository=IssueCorrelationRepository(),
    )
    app = FastAPI()
    app.state.general_agent_benchmark_services = services
    app.include_router(router)
    return app, services, suite


def test_catalog_submission_list_detail_and_lifecycle_resources() -> None:
    async def scenario() -> None:
        app, services = _app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            suites = await client.get("/api/general-agent-benchmarks/suites")
            assert suites.status_code == 200
            assert suites.json()["items"][0]["case_count"] == 37

            submitted = await client.post(
                "/api/general-agent-benchmarks/runs",
                json={
                    "idempotency_key": "api-run",
                    "run_id": "benchmark_run_20260727T000001Z_abcdef123456",
                    "suite_id": "general_writing_agent_core",
                    "suite_content_hash": "a" * 64,
                    "selected_case_ids": ["case_a"],
                    "track": "synthetic",
                },
            )
            assert submitted.status_code == 201
            run_id = submitted.json()["run"]["run_id"]

            listing = await client.get(
                "/api/general-agent-benchmarks/runs",
                params={"page": 1, "page_size": 20},
            )
            detail = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}"
            )
            assert listing.json()["items"][0]["conclusion"] == "passed"
            assert detail.json()["run"]["lifecycle"] == "completed"

            cancellable_id = (
                "benchmark_run_20260727T000002Z_abcdef123457"
            )
            await services.lifecycle.create(
                run_id=cancellable_id,
                suite_content_hash="a" * 64,
                selected_case_ids=("case_a",),
                track="synthetic",
            )
            started = await services.lifecycle.start(
                cancellable_id,
                expected_revision=0,
            )
            cancelled = await client.post(
                f"/api/general-agent-benchmarks/runs/{cancellable_id}/cancel",
                json={"expected_revision": started.revision},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["run"]["lifecycle"] == "cancelling"

            finished = await services.lifecycle.finish_cancel(
                cancellable_id,
                expected_revision=cancelled.json()["run"]["revision"],
            )
            conflict = await client.post(
                f"/api/general-agent-benchmarks/runs/{cancellable_id}/resume",
                json={"expected_revision": finished.revision},
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"]["request_id"].startswith("req_")

    _run(scenario())


def test_suite_detail_and_submission_use_authoritative_37_track_selection() -> None:
    async def scenario() -> None:
        app, services, suite = _authoritative_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            detail = await client.get(
                f"/api/general-agent-benchmarks/suites/{suite.suite_id}"
            )
            payload = detail.json()["suite"]
            assert detail.status_code == 200
            assert payload["content_hash"] == suite.content_hash
            assert payload["case_count"] == 37
            assert payload["case_order"] == list(suite.case_order)
            assert payload["track_case_counts"] == {
                "synthetic": 37,
                "live_provider": 21,
            }
            assert [case["ordinal"] for case in payload["cases"]] == list(
                range(1, 38)
            )
            assert [case["case_id"] for case in payload["cases"]] == list(
                suite.case_order
            )
            assert [domain["name"] for domain in payload["capability_domains"]] == [
                "简单路由与检索",
                "证据与多智能体协作",
                "预览、授权与持久化资源",
                "运行工作记忆",
                "检查点、中断与恢复",
                "五层上下文治理",
            ]
            assert [
                case_id
                for domain in payload["capability_domains"]
                for case_id in domain["case_ids"]
            ] == list(suite.case_order)
            assert all(
                case["name"]
                and case["summary"]
                and case["user_request"]
                and case["tracks"]
                and case["objective"]
                and case["target_final_artifact"]
                and case["behavior_expectations"]
                and case["expected_terminal"]
                and case["budget_limits"]
                and case["capability_domain_id"]
                for case in payload["cases"]
            )
            assert payload["cases"][0]["budget_limits"] == {
                "max_node_executions": 50,
                "max_replans": 4,
                "max_capability_calls": 20,
                "max_model_calls": 20,
                "max_total_tokens": 100000,
                "max_runtime_ms": 600000,
            }
            serialized = str(payload)
            assert "scripted_steps" not in serialized
            assert "required_claim_refs" not in serialized
            assert "user_request_raw" not in serialized
            assert "required_invocations" not in serialized

            invalid_selections = (
                {
                    "suite_content_hash": "f" * 64,
                    "selected_case_ids": list(suite.case_order),
                    "track": "synthetic",
                },
                {
                    "suite_content_hash": suite.content_hash,
                    "selected_case_ids": ["unknown_case"],
                    "track": "synthetic",
                },
                {
                    "suite_content_hash": suite.content_hash,
                    "selected_case_ids": [
                        suite.case_order[0],
                        suite.case_order[0],
                    ],
                    "track": "synthetic",
                },
                {
                    "suite_content_hash": suite.content_hash,
                    "selected_case_ids": [
                        suite.case_order[1],
                        suite.case_order[0],
                    ],
                    "track": "synthetic",
                },
                {
                    "suite_content_hash": suite.content_hash,
                    "selected_case_ids": [suite.case_order[21]],
                    "track": "live_provider",
                },
            )
            for position, selection in enumerate(invalid_selections):
                response = await client.post(
                    "/api/general-agent-benchmarks/runs",
                    json={
                        "idempotency_key": f"invalid-{position}",
                        "run_id": (
                            "benchmark_run_20260731T01010"
                            f"{position}Z_abcdef12345{position}"
                        ),
                        "suite_id": suite.suite_id,
                        **selection,
                    },
                )
                assert response.status_code == 422
                error = response.json()["detail"]
                assert error["error"] == "benchmark_selection_invalid"
                assert error["message"]
                assert error["details"]["code"]

            runs = await services.queries.list_runs(page=1, page_size=20)
            assert runs.total == 0

    _run(scenario())


def test_case_evidence_and_artifact_resources_use_formal_contracts() -> None:
    async def scenario() -> None:
        app, services = _app()
        run_id = "benchmark_run_20260727T000002Z_abcdef123456"
        row = CaseResultRow(
            suite_id="general_writing_agent_core",
            case_id="case_a",
            case_execution_id=f"benchmark_case_{'a' * 32}",
            attempt_number=1,
            execution_state=CaseExecutionState.COMPLETED,
            conclusion=CaseConclusion.PASSED,
            failure_category=None,
            failure_categories=(),
            evidence_bundle_id=f"evidence_{'b' * 64}",
            evidence_availability=EvidenceAvailability.AVAILABLE,
        )
        evidence = EvidenceBundle(
            identity=EvidenceBundleIdentity(
                bundle_id=f"evidence_{'b' * 64}",
                bundle_hash="b" * 64,
                suite_id="general_writing_agent_core",
                case_id="case_a",
                run_id=run_id,
                case_execution_id=f"benchmark_case_{'a' * 32}",
                track="synthetic",
                fixture_snapshot_id=f"fixture_{'c' * 64}",
            ),
            availability={"run_evidence": "available"},
            problems=(),
        )
        artifact = SuiteArtifact(
            artifact_id="suite_artifact_a",
            run_id=run_id,
            conclusion="passed",
            case_rows=(row,),
            evidence_bundles=(evidence,),
            provider_state="not_applicable",
            artifact_hash="d" * 64,
        )
        services.resources.register(artifact)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            cases = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}/cases"
            )
            detail = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}/cases/case_a"
            )
            observed = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}"
                "/cases/case_a/evidence"
            )
            aggregate = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}/artifact"
            )

            assert cases.status_code == 200
            assert detail.json()["case"]["conclusion"] == "passed"
            assert observed.json()["evidence"]["identity"]["case_id"] == "case_a"
            assert aggregate.json()["artifact"]["conclusion"] == "passed"
            assert "coherence" not in aggregate.text

    _run(scenario())


def test_missing_resource_error_contains_request_id() -> None:
    async def scenario() -> None:
        app, _ = _app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/general-agent-benchmarks/runs/missing"
            )

        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "resource_not_found"
        assert response.json()["detail"]["request_id"].startswith("req_")

    _run(scenario())


def test_validation_error_and_openapi_use_only_formal_new_contracts() -> None:
    async def scenario() -> None:
        app, _ = _app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            invalid = await client.post(
                "/api/general-agent-benchmarks/runs",
                json={"track": "synthetic"},
            )
            openapi = (await client.get("/openapi.json")).json()

        assert invalid.status_code == 422
        assert invalid.json()["detail"]["request_id"].startswith("req_")
        paths = openapi["paths"]
        assert "/api/general-agent-benchmarks/runs/{run_id}/artifact" in paths
        assert (
            "/api/general-agent-benchmarks/runs/{run_id}"
            "/cases/{case_id}/evidence"
        ) in paths
        serialized = str(openapi)
        assert "coherence" not in serialized
        assert "five_dimension" not in serialized

    _run(scenario())


def _arm_json(
    arm_id: str,
    *,
    fixture_hash: str = "b" * 64,
    memory_policy: str,
) -> dict[str, object]:
    return {
        "arm_id": arm_id,
        "track": "synthetic",
        "suite_content_hash": "a" * 64,
        "fixture_hash": fixture_hash,
        "selected_case_ids": ["case_a"],
        "user_input_hash": "c" * 64,
        "conditions_hash": "d" * 64,
        "capability_catalog_hash": "e" * 64,
        "authorization_policy_hash": "f" * 64,
        "verifier_registry_hash": "1" * 64,
        "gate_policy_hash": "2" * 64,
        "decode_configuration_hash": "3" * 64,
        "environment_hash": "4" * 64,
        "provider_id": None,
        "model_id": None,
        "repetition_count": 2,
        "declared_settings": {
            "runtime_memory_policy_identity": memory_policy,
        },
    }


def test_experiment_and_iteration_resources_return_server_decisions() -> None:
    async def scenario() -> None:
        app, _ = _app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            experiment = await client.post(
                "/api/general-agent-benchmarks/experiments",
                json={
                    "experiment_id": "memory_policy_experiment",
                    "name": "运行记忆策略实验",
                    "mechanism": "memory",
                    "control": _arm_json(
                        "control",
                        memory_policy="disabled",
                    ),
                    "treatment": _arm_json(
                        "treatment",
                        fixture_hash="9" * 64,
                        memory_policy="active_only",
                    ),
                    "declared_differences": [
                        "declared_settings.runtime_memory_policy_identity"
                    ],
                    "stability_threshold_profile": "memory_stability",
                    "idempotency_key": "experiment-api",
                    "evidence_refs": [],
                },
            )
            assert experiment.status_code == 201
            assert (
                experiment.json()["experiment"]["comparability"]["status"]
                == "incomparable"
            )
            experiments = await client.get(
                "/api/general-agent-benchmarks/experiments",
                params={"page": 1, "page_size": 20},
            )
            assert experiments.json()["total"] == 1

            iteration = await client.post(
                "/api/general-agent-benchmarks/iterations",
                json={
                    "iteration_id": "deepseek_first_live",
                    "code_hash": "a" * 64,
                    "suite_hash": "b" * 64,
                    "fixture_hash": "c" * 64,
                    "capability_catalog_hash": "d" * 64,
                    "selected_case_ids": ["case_a"],
                    "synthetic_qualification_artifact_refs": [
                        "synthetic_artifact_a"
                    ],
                    "synthetic_suite_passed": False,
                    "core_gates_passed": True,
                    "memory_gates_passed": True,
                    "mechanism_gates_passed": True,
                    "prior_iteration_ids": [],
                },
            )
            assert iteration.status_code == 201
            assert iteration.json()["iteration"]["state"] == "awaiting_synthetic"
            assert iteration.json()["iteration"]["problems"]
            iterations = await client.get(
                "/api/general-agent-benchmarks/iterations",
                params={"page": 1, "page_size": 20},
            )
            assert iterations.json()["total"] == 1

    _run(scenario())


def test_asymmetric_issue_correlation_and_reconciliation_are_structured() -> None:
    async def scenario() -> None:
        app, services = _app()
        intent = await services.issue_correlation_repository.create_intent(
            IssueCorrelationIntent.create(
                iteration_id="deepseek_first_live",
                suite_hash="a" * 64,
                run_id="benchmark_run_20260727T000001Z_abcdef123456",
                failure_record_id="failure_runtime_write",
                frozen_subject_id="b" * 64,
                classification="system_defect",
                evidence_refs=("evidence_a",),
            )
        )
        relation = IssueCorrelationRelationRevision.create(
            intent_id=intent.intent_id,
            subject_id="b" * 64,
            subject_content_hash="c" * 64,
            issue_id="issue_a",
            issue_revision=1,
            issue_status="todo",
            issue_content_hash="d" * 64,
            relation_kind="observed_in",
        )
        services.issue_query.register(
            IssueCorrelationSnapshot(
                intent=intent,
                subject=FrozenSubjectSnapshot(
                    subject_id="b" * 64,
                    content_hash="c" * 64,
                    artifact_ref="first_live_artifact_a",
                ),
                relation_revision=relation,
                relation_manifest=IssueRelationManifest(
                    relation_id=relation.relation_id,
                    revision=1,
                    latest_confirmed_revision_id=relation.revision_id,
                ),
                inbox_readback=InboxIssueReadback(
                    issue_id="issue_a",
                    revision=1,
                    status="todo",
                    content_hash="d" * 64,
                    links=(),
                ),
                iteration=IterationCorrelationSnapshot(
                    iteration_id="deepseek_first_live",
                    pending_intent_ids=(intent.intent_id,),
                    confirmed_relation_revision_ids=(),
                ),
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            status_response = await client.get(
                "/api/general-agent-benchmarks/iterations/"
                "deepseek_first_live/issue-correlations",
                params={"subject_id": "b" * 64},
            )
            reconciled = await client.post(
                "/api/general-agent-benchmarks/iterations/"
                "deepseek_first_live/reconcile-issues",
                json={"subject_id": "b" * 64},
            )

        assert status_response.status_code == 200
        assert status_response.json()["status"]["symmetry"]["passed"] is False
        assert reconciled.json()["report"]["status"] == "repair_required"
        assert reconciled.json()["report"]["actions"]

    _run(scenario())


def _admission_json() -> dict[str, object]:
    return {
        "iteration_state": "ready_for_comparison",
        "code_hash": "1" * 64,
        "suite_hash": "2" * 64,
        "fixture_hash": "3" * 64,
        "case_set_hash": "4" * 64,
        "per_case_budgets_hash": "5" * 64,
        "capability_catalog_hash": "6" * 64,
        "authorization_policy_hash": "7" * 64,
        "decode_configuration_hash": "8" * 64,
        "environment_hash": "9" * 64,
        "all_system_defects_processed": True,
        "symmetry_gates_passed": True,
        "benchmark_verifier_defects_closed": True,
        "core_gates_passed": True,
        "candidates": [
            {
                "candidate_id": "deepseek_v4_pro",
                "requested_model_ref": "deepseek-v4-pro",
                "probe_succeeded": True,
                "actual_provider_id": "deepseek",
                "actual_model_id": "deepseek-v4-pro",
                "fallback_used": False,
                "replay_available": True,
                "usage_available": True,
                "cost_available": True,
                "error_code": None,
            }
        ],
    }


def test_comparison_resource_returns_blocked_and_restorable_detail_url() -> None:
    async def scenario() -> None:
        app, _ = _app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            blocked = await client.post(
                "/api/general-agent-benchmarks/comparisons",
                json={
                    "comparison_id": "comparison_blocked",
                    "idempotency_key": "comparison-blocked",
                    "first_live_artifact_ref": None,
                    "admission_input": {
                        **_admission_json(),
                        "iteration_state": "closing_system_defects",
                    },
                    "closure_decisions": [],
                },
            )
            admitted = await client.post(
                "/api/general-agent-benchmarks/comparisons",
                json={
                    "comparison_id": "comparison_ready",
                    "idempotency_key": "comparison-ready",
                    "first_live_artifact_ref": f"first_live_{'c' * 64}",
                    "admission_input": _admission_json(),
                    "closure_decisions": [],
                },
            )
            detail = await client.get(
                "/api/general-agent-benchmarks/comparisons/comparison_ready"
            )
            listing = await client.get(
                "/api/general-agent-benchmarks/comparisons",
                params={"page": 1, "page_size": 20},
            )

        assert blocked.status_code == 201
        assert blocked.json()["comparison"]["admitted"] is False
        assert blocked.json()["comparison"]["blocked_reasons"]
        assert admitted.json()["comparison"]["admitted"] is True
        assert detail.json() == admitted.json()
        assert listing.json()["total"] == 2

    _run(scenario())


def test_main_route_table_switches_to_unique_new_benchmark_prefix() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        app = create_app(
            Settings(
                project_assets_dir=Path(temporary_directory),
                evaluation_datasets_dir=(
                    Path(temporary_directory) / "custom-empty-datasets"
                ),
            ),
            knowledge_repository=InMemoryKnowledgeRepository(),
        )

    paths: set[str] = set()
    for included in app.routes:
        router = getattr(included, "original_router", None)
        candidates = router.routes if router is not None else (included,)
        paths.update(
            path
            for route in candidates
            if (path := getattr(route, "path", None)) is not None
        )
    assert "/api/general-agent-benchmarks/suites" in paths
    assert (
        app.state.general_agent_benchmark_services.catalog.list()[0].case_count
        == 37
    )
    assert "/health" in paths
    assert not any(
        path.startswith("/api/agent-evaluations/general-agent")
        for path in paths
    )
