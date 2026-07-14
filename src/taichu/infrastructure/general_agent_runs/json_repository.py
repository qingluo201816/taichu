"""把通用写作助手每次运行保存为可恢复 JSON 检查点。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
from typing import Any

from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
)

_RUN_ID_PATTERN = re.compile(r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")


class JsonGeneralAgentRunRepository:
    """在独立目录中原子保存通用 Runtime 业务状态。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "derived" / "general_agent_runs"

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
        _validate_run_id(run.run_id)
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(run.run_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _get_sync(self, run_id: str) -> GeneralAgentRun | None:
        _validate_run_id(run_id)
        path = self._path(run_id)
        if not path.exists():
            return None
        return _load(path)

    def _list_sync(self, status: str) -> list[GeneralAgentRun]:
        self._root.mkdir(parents=True, exist_ok=True)
        runs = [_load(path) for path in self._root.glob("*.json")]
        if status != "all":
            expected = GeneralAgentRunStatus(status)
            runs = [run for run in runs if run.status is expected]
        return sorted(runs, key=lambda item: item.created_at, reverse=True)

    def _delete_sync(self, run_id: str) -> bool:
        _validate_run_id(run_id)
        path = self._path(run_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"


class GeneralAgentRunStoreError(ValueError):
    """通用 Runtime 检查点文件不符合稳定契约。"""


def _load(path: Path) -> GeneralAgentRun:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GeneralAgentRunStoreError(f"运行检查点必须是对象：{path.name}")
    return GeneralAgentRun.model_validate(payload)


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise GeneralAgentRunStoreError("通用 Agent 运行 ID 格式不正确。")
