"""文件型不可变评测关联记录与可验证反向索引。"""

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
from taichu.application.evaluations.general_agent_benchmark.correlation import (
    CorrelationSubjectRef,
    EvaluationCorrelationRecord,
)


class CorrelationAsymmetryError(RuntimeError):
    """关系记录和任一反向索引不对称。"""


class JsonEvaluationCorrelationRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._records = self.root / "records"
        self._subjects = self.root / "subjects"
        self._records.mkdir(parents=True, exist_ok=True)
        self._subjects.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def subject_index_path(self, subject: CorrelationSubjectRef) -> Path:
        digest = hashlib.sha256(subject.key.encode("utf-8")).hexdigest()
        return self._subjects / f"{digest}.json"

    def _record_path(self, relation_id: str) -> Path:
        return self._records / f"{relation_id}.json"

    @staticmethod
    def _atomic_replace(path: Path, payload: dict[str, Any]) -> None:
        descriptor, raw = tempfile.mkstemp(
            prefix=".pending-",
            suffix=".json",
            dir=path.parent,
        )
        temporary = Path(raw)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(payload))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def append(
        self,
        record: EvaluationCorrelationRecord,
    ) -> EvaluationCorrelationRecord:
        record.verify_identity()
        target = self._record_path(record.relation_id)
        encoded = canonical_json_bytes(record)
        with self._lock:
            if target.exists():
                if target.read_bytes() != encoded:
                    raise ValueError("相同关联 ID 已绑定不同内容。")
            else:
                descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            for subject in record.subjects:
                index_path = self.subject_index_path(subject)
                if index_path.exists():
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                    relation_ids = set(index["relation_ids"])
                else:
                    relation_ids = set()
                relation_ids.add(record.relation_id)
                self._atomic_replace(
                    index_path,
                    {
                        "subject": subject.model_dump(mode="json"),
                        "relation_ids": sorted(relation_ids),
                    },
                )
        return record

    def _read_record(self, relation_id: str) -> EvaluationCorrelationRecord:
        path = self._record_path(relation_id)
        record = EvaluationCorrelationRecord.model_validate_json(path.read_bytes())
        record.verify_identity()
        return record

    def read_closure(
        self,
        subject: CorrelationSubjectRef,
    ) -> tuple[CorrelationSubjectRef, ...]:
        index_path = self.subject_index_path(subject)
        if not index_path.exists():
            return ()
        index = json.loads(index_path.read_text(encoding="utf-8"))
        indexed_subject = CorrelationSubjectRef.model_validate(index["subject"])
        if indexed_subject != subject:
            raise CorrelationAsymmetryError("反向索引 subject identity 不一致。")
        closure: dict[str, CorrelationSubjectRef] = {}
        for relation_id in index["relation_ids"]:
            record = self._read_record(relation_id)
            if subject not in record.subjects:
                raise CorrelationAsymmetryError("反向索引指向不含该主题的关系。")
            for related in record.subjects:
                related_index_path = self.subject_index_path(related)
                if not related_index_path.exists():
                    raise CorrelationAsymmetryError("关联端点缺少反向索引。")
                related_index = json.loads(
                    related_index_path.read_text(encoding="utf-8")
                )
                if relation_id not in related_index["relation_ids"]:
                    raise CorrelationAsymmetryError("关联端点反向索引不对称。")
                closure[related.key] = related
        return tuple(closure[key] for key in sorted(closure))
