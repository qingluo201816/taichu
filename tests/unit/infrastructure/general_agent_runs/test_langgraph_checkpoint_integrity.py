"""LangGraph Checkpoint 损坏、线程与版本完整性选择测试。"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from taichu.infrastructure.general_agent_runs import JsonLangGraphCheckpointSaver


@pytest.mark.parametrize(
    "damage_kind",
    [
        "corrupt_json",
        "thread_mismatch",
        "revision_version_incompatible",
        "state_version_incompatible",
    ],
)
def test_checkpoint_selects_latest_valid_revision_and_keeps_invalid_evidence(
    tmp_path: Path,
    damage_kind: str,
) -> None:
    thread_id = "general_run_20260730_010101_abcdef"
    saver = JsonLangGraphCheckpointSaver(tmp_path)
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
    }
    updated = config
    for step in range(3):
        updated = saver.put(
            updated,
            empty_checkpoint(),
            {"source": "loop", "step": step, "parents": {}},
            {},
        )
    before = saver.inspect_thread(thread_id)
    damaged_revision = before.current_revision
    damaged_path = _revision_path(tmp_path, thread_id, damaged_revision)

    if damage_kind == "corrupt_json":
        damaged_path.write_text("{损坏", encoding="utf-8")
    else:
        payload = json.loads(damaged_path.read_text(encoding="utf-8"))
        if damage_kind == "thread_mismatch":
            payload["thread_id"] = "general_run_20260730_010101_fedcba"
        elif damage_kind == "revision_version_incompatible":
            payload["format_version"] = 999
        else:
            payload["state"]["format_version"] = 999
        payload["content_sha256"] = _content_sha256(payload)
        damaged_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    restored = JsonLangGraphCheckpointSaver(tmp_path)
    summary = restored.inspect_thread(thread_id)

    assert summary.integrity_status == "recovered"
    assert summary.current_revision == damaged_revision - 1
    assert summary.recovered_from_revision == damaged_revision - 1
    assert summary.available_revisions == list(range(1, damaged_revision))
    assert summary.invalid_revisions == [damaged_revision]
    assert summary.damage_warnings
    assert list(
        (
            tmp_path
            / "derived"
            / "general_agent_graph_checkpoints"
            / thread_id
            / "corrupt"
        ).glob(f"{damaged_revision:06d}*.json")
    )

    reloaded = JsonLangGraphCheckpointSaver(tmp_path).inspect_thread(thread_id)
    assert reloaded.integrity_status == "recovered"
    assert reloaded.current_revision == damaged_revision - 1
    assert reloaded.invalid_revisions == [damaged_revision]


def test_checkpoint_reports_all_revisions_invalid_without_loading_state(
    tmp_path: Path,
) -> None:
    thread_id = "general_run_20260730_020202_abcdef"
    saver = JsonLangGraphCheckpointSaver(tmp_path)
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
    }
    updated = config
    for step in range(3):
        updated = saver.put(
            updated,
            empty_checkpoint(),
            {"source": "loop", "step": step, "parents": {}},
            {},
        )
    first_revision = _revision_path(tmp_path, thread_id, 1)
    first_revision.write_text("{全链损坏", encoding="utf-8")

    restored = JsonLangGraphCheckpointSaver(tmp_path)
    summary = restored.inspect_thread(thread_id)

    assert summary.integrity_status == "invalid"
    assert summary.current_revision == 0
    assert summary.available_revisions == []
    assert summary.invalid_revisions == [1, 2, 3]
    assert summary.recovered_from_revision is None
    assert summary.damage_warnings


def _revision_path(root: Path, thread_id: str, revision: int) -> Path:
    return (
        root
        / "derived"
        / "general_agent_graph_checkpoints"
        / thread_id
        / "revisions"
        / f"{revision:06d}.json"
    )


def _content_sha256(payload: dict[str, Any]) -> str:
    without_hash = {
        key: value for key, value in payload.items() if key != "content_sha256"
    }
    canonical = json.dumps(
        without_hash,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
