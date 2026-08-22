"""需求 16.1、16.2、16.3：冻结评测查询工件的只读恢复。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from collections.abc import Coroutine
from pathlib import Path
from typing import TypeVar

import httpx
import pytest
from fastapi import FastAPI

from taichu.api.routes.general_agent_benchmarks import router
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.container import (
    build_general_agent_benchmark_services,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ArtifactIdentity,
    CaseContractIdentity,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueCorrelationRepository,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    InMemorySuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    EvidenceBundle,
    EvidenceBundleIdentity,
    ProviderExecutionState,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
    SuiteRunLifecycle,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_hydration import (
    load_frozen_benchmark_query_snapshot,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)

_ResultT = TypeVar("_ResultT")
_PROJECT_ROOT = Path(__file__).parents[4]
_SOURCE_ROOT = (
    _PROJECT_ROOT
    / "project_assets"
    / "derived"
    / "general_agent_benchmarks"
)
_SUITE_PATH = (
    _PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "evaluations"
    / "general_writing_agent_benchmark"
    / "suite.json"
)
_FROZEN_REFS = (
    "iterations/deepseek_v4_pro_catalog_audited_20260728.json",
    "iterations/deepseek_v4_pro_catalog_audited_20260728_completed.json",
    "iterations/deepseek_v4_pro_catalog_audited_20260728_classification.json",
)
_INDEX_REFS = (
    "indexes/synthetic-passed-baseline.json",
    "indexes/deepseek-first-live.json",
    "indexes/deepseek-first-live-classification.json",
)


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


async def _execute_case(run: SuiteRun, case_id: str) -> str:
    return f"row:{run.run_id}:{case_id}"


async def _finalize(run: SuiteRun) -> tuple[SuiteConclusion, str]:
    return SuiteConclusion.PASSED, f"artifact:{run.run_id}"


def _copy_authoritative_snapshot(target: Path) -> dict[str, str]:
    baseline_index = json.loads(
        (_SOURCE_ROOT / "indexes/synthetic-passed-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    baseline_ref = str(baseline_index["baseline_ref"])
    hashes: dict[str, str] = {}
    for relative in (baseline_ref, *_FROZEN_REFS, *_INDEX_REFS):
        source = _SOURCE_ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        hashes[relative] = hashlib.sha256(destination.read_bytes()).hexdigest()
    return hashes


def _indexed_baseline_path(root: Path) -> Path:
    index = json.loads(
        (root / "indexes/synthetic-passed-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    return root / str(index["baseline_ref"])


def _write_current_37_baseline(root: Path) -> tuple[str, str]:
    """只为 Hydration 测试构造完整 @2 工件，不借用当前身份补历史。"""

    historical = load_frozen_benchmark_query_snapshot(
        GeneralAgentBenchmarkArtifactRepository(root)
    ).synthetic_entries[0]
    assert historical.suite_artifact is not None
    template_row = historical.suite_artifact.case_rows[0]
    template_bundle = historical.suite_artifact.evidence_bundles[0]
    suite_payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    cases = suite_payload["cases"]
    selected_case_ids = tuple(str(case["case_id"]) for case in cases)
    assert len(selected_case_ids) == 37
    run_id = "benchmark_run_20260731T000000Z_abcdef123456"
    fixture_snapshot_id = str(suite_payload["fixture"]["snapshot_id"])
    rows = []
    bundles = []
    for case_id in selected_case_ids:
        case_execution_id = (
            "benchmark_case_"
            + canonical_sha256({"run_id": run_id, "case_id": case_id})[:32]
        )
        bundle_payload = {
            "suite_id": template_row.suite_id,
            "case_id": case_id,
            "run_id": run_id,
            "case_execution_id": case_execution_id,
            "track": "synthetic",
            "fixture_snapshot_id": fixture_snapshot_id,
            "details": template_bundle.details,
            "source_ref": "hydration-test",
        }
        bundle_hash = canonical_sha256(bundle_payload)
        bundle_id = f"evidence_{bundle_hash}"
        bundles.append(
            EvidenceBundle(
                identity=EvidenceBundleIdentity(
                    bundle_id=bundle_id,
                    bundle_hash=bundle_hash,
                    suite_id=template_row.suite_id,
                    case_id=case_id,
                    run_id=run_id,
                    case_execution_id=case_execution_id,
                    track="synthetic",
                    fixture_snapshot_id=fixture_snapshot_id,
                ),
                availability=template_bundle.availability,
                problems=(),
                details=template_bundle.details,
            )
        )
        rows.append(
            template_row.model_copy(
                update={
                    "case_id": case_id,
                    "case_execution_id": case_execution_id,
                    "evidence_bundle_id": bundle_id,
                }
            )
        )
    artifact_content = {
        "artifact_id": "synthetic_detail_current_37",
        "run_id": run_id,
        "conclusion": SuiteConclusion.PASSED,
        "case_rows": tuple(rows),
        "evidence_bundles": tuple(bundles),
        "provider_state": ProviderExecutionState.NOT_APPLICABLE,
    }
    artifact = SuiteArtifact(
        **artifact_content,
        artifact_hash=canonical_sha256(artifact_content),
    )
    current_ref = "runs/synthetic_baseline_current_37.json"
    run = SuiteRun(
        run_id=run_id,
        revision=37,
        lifecycle=SuiteRunLifecycle.COMPLETED,
        conclusion=SuiteConclusion.PASSED,
        suite_content_hash=str(suite_payload["content_hash"]),
        selected_case_ids=selected_case_ids,
        track="synthetic",
        provider_state=ProviderExecutionState.NOT_APPLICABLE,
        case_row_refs=tuple(
            f"{artifact.artifact_id}#/case_rows/{index}"
            for index in range(37)
        ),
        pending_case_ids=(),
        terminal_artifact_ref=artifact.artifact_id,
    )
    contracts = tuple(
        CaseContractIdentity(
            case_id=str(case["case_id"]),
            contract_hash=canonical_sha256(case),
        )
        for case in cases
    )
    identity = ArtifactIdentity.create(
        selected_case_ids=selected_case_ids,
        case_contracts=contracts,
        artifact_schema=(
            "taichu.general_agent_benchmark.synthetic-baseline@2"
        ),
        artifact_kind="synthetic_baseline",
        artifact_ref=current_ref,
        artifact_content_hash=artifact.artifact_hash,
        suite_content_hash=run.suite_content_hash,
        track="synthetic",
        fixture_snapshot_hash=fixture_snapshot_id.removeprefix("fixture_"),
        capability_catalog_hash=str(
            suite_payload["capability_catalog_hash"]
        ),
        oracle_rule_set_hash="1" * 64,
        runtime_config_hash="2" * 64,
        runtime_code_snapshot_hash="3" * 64,
        runner_protocol_hash="4" * 64,
        synthetic_script_identity="5" * 64,
        synthetic_admission_passed=True,
        result_hash="6" * 64,
    )
    envelope_content = {
        "schema": "taichu.general_agent_benchmark.synthetic-baseline@2",
        "identity": identity.model_dump(mode="json"),
        "suite_run": run.model_dump(mode="json"),
        "suite_artifact": artifact.model_dump(mode="json"),
    }
    envelope = {
        **envelope_content,
        "manifest_hash": canonical_sha256(envelope_content),
    }
    repository = GeneralAgentBenchmarkArtifactRepository(root)
    repository.append_immutable(
        collection="runs",
        object_id="synthetic_baseline_current_37",
        payload=envelope,
    )
    historical_ref = str(
        repository.read("indexes", "synthetic-passed-baseline")[
            "baseline_ref"
        ]
    )
    catalog_content = {
        "schema": "taichu.general_agent_benchmark.baseline-catalog@2",
        "active_synthetic_ref": current_ref,
        "history_refs": [historical_ref],
    }
    repository.replace_index(
        "benchmark-baseline-catalog",
        {
            **catalog_content,
            "catalog_hash": canonical_sha256(catalog_content),
        },
    )
    return current_ref, historical_ref


def _services(root: Path):
    snapshot = load_frozen_benchmark_query_snapshot(
        GeneralAgentBenchmarkArtifactRepository(root)
    )
    services = build_general_agent_benchmark_services(
        catalog_entries=(
            BenchmarkCatalogEntry(
                suite_id="general_writing_agent_core",
                name="通用写作智能体固定基准",
                content_hash="136ce63f581b72b44713c0442089ded9757d5c45ea4d765648b26f47585401e3",
                case_count=23,
            ),
        ),
        suite_run_store=InMemorySuiteRunStore(),
        execute_case=_execute_case,
        finalize_suite=_finalize,
        issue_correlation_repository=IssueCorrelationRepository(),
        query_hydration=snapshot,
    )
    return snapshot, services


def test_fresh_services_restore_only_indexed_frozen_query_state_without_writes(
    tmp_path: Path,
) -> None:
    before = _copy_authoritative_snapshot(tmp_path)
    rogue = tmp_path / "runs" / "unindexed-history.json"
    rogue.write_text('{"must_not_be_loaded":true}', encoding="utf-8")

    snapshot, services = _services(tmp_path)

    async def scenario() -> None:
        runs = await services.queries.list_runs(page=1, page_size=20)
        assert runs.total == 1
        assert runs.items[0].lifecycle == "completed"
        assert runs.items[0].conclusion == "passed"
        assert runs.items[0].provider_state == "not_applicable"

    _run(scenario())
    assert snapshot.status == "partial"
    assert len(snapshot.synthetic_entries) == 1
    historical = snapshot.synthetic_entries[0]
    assert historical.lineage == "historical"
    assert historical.status == "hydrated_read_only_identity_incomplete"
    assert len(historical.identity.selected_case_ids) == 23
    assert historical.identity.oracle_rule_set_hash is None
    assert historical.identity.runtime_code_snapshot_hash is None
    assert historical.identity.runner_protocol_hash is None
    assert "oracle_rule_set_hash" in historical.missing_identity_fields
    assert snapshot.suite_artifact is not None
    suite_artifact = services.resources.get_artifact(
        snapshot.suite_artifact.run_id
    )
    assert suite_artifact.conclusion == "passed"
    assert len(suite_artifact.case_rows) == 23
    assert len(suite_artifact.evidence_bundles) == 23
    assert all(
        bundle.details is not None
        and bundle.details.gates
        and bundle.details.normalization_actions
        and any(gate.gate_kind == "budget" for gate in bundle.details.gates)
        for bundle in suite_artifact.evidence_bundles
    )
    assert len(services.first_live.list_iterations()) == 1
    iteration = services.first_live.list_iterations()[0]
    assert iteration.state == "ready_for_comparison"
    artifact = services.first_live.get_artifact(
        iteration.first_live_artifact_ref or ""
    )
    assert artifact.provider_state == "completed"
    assert artifact.complete is True
    assert artifact.error_code is None
    comparisons = services.model_comparisons.list()
    assert len(comparisons) == 1
    assert comparisons[0].admitted is False
    assert comparisons[0].ranking_candidate_ids == ()
    assert services.query_hydration.status == "partial"

    after = {
        relative: hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
        for relative in before
    }
    assert after == before

    async def api_scenario() -> None:
        app = FastAPI()
        app.state.general_agent_benchmark_services = services
        app.include_router(router)
        transport = httpx.ASGITransport(app=app)
        run_id = suite_artifact.run_id
        case_id = suite_artifact.case_rows[0].case_id
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            detail = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}"
            )
            cases = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}/cases",
                params={"page": 1, "page_size": 100},
            )
            artifact = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}/artifact"
            )
            evidence = await client.get(
                f"/api/general-agent-benchmarks/runs/{run_id}"
                f"/cases/{case_id}/evidence"
            )
            assert detail.status_code == 200
            assert cases.status_code == 200
            assert cases.json()["total"] == 23
            assert artifact.status_code == 200
            assert len(artifact.json()["artifact"]["case_rows"]) == 23
            evidence_payload = evidence.json()["evidence"]
            assert evidence_payload["details"]["gates"]
            assert evidence_payload["details"]["normalization_actions"]

    _run(api_scenario())


@pytest.mark.parametrize("failure_mode", ("missing", "corrupt"))
def test_missing_or_corrupt_live_index_keeps_historical_synthetic_queryable(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    index_path = tmp_path / "indexes" / "deepseek-first-live.json"
    if failure_mode == "missing":
        index_path.unlink()
    else:
        index_path.write_text(
            '{"iteration_ref":"../../任意历史.json"}',
            encoding="utf-8",
        )

    snapshot = load_frozen_benchmark_query_snapshot(
        GeneralAgentBenchmarkArtifactRepository(tmp_path)
    )

    assert snapshot.status == "partial"
    assert snapshot.problems
    assert snapshot.suite_run is not None
    assert snapshot.first_live_iteration is None
    assert snapshot.blocked_comparison is None

    services = build_general_agent_benchmark_services(
        catalog_entries=(),
        suite_run_store=InMemorySuiteRunStore(),
        execute_case=_execute_case,
        finalize_suite=_finalize,
        issue_correlation_repository=IssueCorrelationRepository(),
        query_hydration=snapshot,
    )
    app = FastAPI()
    app.state.general_agent_benchmark_services = services
    app.include_router(router)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            runs = await client.get("/api/general-agent-benchmarks/runs")
            iterations = await client.get(
                "/api/general-agent-benchmarks/iterations"
            )
            comparisons = await client.get(
                "/api/general-agent-benchmarks/comparisons"
            )
            assert runs.status_code == 200
            assert runs.json()["total"] == 1
            assert iterations.status_code == 200
            assert iterations.json()["total"] == 0
            assert comparisons.status_code == 200
            assert comparisons.json()["total"] == 0

    _run(scenario())


def test_validly_hashed_baseline_without_detail_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    baseline_path = _indexed_baseline_path(tmp_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["case_summaries"][0].pop("gates")
    baseline["artifact_hash"] = canonical_sha256(
        {
            key: value
            for key, value in baseline.items()
            if key != "artifact_hash"
        }
    )
    baseline_path.write_text(
        json.dumps(
            baseline,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "indexes" / "synthetic-passed-baseline.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["artifact_hash"] = baseline["artifact_hash"]
    index_path.write_text(
        json.dumps(
            index,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    snapshot, services = _services(tmp_path)

    assert snapshot.status == "partial"
    assert snapshot.suite_run is None
    assert snapshot.suite_artifact is None
    assert snapshot.first_live_iteration is not None

    async def scenario() -> None:
        app = FastAPI()
        app.state.general_agent_benchmark_services = services
        app.include_router(router)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/general-agent-benchmarks/runs"
            )
            assert response.status_code == 200
            assert response.json()["total"] == 0

    _run(scenario())


def test_current_37_and_historical_23_hydrate_independently_without_writes(
    tmp_path: Path,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    current_ref, historical_ref = _write_current_37_baseline(tmp_path)
    protected_refs = (
        current_ref,
        historical_ref,
        "indexes/benchmark-baseline-catalog.json",
        "indexes/synthetic-passed-baseline.json",
    )
    before = {
        ref: hashlib.sha256((tmp_path / ref).read_bytes()).hexdigest()
        for ref in protected_refs
    }

    snapshot = load_frozen_benchmark_query_snapshot(
        GeneralAgentBenchmarkArtifactRepository(tmp_path)
    )

    assert snapshot.status == "available"
    assert len(snapshot.synthetic_entries) == 2
    current, historical = snapshot.synthetic_entries
    assert current.lineage == "current"
    assert current.status == "hydrated"
    assert current.suite_run is not None
    assert current.suite_artifact is not None
    assert len(current.suite_run.selected_case_ids) == 37
    assert len(current.suite_artifact.case_rows) == 37
    assert historical.lineage == "historical"
    assert historical.status == "hydrated_read_only_identity_incomplete"
    assert historical.suite_run is not None
    assert historical.suite_artifact is not None
    assert len(historical.suite_run.selected_case_ids) == 23
    assert len(historical.suite_artifact.case_rows) == 23
    assert historical.identity.oracle_rule_set_hash is None
    assert historical.identity.runtime_code_snapshot_hash is None
    assert historical.identity.runner_protocol_hash is None
    assert snapshot.suite_run == current.suite_run
    assert snapshot.suite_artifact == current.suite_artifact
    after = {
        ref: hashlib.sha256((tmp_path / ref).read_bytes()).hexdigest()
        for ref in protected_refs
    }
    assert after == before


def test_invalid_current_identity_does_not_erase_readable_history(
    tmp_path: Path,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    current_ref, _historical_ref = _write_current_37_baseline(tmp_path)
    current_path = tmp_path / current_ref
    envelope = json.loads(current_path.read_text(encoding="utf-8"))
    envelope["identity"]["suite_content_hash"] = "f" * 64
    envelope["manifest_hash"] = canonical_sha256(
        {
            key: value
            for key, value in envelope.items()
            if key != "manifest_hash"
        }
    )
    current_path.write_text(
        json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    snapshot = load_frozen_benchmark_query_snapshot(
        GeneralAgentBenchmarkArtifactRepository(tmp_path)
    )

    assert snapshot.status == "partial"
    assert len(snapshot.synthetic_entries) == 2
    current, historical = snapshot.synthetic_entries
    assert current.status == "unavailable_artifact_identity_mismatch"
    assert current.suite_run is None
    assert historical.status == "hydrated_read_only_identity_incomplete"
    assert historical.suite_run is not None
    assert len(historical.suite_run.selected_case_ids) == 23
    assert snapshot.suite_run == historical.suite_run


def test_historical_v1_cannot_be_promoted_by_current_identity_substitution(
    tmp_path: Path,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path)
    historical_ref = str(
        repository.read("indexes", "synthetic-passed-baseline")[
            "baseline_ref"
        ]
    )
    catalog_content = {
        "schema": "taichu.general_agent_benchmark.baseline-catalog@2",
        "active_synthetic_ref": historical_ref,
        "history_refs": [historical_ref.replace(".json", "_copy.json")],
    }
    original = json.loads((tmp_path / historical_ref).read_text(encoding="utf-8"))
    copy_ref = str(catalog_content["history_refs"][0])
    repository.append_immutable(
        collection="runs",
        object_id=Path(copy_ref).stem,
        payload=original,
    )
    repository.replace_index(
        "benchmark-baseline-catalog",
        {
            **catalog_content,
            "catalog_hash": canonical_sha256(catalog_content),
        },
    )

    snapshot = load_frozen_benchmark_query_snapshot(repository)

    assert snapshot.status == "partial"
    current, historical = snapshot.synthetic_entries
    assert (
        current.status
        == "unavailable_identity_substitution_forbidden"
    )
    assert current.identity.oracle_rule_set_hash is None
    assert current.suite_run is None
    assert historical.status == "hydrated_read_only_identity_incomplete"
    assert historical.suite_run is not None
    assert len(historical.suite_run.selected_case_ids) == 23


def test_superseded_v2_baseline_remains_readable_as_complete_history(
    tmp_path: Path,
) -> None:
    _copy_authoritative_snapshot(tmp_path)
    previous_ref, historical_v1_ref = _write_current_37_baseline(tmp_path)
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path)
    next_ref = "runs/synthetic_baseline_next_37.json"
    next_envelope = repository.read("runs", Path(previous_ref).stem)
    next_envelope["identity"]["artifact_ref"] = next_ref
    next_envelope["manifest_hash"] = canonical_sha256(
        {
            key: value
            for key, value in next_envelope.items()
            if key != "manifest_hash"
        }
    )
    repository.append_immutable(
        collection="runs",
        object_id=Path(next_ref).stem,
        payload=next_envelope,
    )
    catalog_content = {
        "schema": "taichu.general_agent_benchmark.baseline-catalog@2",
        "active_synthetic_ref": next_ref,
        "history_refs": [previous_ref, historical_v1_ref],
    }
    repository.replace_index(
        "benchmark-baseline-catalog",
        {
            **catalog_content,
            "catalog_hash": canonical_sha256(catalog_content),
        },
    )

    snapshot = load_frozen_benchmark_query_snapshot(repository)

    assert snapshot.status == "available"
    assert tuple(
        (entry.lineage, entry.status, len(entry.suite_run.selected_case_ids))
        for entry in snapshot.synthetic_entries
        if entry.suite_run is not None
    ) == (
        ("current", "hydrated", 37),
        ("historical", "hydrated", 37),
        ("historical", "hydrated_read_only_identity_incomplete", 23),
    )
