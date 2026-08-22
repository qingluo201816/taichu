"""把通过的真实套件原始工件冻结为页面只读首轮信封。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveIterationService,
    FirstLiveIterationState,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.code_snapshot import (
    benchmark_code_snapshot_hash,
)

ROOT = Path("project_assets/derived/general_agent_benchmarks")
SUITE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"工件必须是 JSON 对象：{path}")
    return value


def _code_hash() -> str:
    return benchmark_code_snapshot_hash()


def main() -> None:
    run_id = _arguments().run_id
    repository = GeneralAgentBenchmarkArtifactRepository(ROOT)
    raw = repository.read("iterations", run_id)
    if (
        raw.get("schema")
        != "taichu.general_agent_benchmark.live-suite-raw@1"
        or canonical_sha256(
            {key: value for key, value in raw.items() if key != "artifact_hash"}
        )
        != raw.get("artifact_hash")
    ):
        raise ValueError("真实套件原始工件 schema 或哈希无效。")
    result = raw.get("suite_result")
    audits = raw.get("provider_audits")
    if (
        not isinstance(result, dict)
        or result.get("complete") is not True
        or result.get("case_count") != 21
        or result.get("passed_case_count") != 21
        or not isinstance(audits, dict)
        or any(not isinstance(audit, dict) for audit in audits.values())
    ):
        raise ValueError("只有 Live 轨道完整 21/21 且无 Provider 错误的原始工件可以冻结。")
    usage_records = [
        record
        for audit in audits.values()
        for record in audit["usage_records"]
    ]
    replay_records = [
        record
        for audit in audits.values()
        for record in audit["replay_records"]
    ]
    completed_usage = [
        record for record in usage_records if record.get("status") == "completed"
    ]
    actual_provider_ids = {
        str(record["provider"]) for record in completed_usage
    }
    actual_model_ids = {
        str(record["model_id"]) for record in completed_usage
    }
    if len(actual_provider_ids) != 1 or len(actual_model_ids) != 1:
        raise ValueError("真实套件没有形成唯一的实际提供商与模型身份。")
    actual_provider_id = next(iter(actual_provider_ids))
    actual_model_id = next(iter(actual_model_ids))
    cost_available = bool(completed_usage) and all(
        record.get("cost_amount") is not None
        and record.get("cost_kind") in {"actual", "estimated"}
        for record in completed_usage
    )
    failure_record_refs = tuple(
        f"iterations/{run_id}.json#/provider_audits/{case_id}"
        f"/gateway_failures/{position}"
        for case_id, audit in audits.items()
        for position, _failure in enumerate(audit["gateway_failures"])
    )
    suite = _read(SUITE_PATH)
    raw_cases = result.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("真实套件结果缺少案例明细。")
    case_ids = tuple(
        str(case["case_id"])
        for case in raw_cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    )
    if len(case_ids) != 21 or len(set(case_ids)) != 21:
        raise ValueError("Live 冻结案例集必须精确为 21 条且不得重复。")
    fixture_snapshot = str(suite["fixture"]["snapshot_id"])  # type: ignore[index]
    if not fixture_snapshot.startswith("fixture_"):
        raise ValueError("夹具快照身份无效。")
    baseline_catalog = repository.read(
        "indexes",
        "benchmark-baseline-catalog",
    )
    if (
        baseline_catalog.get("schema")
        != "taichu.general_agent_benchmark.baseline-catalog@2"
        or canonical_sha256(
            {
                key: value
                for key, value in baseline_catalog.items()
                if key != "catalog_hash"
            }
        )
        != baseline_catalog.get("catalog_hash")
    ):
        raise ValueError("Live 冻结缺少有效的当前 Synthetic 基线目录。")
    synthetic_ref = str(baseline_catalog["active_synthetic_ref"])
    synthetic = _read(ROOT / synthetic_ref)
    synthetic_identity = synthetic.get("identity")
    synthetic_counts = synthetic.get("counts")
    if (
        synthetic.get("schema")
        != "taichu.general_agent_benchmark.synthetic-baseline@2"
        or not isinstance(synthetic_identity, dict)
        or synthetic_identity.get("synthetic_admission_passed") is not True
        or not isinstance(synthetic_counts, dict)
        or synthetic_counts.get("total") != 37
        or synthetic_counts.get("passed") != 37
    ):
        raise ValueError("Live 冻结只能由当前完整 37/37 Synthetic 基线取得资格。")
    service = FirstLiveIterationService()
    manifest = service.create_iteration(
        iteration_id=run_id,
        code_hash=_code_hash(),
        suite_hash=str(result["suite_content_hash"]),
        fixture_hash=fixture_snapshot.removeprefix("fixture_"),
        capability_catalog_hash=str(raw["capability_catalog_hash"]),
        selected_case_ids=case_ids,
        synthetic_qualification_artifact_refs=(synthetic_ref,),
        synthetic_suite_passed=True,
        core_gates_passed=True,
        memory_gates_passed=True,
        mechanism_gates_passed=True,
    )
    manifest = service.start(
        run_id,
        expected_revision=manifest.revision,
        requested_model_ref=str(raw["requested_model_id"]),
    )
    artifact, manifest = service.freeze(
        run_id,
        expected_revision=manifest.revision,
        provider_state=ProviderExecutionState.COMPLETED,
        completed_case_ids=case_ids,
        suite_artifact_ref=f"iterations/{run_id}.json",
        actual_provider_id=actual_provider_id,
        actual_model_id=actual_model_id,
        probe_succeeded=bool(completed_usage),
        fallback_used=any(
            record.get("fallback_from_provider") is not None
            for record in usage_records
        ),
        replay_available=bool(replay_records),
        usage_available=bool(usage_records),
        cost_available=cost_available,
        error_code=None,
        failure_record_refs=failure_record_refs,
    )
    manifest = manifest.model_copy(
        update={
            "revision": manifest.revision + 1,
            "state": FirstLiveIterationState.READY_FOR_COMPARISON,
        }
    )
    envelope = {
        "schema": "taichu.general_agent_benchmark.first-live-envelope@1",
        "iteration": manifest.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
        "case_states": [
            {
                "case_id": case_id,
                "state": "passed",
                "reason_code": None,
                "evidence_ref": f"iterations/{run_id}.json",
            }
            for case_id in case_ids
        ],
        "comparison_admission": "blocked",
        "suite_raw_ref": f"iterations/{run_id}.json",
    }
    envelope_id = f"{run_id}_completed"
    repository.append_immutable(
        collection="iterations",
        object_id=envelope_id,
        payload=envelope,
    )
    classification_content = {
        "schema": "taichu.general_agent_benchmark.first-live-classification@1",
        "provider_state": "completed",
        "first_live_artifact_ref": artifact.artifact_id,
        "first_live_artifact_hash": artifact.artifact_hash,
        "passed_case_count": len(case_ids),
        "failed_case_count": 0,
        "case_dispositions": [
            {"case_id": case_id, "disposition": "passed"}
            for case_id in case_ids
        ],
        "system_issue_candidates": [],
    }
    classification = {
        **classification_content,
        "classification_hash": canonical_sha256(classification_content),
    }
    classification_id = f"{run_id}_classification"
    repository.append_immutable(
        collection="iterations",
        object_id=classification_id,
        payload=classification,
    )
    repository.replace_index(
        "deepseek-first-live",
        {
            "provider_state": "completed",
            "comparison_admission": "blocked",
            "iteration_ref": f"iterations/{envelope_id}.json",
            "suite_raw_ref": f"iterations/{run_id}.json",
            "artifact_id": artifact.artifact_id,
            "artifact_hash": artifact.artifact_hash,
        },
    )
    repository.replace_index(
        "deepseek-first-live-classification",
        {
            "provider_state": "completed",
            "origin": "live_suite",
            "primary_category": "passed",
            "system_issue_candidate_count": 0,
            "classification_ref": f"iterations/{classification_id}.json",
            "classification_hash": classification["classification_hash"],
        },
    )
    print(
        f"首轮已冻结：{artifact.artifact_id}；原始工件 {raw['artifact_hash']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
