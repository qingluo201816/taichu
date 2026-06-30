"""MVP settings preference endpoints."""

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_settings_preference_service
from taichu.api.schemas.mvp import (
    PatchPreferencesRequest,
    PreferencesResponse,
)
from taichu.application.services.settings_service import SettingsPreferenceService

router = APIRouter(prefix="/api")


@router.get("/settings/preferences", response_model=PreferencesResponse)
async def api_get_preferences(
    service: SettingsPreferenceService = Depends(provide_settings_preference_service),
) -> PreferencesResponse:
    """Return basic editor preferences without real model configuration."""
    return PreferencesResponse(preferences=await service.get_preferences())


@router.patch("/settings/preferences", response_model=PreferencesResponse)
async def api_patch_preferences(
    request: PatchPreferencesRequest,
    service: SettingsPreferenceService = Depends(provide_settings_preference_service),
) -> PreferencesResponse:
    """Patch basic editor preferences."""
    try:
        preferences = await service.patch_preferences(request.updates)
    except ValidationError as error:
        raise _bad_request(
            "设置内容不完整或格式不正确，请检查后再保存。"
        ) from error
    return PreferencesResponse(preferences=preferences)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )
