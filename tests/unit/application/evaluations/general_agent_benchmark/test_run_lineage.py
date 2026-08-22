"""Benchmark 案例 run 谱系必须从执行前后真实集合中 fail-closed 重建。"""

import pytest

from taichu.application.evaluations.general_agent_benchmark.run_lineage import (
    RunLineageError,
    capture_run_lineage,
)
from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
)

_REQUEST = "请先预览，确认后再写入。"


def _run(
    suffix: str,
    *,
    index: int,
    goal: str,
    parent: str | None,
) -> GeneralAgentRun:
    return GeneralAgentRun(
        run_id=f"general_run_20260730_12000{index}_{suffix}",
        task_id="benchmark_task",
        conversation_id="benchmark_conversation",
        request_index=index,
        parent_run_id=parent,
        user_goal=goal,
        status=GeneralAgentRunStatus.COMPLETED,
        resumable=False,
        created_at="2026-07-30T12:00:00Z",
        updated_at="2026-07-30T12:00:00Z",
        started_at="2026-07-30T12:00:00Z",
        finished_at="2026-07-30T12:00:00Z",
    )


def test_seed_parent_and_followup_form_one_ordered_lineage() -> None:
    seed = _run("seed00", index=1, goal="初始化。", parent=None)
    entry = _run(
        "entry1",
        index=2,
        goal=_REQUEST,
        parent=seed.run_id,
    )
    followup = _run(
        "leaf02",
        index=3,
        goal="继续使用创建返回的稳定标识。",
        parent=entry.run_id,
    )

    lineage = capture_run_lineage(
        preexisting_run_ids=(seed.run_id,),
        observed_runs=(followup, seed, entry),
        returned_run_id=followup.run_id,
        case_user_request_raw=_REQUEST,
    )

    assert lineage.entry_run_id == entry.run_id
    assert lineage.terminal_run_id == followup.run_id
    assert lineage.lineage_run_ids == (entry.run_id, followup.run_id)


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("wrong_request", "entry_request_mismatch"),
        ("unknown_parent", "lineage_orphan"),
        ("index_gap", "request_index_discontinuity"),
        ("wrong_leaf", "terminal_run_mismatch"),
    ),
)
def test_corrupt_lineage_fails_closed(mutation: str, code: str) -> None:
    seed = _run("seed00", index=1, goal="初始化。", parent=None)
    entry = _run(
        "entry1",
        index=2,
        goal=("错误请求" if mutation == "wrong_request" else _REQUEST),
        parent=("general_run_20260730_115959_ghost0" if mutation == "unknown_parent" else seed.run_id),
    )
    leaf = _run(
        "leaf02",
        index=(4 if mutation == "index_gap" else 3),
        goal="继续。",
        parent=entry.run_id,
    )

    with pytest.raises(RunLineageError) as captured:
        capture_run_lineage(
            preexisting_run_ids=(seed.run_id,),
            observed_runs=(seed, entry, leaf),
            returned_run_id=(
                entry.run_id if mutation == "wrong_leaf" else leaf.run_id
            ),
            case_user_request_raw=_REQUEST,
        )

    assert captured.value.code == code


def test_branching_is_rejected_instead_of_selecting_latest_run() -> None:
    seed = _run("seed00", index=1, goal="初始化。", parent=None)
    entry = _run("entry1", index=2, goal=_REQUEST, parent=seed.run_id)
    left = _run("left01", index=3, goal="左分支", parent=entry.run_id)
    right = _run("right1", index=3, goal="右分支", parent=entry.run_id)

    with pytest.raises(RunLineageError) as captured:
        capture_run_lineage(
            preexisting_run_ids=(seed.run_id,),
            observed_runs=(seed, entry, left, right),
            returned_run_id=right.run_id,
            case_user_request_raw=_REQUEST,
        )

    assert captured.value.code == "lineage_branching"
