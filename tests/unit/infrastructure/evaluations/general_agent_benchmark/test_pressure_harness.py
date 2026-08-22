"""任务 7.1：正式 Synthetic 环境接通 30—37 的压力投影。"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    FixtureManifestV2Spec,
    PressurePlanAssetSpec,
    load_authored_suite,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.pressure_harness import (
    SyntheticPressureHarness,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)


_FIXTURE_MANIFEST = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/"
    "fixtures/core_novel/fixture-manifest.json"
)
_SUITE = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
)


def test_all_sealed_pressure_assets_produce_typed_oracle_context(
    tmp_path: Path,
) -> None:
    async def scenario() -> dict[str, object]:
        manifest = FixtureManifestV2Spec.model_validate(
            json.loads(_FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        )
        assets = tuple(
            item
            for item in manifest.scenario_assets
            if isinstance(item, PressurePlanAssetSpec)
        )
        suite = load_authored_suite(
            _SUITE,
            expected_capability_catalog_hash=(
                production_capability_catalog_snapshot().canonical_hash
            ),
        )
        current_request_by_pressure_ref = {
            case.setup.pressure_plan_ref: case.user_request_raw
            for case in suite.cases
            if case.setup.pressure_plan_ref is not None
        }
        results = {}
        for asset in assets:
            results[asset.asset_id] = await SyntheticPressureHarness(
                workspace=tmp_path
            ).execute(
                asset=asset,
                memory_seed_ref="memory_seed_runtime_default",
                current_request=current_request_by_pressure_ref[asset.asset_id],
            )
        return results

    results = asyncio.run(scenario())

    assert tuple(sorted(results)) == (
        "pressure_equivalence",
        "pressure_invalid_memory",
        "pressure_large_node_output",
        "pressure_long_current_request",
        "pressure_long_history",
        "pressure_long_working_memory",
        "pressure_multi_source",
        "pressure_unsafe_compression",
    )
    for pressure_ref, result in results.items():
        context = result.assertion_context
        if pressure_ref == "pressure_equivalence":
            assert len(context.result_contract_equivalences) == 1
        elif pressure_ref == "pressure_invalid_memory":
            assert len(context.context_preservation) == 1
            assert context.memory_carriers
            assert all(item.occurrence_count == 0 for item in context.memory_carriers)
        else:
            assert len(context.context_preservation) == 1
        if result.behavior is not None:
            assert result.behavior.status == "completed"
        else:
            assert result.unsafe_refusal is not None
            assert result.unsafe_refusal.run_status == "safe_failure"
            assert result.unsafe_refusal.capability_call_count == 0
            assert result.unsafe_refusal.effect_count == 0


def test_pressure_dispatch_is_carrier_driven_not_case_id() -> None:
    assert "case_id" not in inspect.signature(
        SyntheticPressureHarness.execute
    ).parameters
