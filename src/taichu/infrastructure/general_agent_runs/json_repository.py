"""把通用写作助手每次运行保存为可恢复 JSON 检查点。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import threading
import time
from typing import Any
from uuid import uuid4

from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
    context_snapshot_sha256,
)

_RUN_ID_PATTERN = re.compile(r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")


class JsonGeneralAgentRunRepository:
    """在独立目录中原子保存通用 Runtime 业务状态。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "general_agent_runs"
        self._lock = threading.RLock()

    async def save(self, run: GeneralAgentRun) -> GeneralAgentRun:
        await asyncio.to_thread(self._save_sync, run)
        return run

    async def get(self, run_id: str) -> GeneralAgentRun | None:
        return await asyncio.to_thread(self._get_sync, run_id)

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[GeneralAgentRun], int]:
        runs = await asyncio.to_thread(self._list_sync, status)
        start = (page - 1) * page_size
        return runs[start : start + page_size], len(runs)

    async def delete(self, run_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, run_id)

    def _save_sync(self, run: GeneralAgentRun) -> None:
        with self._lock:
            _validate_run_id(run.run_id)
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._path(run.run_id)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(
                        run.model_dump(mode="json"),
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    def _get_sync(self, run_id: str) -> GeneralAgentRun | None:
        with self._lock:
            _validate_run_id(run_id)
            path = self._path(run_id)
            if not path.exists():
                return None
            payloads = self._load_payloads()
            payload = payloads.get(run_id)
            if payload is None:
                return None
            return _load_payload(payload, path=path, payloads=payloads)

    def _list_sync(self, status: str) -> list[GeneralAgentRun]:
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            payloads = self._load_payloads()
            runs = [
                _load_payload(
                    payload,
                    path=self._path(run_id),
                    payloads=payloads,
                )
                for run_id, payload in payloads.items()
            ]
            if status != "all":
                expected = GeneralAgentRunStatus(status)
                runs = [run for run in runs if run.status is expected]
            return sorted(runs, key=lambda item: item.created_at, reverse=True)

    def _delete_sync(self, run_id: str) -> bool:
        with self._lock:
            _validate_run_id(run_id)
            path = self._path(run_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    def _path(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"

    def _load_payloads(self) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        for path in self._root.glob("*.json"):
            try:
                payload = _read_payload(path)
            except FileNotFoundError:
                # 允许另一个仓储实例在列表扫描期间删除业务投影。
                continue
            run_id = payload.get("run_id")
            if not isinstance(run_id, str):
                raise GeneralAgentRunStoreError(f"运行检查点缺少运行标识：{path.name}")
            payloads[run_id] = payload
        return payloads


class GeneralAgentRunStoreError(ValueError):
    """通用 Runtime 检查点文件不符合稳定契约。"""


def _read_payload(path: Path) -> dict[str, Any]:
    payload: Any = None
    for attempt in range(5):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            break
        except PermissionError:
            if attempt == 4:
                raise
            # Windows 在原子替换的极短窗口内可能暂时拒绝并发读取。
            time.sleep(0.005 * (attempt + 1))
    if not isinstance(payload, dict):
        raise GeneralAgentRunStoreError(f"运行检查点必须是对象：{path.name}")
    return payload


def _load_payload(
    payload: dict[str, Any],
    *,
    path: Path,
    payloads: dict[str, dict[str, Any]],
) -> GeneralAgentRun:
    migrated = dict(payload)
    canonical_conversation_id = _canonical_conversation_id(
        migrated,
        payloads=payloads,
    )
    migrated["conversation_id"] = canonical_conversation_id
    if str(migrated.get("task_id", "")).startswith("general_run_"):
        migrated["task_id"] = canonical_conversation_id
    snapshot = migrated.get("context_snapshot")
    if isinstance(snapshot, dict):
        envelope = snapshot.get("envelope")
        if not isinstance(envelope, dict) or "current_request" not in envelope:
            migrated["context_snapshot_id"] = None
            migrated["context_snapshot"] = None
            migrated["context_resume_differences"] = [
                *migrated.get("context_resume_differences", []),
                "旧版上下文快照已按五层上下文设计失效，恢复时将自动重建。",
            ]
            return GeneralAgentRun.model_validate(migrated)
        migrated_snapshot = dict(snapshot)
        migrated_snapshot["conversation_id"] = canonical_conversation_id
        migrated_snapshot["content_sha256"] = context_snapshot_sha256(
            {
                key: value
                for key, value in migrated_snapshot.items()
                if key != "content_sha256"
            }
        )
        migrated["context_snapshot"] = migrated_snapshot
    return GeneralAgentRun.model_validate(migrated)


def _canonical_conversation_id(
    payload: dict[str, Any],
    *,
    payloads: dict[str, dict[str, Any]],
) -> str:
    candidate = payload.get("conversation_id") or payload.get("task_id")
    visited: set[str] = set()
    while isinstance(candidate, str) and candidate.startswith("general_run_"):
        if candidate in visited:
            break
        visited.add(candidate)
        referenced = payloads.get(candidate)
        if referenced is None:
            break
        candidate = referenced.get("conversation_id") or referenced.get("task_id")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise GeneralAgentRunStoreError("运行检查点缺少可恢复的会话标识。")
    return run_id


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise GeneralAgentRunStoreError("通用 Agent 运行 ID 格式不正确。")
