"""需求 15.4、15.5、15.12：区分 provider、benchmark 与系统缺陷。"""

from taichu.application.evaluations.general_agent_benchmark.failure_triage import (
    FailureOrigin,
    FailureTriageRecord,
    select_system_defects,
    triage_provider_error,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    FailureCategory,
)


def test_provider_network_error_is_execution_error_but_not_system_defect() -> None:
    record = triage_provider_error(
        failure_id="deepseek_probe_network_error",
        evidence_refs=(
            "iterations/deepseek_v4_pro_20260727_bounded3_probe.json",
        ),
    )

    assert record.primary is FailureCategory.EXECUTION_ERROR
    assert record.origin is FailureOrigin.PROVIDER_ENVIRONMENT
    assert record.benchmark_invalid is False
    assert record.system_issue_eligible is False
    assert select_system_defects((record,)) == ()


def test_only_explicit_system_defect_is_eligible_for_inbox() -> None:
    benchmark = FailureTriageRecord(
        failure_id="broken_fixture",
        primary=FailureCategory.BENCHMARK_INVALID,
        origin=FailureOrigin.BENCHMARK,
        benchmark_invalid=True,
        system_issue_eligible=False,
        evidence_refs=("suite:broken",),
        next_action="修复评测基准。",
    )
    system = FailureTriageRecord(
        failure_id="runtime_duplicate_write",
        primary=FailureCategory.EXECUTION_ERROR,
        origin=FailureOrigin.SYSTEM,
        benchmark_invalid=False,
        system_issue_eligible=True,
        evidence_refs=("runtime:duplicate",),
        next_action="为 Runtime 重复写入补回归测试并修复。",
    )

    assert select_system_defects((benchmark, system)) == (system,)
