"""LangGraph 节点检查点的原子 JSON 持久化。"""

from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from threading import RLock
from collections.abc import Callable
from typing import Any, Sequence
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import InMemorySaver


class JsonLangGraphCheckpointSaver(InMemorySaver):
    """复用 LangGraph 官方检查点语义，并保存可校验的线程修订历史。"""

    def __init__(
        self,
        project_assets_dir: Path,
        *,
        fault_injector: Callable[[str, Path], None] | None = None,
    ) -> None:
        super().__init__()
        self._root = project_assets_dir / "derived" / "general_agent_graph_checkpoints"
        self._lock = RLock()
        self._fault_injector = fault_injector
        self._summaries: dict[str, LangGraphCheckpointSummary] = {}
        self._load_all()

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        with self._lock:
            updated = super().put(config, checkpoint, metadata, new_versions)
            self._persist_thread(
                str(updated["configurable"]["thread_id"]),
                event_type="checkpoint_put",
            )
            return updated

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)
            self._persist_thread(
                str(config["configurable"]["thread_id"]),
                event_type="checkpoint_writes",
            )

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            super().delete_thread(thread_id)
            root = self._thread_root(thread_id)
            if root.exists():
                shutil.rmtree(root)
            self._legacy_path(thread_id).unlink(missing_ok=True)
            self._legacy_backup_path(thread_id).unlink(missing_ok=True)
            self._summaries.pop(thread_id, None)

    def inspect_thread(self, thread_id: str) -> "LangGraphCheckpointSummary":
        """返回脱敏的检查点完整性与恢复摘要。"""
        _validate_thread_id(thread_id)
        return self._summaries.get(
            thread_id,
            LangGraphCheckpointSummary(thread_id=thread_id),
        )

    def list_revisions(
        self,
        thread_id: str,
    ) -> list["LangGraphCheckpointRevisionSummary"]:
        """列出检查点修订证据，不返回运行输入与正文内容。"""
        _validate_thread_id(thread_id)
        summaries: list[LangGraphCheckpointRevisionSummary] = []
        for path in sorted((self._thread_root(thread_id) / "revisions").glob("*.json")):
            record = _read_revision_record(path, thread_id=thread_id)
            summaries.append(_revision_summary(record))
        return summaries

    def get_revision(
        self,
        thread_id: str,
        revision: int,
    ) -> "LangGraphCheckpointRevisionSummary":
        """读取一个修订的完整性元数据。"""
        if revision < 1:
            raise LangGraphCheckpointStoreError("检查点修订编号必须大于零。")
        record = _read_revision_record(
            self._revision_path(thread_id, revision),
            thread_id=thread_id,
        )
        return _revision_summary(record)

    def repair_latest(self, thread_id: str, *, revision: int) -> None:
        """从指定有效修订重建内存状态，并追加一条新的修复修订。"""
        with self._lock:
            current = self.inspect_thread(thread_id)
            if revision not in current.available_revisions:
                raise LangGraphCheckpointStoreError("指定检查点修订不可用。")
            record = _read_revision_record(
                self._revision_path(thread_id, revision),
                thread_id=thread_id,
            )
            self.storage.pop(thread_id, None)
            for key in [key for key in self.writes if key[0] == thread_id]:
                self.writes.pop(key, None)
            for key in [key for key in self.blobs if key[0] == thread_id]:
                self.blobs.pop(key, None)
            self._restore_thread(
                record["state"],
                path=self._revision_path(thread_id, revision),
            )
            self._persist_thread(
                thread_id,
                event_type=f"repaired_from_revision_{revision}",
            )
            repaired = self._summaries[thread_id]
            self._summaries[thread_id] = LangGraphCheckpointSummary(
                **{
                    **repaired.__dict__,
                    "integrity_status": "recovered",
                    "recovered_from_revision": revision,
                    "damage_warnings": [
                        f"已按显式恢复操作从第 {revision} 个修订重建最新状态。"
                    ],
                }
            )

    def _load_all(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for root in sorted(self._root.glob("general_run_*")):
            if root.is_dir():
                self._load_thread_history(root)
        for path in sorted(self._root.glob("general_run_*.json")):
            if self._thread_root(path.stem).exists():
                continue
            self._migrate_legacy_thread(path)

    def _load_thread_history(self, root: Path) -> None:
        thread_id = root.name
        _validate_thread_id(thread_id)
        revision_paths = sorted((root / "revisions").glob("*.json"))
        valid: list[tuple[Path, dict[str, Any]]] = []
        warnings: list[str] = []
        previous_hash: str | None = None
        for index, path in enumerate(revision_paths):
            try:
                record = _read_revision_record(path, thread_id=thread_id)
                if valid and record["previous_sha256"] != previous_hash:
                    raise LangGraphCheckpointStoreError(
                        f"检查点修订哈希链断裂：{path.name}"
                    )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                warnings.append(str(error))
                self._quarantine_revisions(root, revision_paths[index:])
                break
            valid.append((path, record))
            previous_hash = str(record["content_sha256"])

        if not valid:
            self._summaries[thread_id] = LangGraphCheckpointSummary(
                thread_id=thread_id,
                integrity_status="invalid",
                damage_warnings=warnings or ["没有可恢复的 LangGraph 检查点修订。"],
            )
            return

        _, latest_record = valid[-1]
        pointer_warning = self._latest_pointer_warning(root, latest_record)
        if pointer_warning:
            warnings.append(pointer_warning)
        self._restore_thread(latest_record["state"], path=valid[-1][0])
        revision = int(latest_record["revision"])
        status = "recovered" if warnings else "valid"
        summary = LangGraphCheckpointSummary(
            thread_id=thread_id,
            current_revision=revision,
            available_revisions=[int(item[1]["revision"]) for item in valid],
            integrity_status=status,
            recovered_from_revision=revision if warnings else None,
            latest_checkpoint_id=_latest_checkpoint_id(latest_record["state"]),
            damage_warnings=warnings,
        )
        self._summaries[thread_id] = summary
        if warnings:
            self._write_latest_pointer(
                thread_id,
                revision=revision,
                content_sha256=str(latest_record["content_sha256"]),
            )

    def _migrate_legacy_thread(self, path: Path) -> None:
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise LangGraphCheckpointStoreError(
                    f"LangGraph 检查点必须是对象：{path.name}"
                )
            self._restore_thread(payload, path=path)
            thread_id = str(payload.get("thread_id", ""))
            _validate_thread_id(thread_id)
            self._persist_thread(thread_id, event_type="legacy_migrated")
            backup = self._legacy_backup_path(thread_id)
            backup.parent.mkdir(parents=True, exist_ok=True)
            path.replace(backup)
            summary = self.inspect_thread(thread_id)
            self._summaries[thread_id] = LangGraphCheckpointSummary(
                **{
                    **summary.__dict__,
                    "legacy_migrated": True,
                }
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            thread_id = path.stem
            self._summaries[thread_id] = LangGraphCheckpointSummary(
                thread_id=thread_id,
                integrity_status="invalid",
                damage_warnings=[str(error)],
            )

    def _restore_thread(self, payload: dict[str, Any], *, path: Path) -> None:
        if payload.get("format_version") != 1:
            raise LangGraphCheckpointStoreError(
                f"LangGraph 检查点格式不受支持：{path.name}"
            )
        thread_id = payload.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise LangGraphCheckpointStoreError(
                f"LangGraph 检查点缺少运行标识：{path.name}"
            )
        storage = payload.get("storage", {})
        if not isinstance(storage, dict):
            raise LangGraphCheckpointStoreError(
                f"LangGraph 检查点节点状态损坏：{path.name}"
            )
        for namespace, checkpoints in storage.items():
            if not isinstance(namespace, str) or not isinstance(checkpoints, dict):
                raise LangGraphCheckpointStoreError(
                    f"LangGraph 检查点命名空间损坏：{path.name}"
                )
            for checkpoint_id, record in checkpoints.items():
                if not isinstance(record, dict):
                    raise LangGraphCheckpointStoreError(
                        f"LangGraph 检查点记录损坏：{path.name}"
                    )
                self.storage[thread_id][namespace][checkpoint_id] = (
                    _decode_typed(record["checkpoint"]),
                    _decode_typed(record["metadata"]),
                    record.get("parent_checkpoint_id"),
                )
        writes = payload.get("writes", [])
        if not isinstance(writes, list):
            raise LangGraphCheckpointStoreError(
                f"LangGraph 检查点中间写入损坏：{path.name}"
            )
        for record in writes:
            if not isinstance(record, dict):
                continue
            outer_key = (
                thread_id,
                str(record["checkpoint_ns"]),
                str(record["checkpoint_id"]),
            )
            inner_key = (str(record["task_id"]), int(record["write_index"]))
            self.writes[outer_key][inner_key] = (
                str(record["stored_task_id"]),
                str(record["channel"]),
                _decode_typed(record["value"]),
                str(record.get("task_path", "")),
            )
        blobs = payload.get("blobs", [])
        if not isinstance(blobs, list):
            raise LangGraphCheckpointStoreError(
                f"LangGraph 检查点通道数据损坏：{path.name}"
            )
        for record in blobs:
            if not isinstance(record, dict):
                continue
            version = record.get("version")
            self.blobs[
                (
                    thread_id,
                    str(record["checkpoint_ns"]),
                    str(record["channel"]),
                    version,
                )
            ] = _decode_typed(record["value"])

    def _persist_thread(self, thread_id: str, *, event_type: str) -> None:
        _validate_thread_id(thread_id)
        self._root.mkdir(parents=True, exist_ok=True)
        state = self._thread_state(thread_id)
        previous = self._summaries.get(thread_id)
        revision = (previous.current_revision if previous is not None else 0) + 1
        previous_sha256 = self._latest_content_sha256(thread_id)
        record_without_hash = {
            "format_version": 2,
            "thread_id": thread_id,
            "revision": revision,
            "previous_sha256": previous_sha256,
            "event_type": event_type,
            "created_at": _now_iso(),
            "state": state,
        }
        content_sha256 = _json_sha256(record_without_hash)
        record = {**record_without_hash, "content_sha256": content_sha256}
        revision_path = self._revision_path(thread_id, revision)
        _atomic_write_json(
            revision_path,
            record,
            before_write=self._inject_before_checkpoint_write,
            after_fsync=self._inject_after_checkpoint_fsync,
        )
        self._inject("after_checkpoint_replace_before_latest", revision_path)
        self._write_latest_pointer(
            thread_id,
            revision=revision,
            content_sha256=content_sha256,
        )
        previous_revisions = previous.available_revisions if previous else []
        self._summaries[thread_id] = LangGraphCheckpointSummary(
            thread_id=thread_id,
            current_revision=revision,
            available_revisions=[*previous_revisions, revision],
            integrity_status="valid",
            latest_checkpoint_id=_latest_checkpoint_id(state),
            legacy_migrated=previous.legacy_migrated if previous else False,
        )

    def _thread_state(self, thread_id: str) -> dict[str, Any]:
        latest_by_namespace: dict[str, str] = {}
        required_blob_keys: set[tuple[str, str, Any]] = set()
        storage: dict[str, dict[str, dict[str, Any]]] = {}
        for namespace, checkpoints in self.storage.get(thread_id, {}).items():
            if not checkpoints:
                continue
            checkpoint_id = max(checkpoints)
            checkpoint, metadata, _parent_checkpoint_id = checkpoints[checkpoint_id]
            latest_by_namespace[namespace] = checkpoint_id
            storage[namespace] = {
                checkpoint_id: {
                    "checkpoint": _encode_typed(checkpoint),
                    "metadata": _encode_typed(metadata),
                    # 当前修订本身是完整恢复边界，不依赖另一个修订内部的父节点。
                    "parent_checkpoint_id": None,
                }
            }
            decoded = self.serde.loads_typed(checkpoint)
            channel_versions = decoded.get("channel_versions", {})
            if isinstance(channel_versions, dict):
                required_blob_keys.update(
                    (namespace, str(channel), version)
                    for channel, version in channel_versions.items()
                )
        writes = [
            {
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "write_index": write_index,
                "stored_task_id": stored_task_id,
                "channel": channel,
                "value": _encode_typed(value),
                "task_path": task_path,
            }
            for (
                stored_thread_id,
                checkpoint_ns,
                checkpoint_id,
            ), records in self.writes.items()
            if stored_thread_id == thread_id
            and latest_by_namespace.get(checkpoint_ns) == checkpoint_id
            for (task_id, write_index), (
                stored_task_id,
                channel,
                value,
                task_path,
            ) in records.items()
        ]
        blobs = [
            {
                "checkpoint_ns": checkpoint_ns,
                "channel": channel,
                "version": version,
                "value": _encode_typed(value),
            }
            for (
                stored_thread_id,
                checkpoint_ns,
                channel,
                version,
            ), value in self.blobs.items()
            if stored_thread_id == thread_id
            and (checkpoint_ns, channel, version) in required_blob_keys
        ]
        return {
            "format_version": 1,
            "thread_id": thread_id,
            "storage": storage,
            "writes": writes,
            "blobs": blobs,
        }

    def _latest_pointer_warning(
        self,
        root: Path,
        latest_record: dict[str, Any],
    ) -> str:
        path = root / "latest.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return f"最新检查点指针损坏：{error}"
        if not isinstance(payload, dict):
            return "最新检查点指针不是对象。"
        if (
            payload.get("revision") != latest_record["revision"]
            or payload.get("content_sha256") != latest_record["content_sha256"]
        ):
            return "最新检查点指针与最近有效修订不一致。"
        return ""

    def _write_latest_pointer(
        self,
        thread_id: str,
        *,
        revision: int,
        content_sha256: str,
    ) -> None:
        path = self._thread_root(thread_id) / "latest.json"
        self._inject("before_latest_pointer_update", path)
        _atomic_write_json(
            path,
            {
                "format_version": 2,
                "thread_id": thread_id,
                "revision": revision,
                "revision_file": f"revisions/{revision:06d}.json",
                "content_sha256": content_sha256,
                "updated_at": _now_iso(),
            },
        )

    def _inject_before_checkpoint_write(self, path: Path) -> None:
        self._inject("before_checkpoint_temp_write", path)

    def _inject_after_checkpoint_fsync(self, path: Path) -> None:
        self._inject("after_checkpoint_temp_fsync_before_replace", path)

    def _inject(self, point: str, path: Path) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point, path)

    def _latest_content_sha256(self, thread_id: str) -> str | None:
        summary = self._summaries.get(thread_id)
        if summary is None or summary.current_revision == 0:
            return None
        path = self._revision_path(thread_id, summary.current_revision)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = payload.get("content_sha256") if isinstance(payload, dict) else None
        return value if isinstance(value, str) else None

    def _quarantine_revisions(self, root: Path, paths: list[Path]) -> None:
        quarantine = root / "corrupt"
        quarantine.mkdir(parents=True, exist_ok=True)
        for path in paths:
            if not path.exists():
                continue
            destination = quarantine / path.name
            if destination.exists():
                destination = quarantine / f"{path.stem}-{uuid4().hex[:8]}.json"
            path.replace(destination)

    def _thread_root(self, thread_id: str) -> Path:
        _validate_thread_id(thread_id)
        return self._root / thread_id

    def _revision_path(self, thread_id: str, revision: int) -> Path:
        return self._thread_root(thread_id) / "revisions" / f"{revision:06d}.json"

    def _legacy_path(self, thread_id: str) -> Path:
        _validate_thread_id(thread_id)
        return self._root / f"{thread_id}.json"

    def _legacy_backup_path(self, thread_id: str) -> Path:
        _validate_thread_id(thread_id)
        return self._root / "legacy_backups" / f"{thread_id}.json"


@dataclass(frozen=True)
class LangGraphCheckpointSummary:
    thread_id: str
    current_revision: int = 0
    available_revisions: list[int] = field(default_factory=list)
    integrity_status: str = "missing"
    recovered_from_revision: int | None = None
    latest_checkpoint_id: str | None = None
    damage_warnings: list[str] = field(default_factory=list)
    legacy_migrated: bool = False


@dataclass(frozen=True)
class LangGraphCheckpointRevisionSummary:
    thread_id: str
    revision: int
    previous_sha256: str | None
    content_sha256: str
    event_type: str
    created_at: str


def _revision_summary(
    record: dict[str, Any],
) -> LangGraphCheckpointRevisionSummary:
    return LangGraphCheckpointRevisionSummary(
        thread_id=str(record["thread_id"]),
        revision=int(record["revision"]),
        previous_sha256=(
            str(record["previous_sha256"])
            if record.get("previous_sha256") is not None
            else None
        ),
        content_sha256=str(record["content_sha256"]),
        event_type=str(record["event_type"]),
        created_at=str(record["created_at"]),
    )


def _read_revision_record(path: Path, *, thread_id: str) -> dict[str, Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LangGraphCheckpointStoreError(
            f"LangGraph 检查点修订必须是对象：{path.name}"
        )
    if payload.get("format_version") != 2 or payload.get("thread_id") != thread_id:
        raise LangGraphCheckpointStoreError(
            f"LangGraph 检查点修订格式或线程不一致：{path.name}"
        )
    expected_revision = int(path.stem)
    if payload.get("revision") != expected_revision:
        raise LangGraphCheckpointStoreError(
            f"LangGraph 检查点修订编号不一致：{path.name}"
        )
    actual_hash = payload.get("content_sha256")
    if not isinstance(actual_hash, str) or actual_hash != _json_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    ):
        raise LangGraphCheckpointStoreError(
            f"LangGraph 检查点修订校验和不匹配：{path.name}"
        )
    state = payload.get("state")
    if not isinstance(state, dict):
        raise LangGraphCheckpointStoreError(
            f"LangGraph 检查点修订缺少可恢复状态：{path.name}"
        )
    return payload


def _latest_checkpoint_id(state: dict[str, Any]) -> str | None:
    storage = state.get("storage")
    if not isinstance(storage, dict):
        return None
    checkpoint_ids = [
        str(checkpoint_id)
        for checkpoints in storage.values()
        if isinstance(checkpoints, dict)
        for checkpoint_id in checkpoints
    ]
    return max(checkpoint_ids, default=None)


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    before_write: Callable[[Path], None] | None = None,
    after_fsync: Callable[[Path], None] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        if before_write is not None:
            before_write(path)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if after_fsync is not None:
            after_fsync(path)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _validate_thread_id(thread_id: str) -> None:
    if not thread_id.startswith("general_run_"):
        raise LangGraphCheckpointStoreError("LangGraph 线程标识必须是运行标识。")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class LangGraphCheckpointStoreError(ValueError):
    """LangGraph 节点检查点缺失或损坏。"""


def _encode_typed(value: tuple[str, bytes]) -> dict[str, str]:
    value_type, data = value
    return {
        "type": value_type,
        "data_base64": b64encode(data).decode("ascii"),
    }


def _decode_typed(value: Any) -> tuple[str, bytes]:
    if not isinstance(value, dict):
        raise LangGraphCheckpointStoreError("LangGraph 序列化值结构不正确。")
    value_type = value.get("type")
    data = value.get("data_base64")
    if not isinstance(value_type, str) or not isinstance(data, str):
        raise LangGraphCheckpointStoreError("LangGraph 序列化值字段不完整。")
    try:
        return value_type, b64decode(data.encode("ascii"), validate=True)
    except ValueError as error:
        raise LangGraphCheckpointStoreError("LangGraph 序列化值编码损坏。") from error
