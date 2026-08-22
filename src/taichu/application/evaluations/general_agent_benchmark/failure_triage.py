"""首轮失败来源判定与系统问题候选筛选。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    FailureCategory,
    StableId,
)


class FailureOrigin(StrEnum):
    BENCHMARK = "benchmark"
    PROVIDER_ENVIRONMENT = "provider_environment"
    SYSTEM = "system"


class FailureTriageRecord(BenchmarkModel):
    failure_id: StableId
    primary: FailureCategory
    origin: FailureOrigin
    benchmark_invalid: bool
    system_issue_eligible: bool
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    next_action: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def _issue_eligibility_matches_origin(self) -> FailureTriageRecord:
        if self.system_issue_eligible and (
            self.origin is not FailureOrigin.SYSTEM
            or self.benchmark_invalid
        ):
            raise ValueError("只有非基准缺陷的真实系统问题可进入 Inbox。")
        if (
            self.origin is FailureOrigin.BENCHMARK
            and not self.benchmark_invalid
        ):
            raise ValueError("benchmark 来源必须标记 benchmark_invalid。")
        return self


def triage_provider_error(
    *,
    failure_id: str,
    evidence_refs: tuple[str, ...],
) -> FailureTriageRecord:
    return FailureTriageRecord(
        failure_id=failure_id,
        primary=FailureCategory.EXECUTION_ERROR,
        origin=FailureOrigin.PROVIDER_ENVIRONMENT,
        benchmark_invalid=False,
        system_issue_eligible=False,
        evidence_refs=evidence_refs,
        next_action="恢复提供商网络连通后重试同一 DeepSeek V4 Pro 首轮。",
    )


def select_system_defects(
    records: tuple[FailureTriageRecord, ...],
) -> tuple[FailureTriageRecord, ...]:
    """只返回有明确证据且被分类为真实系统缺陷的记录。"""
    return tuple(
        record
        for record in records
        if record.system_issue_eligible
        and record.origin is FailureOrigin.SYSTEM
        and not record.benchmark_invalid
    )
