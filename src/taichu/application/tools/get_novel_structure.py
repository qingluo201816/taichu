"""读取当前单本小说的卷章结构。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.outline_service import OutlineService
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools._structure import current_structure_version
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    GetNovelStructureInput,
    GetNovelStructureOutput,
    NovelChapterItem,
    NovelVolumeItem,
)


manifest = ToolManifest(
    name="get_novel_structure",
    description="读取当前小说的卷章树、章节状态、顺序和结构版本。",
    input_schema=GetNovelStructureInput,
    output_schema=GetNovelStructureOutput,
    required_capabilities=frozenset({"chapter_service", "outline_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=INTERNAL_READ_CALLERS,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = GetNovelStructureInput.model_validate(input_data)
    chapters = await context.require("chapter_service", ChapterService).list_chapters()
    outline_service = context.require("outline_service", OutlineService)
    outline = await outline_service.get_outline()
    chapter_by_id = {item.id: item for item in chapters}
    allowed_volumes = set(tool_input.volume_ids)
    filtered_ids = [
        chapter.id
        for chapter in chapters
        if (not allowed_volumes or chapter.volume_id in allowed_volumes)
        and (not tool_input.statuses or chapter.status in tool_input.statuses)
    ]
    page_ids = set(
        filtered_ids[tool_input.offset : tool_input.offset + tool_input.limit]
    )
    volumes: list[NovelVolumeItem] = []
    for volume in sorted(outline.volumes, key=lambda item: item.order):
        if allowed_volumes and volume.volume_id not in allowed_volumes:
            continue
        chapter_items: list[NovelChapterItem] = []
        for outline_chapter in sorted(volume.chapters, key=lambda item: item.order):
            chapter = chapter_by_id.get(outline_chapter.chapter_id)
            if chapter is None or chapter.id not in page_ids:
                continue
            chapter_items.append(
                NovelChapterItem(
                    chapter_id=chapter.id,
                    volume_id=chapter.volume_id,
                    title=chapter.title,
                    order=chapter.order,
                    word_count=chapter.word_count,
                    status=chapter.status,
                    markdown_path=chapter.markdown_path,
                    updated_at=chapter.updated_at,
                )
            )
        if chapter_items:
            volumes.append(
                NovelVolumeItem(
                    volume_id=volume.volume_id,
                    title=volume.name,
                    order=volume.order,
                    chapters=chapter_items,
                )
            )
    return GetNovelStructureOutput(
        structure_version=await current_structure_version(
            context.require("chapter_service", ChapterService),
            outline_service,
        ),
        current_volume_id=outline.current_volume_id,
        current_chapter_id=outline.current_chapter_id,
        total_chapters=len(filtered_ids),
        returned_chapters=len(page_ids),
        volumes=volumes,
        truncated=tool_input.offset + len(page_ids) < len(filtered_ids),
        source_refs=["manuscript:manifest", "manuscript:outline"],
    )
