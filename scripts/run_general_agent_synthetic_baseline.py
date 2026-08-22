"""运行并冻结通用写作智能体的确定性 synthetic 基线。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path

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
    FinalClaimsAssertionSpec,
    load_authored_suite,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticSuiteRunner,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.code_snapshot import (
    benchmark_code_snapshot_hash,
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

SUITE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
)
FIXTURE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel"
)
FIXTURE_MANIFEST_PATH = FIXTURE_PATH / "fixture-manifest.json"
CLAIM_CATALOG_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/claim-catalog.json"
)
ARTIFACT_ROOT = Path("project_assets/derived/general_agent_benchmarks")


async def _run() -> dict[str, object]:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        SUITE_PATH,
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    fixture_manifest = json.loads(FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
    claim_catalog = load_claim_catalog(
        CLAIM_CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(
            item["asset_id"] for item in fixture_manifest["scenario_assets"]
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
    code_snapshot_hash = benchmark_code_snapshot_hash()
    runtime_config_identity = canonical_sha256(
        {
            "track": "synthetic",
            "rule_set_id": "strict_core",
            "gateway_identity": "synthetic",
            "suite_hash": suite.content_hash,
            "code_hash": code_snapshot_hash,
        }
    )
    run_id = datetime.now(UTC).strftime("synthetic_%Y%m%dT%H%M%SZ")
    results = []
    for iteration in ("first", "second"):
        runner = SyntheticSuiteRunner(
            runtime=SyntheticFixtureRuntime(
                sealed_fixture_root=FIXTURE_PATH,
                workspaces_root=(
                    ARTIFACT_ROOT
                    / "synthetic-workspaces"
                    / run_id
                    / iteration
                ),
            ),
            runtime_config_identity=runtime_config_identity,
            capability_catalog=catalog,
            oracle=TypedOracle(catalog=claim_catalog),
        )
        results.append(await runner.run(suite))
    result, repeated_result = results
    repository = GeneralAgentBenchmarkArtifactRepository(ARTIFACT_ROOT)
    return SyntheticBaselineFreezer(repository).freeze(
        result,
        repeated_result=repeated_result,
        suite=suite,
        capability_catalog_hash=catalog.canonical_hash,
        oracle_rule_set_hash=OracleRuleSetIdentity.create(
            catalog=claim_catalog,
            registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        ).oracle_rule_set_sha256,
        runtime_code_snapshot_hash=code_snapshot_hash,
        runner_protocol_hash=canonical_sha256(
            {
                "schema": (
                    "taichu.general_agent_benchmark."
                    "synthetic-runner-protocol@2"
                ),
                "selection": "synthetic_complete",
                "stability_runs": 2,
                "gate_kinds": (
                    "budget",
                    "verifier",
                    "artifact",
                    "stop_reason",
                    "security",
                    "evidence",
                ),
            }
        ),
    )


def main() -> None:
    artifact = asyncio.run(_run())
    print(
        "确定性基线已冻结："
        f"{artifact['counts']['passed']}/{artifact['counts']['total']} 通过；"
        f"工件 {artifact['identity']['artifact_ref']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
