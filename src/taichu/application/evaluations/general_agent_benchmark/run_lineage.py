"""一次 Benchmark 案例跨多个 Runtime run 的确定性谱系。"""

from __future__ import annotations

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
)
from taichu.application.general_agent.models import GeneralAgentRun


class RunLineageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CapturedRunLineage(BenchmarkModel):
    preexisting_run_ids: tuple[str, ...]
    entry_run_id: str = Field(min_length=1, max_length=128)
    terminal_run_id: str = Field(min_length=1, max_length=128)
    lineage_run_ids: tuple[str, ...] = Field(min_length=1)
    runs: tuple[GeneralAgentRun, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _identities_match_runs(self) -> CapturedRunLineage:
        actual = tuple(item.run_id for item in self.runs)
        if actual != self.lineage_run_ids:
            raise ValueError("谱系 run 身份与有序运行集合不一致。")
        if self.entry_run_id != actual[0] or self.terminal_run_id != actual[-1]:
            raise ValueError("谱系入口或叶节点与有序运行集合不一致。")
        if self.preexisting_run_ids != tuple(
            sorted(set(self.preexisting_run_ids))
        ):
            raise ValueError("执行前 run 身份必须排序且不得重复。")
        return self


def capture_run_lineage(
    *,
    preexisting_run_ids: tuple[str, ...],
    observed_runs: tuple[GeneralAgentRun, ...],
    returned_run_id: str,
    case_user_request_raw: str,
) -> CapturedRunLineage:
    """从执行前后 run 集合重建唯一线性谱系；不按时间或列表位置猜测。"""

    frozen_preexisting = tuple(sorted(set(preexisting_run_ids)))
    if len(frozen_preexisting) != len(preexisting_run_ids):
        raise RunLineageError(
            "preexisting_run_id_conflict",
            "执行前 run 身份包含重复项。",
        )
    by_id: dict[str, GeneralAgentRun] = {}
    for run in observed_runs:
        if run.run_id in by_id:
            raise RunLineageError(
                "run_id_conflict",
                f"运行身份重复：{run.run_id}。",
            )
        by_id[run.run_id] = run
    new_runs = {
        run_id: run
        for run_id, run in by_id.items()
        if run_id not in set(frozen_preexisting)
    }
    if not new_runs:
        raise RunLineageError("lineage_missing", "案例没有产生新的 Runtime run。")

    entries = tuple(
        run
        for run in new_runs.values()
        if run.parent_run_id not in new_runs
    )
    if len(entries) != 1:
        raise RunLineageError(
            "lineage_entry_invalid",
            "案例谱系必须只有一个入口 run。",
        )
    entry = entries[0]
    if (
        entry.parent_run_id is not None
        and entry.parent_run_id not in frozen_preexisting
    ):
        raise RunLineageError(
            "lineage_orphan",
            "案例入口引用了执行前不存在的父 run。",
        )
    if entry.user_goal != case_user_request_raw:
        raise RunLineageError(
            "entry_request_mismatch",
            "案例入口 run 未逐字保留当前请求原文。",
        )

    conversation_ids = {item.conversation_id for item in new_runs.values()}
    task_ids = {item.task_id for item in new_runs.values()}
    if len(conversation_ids) != 1 or len(task_ids) != 1:
        raise RunLineageError(
            "lineage_owner_mismatch",
            "案例谱系跨越了 conversation 或 task owner。",
        )

    children: dict[str, list[GeneralAgentRun]] = {
        run_id: [] for run_id in new_runs
    }
    for run in new_runs.values():
        if run.run_id == entry.run_id:
            continue
        parent_id = run.parent_run_id
        if parent_id not in new_runs:
            raise RunLineageError(
                "lineage_orphan",
                f"谱系 run {run.run_id} 缺少案例内父节点。",
            )
        parent = new_runs[parent_id]
        if run.request_index != parent.request_index + 1:
            raise RunLineageError(
                "request_index_discontinuity",
                "案例谱系 request_index 不连续。",
            )
        children[parent_id].append(run)
    if any(len(items) > 1 for items in children.values()):
        raise RunLineageError(
            "lineage_branching",
            "当前 Benchmark 案例不接受分叉 run 谱系。",
        )

    ordered: list[GeneralAgentRun] = []
    seen: set[str] = set()
    current = entry
    while True:
        if current.run_id in seen:
            raise RunLineageError("lineage_cycle", "案例 run 谱系存在循环。")
        seen.add(current.run_id)
        ordered.append(current)
        next_runs = children[current.run_id]
        if not next_runs:
            break
        current = next_runs[0]
    if seen != set(new_runs):
        raise RunLineageError(
            "lineage_disconnected",
            "案例存在无法从入口到达的 run。",
        )
    if current.run_id != returned_run_id:
        raise RunLineageError(
            "terminal_run_mismatch",
            "执行器返回的 run 不是案例谱系唯一叶节点。",
        )
    return CapturedRunLineage(
        preexisting_run_ids=frozen_preexisting,
        entry_run_id=entry.run_id,
        terminal_run_id=current.run_id,
        lineage_run_ids=tuple(item.run_id for item in ordered),
        runs=tuple(ordered),
    )


__all__ = [
    "CapturedRunLineage",
    "RunLineageError",
    "capture_run_lineage",
]
