"""按消费者和召回模式解析预算、策略与回退。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Set
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from taichu.application.retrieval.execution import RetrievalExecutionPlan
from taichu.application.retrieval.models import RetrievalMode, RetrievalRequest

MONGO_LEXICAL_STRATEGY = "mongo_lexical"
_STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class RetrievalPolicyProfile(BaseModel):
    """一个消费者策略的默认预算和后端选择。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k: int = Field(ge=1, le=200)
    max_content_chars: int = Field(ge=500, le=50_000)
    timeout_ms: int = Field(ge=100, le=120_000)
    strategy: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
    )
    fallback_strategy: str | None = Field(
        default=MONGO_LEXICAL_STRATEGY,
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
    )


_DEFAULT_PROFILES: dict[str, RetrievalPolicyProfile] = {
    "writing_task": RetrievalPolicyProfile(
        top_k=12,
        max_content_chars=6_000,
        timeout_ms=5_000,
    ),
    "chapter_summary": RetrievalPolicyProfile(
        top_k=20,
        max_content_chars=10_000,
        timeout_ms=5_000,
    ),
    "knowledge_workflow": RetrievalPolicyProfile(
        top_k=20,
        max_content_chars=10_000,
        timeout_ms=5_000,
    ),
    "general_agent_runtime": RetrievalPolicyProfile(
        top_k=12,
        max_content_chars=12_000,
        timeout_ms=5_000,
    ),
    "retrieval_evaluation": RetrievalPolicyProfile(
        top_k=10,
        max_content_chars=50_000,
        timeout_ms=10_000,
    ),
    "identity": RetrievalPolicyProfile(
        top_k=20,
        max_content_chars=10_000,
        timeout_ms=5_000,
        strategy=MONGO_LEXICAL_STRATEGY,
    ),
    "catalog": RetrievalPolicyProfile(
        top_k=200,
        max_content_chars=50_000,
        timeout_ms=10_000,
        strategy=MONGO_LEXICAL_STRATEGY,
    ),
    "default_relevance": RetrievalPolicyProfile(
        top_k=12,
        max_content_chars=6_000,
        timeout_ms=5_000,
    ),
}
_CONSUMER_PROFILES = frozenset(
    {
        "writing_task",
        "chapter_summary",
        "knowledge_workflow",
        "general_agent_runtime",
        "retrieval_evaluation",
    }
)


class RetrievalPolicyResolver:
    """把配置和请求合并为不可变执行计划。"""

    def __init__(
        self,
        profiles: Mapping[str, RetrievalPolicyProfile] | None = None,
        *,
        default_relevance_strategy: str = MONGO_LEXICAL_STRATEGY,
    ) -> None:
        if not _STRATEGY_NAME.fullmatch(default_relevance_strategy):
            raise ValueError("默认召回策略名称格式不正确。")
        self._profiles = dict(profiles or _DEFAULT_PROFILES)
        self._default_relevance_strategy = default_relevance_strategy

    @classmethod
    def from_json(
        cls,
        raw_json: str,
        *,
        default_relevance_strategy: str = MONGO_LEXICAL_STRATEGY,
    ) -> RetrievalPolicyResolver:
        """读取可选覆盖；任何无效值都以中文安全错误阻止启动。"""
        try:
            payload: Any = json.loads(raw_json or "{}")
        except json.JSONDecodeError as error:
            raise ValueError("召回策略配置不是有效的 JSON 对象。") from error
        if not isinstance(payload, dict):
            raise ValueError("召回策略配置必须是 JSON 对象。")

        unknown_profiles = sorted(set(payload) - set(_DEFAULT_PROFILES))
        if unknown_profiles:
            raise ValueError(
                "召回策略配置包含未知策略档案："
                + "、".join(unknown_profiles)
                + "。"
            )

        profiles = dict(_DEFAULT_PROFILES)
        for profile_name, overrides in payload.items():
            if not isinstance(overrides, dict):
                raise ValueError(f"召回策略档案“{profile_name}”必须是 JSON 对象。")
            try:
                profiles[profile_name] = RetrievalPolicyProfile.model_validate(
                    {
                        **profiles[profile_name].model_dump(mode="json"),
                        **overrides,
                    }
                )
            except ValidationError as error:
                raise ValueError(
                    f"召回策略档案“{profile_name}”包含无效预算或字段。"
                ) from error

        for deterministic_name in ("identity", "catalog"):
            strategy = profiles[deterministic_name].strategy
            if strategy not in (None, MONGO_LEXICAL_STRATEGY):
                raise ValueError(
                    f"召回策略档案“{deterministic_name}”必须使用确定性词法策略。"
                )
        return cls(
            profiles,
            default_relevance_strategy=default_relevance_strategy,
        )

    def resolve(self, request: RetrievalRequest) -> RetrievalExecutionPlan:
        profile_name = self._profile_name(request)
        profile = self._profiles[profile_name]
        if request.mode in {RetrievalMode.IDENTITY, RetrievalMode.CATALOG}:
            requested_strategy = MONGO_LEXICAL_STRATEGY
        else:
            requested_strategy = (
                request.requested_strategy
                or profile.strategy
                or self._default_relevance_strategy
            )
        fallback_strategy = profile.fallback_strategy
        if fallback_strategy == requested_strategy:
            fallback_strategy = None
        return RetrievalExecutionPlan(
            policy_name=profile_name,
            top_k=request.top_k or profile.top_k,
            max_content_chars=(
                request.max_content_chars or profile.max_content_chars
            ),
            timeout_ms=profile.timeout_ms,
            requested_strategy=requested_strategy,
            fallback_strategy=fallback_strategy,
        )

    def validate_backends(self, available_strategies: Set[str]) -> None:
        """启动时拒绝引用未注册后端的配置。"""
        configured = {self._default_relevance_strategy}
        for profile in self._profiles.values():
            if profile.strategy:
                configured.add(profile.strategy)
            if profile.fallback_strategy:
                configured.add(profile.fallback_strategy)
        missing = sorted(configured - set(available_strategies))
        if missing:
            raise ValueError(
                "召回策略配置引用了未注册的后端：" + "、".join(missing) + "。"
            )

    def _profile_name(self, request: RetrievalRequest) -> str:
        if request.consumer.consumer_type in _CONSUMER_PROFILES:
            return request.consumer.consumer_type
        if request.mode is RetrievalMode.IDENTITY:
            return "identity"
        if request.mode is RetrievalMode.CATALOG:
            return "catalog"
        return "default_relevance"
