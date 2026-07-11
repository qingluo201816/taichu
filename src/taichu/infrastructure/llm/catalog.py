"""Right Code 模型目录及选择校验。"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from taichu.application.contracts.llm import LLMModelProfile
from taichu.config import Settings


class LLMModelSelectionError(ValueError):
    """模型选择错误，包含稳定中文错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_MODEL_DEFINITIONS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    (
        "gpt-5-6-luna",
        "GPT-5.6 Luna",
        "gpt-5.6-luna",
        "openai_responses",
        "RIGHTCODE_RESPONSES_BASE_URL",
        True,
    ),
    (
        "gpt-5-6-sol",
        "GPT-5.6 Sol",
        "gpt-5.6-sol",
        "openai_responses",
        "RIGHTCODE_RESPONSES_BASE_URL",
        True,
    ),
    (
        "gpt-5-6-terra",
        "GPT-5.6 Terra",
        "gpt-5.6-terra",
        "openai_responses",
        "RIGHTCODE_RESPONSES_BASE_URL",
        True,
    ),
    (
        "deepseek-v4-flash",
        "DeepSeek V4 Flash",
        "deepseek-v4-flash",
        "anthropic_messages",
        "RIGHTCODE_DEEPSEEK_ANTHROPIC_BASE_URL",
        True,
    ),
    (
        "deepseek-v4-pro",
        "DeepSeek V4 Pro",
        "deepseek-v4-pro",
        "anthropic_messages",
        "RIGHTCODE_DEEPSEEK_ANTHROPIC_BASE_URL",
        True,
    ),
    (
        "claude-opus-4-6",
        "Claude Opus 4.6",
        "claude-opus-4-6",
        "anthropic_messages",
        "RIGHTCODE_CLAUDE_SALE_BASE_URL",
        True,
    ),
    (
        "claude-opus-4-7",
        "Claude Opus 4.7",
        "claude-opus-4-7",
        "anthropic_messages",
        "RIGHTCODE_CLAUDE_SALE_BASE_URL",
        True,
    ),
    (
        "claude-opus-4-8",
        "Claude Opus 4.8",
        "claude-opus-4-8",
        "anthropic_messages",
        "RIGHTCODE_CLAUDE_SALE_BASE_URL",
        True,
    ),
    (
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        "claude-sonnet-4-6",
        "anthropic_messages",
        "RIGHTCODE_CLAUDE_SALE_BASE_URL",
        True,
    ),
    (
        "claude-sonnet-5",
        "Claude Sonnet 5",
        "claude-sonnet-5",
        "anthropic_messages",
        "RIGHTCODE_CLAUDE_SALE_BASE_URL",
        True,
    ),
)


class LLMModelCatalog:
    """后端唯一模型目录事实源。"""

    def __init__(self, settings: Settings) -> None:
        prices = _parse_prices(settings.rightcode_model_prices_json)
        profiles = [
            LLMModelProfile(
                id=model_id,
                display_name=display_name,
                provider="rightcode",
                upstream_model=upstream_model,
                wire_protocol=wire_protocol,  # type: ignore[arg-type]
                base_url_key=base_url_key,
                enabled=True,
                is_default=model_id == settings.rightcode_default_model_id,
                supports_streaming=True,
                upstream_verified=upstream_verified,
                **prices.get(model_id, {}),
            )
            for (
                model_id,
                display_name,
                upstream_model,
                wire_protocol,
                base_url_key,
                upstream_verified,
            ) in _MODEL_DEFINITIONS
        ]
        self._profiles = tuple(profiles)
        self._by_id = {profile.id: profile for profile in profiles}
        self._validate(settings.rightcode_default_model_id)

    @property
    def default_model_id(self) -> str:
        return next(profile.id for profile in self._profiles if profile.is_default)

    def list_models(self) -> list[LLMModelProfile]:
        return list(self._profiles)

    def resolve(self, model_id: str | None) -> LLMModelProfile:
        actual_id = (model_id or self.default_model_id).strip()
        profile = self._by_id.get(actual_id)
        if profile is None:
            raise LLMModelSelectionError(
                "LLM_MODEL_UNKNOWN",
                "所选模型不存在，请刷新模型列表后重试。",
            )
        if not profile.enabled:
            raise LLMModelSelectionError(
                "LLM_MODEL_DISABLED",
                f"模型“{profile.display_name}”当前已停用，请选择其他模型。",
            )
        return profile

    def with_protocol(
        self,
        model_id: str,
        *,
        wire_protocol: str,
        base_url_key: str,
        verified: bool,
    ) -> LLMModelProfile:
        """供真实探测结果生成本地配置建议，不会静默改变全局目录。"""
        profile = self.resolve(model_id)
        if wire_protocol not in {"openai_responses", "anthropic_messages"}:
            raise ValueError("不支持的模型传输协议。")
        return replace(
            profile,
            wire_protocol=wire_protocol,  # type: ignore[arg-type]
            base_url_key=base_url_key,
            upstream_verified=verified,
        )

    def _validate(self, configured_default: str) -> None:
        ids = [profile.id for profile in self._profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("模型目录中存在重复模型 ID。")
        defaults = [profile for profile in self._profiles if profile.is_default]
        if len(defaults) != 1:
            raise ValueError("模型目录必须且只能配置一个默认模型。")
        if configured_default not in self._by_id:
            raise ValueError("RIGHTCODE_DEFAULT_MODEL_ID 不在模型目录中。")
        if not defaults[0].enabled:
            raise ValueError("默认模型必须处于启用状态。")


def _parse_prices(raw: str) -> dict[str, dict[str, Any]]:
    """解析可选价格配置；未配置时保持不可计算。"""
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("RIGHTCODE_MODEL_PRICES_JSON 不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("RIGHTCODE_MODEL_PRICES_JSON 顶层必须是对象。")
    known_ids = {item[0] for item in _MODEL_DEFINITIONS}
    field_map = {
        "input": "input_price_per_million",
        "cached_input": "cached_input_price_per_million",
        "output": "output_price_per_million",
        "reasoning_output": "reasoning_output_price_per_million",
    }
    result: dict[str, dict[str, Any]] = {}
    for model_id, values in payload.items():
        if model_id not in known_ids or not isinstance(values, dict):
            raise ValueError("价格配置包含未知模型或无效价格对象。")
        parsed: dict[str, Any] = {"currency": str(values.get("currency") or "CNY")}
        for source, target in field_map.items():
            value = values.get(source)
            if value is None:
                continue
            try:
                amount = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError("模型价格必须是十进制数字。") from exc
            if amount < 0:
                raise ValueError("模型价格不能小于零。")
            parsed[target] = amount
        result[model_id] = parsed
    return result
