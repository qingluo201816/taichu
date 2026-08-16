"""Right Code 模型目录、显式检测和模型监控 API。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_llm_gateway, provide_llm_usage_repository
from taichu.api.schemas.llm import (
    LLMCallListResponse,
    LLMModelListResponse,
    LLMModelProbeResponse,
    LLMUsageSummaryResponse,
    LLMTokenTrendResponse,
    PublicLLMModel,
)
from taichu.application.contracts.llm import LLMGatewayContract
from taichu.application.contracts.llm_usage import LLMUsageRepository
from taichu.application.models.llm_usage import LLMCallRecord, LLMUsageQuery
from taichu.infrastructure.llm.catalog import LLMModelSelectionError
from taichu.infrastructure.llm.rightcode import RightCodeLLMGateway


router = APIRouter(prefix="/api/llm", tags=["模型服务"])


@router.get("/models", response_model=LLMModelListResponse)
async def api_list_llm_models(
    gateway: LLMGatewayContract = Depends(provide_llm_gateway),
) -> LLMModelListResponse:
    profiles = gateway.list_models()
    default = next((item for item in profiles if item.is_default), None)
    return LLMModelListResponse(
        default_model_id=default.id if default is not None else "",
        models=[_public_model(gateway, profile) for profile in profiles],
    )


@router.post("/models/{model_id}/probe", response_model=LLMModelProbeResponse)
async def api_probe_llm_model(
    model_id: str,
    gateway: LLMGatewayContract = Depends(provide_llm_gateway),
) -> LLMModelProbeResponse:
    if not isinstance(gateway, RightCodeLLMGateway):
        raise _llm_error(
            409,
            "LLM_PROBE_UNAVAILABLE",
            "当前测试运行环境不支持真实模型检测。",
        )
    try:
        state = await gateway.probe_model(model_id)
    except LLMModelSelectionError as exc:
        raise _llm_error(422, exc.code, exc.message) from exc
    return LLMModelProbeResponse(
        model_id=model_id,
        availability=state.availability,
        last_probed_at=state.last_probed_at,
        requested_provider=state.requested_provider or "rightcode",
        requested_model_id=state.requested_model_id or model_id,
        actual_provider=state.actual_provider,
        actual_model_id=state.actual_model_id,
        fallback_used=state.fallback_used,
        fallback_from_provider=state.fallback_from_provider,
        wire_protocol=state.wire_protocol or "anthropic_messages",
        provider_request_id=state.provider_request_id,
        message=(
            "模型检测成功：请求的 RightCode 提供商可用。"
            if state.availability == "available"
            else "模型检测失败：请求的 RightCode 提供商不可用。"
        ),
    )


@router.get("/usage/calls", response_model=LLMCallListResponse)
async def api_list_llm_calls(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    started_from: str | None = None,
    started_to: str | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    status: Literal["running", "completed", "failed"] | None = None,
    repository: LLMUsageRepository = Depends(provide_llm_usage_repository),
) -> LLMCallListResponse:
    result = await repository.list_calls(
        _query(
            page=page,
            page_size=page_size,
            started_from=started_from,
            started_to=started_to,
            model_id=model_id,
            task_type=task_type,
            status=status,
        )
    )
    return LLMCallListResponse(**result.model_dump())


@router.get("/usage/calls/{call_id}", response_model=LLMCallRecord)
async def api_get_llm_call(
    call_id: str,
    repository: LLMUsageRepository = Depends(provide_llm_usage_repository),
) -> LLMCallRecord:
    record = await repository.get(call_id)
    if record is None:
        raise _llm_error(404, "LLM_CALL_NOT_FOUND", "模型调用记录不存在。")
    return record


@router.get("/usage/summary", response_model=LLMUsageSummaryResponse)
async def api_get_llm_usage_summary(
    started_from: str | None = None,
    started_to: str | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    status: Literal["running", "completed", "failed"] | None = None,
    repository: LLMUsageRepository = Depends(provide_llm_usage_repository),
) -> LLMUsageSummaryResponse:
    summary = await repository.summarize(
        _query(
            started_from=started_from,
            started_to=started_to,
            model_id=model_id,
            task_type=task_type,
            status=status,
        )
    )
    return LLMUsageSummaryResponse(**summary.model_dump())


@router.get("/usage/trend", response_model=LLMTokenTrendResponse)
async def api_get_llm_token_trend(
    bucket: Literal["hour", "day"] = "day",
    started_from: str | None = None,
    started_to: str | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    status: Literal["running", "completed", "failed"] | None = None,
    repository: LLMUsageRepository = Depends(provide_llm_usage_repository),
) -> LLMTokenTrendResponse:
    points = await repository.token_trend(
        _query(
            started_from=started_from,
            started_to=started_to,
            model_id=model_id,
            task_type=task_type,
            status=status,
        ),
        bucket,
    )
    return LLMTokenTrendResponse(bucket=bucket, points=points)


def _public_model(gateway: LLMGatewayContract, profile) -> PublicLLMModel:
    availability = "unknown"
    last_probed_at = None
    error = None
    if isinstance(gateway, RightCodeLLMGateway):
        state = gateway.availability_for(profile.id)
        availability = state.availability
        last_probed_at = state.last_probed_at
        error = state.error
    return PublicLLMModel(
        id=profile.id,
        display_name=profile.display_name,
        enabled=profile.enabled,
        is_default=profile.is_default,
        supports_streaming=profile.supports_streaming,
        availability=availability,
        last_probed_at=last_probed_at,
        availability_error=error,
        upstream_verified=profile.upstream_verified,
    )


def _query(**values) -> LLMUsageQuery:
    return LLMUsageQuery(**{key: value for key, value in values.items() if value is not None})


def _llm_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
    )
