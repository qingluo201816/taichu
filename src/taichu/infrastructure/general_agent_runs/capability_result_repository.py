"""CapabilityResult 的 per-result record/index JSON 持久化。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultConflictError,
    CapabilityResultIndexCorruptError,
    CapabilityResultInvalidIdentityError,
    CapabilityResultOwner,
    CapabilityResultOwnerMismatchError,
    CapabilityResultPathEscapeError,
    CapabilityResultRecord,
    CapabilityResultRecordCorruptError,
    DeleteRunOutcome,
    canonical_capability_result_json,
    canonical_capability_result_sha256,
    capability_result_id,
)

_RESULT_ID_PATTERN = re.compile(r"cr_[a-f0-9]{64}\Z")


class _CapabilityResultIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: CapabilityResultOwner
    result_id: str = Field(pattern=r"^cr_[a-f0-9]{64}$")
    record_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    semantic_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    committed_at: str = Field(min_length=1, max_length=128)
    entry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_entry_hash(self) -> _CapabilityResultIndexEntry:
        if self.entry_sha256 != _index_entry_sha256(
            owner=self.owner,
            result_id=self.result_id,
            record_content_sha256=self.record_content_sha256,
            semantic_content_sha256=self.semantic_content_sha256,
            committed_at=self.committed_at,
        ):
            raise ValueError("能力结果索引条目校验和不匹配。")
        return self


class JsonGeneralAgentCapabilityResultRepository:
    """以独立 create-once record/index 保存每个可恢复能力结果。"""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)

    async def get_completed(
        self,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord | None:
        return await asyncio.to_thread(self._get_completed_sync, owner, result_id)

    async def commit_completed(
        self,
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> CapabilityResultRecord:
        return await asyncio.to_thread(self._commit_completed_sync, owner, record)

    async def list_for_run(
        self,
        owner: CapabilityResultOwner,
    ) -> tuple[CapabilityResultRecord, ...]:
        return await asyncio.to_thread(self._list_for_run_sync, owner)

    async def delete_run(
        self,
        owner: CapabilityResultOwner,
    ) -> DeleteRunOutcome:
        return await asyncio.to_thread(self._delete_run_sync, owner)

    def _get_completed_sync(
        self,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord | None:
        _validate_result_id(result_id)
        owner_root = self._owner_root(owner)
        record_path = self._result_path(owner_root, "completed", result_id)
        index_path = self._result_path(owner_root, "index", result_id)
        record_exists = record_path.is_file()
        index_exists = index_path.is_file()
        if not record_exists and not index_exists:
            return None
        if not record_exists:
            raise CapabilityResultRecordCorruptError(
                "能力结果索引存在，但对应 Completed record 缺失。"
            )
        record = self._read_record(record_path, owner=owner, result_id=result_id)
        if not index_exists:
            self._publish_index(owner_root, record)
            return record
        entry = self._read_index(index_path, owner=owner, result_id=result_id)
        self._validate_entry_record_relation(entry, record)
        return record

    def _commit_completed_sync(
        self,
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> CapabilityResultRecord:
        self._validate_commit_request(owner, record)
        owner_root = self._owner_root(owner)
        record_path = self._result_path(
            owner_root,
            "completed",
            record.result_id,
        )
        record_bytes = canonical_capability_result_json(record) + b"\n"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        self._publish_create_once(record_path, record_bytes)

        winner = self._read_record(
            record_path,
            owner=owner,
            result_id=record.result_id,
        )
        if winner.semantic_content_sha256 != record.semantic_content_sha256:
            raise CapabilityResultConflictError()
        self._publish_index(owner_root, winner)
        return winner

    def _list_for_run_sync(
        self,
        owner: CapabilityResultOwner,
    ) -> tuple[CapabilityResultRecord, ...]:
        owner_root = self._owner_root(owner)
        index_root = self._child_path(owner_root, "index")
        if not index_root.is_dir():
            return ()
        records: list[CapabilityResultRecord] = []
        for index_path in sorted(index_root.glob("*.json")):
            result_id = index_path.stem
            if _RESULT_ID_PATTERN.fullmatch(result_id) is None:
                raise CapabilityResultIndexCorruptError(
                    f"能力结果索引文件名无效：{index_path.name}"
                )
            checked_index_path = self._result_path(
                owner_root,
                "index",
                result_id,
            )
            entry = self._read_index(
                checked_index_path,
                owner=owner,
                result_id=result_id,
            )
            record_path = self._result_path(
                owner_root,
                "completed",
                result_id,
            )
            if not record_path.is_file():
                raise CapabilityResultRecordCorruptError(
                    f"能力结果索引缺少对应记录：{result_id}"
                )
            record = self._read_record(
                record_path,
                owner=owner,
                result_id=result_id,
            )
            self._validate_entry_record_relation(entry, record)
            records.append(record)
        return tuple(
            sorted(records, key=lambda item: (item.committed_at, item.result_id))
        )

    def _delete_run_sync(
        self,
        owner: CapabilityResultOwner,
    ) -> DeleteRunOutcome:
        owner_root = self._owner_root(owner)
        if not owner_root.exists():
            return DeleteRunOutcome.NOT_FOUND
        if not owner_root.is_dir():
            raise CapabilityResultPathEscapeError(
                "能力结果 owner 路径不是目录，拒绝删除。"
            )
        shutil.rmtree(owner_root)
        return DeleteRunOutcome.DELETED

    def _publish_index(
        self,
        owner_root: Path,
        record: CapabilityResultRecord,
    ) -> _CapabilityResultIndexEntry:
        entry = _build_index_entry(record)
        index_path = self._result_path(
            owner_root,
            "index",
            record.result_id,
        )
        index_path.parent.mkdir(parents=True, exist_ok=True)
        self._publish_create_once(
            index_path,
            canonical_capability_result_json(entry) + b"\n",
        )
        winner = self._read_index(
            index_path,
            owner=record.owner,
            result_id=record.result_id,
        )
        if winner != entry:
            raise CapabilityResultConflictError(
                "同一能力结果标识对应的索引内容发生冲突。"
            )
        self._validate_entry_record_relation(winner, record)
        return winner

    def _publish_create_once(self, final_path: Path, payload: bytes) -> bool:
        final_path = self._assert_contained(final_path, self._root)
        temporary = final_path.with_name(f".{final_path.name}.{uuid4().hex}.tmp")
        temporary = self._assert_contained(temporary, self._root)
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, final_path)
            except FileExistsError:
                return False
            _fsync_directory(final_path.parent)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_commit_request(
        self,
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> None:
        _validate_result_id(record.result_id)
        if record.owner != owner or record.identity.owner != owner:
            raise CapabilityResultOwnerMismatchError()
        if capability_result_id(record.identity) != record.result_id:
            raise CapabilityResultInvalidIdentityError("能力结果标识与身份载荷不一致。")

    def _read_record(
        self,
        path: Path,
        *,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord:
        payload = self._read_object(path, kind="record")
        if payload.get("owner") != owner.model_dump(mode="json"):
            raise CapabilityResultOwnerMismatchError()
        if payload.get("result_id") != result_id:
            raise CapabilityResultRecordCorruptError(
                "能力结果记录中的结果标识与文件名不一致。"
            )
        try:
            return CapabilityResultRecord.model_validate(payload)
        except ValidationError as error:
            raise CapabilityResultRecordCorruptError(
                f"能力结果记录未通过完整性校验：{error}"
            ) from error

    def _read_index(
        self,
        path: Path,
        *,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> _CapabilityResultIndexEntry:
        payload = self._read_object(path, kind="index")
        try:
            entry = _CapabilityResultIndexEntry.model_validate(payload)
        except ValidationError as error:
            raise CapabilityResultIndexCorruptError(
                f"能力结果索引未通过完整性校验：{error}"
            ) from error
        if entry.owner != owner or entry.result_id != result_id:
            raise CapabilityResultIndexCorruptError(
                "能力结果索引的 owner 或结果标识与路径不一致。"
            )
        return entry

    def _read_object(self, path: Path, *, kind: str) -> dict[str, Any]:
        path = self._assert_contained(path, self._root)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            if kind == "index":
                raise CapabilityResultIndexCorruptError(
                    f"无法读取能力结果索引：{path.name}"
                ) from error
            raise CapabilityResultRecordCorruptError(
                f"无法读取能力结果记录：{path.name}"
            ) from error
        if not isinstance(payload, dict):
            if kind == "index":
                raise CapabilityResultIndexCorruptError(
                    "能力结果索引必须是 JSON 对象。"
                )
            raise CapabilityResultRecordCorruptError("能力结果记录必须是 JSON 对象。")
        return payload

    @staticmethod
    def _validate_entry_record_relation(
        entry: _CapabilityResultIndexEntry,
        record: CapabilityResultRecord,
    ) -> None:
        if (
            entry.owner != record.owner
            or entry.result_id != record.result_id
            or entry.record_content_sha256 != record.content_sha256
            or entry.semantic_content_sha256 != record.semantic_content_sha256
            or entry.committed_at != record.committed_at
        ):
            raise CapabilityResultRecordCorruptError(
                "能力结果索引与 Completed record 的内容身份不一致。"
            )

    def _owner_root(self, owner: CapabilityResultOwner) -> Path:
        candidate = (self._root / owner.conversation_id / owner.run_id).resolve(
            strict=False
        )
        return self._assert_contained(candidate, self._root)

    def _child_path(self, owner_root: Path, child: str) -> Path:
        return self._assert_contained(
            (owner_root / child).resolve(strict=False),
            owner_root,
        )

    def _result_path(
        self,
        owner_root: Path,
        category: str,
        result_id: str,
    ) -> Path:
        _validate_result_id(result_id)
        category_root = self._child_path(owner_root, category)
        return self._assert_contained(
            (category_root / f"{result_id}.json").resolve(strict=False),
            owner_root,
        )

    @staticmethod
    def _assert_contained(path: Path, root: Path) -> Path:
        checked_root = root.resolve(strict=False)
        checked_path = path.resolve(strict=False)
        comparable_root = _comparable_path(checked_root)
        comparable_path = _comparable_path(checked_path)
        try:
            common = os.path.commonpath((comparable_root, comparable_path))
        except ValueError as error:
            raise CapabilityResultPathEscapeError() from error
        if common != comparable_root:
            raise CapabilityResultPathEscapeError()
        return checked_path


def _validate_result_id(result_id: str) -> None:
    if (
        not isinstance(result_id, str)
        or _RESULT_ID_PATTERN.fullmatch(result_id) is None
    ):
        raise CapabilityResultInvalidIdentityError(
            "能力结果标识必须是 cr_ 加 64 位小写十六进制哈希。"
        )


def _comparable_path(path: Path) -> str:
    value = os.path.normcase(os.fspath(path))
    if os.name != "nt":
        return value
    value = value.replace("/", "\\")
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def _build_index_entry(
    record: CapabilityResultRecord,
) -> _CapabilityResultIndexEntry:
    entry_sha256 = _index_entry_sha256(
        owner=record.owner,
        result_id=record.result_id,
        record_content_sha256=record.content_sha256,
        semantic_content_sha256=record.semantic_content_sha256,
        committed_at=record.committed_at,
    )
    return _CapabilityResultIndexEntry(
        owner=record.owner,
        result_id=record.result_id,
        record_content_sha256=record.content_sha256,
        semantic_content_sha256=record.semantic_content_sha256,
        committed_at=record.committed_at,
        entry_sha256=entry_sha256,
    )


def _index_entry_sha256(
    *,
    owner: CapabilityResultOwner,
    result_id: str,
    record_content_sha256: str,
    semantic_content_sha256: str,
    committed_at: str,
) -> str:
    return canonical_capability_result_sha256(
        {
            "owner": owner,
            "result_id": result_id,
            "record_content_sha256": record_content_sha256,
            "semantic_content_sha256": semantic_content_sha256,
            "committed_at": committed_at,
        }
    )


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
