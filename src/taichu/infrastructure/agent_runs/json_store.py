"""JSON intermediate-state store for knowledge extraction runs."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from taichu.application.agents.models.agent_run import AgentRun, AgentRunStatus

_RUN_ID_PATTERN = re.compile(r"^extract_run_\d{8}_\d{6}_[a-z0-9]{6}$")


class JsonAgentRunStore:
    """Store each knowledge extraction run as one JSON file under derived/."""

    def __init__(self, assets_root: Path) -> None:
        self._root = (
            assets_root
            / "derived"
            / "agent_runs"
            / "knowledge_extraction"
        )

    async def write_run(self, run: AgentRun) -> AgentRun:
        """Write one run JSON atomically."""
        await asyncio.to_thread(self._write_run_sync, run)
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Read one run by id."""
        return await asyncio.to_thread(self._get_run_sync, run_id)

    async def delete_run(self, run_id: str) -> bool:
        """Delete one persisted run JSON."""
        return await asyncio.to_thread(self._delete_run_sync, run_id)

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[AgentRun], int]:
        """List runs newest first with simple pagination."""
        runs = await asyncio.to_thread(self._list_runs_sync, status)
        start = (page - 1) * page_size
        return runs[start : start + page_size], len(runs)

    async def find_run_for_candidate(
        self,
        candidate_id: str,
    ) -> AgentRun | None:
        """Return the run containing one review item id."""
        runs, _ = await self.list_runs(page=1, page_size=10_000, status="all")
        for run in runs:
            if any(
                item.review_item_id == candidate_id for item in run.review_items
            ):
                return run
        return None

    def _write_run_sync(self, run: AgentRun) -> None:
        _validate_run_id(run.run_id)
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path_for_run(run.run_id)
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _get_run_sync(self, run_id: str) -> AgentRun | None:
        _validate_run_id(run_id)
        path = self._path_for_run(run_id)
        if not path.exists():
            return None
        return _load_run(path)

    def _delete_run_sync(self, run_id: str) -> bool:
        _validate_run_id(run_id)
        path = self._path_for_run(run_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _list_runs_sync(self, status: str) -> list[AgentRun]:
        self._root.mkdir(parents=True, exist_ok=True)
        runs = [_load_run(path) for path in sorted(self._root.glob("*.json"))]
        if status != "all":
            expected = AgentRunStatus(status)
            runs = [run for run in runs if run.status is expected]
        return sorted(runs, key=lambda run: run.started_at, reverse=True)

    def _path_for_run(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"


class AgentRunStoreError(ValueError):
    """Raised when run storage receives invalid data."""


def _load_run(path: Path) -> AgentRun:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AgentRunStoreError(f"运行 JSON 必须是对象：{path.name}")
    return AgentRun.model_validate(data)


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise AgentRunStoreError("运行 ID 格式不正确。")
