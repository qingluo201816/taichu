"""外部访问、作者写入授权与幂等控制。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import to_jsonable_python


class GrantReference(BaseModel):
    """供 Runtime 或应用层保存的短期授权引用。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: str = Field(min_length=1)
    grant_type: str = Field(pattern=r"^(external_access|author_write)$")
    expires_at: str = Field(min_length=1)


@dataclass(slots=True)
class _ExternalGrant:
    grant_id: str
    task_id: str
    user_intent_ref: str
    allowed_tools: frozenset[str]
    expires_at: datetime
    remaining_uses: int


@dataclass(slots=True)
class _AuthorGrant:
    grant_id: str
    task_id: str
    tool_name: str
    input_sha256: str
    resource_scopes: tuple[str, ...]
    second_confirmation: bool
    expires_at: datetime
    remaining_uses: int


@dataclass(slots=True)
class _IdempotencyRecord:
    input_sha256: str
    output_payload: dict[str, object]


class InvocationPolicyService:
    """在 Runtime 到来前提供可实际执行的进程内权限门禁。"""

    def __init__(self) -> None:
        self._external_grants: dict[str, _ExternalGrant] = {}
        self._author_grants: dict[str, _AuthorGrant] = {}
        self._idempotency: dict[tuple[str, str], _IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def issue_external_access(
        self,
        *,
        task_id: str,
        user_intent_ref: str,
        allowed_tools: frozenset[str],
        max_uses: int = 20,
        ttl_seconds: int = 1_800,
    ) -> GrantReference:
        """根据明确用户意图签发限范围外部访问许可。"""
        if not user_intent_ref.strip():
            raise InvocationAuthorizationError("外部访问授权必须关联明确用户意图。")
        if not allowed_tools:
            raise InvocationAuthorizationError("外部访问授权必须指定允许的工具。")
        now = datetime.now(UTC)
        grant_id = f"external_{uuid4().hex}"
        grant = _ExternalGrant(
            grant_id=grant_id,
            task_id=task_id,
            user_intent_ref=user_intent_ref,
            allowed_tools=allowed_tools,
            expires_at=now + timedelta(seconds=ttl_seconds),
            remaining_uses=max_uses,
        )
        async with self._lock:
            self._external_grants[grant_id] = grant
        return GrantReference(
            grant_id=grant_id,
            grant_type="external_access",
            expires_at=_as_iso(grant.expires_at),
        )

    async def issue_author_write(
        self,
        *,
        task_id: str,
        tool_name: str,
        input_payload: BaseModel | Mapping[str, object],
        resource_scopes: tuple[str, ...],
        second_confirmation: bool = False,
        max_uses: int = 1,
        ttl_seconds: int = 900,
    ) -> GrantReference:
        """把作者确认绑定到工具、资源范围和规范化输入哈希。"""
        if not resource_scopes:
            raise InvocationAuthorizationError("作者写入授权必须绑定资源范围。")
        now = datetime.now(UTC)
        grant_id = f"author_{uuid4().hex}"
        grant = _AuthorGrant(
            grant_id=grant_id,
            task_id=task_id,
            tool_name=tool_name,
            input_sha256=canonical_input_hash(input_payload),
            resource_scopes=resource_scopes,
            second_confirmation=second_confirmation,
            expires_at=now + timedelta(seconds=ttl_seconds),
            remaining_uses=max_uses,
        )
        async with self._lock:
            self._author_grants[grant_id] = grant
        return GrantReference(
            grant_id=grant_id,
            grant_type="author_write",
            expires_at=_as_iso(grant.expires_at),
        )

    async def authorize_external(
        self,
        *,
        grant_id: str | None,
        task_id: str,
        tool_name: str,
    ) -> str:
        """校验并消费一次外部访问许可。"""
        if not grant_id:
            raise InvocationAuthorizationError("本次任务没有外部访问许可。")
        async with self._lock:
            grant = self._external_grants.get(grant_id)
            if grant is None:
                raise InvocationAuthorizationError("外部访问许可不存在或已失效。")
            _ensure_not_expired(grant.expires_at, "外部访问许可")
            if grant.task_id != task_id:
                raise InvocationAuthorizationError("外部访问许可不属于当前任务。")
            if tool_name not in grant.allowed_tools:
                raise InvocationAuthorizationError("外部访问许可不包含当前工具。")
            if grant.remaining_uses <= 0:
                raise InvocationAuthorizationError("外部访问许可使用次数已耗尽。")
            grant.remaining_uses -= 1
        return grant_id

    async def authorize_write(
        self,
        *,
        grant_id: str | None,
        task_id: str,
        tool_name: str,
        input_payload: BaseModel | Mapping[str, object],
        require_second_confirmation: bool,
    ) -> str:
        """校验并消费一次绑定输入哈希的作者写入授权。"""
        if not grant_id:
            raise InvocationAuthorizationError("写入操作缺少作者授权。")
        actual_hash = canonical_input_hash(input_payload)
        async with self._lock:
            grant = self._author_grants.get(grant_id)
            if grant is None:
                raise InvocationAuthorizationError("作者写入授权不存在或已失效。")
            _ensure_not_expired(grant.expires_at, "作者写入授权")
            if grant.task_id != task_id or grant.tool_name != tool_name:
                raise InvocationAuthorizationError("作者授权与当前任务或工具不匹配。")
            if grant.input_sha256 != actual_hash:
                raise InvocationAuthorizationError(
                    "写入参数已变化，必须重新预览并授权。"
                )
            if require_second_confirmation and not grant.second_confirmation:
                raise InvocationAuthorizationError("该高风险写入缺少二次确认。")
            if grant.remaining_uses <= 0:
                raise InvocationAuthorizationError("作者写入授权已使用。")
            grant.remaining_uses -= 1
        return grant_id

    async def get_idempotent_result(
        self,
        *,
        tool_name: str,
        idempotency_key: str,
        input_payload: BaseModel | Mapping[str, object],
    ) -> dict[str, object] | None:
        """返回相同输入的既有结果，并拒绝键相同但输入不同。"""
        key = (tool_name, idempotency_key)
        input_sha256 = canonical_input_hash(input_payload)
        async with self._lock:
            record = self._idempotency.get(key)
            if record is None:
                return None
            if record.input_sha256 != input_sha256:
                raise IdempotencyConflictError("相同幂等键对应了不同输入，写入已拒绝。")
            return dict(record.output_payload)

    async def save_idempotent_result(
        self,
        *,
        tool_name: str,
        idempotency_key: str,
        input_payload: BaseModel | Mapping[str, object],
        output: BaseModel,
    ) -> None:
        """在写入成功后冻结该幂等键的结果。"""
        key = (tool_name, idempotency_key)
        record = _IdempotencyRecord(
            input_sha256=canonical_input_hash(input_payload),
            output_payload=output.model_dump(mode="json"),
        )
        async with self._lock:
            current = self._idempotency.get(key)
            if current is not None and current.input_sha256 != record.input_sha256:
                raise IdempotencyConflictError(
                    "相同幂等键对应了不同输入，结果不能覆盖。"
                )
            self._idempotency[key] = record


class InvocationAuthorizationError(PermissionError):
    """调用未通过外部访问或作者写入授权。"""


class IdempotencyConflictError(ValueError):
    """幂等键被不同业务输入重复使用。"""


def canonical_input_hash(
    value: BaseModel | Mapping[str, object],
) -> str:
    """计算排除授权引用后的稳定业务输入哈希。"""
    payload = (
        value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    )
    sanitized = {
        key: item
        for key, item in payload.items()
        if key not in {"author_grant_id", "external_access_grant_id"}
    }
    text = json.dumps(
        to_jsonable_python(sanitized),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_not_expired(expires_at: datetime, label: str) -> None:
    if expires_at <= datetime.now(UTC):
        raise InvocationAuthorizationError(f"{label}已过期。")


def _as_iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
