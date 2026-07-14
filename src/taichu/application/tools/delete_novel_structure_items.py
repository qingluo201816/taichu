"""经二次确认后归档删除真实卷章结构项。"""

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
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolIdempotencyPolicy,
    ToolManifest,
    ToolSideEffect,
)
from taichu.application.tools.models import (
    DeleteNovelStructureItemsInput,
    NovelStructureWriteOutput,
    StructureChangeResult,
)


manifest = ToolManifest(
    name="delete_novel_structure_items",
    description="经作者二次确认后归档删除卷或章节，不物理清除 Markdown。",
    input_schema=DeleteNovelStructureItemsInput,
    output_schema=NovelStructureWriteOutput,
    required_capabilities=frozenset({"chapter_service", "outline_service"}),
    exposures=frozenset({"agent_runtime"}),
    side_effect=ToolSideEffect.HIGH_RISK_WRITE,
    allowed_callers=ORCHESTRATOR_WRITE_CALLERS,
    authorization_policy=ToolAuthorizationPolicy.SECOND_CONFIRMATION,
    idempotency_policy=ToolIdempotencyPolicy.REQUIRED,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = DeleteNovelStructureItemsInput.model_validate(input_data)
    chapter_service = context.require("chapter_service", ChapterService)
    outline_service = context.require("outline_service", OutlineService)
    previous = await require_structure_version(
        tool_input.expected_structure_version,
        chapter_service,
        outline_service,
    )
    outline = await outline_service.get_outline()
    volumes = {volume.volume_id: volume for volume in outline.volumes}
    chapters = {
        chapter.chapter_id: (volume.volume_id, chapter)
        for volume in outline.volumes
        for chapter in volume.chapters
    }
    for target in tool_input.targets:
        if target.kind == "volume" and target.target_id not in volumes:
            raise ValueError(f"目标卷“{target.target_id}”不存在。")
        if target.kind == "chapter" and target.target_id not in chapters:
            raise ValueError(f"目标章节“{target.target_id}”不存在。")
    deleted_volume_ids = {
        target.target_id for target in tool_input.targets if target.kind == "volume"
    }
    chapter_targets = [
        target
        for target in tool_input.targets
        if target.kind == "chapter"
        and chapters[target.target_id][0] not in deleted_volume_ids
    ]
    changes: list[StructureChangeResult] = []
    for target in chapter_targets:
        chapter = chapters[target.target_id][1]
        await outline_service.delete_chapter(target.target_id)
        changes.append(
            StructureChangeResult(
                kind="chapter",
                item_id=target.target_id,
                action="archived",
                title=chapter.display_title,
            )
        )
    for volume_id in deleted_volume_ids:
        volume = volumes[volume_id]
        await outline_service.delete_volume(volume_id)
        changes.append(
            StructureChangeResult(
                kind="volume",
                item_id=volume_id,
                action="archived",
                title=volume.name,
            )
        )
    return NovelStructureWriteOutput(
        previous_structure_version=previous,
        structure_version=await current_structure_version(
            chapter_service,
            outline_service,
        ),
        changes=changes,
        audit_ref=f"structure_delete:{sha256_text(tool_input.idempotency_key)[:24]}",
        source_refs=["manuscript:manifest", "manuscript:outline"],
    )
