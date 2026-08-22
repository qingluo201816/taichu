"""通用 Agent 可恢复能力结果的应用层合同。

CapabilityResult 只保存无副作用 Tool 与 Subagent 已完成的运行结果，用于同一
会话、同一运行内的精确恢复。写入型 Tool 的副作用仍由 Effect 合同负责。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
    runtime_checkable,
)

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)

CAPABILITY_RESULT_ID_TAG = "taichu.general_agent.capability_result_id@1"
_STABLE_PATH_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256_PATTERN = r"^[a-f0-9]{64}$"
_RESULT_ID_PATTERN = r"^cr_[a-f0-9]{64}$"


def _validate_stable_path_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("稳定路径标识必须是字符串。")
    if value in {".", ".."} or _STABLE_PATH_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "稳定路径标识必须是原值即规范值的 ASCII 字母、数字、点、"
            "下划线或连字符，且不得形成路径逃逸。"
        )
    return value


StablePathId = Annotated[str, BeforeValidator(_validate_stable_path_id)]


class _CapabilityResultModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CapabilityResultOwner(_CapabilityResultModel):
    """能力结果不可省略的双层所有者。"""

    conversation_id: StablePathId
    run_id: StablePathId


class ResultIdentityPayload(_CapabilityResultModel):
    """决定一次能力调用是否可以安全复用的完整身份。"""

    owner: CapabilityResultOwner
    plan_revision: StrictInt = Field(ge=0)
    node_id: StablePathId
    attempt_id: StablePathId
    capability_kind: Literal["tool", "subagent"]
    capability_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    handler_identity_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_schema_sha256: str = Field(pattern=_SHA256_PATTERN)
    output_schema_sha256: str = Field(pattern=_SHA256_PATTERN)


class CapabilityResultRecord(_CapabilityResultModel):
    """已完成且可恢复的完整能力结果记录。"""

    owner: CapabilityResultOwner
    identity: ResultIdentityPayload
    result_id: str = Field(pattern=_RESULT_ID_PATTERN)
    output: dict[str, Any]
    source_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    trace_id: str | None = None
    identity_payload_sha256: str = Field(pattern=_SHA256_PATTERN)
    semantic_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    committed_at: str = Field(min_length=1, max_length=128)
    content_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_identity_and_hashes(self) -> CapabilityResultRecord:
        if self.owner != self.identity.owner:
            raise ValueError("能力结果所有者与身份载荷所有者不一致。")
        if self.result_id != capability_result_id(self.identity):
            raise ValueError("能力结果标识不是身份载荷的规范哈希。")
        if self.identity_payload_sha256 != canonical_capability_result_sha256(
            self.identity
        ):
            raise ValueError("能力结果身份载荷校验和不匹配。")
        if self.semantic_content_sha256 != _semantic_content_sha256(
            owner=self.owner,
            identity=self.identity,
            result_id=self.result_id,
            output=self.output,
            source_refs=self.source_refs,
            artifact_refs=self.artifact_refs,
            trace_id=self.trace_id,
            identity_payload_sha256=self.identity_payload_sha256,
        ):
            raise ValueError("能力结果语义内容校验和不匹配。")
        if self.content_sha256 != _record_content_sha256(
            owner=self.owner,
            identity=self.identity,
            result_id=self.result_id,
            output=self.output,
            source_refs=self.source_refs,
            artifact_refs=self.artifact_refs,
            trace_id=self.trace_id,
            identity_payload_sha256=self.identity_payload_sha256,
            semantic_content_sha256=self.semantic_content_sha256,
            committed_at=self.committed_at,
        ):
            raise ValueError("能力结果记录内容校验和不匹配。")
        return self


class DeleteRunOutcome(StrEnum):
    """删除某个 owner 的运行结果时可审计的确定性结论。"""

    DELETED = "deleted"
    NOT_FOUND = "not_found"


class CapabilityResultErrorCode(StrEnum):
    OWNER_NOT_FOUND = "capability_result_owner_not_found"
    OWNER_MISMATCH = "capability_result_owner_mismatch"
    INVALID_IDENTITY = "capability_result_invalid_identity"
    PATH_ESCAPE = "capability_result_path_escape"
    CONFLICT = "capability_result_conflict"
    INDEX_CORRUPT = "capability_result_index_corrupt"
    RECORD_CORRUPT = "capability_result_record_corrupt"


class CapabilityResultContractError(RuntimeError):
    """CapabilityResult 合同失败；错误码可供恢复流程稳定判定。"""

    def __init__(
        self,
        code: CapabilityResultErrorCode,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class CapabilityResultOwnerNotFoundError(CapabilityResultContractError):
    def __init__(self, message: str = "未找到能力结果所属运行。") -> None:
        super().__init__(CapabilityResultErrorCode.OWNER_NOT_FOUND, message)


class CapabilityResultOwnerMismatchError(CapabilityResultContractError):
    def __init__(self, message: str = "能力结果所有者不匹配。") -> None:
        super().__init__(CapabilityResultErrorCode.OWNER_MISMATCH, message)


class CapabilityResultInvalidIdentityError(CapabilityResultContractError):
    def __init__(self, message: str = "能力结果身份无效。") -> None:
        super().__init__(CapabilityResultErrorCode.INVALID_IDENTITY, message)


class CapabilityResultPathEscapeError(CapabilityResultContractError):
    def __init__(self, message: str = "能力结果路径越过允许根目录。") -> None:
        super().__init__(CapabilityResultErrorCode.PATH_ESCAPE, message)


class CapabilityResultConflictError(CapabilityResultContractError):
    def __init__(self, message: str = "同一能力结果标识存在内容冲突。") -> None:
        super().__init__(CapabilityResultErrorCode.CONFLICT, message)


class CapabilityResultIndexCorruptError(CapabilityResultContractError):
    def __init__(self, message: str = "能力结果索引损坏。") -> None:
        super().__init__(CapabilityResultErrorCode.INDEX_CORRUPT, message)


class CapabilityResultRecordCorruptError(CapabilityResultContractError):
    def __init__(self, message: str = "能力结果记录损坏。") -> None:
        super().__init__(CapabilityResultErrorCode.RECORD_CORRUPT, message)


@runtime_checkable
class GeneralAgentCapabilityResultRepository(Protocol):
    """CapabilityResult 持久化协议。

    已知父 owner 尚无目录时，读取返回 ``None``、列举返回空元组、删除返回
    ``NOT_FOUND``；父 owner 是否真实存在由调用此协议的应用服务先行校验。
    """

    async def get_completed(
        self,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord | None: ...

    async def commit_completed(
        self,
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> CapabilityResultRecord: ...

    async def list_for_run(
        self,
        owner: CapabilityResultOwner,
    ) -> tuple[CapabilityResultRecord, ...]: ...

    async def delete_run(
        self,
        owner: CapabilityResultOwner,
    ) -> DeleteRunOutcome: ...


def capability_result_id(identity: ResultIdentityPayload) -> str:
    """按机器兼容标签与规范 JSON 计算稳定结果标识。"""

    digest = hashlib.sha256(
        CAPABILITY_RESULT_ID_TAG.encode("utf-8")
        + b"\0"
        + canonical_capability_result_json(identity)
    ).hexdigest()
    return f"cr_{digest}"


def canonical_capability_result_sha256(value: object) -> str:
    return hashlib.sha256(canonical_capability_result_json(value)).hexdigest()


def canonical_capability_result_json(value: object) -> bytes:
    """输出 NFC、键排序、固定分隔符的规范 UTF-8 JSON。"""

    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_capability_result_record(
    *,
    identity: ResultIdentityPayload,
    output: dict[str, Any],
    committed_at: str,
    source_refs: tuple[str, ...] = (),
    artifact_refs: tuple[str, ...] = (),
    trace_id: str | None = None,
) -> CapabilityResultRecord:
    """从完整身份与实际结果构造自校验 Completed record。"""

    result_id = capability_result_id(identity)
    identity_payload_sha256 = canonical_capability_result_sha256(identity)
    semantic_content_sha256 = _semantic_content_sha256(
        owner=identity.owner,
        identity=identity,
        result_id=result_id,
        output=output,
        source_refs=source_refs,
        artifact_refs=artifact_refs,
        trace_id=trace_id,
        identity_payload_sha256=identity_payload_sha256,
    )
    content_sha256 = _record_content_sha256(
        owner=identity.owner,
        identity=identity,
        result_id=result_id,
        output=output,
        source_refs=source_refs,
        artifact_refs=artifact_refs,
        trace_id=trace_id,
        identity_payload_sha256=identity_payload_sha256,
        semantic_content_sha256=semantic_content_sha256,
        committed_at=committed_at,
    )
    return CapabilityResultRecord(
        owner=identity.owner,
        identity=identity,
        result_id=result_id,
        output=output,
        source_refs=source_refs,
        artifact_refs=artifact_refs,
        trace_id=trace_id,
        identity_payload_sha256=identity_payload_sha256,
        semantic_content_sha256=semantic_content_sha256,
        committed_at=committed_at,
        content_sha256=content_sha256,
    )


def _semantic_content_sha256(
    *,
    owner: CapabilityResultOwner,
    identity: ResultIdentityPayload,
    result_id: str,
    output: dict[str, Any],
    source_refs: tuple[str, ...],
    artifact_refs: tuple[str, ...],
    trace_id: str | None,
    identity_payload_sha256: str,
) -> str:
    return canonical_capability_result_sha256(
        {
            "owner": owner,
            "identity": identity,
            "result_id": result_id,
            "output": output,
            "source_refs": source_refs,
            "artifact_refs": artifact_refs,
            "trace_id": trace_id,
            "identity_payload_sha256": identity_payload_sha256,
        }
    )


def _record_content_sha256(
    *,
    owner: CapabilityResultOwner,
    identity: ResultIdentityPayload,
    result_id: str,
    output: dict[str, Any],
    source_refs: tuple[str, ...],
    artifact_refs: tuple[str, ...],
    trace_id: str | None,
    identity_payload_sha256: str,
    semantic_content_sha256: str,
    committed_at: str,
) -> str:
    return canonical_capability_result_sha256(
        {
            "owner": owner,
            "identity": identity,
            "result_id": result_id,
            "output": output,
            "source_refs": source_refs,
            "artifact_refs": artifact_refs,
            "trace_id": trace_id,
            "identity_payload_sha256": identity_payload_sha256,
            "semantic_content_sha256": semantic_content_sha256,
            "committed_at": committed_at,
        }
    )


def _canonical_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, StrEnum):
        return _canonical_value(value.value)
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("能力结果规范 JSON 不允许 NaN 或 Infinity。")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("能力结果规范 JSON 的对象键必须是字符串。")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError("NFC 规范化后出现重复对象键。")
            normalized[normalized_key] = _canonical_value(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"能力结果包含无法规范化的值：{type(value).__name__}")

