"""Atomic file-backed store for knowledge-extraction evaluation reports."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Any

from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationRunResult,
    EvaluationStatus,
    JudgeCallRecord,
    KnowledgeEvaluationRecord,
)


_EVALUATION_ID_PATTERN = re.compile(r"^knowledge_eval_\d{8}_\d{6}_[a-z0-9]{6}$")
_CALL_ID_PATTERN = re.compile(r"^judge_call_[a-z0-9]{12}$")
_RUN_ID_PATTERN = re.compile(r"^extract_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_SNAPSHOT_MANIFEST = "_snapshot_manifest.json"


class JsonEvaluationResultStore:
    """Store every report as an isolated directory under derived assets."""

    def __init__(self, assets_root: Path) -> None:
        self._root = (
            assets_root / "derived" / "agent_evaluations" / "knowledge_extraction"
        ).resolve()
        self._lock = asyncio.Lock()

    async def publish_pending(
        self,
        record: KnowledgeEvaluationRecord,
        snapshot_files: dict[str, bytes],
    ) -> KnowledgeEvaluationRecord:
        """Write a complete snapshot and atomically publish its pending summary."""
        async with self._lock:
            duplicate = await asyncio.to_thread(
                self._find_active_fingerprint_sync,
                record.request_fingerprint,
            )
            if duplicate is not None:
                raise EvaluationResultStoreError(
                    "EVALUATION_ALREADY_RUNNING",
                    "相同评估正在执行，请勿重复提交。",
                )
            return await asyncio.to_thread(
                self._publish_pending_sync,
                record,
                snapshot_files,
            )

    async def get_record(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord | None:
        """Return one summary by its safe server-generated ID."""
        return await asyncio.to_thread(self._get_record_sync, evaluation_id)

    async def list_records(
        self,
        *,
        page: int,
        page_size: int,
        status: str,
    ) -> tuple[list[KnowledgeEvaluationRecord], int]:
        """List visible summaries newest first."""
        records = await asyncio.to_thread(self._list_records_sync, status)
        start = (page - 1) * page_size
        return records[start : start + page_size], len(records)

    async def mutate_record(
        self,
        evaluation_id: str,
        updates: dict[str, Any],
        *,
        expected_status: str | None = None,
        expected_execution_token: str | None = None,
    ) -> KnowledgeEvaluationRecord:
        """Patch the current summary under the process-wide repository lock."""
        async with self._lock:
            return await asyncio.to_thread(
                self._mutate_record_sync,
                evaluation_id,
                updates,
                expected_status,
                expected_execution_token,
            )

    async def write_judge_call(self, call: JudgeCallRecord) -> None:
        """Write one judge call atomically."""
        await asyncio.to_thread(self._write_judge_call_sync, call)

    async def write_run_result(
        self,
        evaluation_id: str,
        result: EvaluationRunResult,
    ) -> None:
        """Write one complete run result atomically."""
        await asyncio.to_thread(
            self._write_run_result_sync,
            evaluation_id,
            result,
        )

    async def get_run_result(
        self,
        evaluation_id: str,
        run_id: str,
    ) -> EvaluationRunResult | None:
        """Read one complete run result."""
        return await asyncio.to_thread(
            self._get_run_result_sync,
            evaluation_id,
            run_id,
        )

    async def get_judge_call(
        self,
        evaluation_id: str,
        call_id: str,
    ) -> JudgeCallRecord | None:
        """Read one judge call without scanning other audit files."""
        return await asyncio.to_thread(
            self._get_judge_call_sync,
            evaluation_id,
            call_id,
        )

    async def read_snapshot_files(self, evaluation_id: str) -> dict[str, bytes]:
        """Read the immutable input snapshot after validating its root hash."""
        return await asyncio.to_thread(self._read_snapshot_files_sync, evaluation_id)

    async def find_active_fingerprint(
        self,
        request_fingerprint: str,
    ) -> KnowledgeEvaluationRecord | None:
        """Return an active report with the same deterministic request key."""
        return await asyncio.to_thread(
            self._find_active_fingerprint_sync,
            request_fingerprint,
        )

    async def discard_unstarted(self, evaluation_id: str) -> None:
        """Delete a pending report only when no worker has claimed it."""
        async with self._lock:
            await asyncio.to_thread(self._discard_unstarted_sync, evaluation_id)

    def _publish_pending_sync(
        self,
        record: KnowledgeEvaluationRecord,
        snapshot_files: dict[str, bytes],
    ) -> KnowledgeEvaluationRecord:
        _validate_evaluation_id(record.evaluation_id)
        if record.status is not EvaluationStatus.PENDING:
            raise EvaluationResultStoreError(
                "EVALUATION_INVALID_TRANSITION",
                "只有等待中的评估可以发布。",
            )
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._evaluation_path(record.evaluation_id)
        temporary = target.with_name(f"{record.evaluation_id}.tmp")
        if target.exists() or temporary.exists():
            raise EvaluationResultStoreError(
                "EVALUATION_ALREADY_RUNNING",
                "评估标识已经存在。",
            )
        try:
            snapshot_root = temporary / "input_snapshot"
            snapshot_root.mkdir(parents=True)
            snapshot_entries: list[dict[str, Any]] = []
            for relative_path, content in sorted(snapshot_files.items()):
                if relative_path == _SNAPSHOT_MANIFEST:
                    raise EvaluationResultStoreError(
                        "EVALUATION_ID_INVALID",
                        "快照文件名不允许使用保留名称。",
                    )
                path = _safe_snapshot_path(snapshot_root, relative_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                snapshot_entries.append(
                    {
                        "path": relative_path.replace("\\", "/"),
                        "size": len(content),
                        "sha256": sha256(content).hexdigest(),
                    }
                )
            snapshot_root_hash = _snapshot_root_hash(snapshot_entries)
            _write_json(
                snapshot_root / _SNAPSHOT_MANIFEST,
                {
                    "files": snapshot_entries,
                    "snapshot_root_hash": snapshot_root_hash,
                },
            )
            published = record.model_copy(
                update={"snapshot_root_hash": snapshot_root_hash}
            )
            _write_json(temporary / "summary.json", published.model_dump(mode="json"))
            (temporary / "runs").mkdir()
            (temporary / "judge_calls").mkdir()
            temporary.replace(target)
            return published
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

    def _get_record_sync(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord | None:
        _validate_evaluation_id(evaluation_id)
        path = self._evaluation_path(evaluation_id) / "summary.json"
        if not path.is_file():
            return None
        try:
            return KnowledgeEvaluationRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise EvaluationResultStoreError(
                "EVALUATION_SNAPSHOT_CORRUPTED",
                "评估记录损坏，无法读取。",
            ) from error

    def _list_records_sync(self, status: str) -> list[KnowledgeEvaluationRecord]:
        if not self._root.exists():
            return []
        records: list[KnowledgeEvaluationRecord] = []
        for directory in self._root.iterdir():
            if not directory.is_dir() or not _EVALUATION_ID_PATTERN.fullmatch(
                directory.name
            ):
                continue
            record = self._get_record_sync(directory.name)
            if record is None or record.lifecycle is EvaluationLifecycle.REJECTED:
                continue
            if status != "all" and record.status.value != status:
                continue
            records.append(record)
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def _mutate_record_sync(
        self,
        evaluation_id: str,
        updates: dict[str, Any],
        expected_status: str | None,
        expected_execution_token: str | None,
    ) -> KnowledgeEvaluationRecord:
        record = self._get_record_sync(evaluation_id)
        if record is None:
            raise EvaluationResultStoreError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        if expected_status is not None and record.status.value != expected_status:
            raise EvaluationResultStoreError(
                "EVALUATION_INVALID_TRANSITION",
                "评估状态已经变化，当前操作未执行。",
            )
        if (
            expected_execution_token is not None
            and record.execution_token != expected_execution_token
        ):
            raise EvaluationResultStoreError(
                "EVALUATION_INVALID_TRANSITION",
                "评估执行权已经变化，当前操作未执行。",
            )
        payload = record.model_dump(mode="json")
        payload.update(updates)
        updated = KnowledgeEvaluationRecord.model_validate(payload)
        _write_json(
            self._evaluation_path(evaluation_id) / "summary.json",
            updated.model_dump(mode="json"),
        )
        return updated

    def _write_judge_call_sync(self, call: JudgeCallRecord) -> None:
        _validate_evaluation_id(call.evaluation_id)
        _validate_call_id(call.call_id)
        directory = self._evaluation_path(call.evaluation_id) / "judge_calls"
        if not directory.is_dir():
            raise EvaluationResultStoreError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        _write_json(directory / f"{call.call_id}.json", call.model_dump(mode="json"))

    def _write_run_result_sync(
        self,
        evaluation_id: str,
        result: EvaluationRunResult,
    ) -> None:
        _validate_evaluation_id(evaluation_id)
        _validate_run_id(result.run_id)
        directory = self._evaluation_path(evaluation_id) / "runs"
        if not directory.is_dir():
            raise EvaluationResultStoreError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        _write_json(
            directory / f"{result.run_id}.json",
            result.model_dump(mode="json"),
        )

    def _get_run_result_sync(
        self,
        evaluation_id: str,
        run_id: str,
    ) -> EvaluationRunResult | None:
        _validate_evaluation_id(evaluation_id)
        _validate_run_id(run_id)
        path = self._evaluation_path(evaluation_id) / "runs" / f"{run_id}.json"
        if not path.is_file():
            return None
        return EvaluationRunResult.model_validate_json(path.read_text(encoding="utf-8"))

    def _get_judge_call_sync(
        self,
        evaluation_id: str,
        call_id: str,
    ) -> JudgeCallRecord | None:
        _validate_evaluation_id(evaluation_id)
        _validate_call_id(call_id)
        path = self._evaluation_path(evaluation_id) / "judge_calls" / f"{call_id}.json"
        if not path.is_file():
            return None
        return JudgeCallRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def _read_snapshot_files_sync(self, evaluation_id: str) -> dict[str, bytes]:
        record = self._get_record_sync(evaluation_id)
        if record is None:
            raise EvaluationResultStoreError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        root = self._evaluation_path(evaluation_id) / "input_snapshot"
        manifest_path = root / _SNAPSHOT_MANIFEST
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = manifest["files"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise EvaluationResultStoreError(
                "EVALUATION_SNAPSHOT_CORRUPTED",
                "评估输入快照损坏。",
            ) from error
        files: dict[str, bytes] = {}
        verified_entries: list[dict[str, Any]] = []
        for entry in entries:
            relative_path = str(entry["path"])
            content = _safe_snapshot_path(root, relative_path).read_bytes()
            digest = sha256(content).hexdigest()
            if digest != entry["sha256"] or len(content) != entry["size"]:
                raise EvaluationResultStoreError(
                    "EVALUATION_SNAPSHOT_CORRUPTED",
                    "评估输入快照校验失败。",
                )
            files[relative_path] = content
            verified_entries.append(
                {"path": relative_path, "size": len(content), "sha256": digest}
            )
        root_hash = _snapshot_root_hash(verified_entries)
        if root_hash != record.snapshot_root_hash or root_hash != manifest.get(
            "snapshot_root_hash"
        ):
            raise EvaluationResultStoreError(
                "EVALUATION_SNAPSHOT_CORRUPTED",
                "评估输入快照根校验失败。",
            )
        return files

    def _find_active_fingerprint_sync(
        self,
        request_fingerprint: str,
    ) -> KnowledgeEvaluationRecord | None:
        if not self._root.exists():
            return None
        for directory in self._root.iterdir():
            if not directory.is_dir() or not _EVALUATION_ID_PATTERN.fullmatch(
                directory.name
            ):
                continue
            record = self._get_record_sync(directory.name)
            if (
                record is not None
                and record.request_fingerprint == request_fingerprint
                and record.is_active
            ):
                return record
        return None

    def _discard_unstarted_sync(self, evaluation_id: str) -> None:
        record = self._get_record_sync(evaluation_id)
        if record is None:
            return
        if record.status is not EvaluationStatus.PENDING or record.execution_token:
            raise EvaluationResultStoreError(
                "EVALUATION_INVALID_TRANSITION",
                "已经开始的评估不能按未启动任务清理。",
            )
        shutil.rmtree(self._evaluation_path(evaluation_id))

    def _evaluation_path(self, evaluation_id: str) -> Path:
        _validate_evaluation_id(evaluation_id)
        path = (self._root / evaluation_id).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as error:
            raise EvaluationResultStoreError(
                "EVALUATION_ID_INVALID",
                "评估标识格式不正确。",
            ) from error
        return path


class EvaluationResultStoreError(ValueError):
    """Stable persistence error surfaced by the evaluation API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_evaluation_id(evaluation_id: str) -> None:
    if not _EVALUATION_ID_PATTERN.fullmatch(evaluation_id):
        raise EvaluationResultStoreError(
            "EVALUATION_ID_INVALID",
            "评估标识格式不正确。",
        )


def _validate_call_id(call_id: str) -> None:
    if not _CALL_ID_PATTERN.fullmatch(call_id):
        raise EvaluationResultStoreError(
            "EVALUATION_ID_INVALID",
            "裁判调用标识格式不正确。",
        )


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise EvaluationResultStoreError(
            "EVALUATION_ID_INVALID",
            "运行标识格式不正确。",
        )


def _safe_snapshot_path(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise EvaluationResultStoreError(
            "EVALUATION_ID_INVALID",
            "快照路径不安全。",
        )
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise EvaluationResultStoreError(
            "EVALUATION_ID_INVALID",
            "快照路径不安全。",
        ) from error
    return resolved


def _snapshot_root_hash(entries: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        sorted(entries, key=lambda item: item["path"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
