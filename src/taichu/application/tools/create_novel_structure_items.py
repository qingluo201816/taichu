"""在作者授权后创建真实卷章结构项。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.outline_service import OutlineService
from taichu.application.tools._shared import (
    ORCHESTRATOR_WRITE_CALLERS,
    sha256_text,
)
from taichu.application.tools._structure import (
    current_structure_version,
    require_structure_version,
)
from taichu.application.tools._structure_reconciliation import (
    reconcile_created_items,
)
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolIdempotencyPolicy,
    ToolManifest,
    ToolSideEffect,
)
from taichu.application.tools.models import (
    CreateNovelStructureItemsInput,
    NovelStructureWriteOutput,
    StructureChangeResult,
)


manifest = ToolManifest(
    name="create_novel_structure_items",
    description="在作者授权和结构版本校验后创建卷或章节。",
    input_schema=CreateNovelStructureItemsInput,
    output_schema=NovelStructureWriteOutput,
    required_capabilities=frozenset({"chapter_service", "outline_service"}),
    exposures=frozenset({"agent_runtime"}),
    side_effect=ToolSideEffect.WRITE,
    allowed_callers=ORCHESTRATOR_WRITE_CALLERS,
    authorization_policy=ToolAuthorizationPolicy.AUTHOR_GRANT,
    idempotency_policy=ToolIdempotencyPolicy.REQUIRED,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = CreateNovelStructureItemsInput.model_validate(input_data)
    chapter_service = context.require("chapter_service", ChapterService)
    outline_service = context.require("outline_service", OutlineService)
    previous = await require_structure_version(
        tool_input.expected_structure_version,
        chapter_service,
        outline_service,
    )
    initial = await outline_service.get_outline()
    volume_ids = {item.volume_id for item in initial.volumes}
    chapter_ids = {
        chapter.chapter_id for volume in initial.volumes for chapter in volume.chapters
    }
    for item in tool_input.items:
        if item.kind == "chapter" and item.volume_id not in volume_ids:
            raise ValueError(f"目标卷“{item.volume_id}”不存在。")
        if item.after_chapter_id and item.after_chapter_id not in chapter_ids:
            raise ValueError(f"定位章节“{item.after_chapter_id}”不存在。")
    changes: list[StructureChangeResult] = []
    for item in tool_input.items:
        before = await outline_service.get_outline()
        if item.kind == "volume":
            updated = await outline_service.create_volume(item.title)
            before_ids = {volume.volume_id for volume in before.volumes}
            created_volume = next(
                volume
                for volume in updated.volumes
                if volume.volume_id not in before_ids
            )
            changes.append(
                StructureChangeResult(
                    kind="volume",
                    item_id=created_volume.volume_id,
                    action="created",
                    title=created_volume.name,
                )
            )
            volume_ids.add(created_volume.volume_id)
        else:
            updated = await outline_service.create_chapter(
                str(item.volume_id),
                item.title,
                after_chapter_id=item.after_chapter_id,
            )
            before_ids = {
                chapter.chapter_id
                for volume in before.volumes
                for chapter in volume.chapters
            }
            created_chapter = next(
                chapter
                for volume in updated.volumes
                for chapter in volume.chapters
                if chapter.chapter_id not in before_ids
            )
            changes.append(
                StructureChangeResult(
                    kind="chapter",
                    item_id=created_chapter.chapter_id,
                    action="created",
                    title=created_chapter.display_title,
                )
            )
            chapter_ids.add(created_chapter.chapter_id)
    current = await current_structure_version(chapter_service, outline_service)
    return NovelStructureWriteOutput(
        previous_structure_version=previous,
        structure_version=current,
        changes=changes,
        audit_ref=f"structure_write:{sha256_text(tool_input.idempotency_key)[:24]}",
        source_refs=["manuscript:manifest", "manuscript:outline"],
    )


async def reconcile(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
):
    del invocation
    tool_input = CreateNovelStructureItemsInput.model_validate(input_data)
    return await reconcile_created_items(
        tool_input,
        context.require("chapter_service", ChapterService),
        context.require("outline_service", OutlineService),
    )
