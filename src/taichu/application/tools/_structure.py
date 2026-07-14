"""卷章结构 Tool 共用的版本和查找逻辑。"""

from __future__ import annotations

from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.outline_service import OutlineService
from taichu.application.tools._shared import stable_model_hash


async def current_structure_version(
    chapter_service: ChapterService,
    outline_service: OutlineService,
) -> str:
    manifest = await chapter_service.get_manifest()
    outline = await outline_service.get_outline()
    return stable_model_hash(
        {
            "manifest": manifest.model_dump(mode="json"),
            "outline": outline.model_dump(mode="json"),
        }
    )


async def require_structure_version(
    expected: str,
    chapter_service: ChapterService,
    outline_service: OutlineService,
) -> str:
    actual = await current_structure_version(chapter_service, outline_service)
    if actual != expected:
        raise StructureVersionConflictError(
            "卷章结构已变化，请刷新、重新预览并再次授权。"
        )
    return actual


class StructureVersionConflictError(ValueError):
    """写操作使用了过期的卷章结构版本。"""
