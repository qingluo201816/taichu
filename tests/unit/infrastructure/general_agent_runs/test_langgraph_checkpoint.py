"""LangGraph 节点检查点跨服务实例恢复测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.base import empty_checkpoint

from taichu.infrastructure.general_agent_runs import JsonLangGraphCheckpointSaver


class _State(TypedDict):
    value: int


class _Nodes:
    def __init__(self) -> None:
        self.fail_second = True
        self.first_calls = 0
        self.second_calls = 0

    async def first(self, state: _State) -> _State:
        self.first_calls += 1
        return {"value": state["value"] + 1}

    async def second(self, state: _State) -> _State:
        self.second_calls += 1
        if self.fail_second:
            raise RuntimeError("模拟第二节点中断")
        return {"value": state["value"] + 10}


def test_checkpoint_resumes_failed_node_without_rerunning_success_node(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        nodes = _Nodes()
        config = {
            "configurable": {
                "thread_id": "general_run_20260719_010101_abcdef",
            }
        }
        first_graph = _graph(nodes, JsonLangGraphCheckpointSaver(tmp_path))
        try:
            await first_graph.ainvoke({"value": 0}, config=config)
        except RuntimeError as error:
            assert str(error) == "模拟第二节点中断"
        else:
            raise AssertionError("第二节点应模拟中断。")

        assert nodes.first_calls == 1
        assert (await first_graph.aget_state(config)).next == ("second",)

        nodes.fail_second = False
        restored_graph = _graph(nodes, JsonLangGraphCheckpointSaver(tmp_path))
        result = await restored_graph.ainvoke(None, config=config)
        assert result == {"value": 11}
        assert nodes.first_calls == 1
        assert nodes.second_calls == 2

    asyncio.run(scenario())


def test_checkpoint_keeps_hash_chained_history_and_repairs_corrupt_latest(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_010101_abcdef"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        nodes = _Nodes()
        nodes.fail_second = False
        saver = JsonLangGraphCheckpointSaver(tmp_path)
        graph = _graph(nodes, saver)

        result = await graph.ainvoke({"value": 0}, config=config)

        assert result == {"value": 11}
        summary = saver.inspect_thread(thread_id)
        assert summary.current_revision >= 3
        assert summary.available_revisions == list(
            range(1, summary.current_revision + 1)
        )
        assert summary.integrity_status == "valid"
        assert summary.recovered_from_revision is None

        latest_path = (
            tmp_path
            / "derived"
            / "general_agent_graph_checkpoints"
            / thread_id
            / "revisions"
            / f"{summary.current_revision:06d}.json"
        )
        latest_path.write_text("{损坏", encoding="utf-8")

        restored_saver = JsonLangGraphCheckpointSaver(tmp_path)
        restored = restored_saver.inspect_thread(thread_id)
        assert restored.integrity_status == "recovered"
        assert restored.recovered_from_revision == summary.current_revision - 1
        assert restored.current_revision == summary.current_revision - 1
        assert restored.damage_warnings
        state = await _graph(nodes, restored_saver).aget_state(config)
        assert state.values

        latest_pointer = json.loads(
            (
                tmp_path
                / "derived"
                / "general_agent_graph_checkpoints"
                / thread_id
                / "latest.json"
            ).read_text(encoding="utf-8")
        )
        assert latest_pointer["revision"] == summary.current_revision - 1

    asyncio.run(scenario())


def test_checkpoint_delete_removes_revision_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_020202_abcdef"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        nodes = _Nodes()
        nodes.fail_second = False
        saver = JsonLangGraphCheckpointSaver(tmp_path)
        await _graph(nodes, saver).ainvoke({"value": 0}, config=config)
        thread_root = (
            tmp_path / "derived" / "general_agent_graph_checkpoints" / thread_id
        )
        assert thread_root.exists()

        await saver.adelete_thread(thread_id)

        assert not thread_root.exists()
        assert saver.inspect_thread(thread_id).current_revision == 0

    asyncio.run(scenario())


def test_checkpoint_temp_write_failure_keeps_previous_valid_revision(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_060606_abcdef"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        calls = 0

        def inject(point: str, _path: Path) -> None:
            nonlocal calls
            if point != "after_checkpoint_temp_fsync_before_replace":
                return
            calls += 1
            if calls == 3:
                raise RuntimeError("模拟临时检查点落盘后进程退出")

        saver = JsonLangGraphCheckpointSaver(tmp_path, fault_injector=inject)
        checkpoint_config = config
        for step in range(2):
            checkpoint_config = saver.put(
                checkpoint_config,
                empty_checkpoint(),
                {"source": "loop", "step": step, "parents": {}},
                {},
            )
        try:
            saver.put(
                checkpoint_config,
                empty_checkpoint(),
                {"source": "loop", "step": 2, "parents": {}},
                {},
            )
        except RuntimeError as error:
            assert str(error) == "模拟临时检查点落盘后进程退出"
        else:
            raise AssertionError("故障注入应中止本次检查点写入。")

        restored = JsonLangGraphCheckpointSaver(tmp_path)
        summary = restored.inspect_thread(thread_id)
        assert summary.integrity_status == "valid"
        assert summary.current_revision == 2
        assert not list(
            (
                tmp_path
                / "derived"
                / "general_agent_graph_checkpoints"
                / thread_id
                / "revisions"
            ).glob("*.tmp")
        )

    asyncio.run(scenario())


def test_checkpoint_latest_pointer_failure_repairs_to_newest_valid_revision(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_070707_abcdef"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        calls = 0

        def inject(point: str, _path: Path) -> None:
            nonlocal calls
            if point != "before_latest_pointer_update":
                return
            calls += 1
            if calls == 3:
                raise RuntimeError("模拟最新指针更新前进程退出")

        saver = JsonLangGraphCheckpointSaver(tmp_path, fault_injector=inject)
        checkpoint_config = config
        for step in range(2):
            checkpoint_config = saver.put(
                checkpoint_config,
                empty_checkpoint(),
                {"source": "loop", "step": step, "parents": {}},
                {},
            )
        try:
            saver.put(
                checkpoint_config,
                empty_checkpoint(),
                {"source": "loop", "step": 2, "parents": {}},
                {},
            )
        except RuntimeError as error:
            assert str(error) == "模拟最新指针更新前进程退出"
        else:
            raise AssertionError("故障注入应中止最新指针更新。")

        restored = JsonLangGraphCheckpointSaver(tmp_path)
        summary = restored.inspect_thread(thread_id)
        assert summary.integrity_status == "recovered"
        assert summary.current_revision == 3
        assert summary.recovered_from_revision == 3
        assert any("最新检查点指针" in item for item in summary.damage_warnings)
        latest = json.loads(
            (
                tmp_path
                / "derived"
                / "general_agent_graph_checkpoints"
                / thread_id
                / "latest.json"
            ).read_text(encoding="utf-8")
        )
        assert latest["revision"] == 3

    asyncio.run(scenario())


def test_checkpoint_can_append_explicit_repair_from_historical_revision(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_080808_abcdef"
        config = {"configurable": {"thread_id": thread_id}}
        nodes = _Nodes()
        nodes.fail_second = False
        saver = JsonLangGraphCheckpointSaver(tmp_path)
        await _graph(nodes, saver).ainvoke({"value": 0}, config=config)
        before = saver.inspect_thread(thread_id)
        selected = before.available_revisions[-2]

        saver.repair_latest(thread_id, revision=selected)

        repaired = saver.inspect_thread(thread_id)
        assert repaired.current_revision == before.current_revision + 1
        assert repaired.recovered_from_revision == selected
        assert repaired.integrity_status == "recovered"
        revisions = saver.list_revisions(thread_id)
        assert revisions[-1].event_type == f"repaired_from_revision_{selected}"
        assert saver.get_revision(thread_id, selected).revision == selected

    asyncio.run(scenario())


def test_legacy_flat_checkpoint_is_migrated_once_with_backup(tmp_path: Path) -> None:
    async def scenario() -> None:
        thread_id = "general_run_20260720_090909_abcdef"
        config = {"configurable": {"thread_id": thread_id}}
        source_root = tmp_path / "source"
        nodes = _Nodes()
        nodes.fail_second = False
        saver = JsonLangGraphCheckpointSaver(source_root)
        await _graph(nodes, saver).ainvoke({"value": 0}, config=config)
        summary = saver.inspect_thread(thread_id)
        latest_revision = json.loads(
            (
                source_root
                / "derived"
                / "general_agent_graph_checkpoints"
                / thread_id
                / "revisions"
                / f"{summary.current_revision:06d}.json"
            ).read_text(encoding="utf-8")
        )

        target_root = tmp_path / "target"
        legacy_path = (
            target_root
            / "derived"
            / "general_agent_graph_checkpoints"
            / f"{thread_id}.json"
        )
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(
            json.dumps(latest_revision["state"], ensure_ascii=False),
            encoding="utf-8",
        )

        migrated = JsonLangGraphCheckpointSaver(target_root)

        migrated_summary = migrated.inspect_thread(thread_id)
        assert migrated_summary.legacy_migrated
        assert migrated_summary.current_revision == 1
        assert not legacy_path.exists()
        assert (
            target_root
            / "derived"
            / "general_agent_graph_checkpoints"
            / "legacy_backups"
            / f"{thread_id}.json"
        ).exists()
        assert (await _graph(nodes, migrated).aget_state(config)).values

    asyncio.run(scenario())


def _graph(nodes: _Nodes, saver: JsonLangGraphCheckpointSaver):
    graph = StateGraph(_State)
    graph.add_node("first", nodes.first)
    graph.add_node("second", nodes.second)
    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", END)
    return graph.compile(checkpointer=saver)
