"""需求 12.2-12.8、14.3-14.5：冻结 Synthetic 37 条准入基线。"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    OracleRuleSetIdentity,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
    FinalClaimsAssertionSpec,
    load_authored_suite,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticSuiteBaselineResult,
    SyntheticSuiteRunner,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_hydration import (
    load_frozen_benchmark_query_snapshot,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_baseline import (
    SyntheticBaselineFreezer,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)

_PROJECT_ROOT = Path(__file__).parents[4]
_FIXTURE_ROOT = (
    _PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "evaluations"
    / "general_writing_agent_benchmark"
)
_SUITE_PATH = _FIXTURE_ROOT / "suite.json"
_SEALED_FIXTURE = _FIXTURE_ROOT / "fixtures" / "core_novel"
_HISTORICAL_ROOT = (
    _PROJECT_ROOT
    / "project_assets"
    / "derived"
    / "general_agent_benchmarks"
)


@pytest.fixture(scope="module")
def stable_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[
    AuthoredSuiteSpec,
    SyntheticSuiteBaselineResult,
    SyntheticSuiteBaselineResult,
    str,
    str,
]:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    manifest = json.loads(
        (_SEALED_FIXTURE / "fixture-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    claim_catalog = load_claim_catalog(
        _FIXTURE_ROOT / "claim-catalog.json",
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=tuple(
            item["asset_id"] for item in manifest["scenario_assets"]
        ),
        referenced_claim_ids=tuple(
            dict.fromkeys(
                claim_id
                for case in suite.cases
                for assertion in case.behavior_assertions
                if isinstance(assertion, FinalClaimsAssertionSpec)
                for claim_id in (
                    *assertion.required_claim_refs,
                    *assertion.forbidden_claim_refs,
                )
            )
        ),
    )
    runtime_config_hash = canonical_sha256(
        {
            "track": "synthetic",
            "suite_hash": suite.content_hash,
            "test_protocol": "freeze@2",
        }
    )
    workspace_root = tmp_path_factory.mktemp("synthetic-freeze")

    async def execute_twice() -> tuple[
        SyntheticSuiteBaselineResult,
        SyntheticSuiteBaselineResult,
    ]:
        results = []
        for name in ("first", "second"):
            runner = SyntheticSuiteRunner(
                runtime=SyntheticFixtureRuntime(
                    sealed_fixture_root=_SEALED_FIXTURE,
                    workspaces_root=workspace_root / name,
                ),
                runtime_config_identity=runtime_config_hash,
                capability_catalog=catalog,
                oracle=TypedOracle(catalog=claim_catalog),
            )
            results.append(await runner.run(suite))
        return results[0], results[1]

    first, second = asyncio.run(execute_twice())
    oracle_hash = OracleRuleSetIdentity.create(
        catalog=claim_catalog,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ).oracle_rule_set_sha256
    return suite, first, second, catalog.canonical_hash, oracle_hash


def _freeze(
    repository: GeneralAgentBenchmarkArtifactRepository,
    inputs: tuple[
        AuthoredSuiteSpec,
        SyntheticSuiteBaselineResult,
        SyntheticSuiteBaselineResult,
        str,
        str,
    ],
    *,
    result: SyntheticSuiteBaselineResult | None = None,
    repeated: SyntheticSuiteBaselineResult | None = None,
) -> dict[str, object]:
    suite, first, second, catalog_hash, oracle_hash = inputs
    return SyntheticBaselineFreezer(repository).freeze(
        result or first,
        repeated_result=repeated or second,
        suite=suite,
        capability_catalog_hash=catalog_hash,
        oracle_rule_set_hash=oracle_hash,
        runtime_code_snapshot_hash="3" * 64,
        runner_protocol_hash="4" * 64,
    )


def _copy_historical_23(root: Path) -> tuple[str, bytes]:
    index_source = (
        _HISTORICAL_ROOT / "indexes" / "synthetic-passed-baseline.json"
    )
    index = json.loads(index_source.read_text(encoding="utf-8"))
    historical_ref = str(index["baseline_ref"])
    for relative in (
        "indexes/synthetic-passed-baseline.json",
        historical_ref,
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_HISTORICAL_ROOT / relative, target)
    return historical_ref, (root / historical_ref).read_bytes()


def test_complete_stable_37_freezes_and_preserves_historical_23(
    tmp_path: Path,
    stable_inputs: tuple[
        AuthoredSuiteSpec,
        SyntheticSuiteBaselineResult,
        SyntheticSuiteBaselineResult,
        str,
        str,
    ],
) -> None:
    historical_ref, historical_before = _copy_historical_23(tmp_path)
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path)

    frozen = _freeze(repository, stable_inputs)
    suite, first, second, _catalog_hash, _oracle_hash = stable_inputs
    replay = _freeze(
        repository,
        stable_inputs,
        result=second,
        repeated=first,
    )

    assert replay == frozen
    assert frozen["schema"] == (
        "taichu.general_agent_benchmark.synthetic-baseline@2"
    )
    assert frozen["counts"]["total"] == 37
    assert frozen["counts"]["passed"] == 37
    assert len(frozen["suite_run"]["selected_case_ids"]) == 37
    assert len(frozen["suite_artifact"]["case_rows"]) == 37
    assert len(frozen["suite_artifact"]["evidence_bundles"]) == 37
    assert frozen["identity"]["synthetic_admission_passed"] is True
    assert frozen["identity"]["case_contracts"] == [
        {
            "case_id": case.case_id,
            "contract_hash": canonical_sha256(case),
        }
        for case in suite.cases
    ]
    catalog = repository.read("indexes", "benchmark-baseline-catalog")
    assert catalog["active_synthetic_ref"] == frozen["identity"]["artifact_ref"]
    assert catalog["history_refs"] == [historical_ref]
    assert (tmp_path / historical_ref).read_bytes() == historical_before

    snapshot = load_frozen_benchmark_query_snapshot(repository)
    assert tuple(
        len(entry.suite_run.selected_case_ids)
        for entry in snapshot.synthetic_entries
        if entry.suite_run is not None
    ) == (37, 23)


def test_partial_missing_gate_or_drift_cannot_change_active_catalog(
    tmp_path: Path,
    stable_inputs: tuple[
        AuthoredSuiteSpec,
        SyntheticSuiteBaselineResult,
        SyntheticSuiteBaselineResult,
        str,
        str,
    ],
) -> None:
    _copy_historical_23(tmp_path)
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path)
    frozen = _freeze(repository, stable_inputs)
    catalog_before = repository.read("indexes", "benchmark-baseline-catalog")
    _suite, first, second, _catalog_hash, _oracle_hash = stable_inputs

    partial = first.model_copy(
        update={
            "cases": first.cases[:-1],
            "case_count": 36,
            "passed_case_count": 36,
            "complete": False,
        }
    )
    with pytest.raises(ValueError, match="37/37"):
        _freeze(repository, stable_inputs, result=partial)

    missing_gate_case = first.cases[0].model_copy(
        update={"gates": first.cases[0].gates[:-1]}
    )
    missing_gate = first.model_copy(
        update={"cases": (missing_gate_case, *first.cases[1:])}
    )
    with pytest.raises(ValueError, match="门禁种类"):
        _freeze(repository, stable_inputs, result=missing_gate)

    drift_case = second.cases[0].model_copy(
        update={"evidence_ids": (*second.cases[0].evidence_ids, "drift_ref")}
    )
    drift = second.model_copy(
        update={
            "cases": (drift_case, *second.cases[1:]),
            "stable_result_hash": "f" * 64,
        }
    )
    with pytest.raises(ValueError, match="漂移"):
        _freeze(repository, stable_inputs, repeated=drift)

    assert repository.read("indexes", "benchmark-baseline-catalog") == (
        catalog_before
    )
    assert catalog_before["active_synthetic_ref"] == (
        frozen["identity"]["artifact_ref"]
    )


def test_catalog_validation_failure_keeps_previous_pointer(
    tmp_path: Path,
    stable_inputs: tuple[
        AuthoredSuiteSpec,
        SyntheticSuiteBaselineResult,
        SyntheticSuiteBaselineResult,
        str,
        str,
    ],
) -> None:
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path)
    previous_catalog = {
        "schema": "taichu.general_agent_benchmark.baseline-catalog@2",
        "active_synthetic_ref": "runs/previous_current.json",
        "history_refs": [],
        "catalog_hash": "0" * 64,
    }
    repository.replace_index(
        "benchmark-baseline-catalog",
        previous_catalog,
    )

    with pytest.raises(ValueError, match="目录内容哈希"):
        _freeze(repository, stable_inputs)

    assert repository.read(
        "indexes",
        "benchmark-baseline-catalog",
    ) == previous_catalog
