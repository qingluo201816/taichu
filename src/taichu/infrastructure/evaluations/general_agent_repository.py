"""通用写作助手评测集与结果的 JSON 仓储。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from taichu.application.evaluations.general_agent.models import (
    GeneralAgentEvaluationDataset,
    GeneralAgentEvaluationRecord,
)

_DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_EVALUATION_ID = re.compile(r"^general_eval_\d{8}_\d{6}_[a-z0-9]{6}$")


class JsonGeneralAgentEvaluationDatasetRepository:
    def __init__(self, datasets_root: Path) -> None:
        self._root = datasets_root

    async def list_datasets(self) -> list[GeneralAgentEvaluationDataset]:
        return await asyncio.to_thread(self._list_sync)

    async def get_dataset(
        self,
        dataset_id: str,
    ) -> GeneralAgentEvaluationDataset | None:
        _validate_dataset_id(dataset_id)
        return await asyncio.to_thread(self._get_sync, dataset_id)

    def _list_sync(self) -> list[GeneralAgentEvaluationDataset]:
        if not self._root.exists():
            return []
        datasets: list[GeneralAgentEvaluationDataset] = []
        for path in self._root.glob("*/manifest.json"):
            try:
                raw: Any = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict) or raw.get("agent_name") != "general_writing_assistant":
                continue
            datasets.append(_load_dataset(path, raw))
        return sorted(datasets, key=lambda item: item.dataset_id)

    def _get_sync(self, dataset_id: str) -> GeneralAgentEvaluationDataset | None:
        path = self._root / dataset_id / "manifest.json"
        if not path.exists():
            return None
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("agent_name") != "general_writing_assistant":
            return None
        return _load_dataset(path, raw)


class JsonGeneralAgentEvaluationResultRepository:
    def __init__(self, project_assets_dir: Path) -> None:
        self._root = (
            project_assets_dir / "derived" / "agent_evaluations" / "general_agent"
        )

    async def save(
        self,
        record: GeneralAgentEvaluationRecord,
    ) -> GeneralAgentEvaluationRecord:
        await asyncio.to_thread(self._save_sync, record)
        return record

    async def get(self, evaluation_id: str) -> GeneralAgentEvaluationRecord | None:
        _validate_evaluation_id(evaluation_id)
        return await asyncio.to_thread(self._get_sync, evaluation_id)

    async def list_records(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[GeneralAgentEvaluationRecord], int]:
        records = await asyncio.to_thread(self._list_sync, status)
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    async def delete(self, evaluation_id: str) -> bool:
        _validate_evaluation_id(evaluation_id)
        return await asyncio.to_thread(self._delete_sync, evaluation_id)

    def _save_sync(self, record: GeneralAgentEvaluationRecord) -> None:
        _validate_evaluation_id(record.evaluation_id)
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(record.evaluation_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _get_sync(self, evaluation_id: str) -> GeneralAgentEvaluationRecord | None:
        path = self._path(evaluation_id)
        if not path.exists():
            return None
        return _load_record(path)

    def _list_sync(self, status: str) -> list[GeneralAgentEvaluationRecord]:
        self._root.mkdir(parents=True, exist_ok=True)
        records = [_load_record(path) for path in self._root.glob("*.json")]
        if status == "passed":
            records = [record for record in records if record.passed]
        elif status == "failed":
            records = [record for record in records if not record.passed]
        elif status == "warnings":
            records = [record for record in records if record.semantic_review_required]
        elif status != "all":
            raise GeneralAgentEvaluationStoreError("评估筛选状态不受支持。")
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def _delete_sync(self, evaluation_id: str) -> bool:
        path = self._path(evaluation_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, evaluation_id: str) -> Path:
        return self._root / f"{evaluation_id}.json"


def _load_dataset(
    path: Path,
    raw: dict[str, Any],
) -> GeneralAgentEvaluationDataset:
    checksum = sha256(path.read_bytes()).hexdigest()
    return GeneralAgentEvaluationDataset.model_validate(
        {**raw, "checksum": checksum}
    )


def _load_record(path: Path) -> GeneralAgentEvaluationRecord:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    return GeneralAgentEvaluationRecord.model_validate(raw)


def _validate_dataset_id(dataset_id: str) -> None:
    if not _DATASET_ID.fullmatch(dataset_id):
        raise GeneralAgentEvaluationStoreError("通用 Agent 评测集标识格式不正确。")


def _validate_evaluation_id(evaluation_id: str) -> None:
    if not _EVALUATION_ID.fullmatch(evaluation_id):
        raise GeneralAgentEvaluationStoreError("通用 Agent 评估标识格式不正确。")


class GeneralAgentEvaluationStoreError(ValueError):
    """通用 Agent 评测集或结果文件不符合契约。"""
