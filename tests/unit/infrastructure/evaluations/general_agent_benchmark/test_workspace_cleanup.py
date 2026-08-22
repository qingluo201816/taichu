from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from taichu.infrastructure.evaluations.general_agent_benchmark.fixture_manager import (
    FixtureIsolationController,
    FixtureIsolationError,
    build_fixture_snapshot,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)

_CONVERSATION_ID = "benchmark_fixture_conversation"


def _workspace(
    tmp_path: Path,
) -> tuple[FixtureIsolationController, Any]:
    source = tmp_path / "sealed"
    source.mkdir()
    (source / "fixture.txt").write_text("密封夹具", encoding="utf-8")
    controller = FixtureIsolationController(
        sealed_root=source,
        workspaces_root=tmp_path / "workspaces",
    )
    handle = controller.create_workspace(
        snapshot=build_fixture_snapshot(source, fixture_id="cleanup_fixture"),
        case_execution_id="benchmark_case_" + "a" * 32,
    )
    return controller, handle


class _CompletingRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def delete_conversation(self, conversation_id: str) -> int:
        assert conversation_id == _CONVERSATION_ID
        self._events.append("运行时删除")
        return 1


class _FailingRuntime:
    async def delete_conversation(self, conversation_id: str) -> int:
        assert conversation_id == _CONVERSATION_ID
        raise RuntimeError("注入运行时删除失败")


class _MongoClient:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def drop_database(self, database_name: str) -> None:
        assert database_name.startswith("taichu_eval_")
        self.events.append("删除隔离数据库")


def test_workspace_cleanup_only_removes_controller_owned_workspace(
    tmp_path: Path,
) -> None:
    controller, handle = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    forged = handle.model_copy(update={"workspace_root": outside})

    with pytest.raises(FixtureIsolationError, match="不属于控制器"):
        controller.cleanup_workspace(forged)

    assert outside.exists()
    assert handle.workspace_root.exists()

    controller.cleanup_workspace(handle)

    assert not handle.workspace_root.exists()
    assert outside.exists()


@pytest.mark.anyio
async def test_successful_case_uses_existing_runtime_and_workspace_lifecycles(
    tmp_path: Path,
) -> None:
    controller, handle = _workspace(tmp_path)
    events: list[str] = []
    fixture_runtime = object.__new__(SyntheticFixtureRuntime)
    fixture_runtime._controller = controller

    await fixture_runtime._cleanup_successful_case(  # noqa: SLF001
        handle=handle,
        environment={"runtime": _CompletingRuntime(events)},
        client=_MongoClient(events),
    )

    assert events == ["运行时删除", "删除隔离数据库"]
    assert not handle.workspace_root.exists()


@pytest.mark.anyio
async def test_runtime_deletion_failure_preserves_database_and_workspace(
    tmp_path: Path,
) -> None:
    controller, handle = _workspace(tmp_path)
    events: list[str] = []
    fixture_runtime = object.__new__(SyntheticFixtureRuntime)
    fixture_runtime._controller = controller

    with pytest.raises(RuntimeError, match="运行时删除失败"):
        await fixture_runtime._cleanup_successful_case(  # noqa: SLF001
            handle=handle,
            environment={"runtime": _FailingRuntime()},
            client=_MongoClient(events),
        )

    assert events == []
    assert handle.workspace_root.exists()
