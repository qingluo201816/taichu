"""通用写作助手自动运行记忆的应用层模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentMemoryModel(BaseModel):
    """拒绝额外字段的不可变运行记忆模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentMemoryKind(StrEnum):
    """工作记忆的内容类型；相关记忆是运行时选择结果，不重复持久化。"""

    USER_INSTRUCTION = "user_instruction"
    TASK_SUMMARY = "task_summary"
    RESOURCE_SUMMARY = "resource_summary"
    WORK_NOTE = "work_note"
    UNRESOLVED_ISSUE = "unresolved_issue"
    FACT_REFERENCE = "fact_reference"


class AgentMemorySensitivity(StrEnum):
    NORMAL = "normal"
    PRIVATE = "private"
    RESTRICTED = "restricted"


_LEGACY_KIND_MAP = {
    "author_constraint": AgentMemoryKind.USER_INSTRUCTION.value,
    "human_correction": AgentMemoryKind.USER_INSTRUCTION.value,
    "task_conclusion": AgentMemoryKind.TASK_SUMMARY.value,
    "artifact_reference": AgentMemoryKind.RESOURCE_SUMMARY.value,
    "execution_summary": AgentMemoryKind.WORK_NOTE.value,
    "decision": AgentMemoryKind.WORK_NOTE.value,
}


class AgentMemoryEntry(AgentMemoryModel):
    """一条由 Runtime 自动写入、自动过期且可追溯的工作记忆。"""

    memory_id: str = Field(pattern=r"^memory_\d{8}_\d{6}_[a-z0-9]{8}$")
    kind: AgentMemoryKind
    content: str = Field(min_length=1, max_length=20_000)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    artifact_refs: list[str] = Field(default_factory=list, max_length=100)
    run_ids: list[str] = Field(default_factory=list, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=128)
    created_request_index: int = Field(default=1, ge=1)
    expires_after_request_index: int | None = Field(default=None, ge=1)
    retention_priority: int = Field(default=50, ge=0, le=100)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    expires_at: str | None = Field(default=None, max_length=64)
    supersedes_memory_id: str | None = Field(default=None, max_length=128)
    content_sha256: str = Field(min_length=64, max_length=64)
    sensitivity: AgentMemorySensitivity = AgentMemorySensitivity.NORMAL
    deleted_at: str | None = Field(default=None, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_record(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        payload.pop("lifecycle", None)
        payload.pop("scope", None)
        kind = payload.get("kind")
        if isinstance(kind, str):
            payload["kind"] = _LEGACY_KIND_MAP.get(kind, kind)
        payload.setdefault("created_request_index", 1)
        payload.setdefault("expires_after_request_index", None)
        return payload

    @model_validator(mode="after")
    def validate_integrity(self) -> Self:
        if self.content_sha256 != memory_content_sha256(self.content):
            raise ValueError("运行记忆内容校验和不匹配。")
        if self.kind is AgentMemoryKind.FACT_REFERENCE and not self.source_refs:
            raise ValueError("事实引用记忆必须包含稳定来源引用。")
        if (
            self.expires_after_request_index is not None
            and self.expires_after_request_index < self.created_request_index
        ):
            raise ValueError("运行记忆的过期请求序号不能早于创建序号。")
        return self

    def is_active(self, *, as_of: str, request_index: int) -> bool:
        if self.deleted_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= as_of:
            return False
        return not (
            self.expires_after_request_index is not None
            and request_index > self.expires_after_request_index
        )


class MemoryWriteCandidate(AgentMemoryModel):
    """由 Runtime 在明确节点提交的自动记忆写入。"""

    kind: AgentMemoryKind
    content: str = Field(min_length=1, max_length=20_000)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    artifact_refs: list[str] = Field(default_factory=list, max_length=100)
    run_ids: list[str] = Field(default_factory=list, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=128)
    created_request_index: int = Field(ge=1)
    expires_after_request_index: int | None = Field(default=None, ge=1)
    retention_priority: int = Field(default=50, ge=0, le=100)
    expires_at: str | None = Field(default=None, max_length=64)
    supersedes_memory_id: str | None = Field(default=None, max_length=128)
    sensitivity: AgentMemorySensitivity = AgentMemorySensitivity.NORMAL


class AgentMemoryQuery(AgentMemoryModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    current_request_index: int = Field(ge=1)
    query_text: str = Field(default="", max_length=40_000)
    kinds: list[AgentMemoryKind] = Field(default_factory=list, max_length=20)
    run_id: str | None = Field(default=None, max_length=128)
    top_k: int | None = Field(default=None, ge=1, le=100)
    char_budget: int | None = Field(default=None, ge=1, le=200_000)
    as_of: str | None = Field(default=None, max_length=64)


class AgentMemorySelection(AgentMemoryModel):
    entries: list[AgentMemoryEntry] = Field(default_factory=list)
    selected_memory_ids: list[str] = Field(default_factory=list)
    candidate_count: int = Field(default=0, ge=0)
    selected_char_count: int = Field(default=0, ge=0)
    dropped_duplicate_count: int = Field(default=0, ge=0)
    dropped_budget_count: int = Field(default=0, ge=0)
    policy_snapshot: dict[str, int | float | str] = Field(default_factory=dict)


def memory_content_sha256(content: str) -> str:
    return sha256(content.strip().encode("utf-8")).hexdigest()


def memory_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
