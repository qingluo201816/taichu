"""密封夹具快照与案例工作区隔离控制。"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    FixtureEntry,
    FixtureSnapshotSpec,
)


class FixtureIsolationError(RuntimeError):
    """夹具身份或案例工作区边界无法证明。"""


class CaseWorkspaceHandle(BenchmarkModel):
    workspace_id: str = Field(pattern=r"^workspace_[a-f0-9]{32}$")
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    workspace_root: Path
    assets_root: Path
    fixture_snapshot_id: str = Field(pattern=r"^fixture_[a-f0-9]{64}$")
    mongo_database: str = Field(pattern=r"^taichu_eval_[a-f0-9]{32}$")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fixture_snapshot(
    root: Path,
    *,
    fixture_id: str,
) -> FixtureSnapshotSpec:
    resolved = root.resolve(strict=True)
    entries: list[FixtureEntry] = []
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink():
            raise FixtureIsolationError(f"密封夹具禁止符号链接：{path}")
        if not path.is_file():
            continue
        relative = path.relative_to(resolved).as_posix()
        entries.append(
            FixtureEntry(
                path=relative,
                kind="file",
                size_bytes=path.stat().st_size,
                sha256=_file_sha256(path),
            )
        )
    if not entries:
        raise FixtureIsolationError("密封夹具不能为空。")
    payload = {
        "fixture_id": fixture_id,
        "schema": "taichu.general_agent_benchmark.fixture@1",
        "manifest_entries": tuple(entries),
        "manuscript_root": "manuscripts",
        "knowledge_seed": "knowledge/confirmed_cards.json",
        "conversation_seed": "conversation.json",
        "runtime_memory_seed": "runtime_memories.json",
        "external_source_manifest": "external_sources/manifest.json",
    }
    return FixtureSnapshotSpec(
        **payload,
        snapshot_id=f"fixture_{canonical_sha256(payload)}",
    )


class FixtureIsolationController:
    """受信控制面；只为评测创建和清理明确归属的工作区。"""

    def __init__(self, *, sealed_root: Path, workspaces_root: Path) -> None:
        self._sealed_root = sealed_root.resolve(strict=True)
        self._workspaces_root = workspaces_root.resolve()
        self._workspaces_root.mkdir(parents=True, exist_ok=True)
        self._owned: dict[str, Path] = {}

    def verify_sealed_source(self, expected: FixtureSnapshotSpec) -> None:
        observed = build_fixture_snapshot(
            self._sealed_root,
            fixture_id=expected.fixture_id,
        )
        if observed.snapshot_id != expected.snapshot_id:
            raise FixtureIsolationError("密封夹具内容身份发生变化，案例结果不可使用。")

    def create_workspace(
        self,
        *,
        snapshot: FixtureSnapshotSpec,
        case_execution_id: str,
    ) -> CaseWorkspaceHandle:
        self.verify_sealed_source(snapshot)
        identity = uuid.uuid4().hex
        workspace_id = f"workspace_{identity}"
        workspace_root = self._workspaces_root / workspace_id
        assets_root = workspace_root / "source"
        if workspace_root.exists():
            raise FixtureIsolationError("案例工作区身份冲突。")
        try:
            shutil.copytree(self._sealed_root, assets_root)
            (workspace_root / "derived").mkdir()
            copied = build_fixture_snapshot(
                assets_root,
                fixture_id=snapshot.fixture_id,
            )
            if copied.snapshot_id != snapshot.snapshot_id:
                raise FixtureIsolationError("案例夹具副本内容身份不一致。")
        except Exception:
            if workspace_root.exists():
                shutil.rmtree(workspace_root)
            raise
        self._owned[workspace_id] = workspace_root.resolve()
        return CaseWorkspaceHandle(
            workspace_id=workspace_id,
            case_execution_id=case_execution_id,
            workspace_root=workspace_root.resolve(),
            assets_root=assets_root.resolve(),
            fixture_snapshot_id=snapshot.snapshot_id,
            mongo_database=f"taichu_eval_{identity}",
        )

    def assert_write_allowed(
        self,
        handle: CaseWorkspaceHandle,
        target: Path,
    ) -> None:
        owned = self._owned.get(handle.workspace_id)
        candidate = target.resolve()
        if owned is None or not candidate.is_relative_to(owned):
            raise FixtureIsolationError(f"写入越过案例工作区，已拒绝：{candidate}")

    def cleanup_workspace(self, handle: CaseWorkspaceHandle) -> None:
        resolved = self._owned_workspace(handle)
        if resolved.exists():
            shutil.rmtree(resolved)
        self._owned.pop(handle.workspace_id, None)

    def _owned_workspace(self, handle: CaseWorkspaceHandle) -> Path:
        owned = self._owned.get(handle.workspace_id)
        resolved = handle.workspace_root.resolve()
        if (
            owned is None
            or resolved != owned
            or not resolved.is_relative_to(self._workspaces_root)
        ):
            raise FixtureIsolationError(f"拒绝清理不属于控制器的路径：{resolved}")
        return resolved
