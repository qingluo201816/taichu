"""评测派生工件的 append-only 仓储与小型可变清单。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_json_bytes,
)

_COLLECTIONS = frozenset(
    {
        "runs",
        "experiments",
        "iterations",
        "issue-correlations",
        "comparisons",
        "closure-leases",
        "indexes",
        "idempotency",
        "workspaces",
    }
)


class ArtifactConflictError(RuntimeError):
    """同一不可变身份已存在不同内容。"""


class LeaseConflictError(RuntimeError):
    """闭包租约 revision 已变化。"""


class GeneralAgentBenchmarkArtifactRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = threading.RLock()

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for name in sorted(_COLLECTIONS):
            (self.root / name).mkdir(exist_ok=True)

    def _target(self, collection: str, object_id: str) -> Path:
        if collection not in _COLLECTIONS:
            raise ValueError(f"未知评测工件集合：{collection}")
        if not object_id or any(char in object_id for char in ("/", "\\", "..")):
            raise ValueError("工件标识不得为空、包含路径分隔符或 ..。")
        self.ensure_layout()
        target = (self.root / collection / f"{object_id}.json").resolve()
        if not target.is_relative_to(self.root / collection):
            raise ValueError("工件路径越界。")
        return target

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"评测工件必须是 JSON 对象：{path}")
        return value

    def read(self, collection: str, object_id: str) -> dict[str, Any]:
        return self._read_path(self._target(collection, object_id))

    def append_immutable(
        self,
        *,
        collection: str,
        object_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        target = self._target(collection, object_id)
        encoded = canonical_json_bytes(payload)
        with self._lock:
            if target.exists():
                existing = target.read_bytes()
                if existing != encoded:
                    raise ArtifactConflictError(
                        f"不可变工件已冻结且内容不同：{collection}/{object_id}"
                    )
                return self._read_path(target)
            temporary = self._write_temporary(target.parent, encoded)
            try:
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    existing = target.read_bytes()
                    if existing != encoded:
                        raise ArtifactConflictError(
                            f"不可变工件并发冲突：{collection}/{object_id}"
                        ) from None
            finally:
                temporary.unlink(missing_ok=True)
        return self._read_path(target)

    def replace_index(
        self,
        index_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        target = self._target("indexes", index_id)
        encoded = canonical_json_bytes(payload)
        with self._lock:
            temporary = self._write_temporary(target.parent, encoded)
            os.replace(temporary, target)
        return self._read_path(target)

    def claim_idempotency(
        self,
        *,
        key: str,
        submission_hash: str,
        result_ref: str,
    ) -> dict[str, Any]:
        claim_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.append_immutable(
            collection="idempotency",
            object_id=claim_id,
            payload={
                "claim_id": claim_id,
                "submission_hash": submission_hash,
                "result_ref": result_ref,
            },
        )

    def acquire_closure_lease(
        self,
        *,
        lease_key: str,
        owner: str,
        expected_revision: int,
        expires_at: str,
    ) -> dict[str, Any]:
        lease_id = hashlib.sha256(lease_key.encode("utf-8")).hexdigest()
        target = self._target("closure-leases", lease_id)
        with self._lock:
            current = self._read_path(target) if target.exists() else None
            current_revision = int(current["revision"]) if current else 0
            if current_revision != expected_revision:
                raise LeaseConflictError(
                    f"闭包租约 revision 冲突：当前 {current_revision}，"
                    f"期望 {expected_revision}。"
                )
            payload = {
                "lease_id": lease_id,
                "owner": owner,
                "revision": current_revision + 1,
                "expires_at": expires_at,
            }
            temporary = self._write_temporary(
                target.parent,
                canonical_json_bytes(payload),
            )
            os.replace(temporary, target)
            return payload

    @staticmethod
    def _write_temporary(parent: Path, content: bytes) -> Path:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".pending-",
            suffix=".json",
            dir=parent,
        )
        path = Path(raw_path)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path
