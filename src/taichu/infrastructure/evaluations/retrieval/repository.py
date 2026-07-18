"""召回评测数据集和派生结果的文件仓储。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from taichu.application.evaluations.retrieval.models import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationRecord,
)

_DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_EVALUATION_ID = re.compile(r"^retrieval_eval_\d{8}_\d{6}_[a-z0-9]{6}$")


class JsonRetrievalEvaluationDatasetRepository:
    def __init__(self, datasets_root: Path) -> None:
        self._root = datasets_root

    async def get_dataset(
        self,
        dataset_id: str,
    ) -> RetrievalEvaluationDataset | None:
        _validate_dataset_id(dataset_id)
        return await asyncio.to_thread(self._get_sync, dataset_id)

    def _get_sync(self, dataset_id: str) -> RetrievalEvaluationDataset | None:
        path = self._root / dataset_id / "manifest.json"
        if not path.exists():
            return None
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RetrievalEvaluationStoreError("召回评测集文件无法读取。") from error
        if not isinstance(raw, dict) or raw.get("evaluation_type") != "retrieval":
            return None
        checksum = sha256(path.read_bytes()).hexdigest()
        return RetrievalEvaluationDataset.model_validate(
            {**raw, "checksum": checksum}
        )


class JsonRetrievalEvaluationResultRepository:
    def __init__(self, project_assets_dir: Path) -> None:
        self._root = (
            project_assets_dir / "derived" / "agent_evaluations" / "retrieval"
        )

    async def save(
        self,
        record: RetrievalEvaluationRecord,
    ) -> RetrievalEvaluationRecord:
        await asyncio.to_thread(self._save_sync, record)
        return record

    async def get(
        self,
        evaluation_id: str,
    ) -> RetrievalEvaluationRecord | None:
        _validate_evaluation_id(evaluation_id)
        return await asyncio.to_thread(self._get_sync, evaluation_id)

    async def list_records(
        self,
        *,
        limit: int = 20,
    ) -> list[RetrievalEvaluationRecord]:
        if limit < 1 or limit > 200:
            raise RetrievalEvaluationStoreError("召回评测结果读取数量必须为 1 到 200。")
        records = await asyncio.to_thread(self._list_sync)
        return records[:limit]

    def _save_sync(self, record: RetrievalEvaluationRecord) -> None:
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

    def _get_sync(self, evaluation_id: str) -> RetrievalEvaluationRecord | None:
        path = self._path(evaluation_id)
        if not path.exists():
            return None
        return _load_record(path)

    def _list_sync(self) -> list[RetrievalEvaluationRecord]:
        if not self._root.exists():
            return []
        records = [_load_record(path) for path in self._root.glob("*.json")]
        return sorted(records, key=lambda item: item.finished_at, reverse=True)

    def _path(self, evaluation_id: str) -> Path:
        return self._root / f"{evaluation_id}.json"


def _load_record(path: Path) -> RetrievalEvaluationRecord:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RetrievalEvaluationStoreError("召回评测结果文件无法读取。") from error
    return RetrievalEvaluationRecord.model_validate(raw)


def _validate_dataset_id(dataset_id: str) -> None:
    if not _DATASET_ID.fullmatch(dataset_id):
        raise RetrievalEvaluationStoreError("召回评测集标识格式不正确。")


def _validate_evaluation_id(evaluation_id: str) -> None:
    if not _EVALUATION_ID.fullmatch(evaluation_id):
        raise RetrievalEvaluationStoreError("召回评测结果标识格式不正确。")


class RetrievalEvaluationStoreError(ValueError):
    """召回评测集或结果文件不符合契约。"""
