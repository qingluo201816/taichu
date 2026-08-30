"""MVP user preference contracts."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel


class EditorFontStyle(StrEnum):
    """Editor font style preference."""

    SERIF = "serif"
    SANS = "sans"


class EditorBackground(StrEnum):
    """Editor background preference."""

    DARK = "dark"
    SOFT = "soft"


class LLMProvider(StrEnum):
    """当前允许使用的模型供应商。"""

    RIGHTCODE = "rightcode"
    DEEPSEEK_OFFICIAL = "deepseek_official"


class EditorPreferences(DomainModel):
    """Basic settings page preferences without real LLM configuration."""

    font_size: int = Field(default=18, ge=14, le=24)
    font_style: EditorFontStyle = EditorFontStyle.SERIF
    editor_background: EditorBackground = EditorBackground.DARK
    llm_provider: LLMProvider = LLMProvider.RIGHTCODE
    updated_at: str = Field(min_length=1)
