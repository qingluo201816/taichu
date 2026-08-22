"""需求 3.1-3.17：密封夹具与案例工作区隔离。"""

from __future__ import annotations

from pathlib import Path

import pytest

from taichu.infrastructure.evaluations.general_agent_benchmark.fixture_manager import (
    FixtureIsolationController,
    FixtureIsolationError,
    build_fixture_snapshot,
)


def _sealed_fixture(root: Path) -> Path:
    source = root / "sealed"
    (source / "manuscripts").mkdir(parents=True)
    (source / "manuscripts" / "chapter_001.md").write_text(
        "# 第一章\n\n顾长夜站在玄门前。",
        encoding="utf-8",
    )
    (source / "knowledge").mkdir()
    (source / "knowledge" / "confirmed_cards.json").write_text(
        '[{"id":"char_001","lifecycle":"confirmed","name":"顾长夜"}]',
        encoding="utf-8",
    )
    (source / "conversation.json").write_text("[]", encoding="utf-8")
    (source / "runtime_memories.json").write_text("[]", encoding="utf-8")
    (source / "external_sources").mkdir()
    (source / "external_sources" / "manifest.json").write_text(
        '{"queries":{}}',
        encoding="utf-8",
    )
    return source


def test_snapshot_is_deterministic_and_rejects_source_drift(tmp_path: Path) -> None:
    source = _sealed_fixture(tmp_path)
    first = build_fixture_snapshot(source, fixture_id="core_novel")
    second = build_fixture_snapshot(source, fixture_id="core_novel")
    assert first == second
    assert first.snapshot_id.startswith("fixture_")

    (source / "conversation.json").write_text('[{"role":"user"}]', encoding="utf-8")
    changed = build_fixture_snapshot(source, fixture_id="core_novel")
    assert changed.snapshot_id != first.snapshot_id


def test_each_attempt_gets_an_independent_clean_workspace(tmp_path: Path) -> None:
    source = _sealed_fixture(tmp_path)
    snapshot = build_fixture_snapshot(source, fixture_id="core_novel")
    controller = FixtureIsolationController(
        sealed_root=source,
        workspaces_root=tmp_path / "workspaces",
    )
    first = controller.create_workspace(
        snapshot=snapshot,
        case_execution_id="benchmark_case_" + "a" * 32,
    )
    second = controller.create_workspace(
        snapshot=snapshot,
        case_execution_id="benchmark_case_" + "b" * 32,
    )
    assert first.workspace_id != second.workspace_id
    assert first.assets_root != second.assets_root

    first_chapter = first.assets_root / "manuscripts" / "chapter_001.md"
    first_chapter.write_text("# 修改候选", encoding="utf-8")
    second_chapter = second.assets_root / "manuscripts" / "chapter_001.md"
    assert "顾长夜" in second_chapter.read_text(encoding="utf-8")
    assert "顾长夜" in (source / "manuscripts" / "chapter_001.md").read_text(
        encoding="utf-8"
    )


def test_out_of_boundary_write_is_rejected_and_source_drift_is_detected(
    tmp_path: Path,
) -> None:
    source = _sealed_fixture(tmp_path)
    snapshot = build_fixture_snapshot(source, fixture_id="core_novel")
    controller = FixtureIsolationController(
        sealed_root=source,
        workspaces_root=tmp_path / "workspaces",
    )
    handle = controller.create_workspace(
        snapshot=snapshot,
        case_execution_id="benchmark_case_" + "c" * 32,
    )
    with pytest.raises(FixtureIsolationError, match="越过案例工作区"):
        controller.assert_write_allowed(handle, tmp_path / "author" / "chapter.md")

    (source / "conversation.json").write_text('["漂移"]', encoding="utf-8")
    with pytest.raises(FixtureIsolationError, match="密封夹具"):
        controller.verify_sealed_source(snapshot)


def test_cleanup_rejects_unowned_workspace_and_removes_owned_workspace(
    tmp_path: Path,
) -> None:
    source = _sealed_fixture(tmp_path)
    snapshot = build_fixture_snapshot(source, fixture_id="core_novel")
    controller = FixtureIsolationController(
        sealed_root=source,
        workspaces_root=tmp_path / "workspaces",
    )
    handle = controller.create_workspace(
        snapshot=snapshot,
        case_execution_id="benchmark_case_" + "d" * 32,
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    forged = handle.model_copy(
        update={"workspace_root": outside, "assets_root": outside / "source"}
    )
    with pytest.raises(FixtureIsolationError, match="拒绝清理"):
        controller.cleanup_workspace(forged)
    assert outside.exists()
    assert handle.workspace_root.exists()

    controller.cleanup_workspace(handle)

    assert not handle.workspace_root.exists()
    assert outside.exists()
