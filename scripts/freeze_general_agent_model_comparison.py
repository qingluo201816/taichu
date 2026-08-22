"""把同条件真实模型运行冻结为可复盘的多模型比较工件。"""

from __future__ import annotations

import argparse
from collections import Counter
from math import ceil
from pathlib import Path
from typing import Any

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.closure import (
    ModelEvidenceScope,
    ModelComparisonCandidateResult,
    ModelQualification,
    ModelComparisonRecord,
    ProviderExperimentState,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ComparisonAdmissionInput,
    ModelCandidateEvidence,
    evaluate_model_comparison_admission,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)

ROOT = Path("project_assets/derived/general_agent_benchmarks")
_DISPLAY_NAMES = {
    "gpt-5-6-luna": "GPT-5.6 Luna",
    "gpt-5-6-sol": "GPT-5.6 Sol",
    "gpt-5-6-terra": "GPT-5.6 Terra",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "claude-opus-4-6": "Claude Opus 4.6",
    "claude-opus-4-7": "Claude Opus 4.7",
    "claude-opus-4-8": "Claude Opus 4.8",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-sonnet-5": "Claude Sonnet 5",
}
_CATALOG_MODEL_IDS = frozenset(_DISPLAY_NAMES)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--candidate-run-id", action="append", default=[])
    parser.add_argument("--blocked-run-id", action="append", default=[])
    return parser.parse_args()


def _raw(repository: GeneralAgentBenchmarkArtifactRepository, run_id: str) -> dict[str, Any]:
    value = repository.read("iterations", run_id)
    if (
        value.get("schema")
        != "taichu.general_agent_benchmark.live-suite-raw@1"
        or canonical_sha256(
            {key: item for key, item in value.items() if key != "artifact_hash"}
        )
        != value.get("artifact_hash")
    ):
        raise ValueError(f"真实运行工件 schema 或哈希无效：{run_id}")
    return value


def _candidate_result(
    raw: dict[str, Any],
    *,
    eligible: bool,
    blocked_reason: str | None = None,
) -> tuple[ModelComparisonCandidateResult, ModelCandidateEvidence | None]:
    result = raw["suite_result"]
    audits = tuple(raw["provider_audits"].values())
    usage = tuple(
        record for audit in audits for record in audit["usage_records"]
    )
    replays = tuple(
        record for audit in audits for record in audit["replay_records"]
    )
    failures = tuple(
        record for audit in audits for record in audit["gateway_failures"]
    )
    cases = tuple(result["cases"])
    terminal_suite = (
        len(cases) == int(result["case_count"])
        and len({str(case["case_id"]) for case in cases}) == len(cases)
        and all(
            case["conclusion"] in {"passed", "failed"}
            for case in cases
        )
    )
    invocations = tuple(
        invocation for case in cases for invocation in case["invocations"]
    )
    completed_usage = tuple(
        record for record in usage if record["status"] == "completed"
    )
    requested_model_id = str(raw["requested_model_id"])
    candidate_id = requested_model_id.replace("-", "_")
    failure_counts: Counter[str] = Counter()
    gate_pass_counts: Counter[str] = Counter()
    failed_case_ids: list[str] = []
    for case in cases:
        if case["conclusion"] != "passed":
            failed_case_ids.append(case["case_id"])
        for gate in case["gates"]:
            failure_counts.update(gate["failure_categories"])
            if gate["status"] == "passed":
                gate_pass_counts[gate["gate_kind"]] += 1
    costs = [
        float(record["cost_amount"])
        for record in usage
        if record.get("cost_amount") is not None
    ]
    cost_kind_counts = Counter(
        str(record.get("cost_kind") or "unavailable") for record in usage
    )
    case_count = int(result["case_count"])
    passed_case_count = int(result["passed_case_count"])
    actual_provider_ids = {
        str(record["provider"]) for record in completed_usage
    }
    actual_model_ids = {
        str(record["model_id"]) for record in completed_usage
    }
    actual_provider_id = (
        next(iter(actual_provider_ids)) if len(actual_provider_ids) == 1 else None
    )
    actual_model_id = (
        next(iter(actual_model_ids)) if len(actual_model_ids) == 1 else None
    )
    cost_available = bool(completed_usage) and all(
        record.get("cost_amount") is not None
        and record.get("cost_kind") in {"actual", "estimated"}
        for record in completed_usage
    )
    durations = sorted(int(record.get("duration_ms") or 0) for record in usage)
    duration_count = len(durations)

    def percentile(ratio: float) -> int:
        if not durations:
            return 0
        index = min(duration_count - 1, max(0, ceil(duration_count * ratio) - 1))
        return durations[index]

    qualification = (
        ModelQualification.BLOCKED
        if not eligible
        else (
            ModelQualification.QUALIFIED
            if passed_case_count == case_count
            else (
                ModelQualification.PARTIAL
                if passed_case_count > 0
                else ModelQualification.FAILED
            )
        )
    )
    candidate = ModelComparisonCandidateResult(
        candidate_id=candidate_id,
        display_name=_DISPLAY_NAMES.get(requested_model_id, requested_model_id),
        run_id=str(raw["run_id"]),
        execution_state=(
            ProviderExperimentState.COMPLETED
            if eligible
            else ProviderExperimentState.BLOCKED
        ),
        evidence_scope=(
            ModelEvidenceScope.FULL_SUITE
            if eligible
            else ModelEvidenceScope.CAPABILITY_PROBE
        ),
        qualification=qualification,
        eligible_for_ranking=eligible,
        requested_provider_id=str(raw["requested_provider"]),
        requested_model_id=requested_model_id,
        actual_provider_id=actual_provider_id,
        actual_model_id=actual_model_id,
        fallback_used=any(
            record.get("fallback_from_provider") is not None for record in usage
        ),
        request_timeout_seconds=float(
            raw.get("provider_request_policy", {}).get(
                "request_timeout_seconds",
                0,
            )
        ),
        provider_max_retries=int(
            raw.get("provider_request_policy", {}).get(
                "provider_max_retries",
                0,
            )
        ),
        case_count=case_count,
        passed_case_count=passed_case_count,
        pass_rate=(passed_case_count / case_count if case_count else 0),
        model_call_attempts=len(usage),
        completed_model_calls=len(completed_usage),
        failed_model_calls=len(usage) - len(completed_usage),
        avg_model_call_attempts=(len(usage) / case_count if case_count else 0),
        capability_steps=len(invocations),
        avg_capability_steps=(len(invocations) / case_count if case_count else 0),
        tool_steps=sum(item["kind"] == "tool" for item in invocations),
        subagent_steps=sum(item["kind"] == "subagent" for item in invocations),
        input_tokens=sum(record.get("input_tokens") or 0 for record in usage),
        cached_input_tokens=sum(
            record.get("cached_input_tokens") or 0 for record in usage
        ),
        output_tokens=sum(record.get("output_tokens") or 0 for record in usage),
        reasoning_tokens=sum(
            record.get("reasoning_tokens") or 0 for record in usage
        ),
        total_tokens=sum(record.get("total_tokens") or 0 for record in usage),
        suite_elapsed_ms=int(raw.get("suite_elapsed_ms") or 0),
        total_duration_ms=sum(durations),
        avg_model_call_duration_ms=(
            sum(durations) / duration_count if duration_count else 0
        ),
        p50_model_call_duration_ms=percentile(0.50),
        p95_model_call_duration_ms=percentile(0.95),
        cost_amount=(sum(costs) if costs else None),
        cost_currency=(
            str(usage[0].get("cost_currency") or "CNY") if usage else "CNY"
        ),
        cost_kind_counts=dict(sorted(cost_kind_counts.items())),
        unavailable_cost_calls=cost_kind_counts["unavailable"],
        provider_error_count=len(failures),
        failed_case_ids=tuple(failed_case_ids),
        failure_category_counts=dict(sorted(failure_counts.items())),
        gate_pass_counts=dict(sorted(gate_pass_counts.items())),
        artifact_ref=f"iterations/{raw['run_id']}.json",
        artifact_hash=str(raw["artifact_hash"]),
        blocked_reason=blocked_reason,
    )
    if not eligible:
        return candidate, None
    evidence = ModelCandidateEvidence(
        candidate_id=candidate_id,
        requested_model_ref=requested_model_id,
        probe_succeeded=bool(completed_usage),
        actual_provider_id=actual_provider_id,
        actual_model_id=actual_model_id,
        fallback_used=candidate.fallback_used,
        replay_available=bool(replays),
        usage_available=bool(usage),
        cost_available=cost_available,
        error_code=(
            failures[-1]["error_code"]
            if failures and not terminal_suite
            else None
        ),
    )
    return candidate, evidence


def _identity(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"候选缺少可比较身份：{field}")
    return value


def _blocked_reason(raw: dict[str, Any]) -> str:
    error_codes = {
        str(failure.get("error_code") or "")
        for audit in raw["provider_audits"].values()
        for failure in audit["gateway_failures"]
    }
    if "LLM_REQUEST_REJECTED" in error_codes:
        return "提供商端点拒绝请求，请求未进入模型能力评测。"
    if error_codes & {"LLM_TIMEOUT", "LLM_CALL_FAILED"}:
        return "提供商调用超时或失败，请求未形成可用模型能力证据。"
    return "提供商接入探针失败，请求未形成可用模型能力证据。"


def main() -> None:
    arguments = _arguments()
    if len(arguments.candidate_run_id) < 2:
        raise ValueError("正式比较至少需要两个同条件候选。")
    repository = GeneralAgentBenchmarkArtifactRepository(ROOT)
    eligible_raw = [
        _raw(repository, run_id) for run_id in arguments.candidate_run_id
    ]
    identity_fields = (
        "code_hash",
        "capability_catalog_hash",
        "case_set_hash",
        "per_case_budgets_hash",
        "authorization_policy_hash",
        "decode_configuration_hash",
        "environment_hash",
    )
    expected_suite_hash = str(
        eligible_raw[0]["suite_result"]["suite_content_hash"]
    )
    for raw in eligible_raw:
        if (
            raw["suite_result"]["suite_content_hash"] != expected_suite_hash
            or raw["suite_result"]["case_count"] != 21
            or len(raw["suite_result"]["cases"]) != 21
            or any(
                case["conclusion"] not in {"passed", "failed"}
                for case in raw["suite_result"]["cases"]
            )
            or raw["fixture_snapshot_id"]
            != eligible_raw[0]["fixture_snapshot_id"]
            or any(
                _identity(raw, field) != _identity(eligible_raw[0], field)
                for field in identity_fields
            )
        ):
            raise ValueError("正式候选不是同任务、同环境、同预算或同代码运行。")
    candidates: list[ModelComparisonCandidateResult] = []
    evidences: list[ModelCandidateEvidence] = []
    for raw in eligible_raw:
        candidate, evidence = _candidate_result(raw, eligible=True)
        candidates.append(candidate)
        assert evidence is not None
        evidences.append(evidence)
    blocked_identity_fields = (
        "code_hash",
        "capability_catalog_hash",
        "authorization_policy_hash",
        "decode_configuration_hash",
        "environment_hash",
    )
    for run_id in arguments.blocked_run_id:
        blocked_raw = _raw(repository, run_id)
        if (
            blocked_raw["suite_result"]["suite_content_hash"]
            != expected_suite_hash
            or blocked_raw["fixture_snapshot_id"]
            != eligible_raw[0]["fixture_snapshot_id"]
            or any(
                _identity(blocked_raw, field)
                != _identity(eligible_raw[0], field)
                for field in blocked_identity_fields
            )
        ):
            raise ValueError("接入阻断探针不是同套件、同环境或同代码运行。")
        candidate, _ = _candidate_result(
            blocked_raw,
            eligible=False,
            blocked_reason=_blocked_reason(blocked_raw),
        )
        if (
            candidate.case_count != 1
            or candidate.completed_model_calls != 0
            or candidate.provider_error_count == 0
        ):
            raise ValueError(
                "阻断候选必须来自单案例能力探针，且没有成功模型调用并保留提供商错误。"
            )
        candidates.append(candidate)
    candidate_model_ids = [item.requested_model_id for item in candidates]
    if (
        len(candidate_model_ids) != len(set(candidate_model_ids))
        or set(candidate_model_ids) != _CATALOG_MODEL_IDS
    ):
        missing = sorted(_CATALOG_MODEL_IDS - set(candidate_model_ids))
        extra = sorted(set(candidate_model_ids) - _CATALOG_MODEL_IDS)
        raise ValueError(
            "比较工件必须逐项覆盖完整模型目录；"
            f"缺失={missing or '无'}；额外={extra or '无'}。"
        )
    ranked = sorted(
        (item for item in candidates if item.eligible_for_ranking),
        key=lambda item: (
            -item.pass_rate,
            item.provider_error_count,
            item.avg_model_call_attempts,
            item.candidate_id,
        ),
    )
    evidence_by_id = {item.candidate_id: item for item in evidences}
    admission = evaluate_model_comparison_admission(
        ComparisonAdmissionInput(
            iteration_state="ready_for_comparison",
            code_hash=_identity(eligible_raw[0], "code_hash"),
            suite_hash=expected_suite_hash,
            fixture_hash=str(eligible_raw[0]["fixture_snapshot_id"]).removeprefix(
                "fixture_"
            ),
            case_set_hash=_identity(eligible_raw[0], "case_set_hash"),
            per_case_budgets_hash=_identity(
                eligible_raw[0], "per_case_budgets_hash"
            ),
            capability_catalog_hash=_identity(
                eligible_raw[0], "capability_catalog_hash"
            ),
            authorization_policy_hash=_identity(
                eligible_raw[0], "authorization_policy_hash"
            ),
            decode_configuration_hash=_identity(
                eligible_raw[0], "decode_configuration_hash"
            ),
            environment_hash=_identity(eligible_raw[0], "environment_hash"),
            all_system_defects_processed=True,
            symmetry_gates_passed=True,
            benchmark_verifier_defects_closed=True,
            core_gates_passed=True,
            candidates=tuple(
                evidence_by_id[item.candidate_id] for item in ranked
            ),
        )
    )
    if not admission.admitted:
        raise ValueError("正式比较未通过准入：" + "；".join(admission.blocked_reasons))
    live_index = repository.read("indexes", "deepseek-first-live")
    first_live_artifact_ref = str(live_index["artifact_id"])
    payload = {
        "comparison_id": arguments.comparison_id,
        "admitted": True,
        "first_live_artifact_ref": first_live_artifact_ref,
        "admission": admission.model_dump(mode="json"),
        "closure_ids": (),
        "blocked_reasons": (),
        "ranking_candidate_ids": tuple(item.candidate_id for item in ranked),
        "ranking_basis": (
            "任务通过率降序",
            "提供商错误次数升序",
            "平均模型调用次数升序",
        ),
        "candidate_results": tuple(
            item.model_dump(mode="json")
            for item in sorted(
                candidates,
                key=lambda item: (
                    not item.eligible_for_ranking,
                    tuple(x.candidate_id for x in ranked).index(item.candidate_id)
                    if item.eligible_for_ranking
                    else 999,
                ),
            )
        ),
        "catalog_model_count": len(_CATALOG_MODEL_IDS),
        "covered_model_count": len(candidates),
        "full_suite_model_count": len(ranked),
        "blocked_model_count": sum(
            item.qualification is ModelQualification.BLOCKED
            for item in candidates
        ),
    }
    record = ModelComparisonRecord(
        **payload,
        record_hash=canonical_sha256(payload),
    )
    envelope = {
        "schema": "taichu.general_agent_benchmark.model-comparison@1",
        **record.model_dump(mode="json"),
    }
    repository.append_immutable(
        collection="comparisons",
        object_id=record.comparison_id,
        payload=envelope,
    )
    repository.replace_index(
        "model-comparison-latest",
        {
            "schema": (
                "taichu.general_agent_benchmark.model-comparison-index@1"
            ),
            "comparison_ref": f"comparisons/{record.comparison_id}.json",
            "record_hash": record.record_hash,
        },
    )
    print(
        f"多模型比较已冻结：{record.comparison_id}；"
        f"有效候选 {len(ranked)} 个；记录哈希 {record.record_hash}",
        flush=True,
    )


if __name__ == "__main__":
    main()
