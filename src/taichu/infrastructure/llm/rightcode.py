"""Right Code 单一供应商网关实现。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from taichu.application.contracts.llm import (
    LLMCost,
    LLMGatewayContract,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from taichu.application.contracts.llm_usage import LLMUsageRepository
from taichu.application.models.llm_usage import LLMCallRecord
from taichu.config import Settings
from taichu.infrastructure.llm.catalog import (
    LLMModelCatalog,
    LLMModelSelectionError,
)
from taichu.infrastructure.llm.costs import calculate_cost


class RightCodeGatewayError(RuntimeError):
    """不会包含鉴权信息或完整上游响应的稳定错误。"""

    def __init__(self, code: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ModelAvailability:
    """显式探测产生的内存状态。"""

    availability: str = "unknown"
    last_probed_at: str | None = None
    error: str | None = None


class RightCodeLLMGateway(LLMGatewayContract):
    """解析目录、路由 Responses 或 Messages、规范化用量并记录遥测。"""

    def __init__(
        self,
        settings: Settings,
        catalog: LLMModelCatalog,
        usage_repository: LLMUsageRepository,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._catalog = catalog
        self._usage_repository = usage_repository
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.rightcode_request_timeout_seconds)
        )
        self._availability: dict[str, ModelAvailability] = {}

    @property
    def configured(self) -> bool:
        return bool(self._settings.rightcode_api_key.get_secret_value().strip())

    @property
    def default_model_id(self) -> str:
        return self._catalog.default_model_id

    def list_models(self) -> list[LLMModelProfile]:
        return [
            replace(profile, enabled=False)
            if self.availability_for(profile.id).availability == "unavailable"
            else profile
            for profile in self._catalog.list_models()
        ]

    def availability_for(self, model_id: str) -> ModelAvailability:
        return self._availability.get(model_id, ModelAvailability())

    def resolve_model(self, model_id: str | None) -> LLMModelProfile:
        profile = self._catalog.resolve(model_id)
        status = self.availability_for(profile.id)
        if status.availability == "unavailable":
            raise LLMModelSelectionError(
                "LLM_MODEL_UNAVAILABLE",
                f"模型“{profile.display_name}”当前不可用，请选择其他模型或重新检测。",
            )
        return profile

    async def probe_model(self, model_id: str) -> ModelAvailability:
        profile = self._catalog.resolve(model_id)
        request = LLMRequest(
            model_id=profile.id,
            messages=(
                # 探测内容固定且不包含用户数据。
                _message("user", "请只回复：可用"),
            ),
            task_type="model_probe",
            task_name="模型检测",
            feature="模型监控",
            max_output_tokens=1024 if profile.id.startswith("deepseek-") else 8,
        )
        try:
            await self._complete(request, allow_known_unavailable=True)
        except (RightCodeGatewayError, LLMModelSelectionError) as exc:
            state = ModelAvailability(
                availability="unavailable",
                last_probed_at=_now_iso(),
                error=str(exc),
            )
        else:
            state = ModelAvailability(
                availability="available",
                last_probed_at=_now_iso(),
            )
        self._availability[profile.id] = state
        return state

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self._complete(request, allow_known_unavailable=False)

    async def _complete(
        self, request: LLMRequest, *, allow_known_unavailable: bool
    ) -> LLMResponse:
        profile = (
            self._catalog.resolve(request.model_id)
            if allow_known_unavailable
            else self.resolve_model(request.model_id)
        )
        call_id = f"llm-call-{uuid4().hex}"
        started_at = _now_iso()
        timer = perf_counter()
        try:
            self._ensure_configured()
            payload = _request_payload(profile, request, stream=False)
            response = await self._post_with_retries(profile, payload)
            parsed = _parse_response(response.json(), profile, call_id)
            if request.response_mode == "json":
                parsed = replace(parsed, text=_normalize_json_text(parsed.text))
            if not parsed.text.strip():
                raise RightCodeGatewayError(
                    "LLM_EMPTY_RESPONSE", "模型返回了空内容，请稍后重试。"
                )
        except Exception as exc:
            safe = _normalize_error(exc)
            await self._record_failure(
                call_id, request, profile, started_at, timer, safe
            )
            raise safe from None
        await self._record_success(call_id, request, profile, started_at, timer, parsed)
        return parsed

    async def _post_with_retries(
        self, profile: LLMModelProfile, payload: dict[str, Any]
    ) -> httpx.Response:
        url = self._endpoint(profile)
        attempts = max(0, self._settings.rightcode_max_retries) + 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    url,
                    headers=self._headers(profile),
                    json=payload,
                )
                if response.status_code < 400:
                    return response
                error = _status_error(response.status_code)
                if response.status_code != 429 and response.status_code < 500:
                    raise error
                if attempt == attempts - 1:
                    raise error
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == attempts - 1:
                    raise exc
            await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        raise RightCodeGatewayError("LLM_UPSTREAM_ERROR", "模型服务暂时不可用。")

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        profile = self.resolve_model(request.model_id)
        call_id = f"llm-call-{uuid4().hex}"
        started_at = _now_iso()
        timer = perf_counter()
        completed = False
        recorded = False
        last_usage = LLMUsage()
        text_parts: list[str] = []
        yield LLMStreamEvent(event_type="started", call_id=call_id)
        try:
            self._ensure_configured()
            payload = _request_payload(profile, request, stream=True)
            url = self._endpoint(profile)
            async with self._client.stream(
                "POST", url, headers=self._headers(profile), json=payload
            ) as response:
                if response.status_code >= 400:
                    raise _status_error(response.status_code)
                provider_request_id: str | None = None
                finish_reason: str | None = None
                async for event_name, event_payload in _iter_sse(response):
                    event_type = str(event_payload.get("type") or event_name)
                    if event_type == "response.output_text.delta":
                        delta = str(event_payload.get("delta") or "")
                        if delta:
                            text_parts.append(delta)
                            yield LLMStreamEvent(
                                event_type="text_delta",
                                delta=delta,
                                call_id=call_id,
                            )
                    elif event_type in {"response.usage", "response.usage.delta"}:
                        last_usage = _parse_usage(event_payload.get("usage", {}))
                        yield LLMStreamEvent(
                            event_type="usage", usage=last_usage, call_id=call_id
                        )
                    elif event_type == "response.completed":
                        body = event_payload.get("response")
                        if not isinstance(body, dict):
                            body = event_payload
                        parsed = _parse_responses_response(body, profile, call_id)
                        if not parsed.text and text_parts:
                            parsed = LLMResponse(
                                text="".join(text_parts),
                                model_id=parsed.model_id,
                                upstream_model=parsed.upstream_model,
                                usage=parsed.usage,
                                cost=parsed.cost,
                                finish_reason=parsed.finish_reason,
                                provider_request_id=parsed.provider_request_id,
                                call_id=call_id,
                            )
                        if request.response_mode == "json":
                            parsed = replace(
                                parsed, text=_normalize_json_text(parsed.text)
                            )
                        if not parsed.text.strip():
                            raise RightCodeGatewayError(
                                "LLM_EMPTY_RESPONSE", "模型返回了空内容，请稍后重试。"
                            )
                        last_usage = parsed.usage
                        if any(value is not None for value in _usage_values(last_usage)):
                            yield LLMStreamEvent(
                                event_type="usage",
                                usage=last_usage,
                                call_id=call_id,
                            )
                        await self._record_success(
                            call_id, request, profile, started_at, timer, parsed
                        )
                        recorded = True
                        completed = True
                        yield LLMStreamEvent(
                            event_type="completed",
                            response=parsed,
                            usage=last_usage,
                            call_id=call_id,
                        )
                    elif event_type == "message_start":
                        message = event_payload.get("message")
                        if isinstance(message, dict):
                            provider_request_id = _optional_text(message.get("id"))
                            last_usage = _merge_usage(
                                last_usage,
                                _parse_anthropic_usage(message.get("usage", {})),
                            )
                    elif event_type == "content_block_delta":
                        delta_payload = event_payload.get("delta")
                        if isinstance(delta_payload, dict):
                            delta = str(delta_payload.get("text") or "")
                            if delta:
                                text_parts.append(delta)
                                yield LLMStreamEvent(
                                    event_type="text_delta",
                                    delta=delta,
                                    call_id=call_id,
                                )
                    elif event_type == "message_delta":
                        delta_payload = event_payload.get("delta")
                        if isinstance(delta_payload, dict):
                            finish_reason = _optional_text(
                                delta_payload.get("stop_reason")
                            )
                        last_usage = _merge_usage(
                            last_usage,
                            _parse_anthropic_usage(event_payload.get("usage", {})),
                        )
                        if any(value is not None for value in _usage_values(last_usage)):
                            yield LLMStreamEvent(
                                event_type="usage",
                                usage=last_usage,
                                call_id=call_id,
                            )
                    elif event_type == "message_stop":
                        text = "".join(text_parts)
                        if not text.strip():
                            raise RightCodeGatewayError(
                                "LLM_EMPTY_RESPONSE", "模型返回了空内容，请稍后重试。"
                            )
                        parsed = LLMResponse(
                            text=text,
                            model_id=profile.id,
                            upstream_model=profile.upstream_model,
                            usage=last_usage,
                            cost=calculate_cost(profile, last_usage, None),
                            finish_reason=finish_reason,
                            provider_request_id=provider_request_id,
                            call_id=call_id,
                        )
                        if request.response_mode == "json":
                            parsed = replace(
                                parsed, text=_normalize_json_text(parsed.text)
                            )
                        await self._record_success(
                            call_id, request, profile, started_at, timer, parsed
                        )
                        recorded = True
                        completed = True
                        yield LLMStreamEvent(
                            event_type="completed",
                            response=parsed,
                            usage=last_usage,
                            call_id=call_id,
                        )
                    elif event_type in {
                        "response.failed",
                        "response.incomplete",
                        "error",
                    }:
                        raise RightCodeGatewayError(
                            "LLM_STREAM_INTERRUPTED",
                            "模型流式输出中断，请稍后重试。",
                        )
            if not completed:
                raise RightCodeGatewayError(
                    "LLM_STREAM_INTERRUPTED", "模型流式输出中断，请稍后重试。"
                )
        except asyncio.CancelledError:
            safe = RightCodeGatewayError(
                "LLM_CLIENT_DISCONNECTED", "客户端已断开，模型调用已清理。"
            )
            if not recorded:
                await asyncio.shield(
                    self._record_failure(
                        call_id, request, profile, started_at, timer, safe, last_usage
                    )
                )
                recorded = True
            raise
        except Exception as exc:
            safe = _normalize_error(exc)
            if not recorded:
                await self._record_failure(
                    call_id, request, profile, started_at, timer, safe, last_usage
                )
                recorded = True
            yield LLMStreamEvent(
                event_type="failed", error=safe.message, call_id=call_id
            )
        finally:
            if not recorded and not completed:
                safe = RightCodeGatewayError(
                    "LLM_CLIENT_DISCONNECTED", "客户端已断开，模型调用已清理。"
                )
                await self._record_failure(
                    call_id, request, profile, started_at, timer, safe, last_usage
                )

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise RightCodeGatewayError(
                "LLM_TOKEN_MISSING",
                "尚未配置模型服务密钥，请在本机环境中完成配置。",
            )

    def _endpoint(self, profile: LLMModelProfile) -> str:
        if profile.wire_protocol == "anthropic_messages":
            if profile.base_url_key == "RIGHTCODE_DEEPSEEK_ANTHROPIC_BASE_URL":
                return _join_url(
                    self._settings.rightcode_deepseek_anthropic_base_url,
                    "v1/messages",
                )
            return _join_url(
                self._settings.rightcode_claude_sale_base_url, "v1/messages"
            )
        return _join_url(self._settings.rightcode_responses_base_url, "responses")

    def _headers(self, profile: LLMModelProfile) -> dict[str, str]:
        token = self._settings.rightcode_api_key.get_secret_value()
        if profile.wire_protocol == "anthropic_messages":
            return {
                "Content-Type": "application/json",
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
            }
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        }

    async def _record_success(
        self,
        call_id: str,
        request: LLMRequest,
        profile: LLMModelProfile,
        started_at: str,
        timer: float,
        response: LLMResponse,
    ) -> None:
        await self._usage_repository.append(
            _call_record(
                call_id=call_id,
                request=request,
                profile=profile,
                status="completed",
                started_at=started_at,
                timer=timer,
                usage=response.usage,
                cost=response.cost,
                provider_request_id=response.provider_request_id,
            )
        )

    async def _record_failure(
        self,
        call_id: str,
        request: LLMRequest,
        profile: LLMModelProfile,
        started_at: str,
        timer: float,
        error: RightCodeGatewayError,
        usage: LLMUsage | None = None,
    ) -> None:
        await self._usage_repository.append(
            _call_record(
                call_id=call_id,
                request=request,
                profile=profile,
                status="failed",
                started_at=started_at,
                timer=timer,
                usage=usage or LLMUsage(),
                cost=LLMCost(),
                error=error,
            )
        )


def _message(role: str, content: str):
    from taichu.application.contracts.llm import LLMMessage

    return LLMMessage(role=role, content=content)  # type: ignore[arg-type]


def _request_payload(
    profile: LLMModelProfile, request: LLMRequest, *, stream: bool
) -> dict[str, Any]:
    if profile.wire_protocol == "anthropic_messages":
        return _anthropic_payload(profile, request, stream=stream)
    return _responses_payload(profile, request, stream=stream)


def _responses_payload(
    profile: LLMModelProfile, request: LLMRequest, *, stream: bool
) -> dict[str, Any]:
    system_parts = [item.content for item in request.messages if item.role == "system"]
    input_items = [
        {
            "type": "message",
            "role": item.role,
            "content": [{"type": "input_text", "text": item.content}],
        }
        for item in request.messages
        if item.role != "system"
    ]
    payload: dict[str, Any] = {
        "model": profile.upstream_model,
        "input": input_items,
        "stream": stream,
    }
    if system_parts:
        payload["instructions"] = "\n\n".join(system_parts)
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_output_tokens is not None:
        payload["max_output_tokens"] = request.max_output_tokens
    if request.response_mode == "json":
        payload["text"] = {"format": {"type": "json_object"}}
    return payload


def _anthropic_payload(
    profile: LLMModelProfile, request: LLMRequest, *, stream: bool
) -> dict[str, Any]:
    system_parts = [item.content for item in request.messages if item.role == "system"]
    if request.response_mode == "json":
        system_parts.append(
            "只返回一个可通过标准 JSON 解析器解析的 JSON 对象；"
            "不得使用 Markdown 代码块，不得在对象前后添加说明文字。"
        )
    messages = [
        {"role": item.role, "content": item.content}
        for item in request.messages
        if item.role != "system"
    ]
    payload: dict[str, Any] = {
        "model": profile.upstream_model,
        "messages": messages,
        "max_tokens": request.max_output_tokens or 4096,
        "stream": stream,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    return payload


def _parse_response(
    payload: dict[str, Any], profile: LLMModelProfile, call_id: str
) -> LLMResponse:
    if profile.wire_protocol == "anthropic_messages":
        return _parse_anthropic_response(payload, profile, call_id)
    return _parse_responses_response(payload, profile, call_id)


def _parse_responses_response(
    payload: dict[str, Any], profile: LLMModelProfile, call_id: str
) -> LLMResponse:
    text = payload.get("output_text")
    if not isinstance(text, str):
        parts: list[str] = []
        output = payload.get("output", [])
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") in {
                        "output_text",
                        "text",
                    }:
                        value = block.get("text")
                        if isinstance(value, str):
                            parts.append(value)
        text = "".join(parts)
    usage = _parse_usage(payload.get("usage", {}))
    actual_amount, actual_currency = _extract_actual_cost(payload)
    return LLMResponse(
        text=text or "",
        model_id=profile.id,
        upstream_model=profile.upstream_model,
        usage=usage,
        cost=calculate_cost(profile, usage, actual_amount, actual_currency),
        finish_reason=_optional_text(
            payload.get("finish_reason") or payload.get("status")
        ),
        provider_request_id=_optional_text(payload.get("id")),
        call_id=call_id,
    )


def _parse_anthropic_response(
    payload: dict[str, Any], profile: LLMModelProfile, call_id: str
) -> LLMResponse:
    parts: list[str] = []
    content = payload.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
    usage = _parse_anthropic_usage(payload.get("usage", {}))
    actual_amount, actual_currency = _extract_actual_cost(payload)
    return LLMResponse(
        text="".join(parts),
        model_id=profile.id,
        upstream_model=profile.upstream_model,
        usage=usage,
        cost=calculate_cost(profile, usage, actual_amount, actual_currency),
        finish_reason=_optional_text(payload.get("stop_reason")),
        provider_request_id=_optional_text(payload.get("id")),
        call_id=call_id,
    )


def _parse_usage(payload: Any) -> LLMUsage:
    if not isinstance(payload, dict):
        return LLMUsage()
    input_details = payload.get("input_tokens_details")
    output_details = payload.get("output_tokens_details")
    if not isinstance(input_details, dict):
        input_details = {}
    if not isinstance(output_details, dict):
        output_details = {}
    return LLMUsage(
        input_tokens=_optional_int(payload.get("input_tokens")),
        cached_input_tokens=_optional_int(input_details.get("cached_tokens")),
        output_tokens=_optional_int(payload.get("output_tokens")),
        reasoning_tokens=_optional_int(output_details.get("reasoning_tokens")),
        total_tokens=_optional_int(payload.get("total_tokens")),
    )


def _parse_anthropic_usage(payload: Any) -> LLMUsage:
    if not isinstance(payload, dict):
        return LLMUsage()
    input_tokens = _optional_int(payload.get("input_tokens"))
    cached_tokens = _optional_int(
        payload.get("cache_read_input_tokens")
        or payload.get("cached_input_tokens")
    )
    output_tokens = _optional_int(payload.get("output_tokens"))
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    return LLMUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _merge_usage(current: LLMUsage, incoming: LLMUsage) -> LLMUsage:
    input_tokens = (
        incoming.input_tokens
        if incoming.input_tokens is not None
        else current.input_tokens
    )
    output_tokens = (
        incoming.output_tokens
        if incoming.output_tokens is not None
        else current.output_tokens
    )
    total_tokens = (
        incoming.total_tokens
        if incoming.total_tokens is not None
        else (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else current.total_tokens
        )
    )
    return LLMUsage(
        input_tokens=input_tokens,
        cached_input_tokens=(
            incoming.cached_input_tokens
            if incoming.cached_input_tokens is not None
            else current.cached_input_tokens
        ),
        output_tokens=output_tokens,
        reasoning_tokens=(
            incoming.reasoning_tokens
            if incoming.reasoning_tokens is not None
            else current.reasoning_tokens
        ),
        total_tokens=total_tokens,
    )


def _normalize_json_text(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().lower() in {"```", "```json"}:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_actual_cost(payload: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    candidates: list[tuple[Any, Any]] = [
        (payload.get("cost"), payload.get("currency")),
    ]
    for container_name in ("usage", "billing"):
        container = payload.get(container_name)
        if isinstance(container, dict):
            candidates.append(
                (
                    container.get("cost") or container.get("amount"),
                    container.get("currency"),
                )
            )
    for value, currency in candidates:
        if isinstance(value, dict):
            currency = value.get("currency") or currency
            value = value.get("amount") or value.get("total")
        if value is None:
            continue
        try:
            return Decimal(str(value)), _optional_text(currency)
        except InvalidOperation:
            continue
    return None, None


async def _iter_sse(
    response: httpx.Response,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    event_name = ""
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                raw = "\n".join(data_lines)
                if raw != "[DONE]":
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise RightCodeGatewayError(
                            "LLM_STREAM_INVALID", "模型流式响应格式不正确。"
                        ) from exc
                    if isinstance(payload, dict):
                        yield event_name, payload
            event_name = ""
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        raw = "\n".join(data_lines)
        if raw != "[DONE]":
            payload = json.loads(raw)
            if isinstance(payload, dict):
                yield event_name, payload


def _status_error(status_code: int) -> RightCodeGatewayError:
    if status_code in {401, 403}:
        return RightCodeGatewayError(
            "LLM_MODEL_FORBIDDEN",
            "当前密钥无权调用该模型，请检查本机密钥权限。",
            status_code=status_code,
        )
    if status_code == 429:
        return RightCodeGatewayError(
            "LLM_RATE_LIMITED",
            "模型服务请求过多或额度不足，请稍后重试并检查账户额度。",
            status_code=status_code,
        )
    if status_code >= 500:
        return RightCodeGatewayError(
            "LLM_UPSTREAM_ERROR",
            "模型服务暂时不可用，请稍后重试。",
            status_code=status_code,
        )
    return RightCodeGatewayError(
        "LLM_REQUEST_REJECTED",
        "模型服务拒绝了本次请求，请检查模型权限或请求设置。",
        status_code=status_code,
    )


def _normalize_error(exc: Exception) -> RightCodeGatewayError:
    if isinstance(exc, RightCodeGatewayError):
        return exc
    if isinstance(exc, LLMModelSelectionError):
        return RightCodeGatewayError(exc.code, exc.message)
    if isinstance(exc, httpx.TimeoutException):
        return RightCodeGatewayError("LLM_TIMEOUT", "模型调用超时，请稍后重试。")
    if isinstance(exc, httpx.NetworkError):
        return RightCodeGatewayError(
            "LLM_NETWORK_ERROR", "无法连接模型服务，请稍后重试。"
        )
    if isinstance(exc, (json.JSONDecodeError, httpx.DecodingError)):
        return RightCodeGatewayError(
            "LLM_RESPONSE_INVALID", "模型服务返回了无法解析的响应。"
        )
    return RightCodeGatewayError("LLM_CALL_FAILED", "模型调用失败，请稍后重试。")


def _call_record(
    *,
    call_id: str,
    request: LLMRequest,
    profile: LLMModelProfile,
    status: str,
    started_at: str,
    timer: float,
    usage: LLMUsage,
    cost: LLMCost,
    provider_request_id: str | None = None,
    error: RightCodeGatewayError | None = None,
) -> LLMCallRecord:
    return LLMCallRecord(
        call_id=call_id,
        run_id=request.run_id,
        task_type=request.task_type,
        task_name=request.task_name,
        feature=request.feature,
        chapter_ids=list(request.chapter_ids),
        model_id=profile.id,
        model_display_name=profile.display_name,
        upstream_model=profile.upstream_model,
        wire_protocol=profile.wire_protocol,
        status=status,  # type: ignore[arg-type]
        started_at=started_at,
        finished_at=_now_iso(),
        duration_ms=max(0, round((perf_counter() - timer) * 1000)),
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        total_tokens=usage.total_tokens,
        cost_amount=cost.amount,
        cost_currency=cost.currency,
        cost_kind=cost.kind,
        provider_request_id=provider_request_id,
        error_code=error.code if error else None,
        error_message=error.message if error else None,
    )


def _usage_values(usage: LLMUsage) -> tuple[int | None, ...]:
    return (
        usage.input_tokens,
        usage.cached_input_tokens,
        usage.output_tokens,
        usage.reasoning_tokens,
        usage.total_tokens,
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
