"""按显式模型运行通用写作智能体真实固定任务集。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import locale
from pathlib import Path
import platform
import sys
from time import perf_counter

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_authored_suite,
)
from taichu.config import Settings
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.code_snapshot import (
    benchmark_code_snapshot_hash,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.live_runtime import (
    LiveFixtureRuntime,
    LiveSuiteRunner,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)


SUITE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
)
FIXTURE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel"
)
ARTIFACT_ROOT = Path(
    "project_assets/derived/general_agent_benchmarks"
)
EVALUATION_REQUEST_TIMEOUT_SECONDS = 120
EVALUATION_PROVIDER_MAX_RETRIES = 0


def _code_hash() -> str:
    return benchmark_code_snapshot_hash()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id",
        default=datetime.now(UTC).strftime(
            "deepseek_first_live_%Y%m%dT%H%M%SZ"
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="仅运行指定案例；可重复传入，未指定时运行完整固定任务集。",
    )
    parser.add_argument(
        "--model-id",
        default="deepseek-v4-pro",
        help="显式指定真实评测模型；始终禁止回退。",
    )
    return parser.parse_args()


async def _run(
    run_id: str,
    case_ids: tuple[str, ...] = (),
    model_id: str = "deepseek-v4-pro",
) -> dict[str, object]:
    code_hash = _code_hash()
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        SUITE_PATH,
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    live_cases = tuple(
        case
        for case in suite.cases
        if TrackKind.LIVE_PROVIDER in case.applicable_tracks
    )
    if case_ids:
        requested = frozenset(case_ids)
        selected_cases = tuple(
            case for case in live_cases if case.case_id in requested
        )
        missing = requested - {case.case_id for case in selected_cases}
        if missing:
            raise ValueError(
                "未知或不适用于 Live 轨道的案例："
                + "、".join(sorted(missing))
            )
    else:
        selected_cases = live_cases
    suite = suite.model_copy(
        update={
            "case_order": tuple(case.case_id for case in selected_cases),
            "cases": selected_cases,
        }
    )
    settings = Settings(
        deepseek_fallback_enabled=False,
        rightcode_default_model_id=model_id,
        rightcode_request_timeout_seconds=EVALUATION_REQUEST_TIMEOUT_SECONDS,
        rightcode_max_retries=EVALUATION_PROVIDER_MAX_RETRIES,
    )
    runtime_config_identity = canonical_sha256(
        {
            "track": "provider_live",
            "requested_provider": "rightcode",
            "requested_model_id": model_id,
            "fallback_allowed": False,
            "request_timeout_seconds": EVALUATION_REQUEST_TIMEOUT_SECONDS,
            "provider_max_retries": EVALUATION_PROVIDER_MAX_RETRIES,
            "responses_base_url": settings.rightcode_responses_base_url,
            "claude_base_url": settings.rightcode_claude_sale_base_url,
            "deepseek_base_url": settings.rightcode_deepseek_anthropic_base_url,
            "pricing_configuration_hash": canonical_sha256(
                settings.rightcode_model_prices_json
            ),
        }
    )
    live_track = next(
        track for track in suite.tracks if track.kind.value == "live_provider"
    )
    if model_id.replace("-", "_") not in live_track.allowed_model_refs:
        raise ValueError("请求模型不在固定任务集允许的 live 候选目录中。")
    decode_configuration_hash = canonical_sha256(
        live_track.decode_constraints.model_dump(mode="json")
    )
    per_case_budgets_hash = canonical_sha256(
        {
            case.case_id: case.budgets.model_dump(mode="json")
            for case in suite.cases
        }
    )
    authorization_policy_hash = canonical_sha256(
        {
            "fallback_allowed": False,
            "fixture_external_research_only": True,
            "runtime_write_authorization_required": True,
        }
    )
    environment_hash = canonical_sha256(
        {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": platform.system(),
            "timezone": "Asia/Shanghai",
            "locale": locale.getlocale(),
            "request_timeout_seconds": EVALUATION_REQUEST_TIMEOUT_SECONDS,
            "provider_max_retries": EVALUATION_PROVIDER_MAX_RETRIES,
        }
    )
    runtime = LiveFixtureRuntime(
        sealed_fixture_root=FIXTURE_PATH,
        workspaces_root=ARTIFACT_ROOT / "live-workspaces" / run_id,
        settings=settings,
        model_id=model_id,
    )
    runner = LiveSuiteRunner(
        runtime=runtime,
        runtime_config_identity=runtime_config_identity,
        capability_catalog=catalog,
    )

    def progress(
        position: int,
        total: int,
        case_id: str,
        state: str,
    ) -> None:
        label = "开始" if state == "started" else "结论"
        print(
            f"[{position:02d}/{total:02d}] {label}："
            f"{case_id if state == 'started' else state}",
            flush=True,
        )

    started_at = datetime.now(UTC)
    suite_timer = perf_counter()
    suite_result = await runner.run(suite, progress=progress)
    suite_elapsed_ms = max(0, round((perf_counter() - suite_timer) * 1000))
    finished_at = datetime.now(UTC)
    audits: dict[str, object] = {}
    for case in suite.cases:
        audit = runtime.case_audit(case.case_id)
        audits[case.case_id] = {
            "usage_records": [
                record.model_dump(mode="json")
                for record in audit.usage_records
            ],
            "replay_records": [
                record.model_dump(mode="json")
                for record in audit.replay_records
            ],
            "gateway_failures": [
                {
                    "task_name": failure.task_name,
                    "requested_model_id": failure.requested_model_id,
                    "error_type": failure.error_type,
                    "error_code": failure.error_code,
                    "status_code": failure.status_code,
                    "error_message": failure.error_message,
                }
                for failure in audit.gateway_failures
            ],
            "response_call_ids": list(audit.response_call_ids),
        }
    content = {
        "schema": "taichu.general_agent_benchmark.live-suite-raw@1",
        "run_id": run_id,
        "requested_provider": "rightcode",
        "requested_model_id": model_id,
        "fallback_allowed": False,
        "provider_request_policy": {
            "request_timeout_seconds": EVALUATION_REQUEST_TIMEOUT_SECONDS,
            "provider_max_retries": EVALUATION_PROVIDER_MAX_RETRIES,
        },
        "code_hash": code_hash,
        "fixture_snapshot_id": suite.fixture.snapshot_id,
        "capability_catalog_hash": catalog.canonical_hash,
        "case_set_hash": canonical_sha256(suite.case_order),
        "per_case_budgets_hash": per_case_budgets_hash,
        "authorization_policy_hash": authorization_policy_hash,
        "decode_configuration_hash": decode_configuration_hash,
        "environment_hash": environment_hash,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "suite_elapsed_ms": suite_elapsed_ms,
        "suite_result": suite_result.model_dump(mode="json"),
        "provider_audits": audits,
    }
    payload = {
        **content,
        "artifact_hash": canonical_sha256(content),
    }
    repository = GeneralAgentBenchmarkArtifactRepository(ARTIFACT_ROOT)
    return repository.append_immutable(
        collection="iterations",
        object_id=run_id,
        payload=payload,
    )


def main() -> None:
    arguments = _arguments()
    artifact = asyncio.run(
        _run(
            arguments.run_id,
            tuple(arguments.case_id),
            arguments.model_id,
        )
    )
    result = artifact["suite_result"]
    print(
        "真实模型运行完成："
        f"{result['passed_case_count']}/{result['case_count']} 通过；"
        f"工件哈希 {artifact['artifact_hash']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
