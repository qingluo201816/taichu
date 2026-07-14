"""在作者授权后更新真实卷章结构。"""

from typing import Literal

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
    NovelStructureWriteOutput,
    StructureChangeResult,
    UpdateNovelStructureInput,
)


manifest = ToolManifest(
    name="update_novel_structure",
    description="在作者授权和并发版本校验后重命名、移动或更新章节状态。",
    input_schema=UpdateNovelStructureInput,
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
    tool_input = UpdateNovelStructureInput.model_validate(input_data)
    chapter_service = context.require("chapter_service", ChapterService)
    outline_service = context.require("outline_service", OutlineService)
    previous = await require_structure_version(
        tool_input.expected_structure_version,
        chapter_service,
        outline_service,
    )
    outline = await outline_service.get_outline()
    volume_ids = {volume.volume_id for volume in outline.volumes}
    chapter_ids = {
        chapter.chapter_id for volume in outline.volumes for chapter in volume.chapters
    }
    for operation in tool_input.operations:
        _validate_operation(operation, volume_ids, chapter_ids)
    changes: list[StructureChangeResult] = []
    for operation in tool_input.operations:
        if operation.operation == "rename_volume":
            updated = await outline_service.rename_volume(
                operation.target_id,
                str(operation.title),
            )
            target_volume = next(
                item
                for item in updated.volumes
                if item.volume_id == operation.target_id
            )
            changes.append(
                _change(
                    "volume",
                    target_volume.volume_id,
                    "renamed",
                    target_volume.name,
                )
            )
        elif operation.operation == "rename_chapter":
            updated = await outline_service.rename_chapter(
                operation.target_id,
                str(operation.title),
            )
            target_chapter = next(
                chapter
                for volume in updated.volumes
                for chapter in volume.chapters
                if chapter.chapter_id == operation.target_id
            )
            changes.append(
                _change(
                    "chapter",
                    target_chapter.chapter_id,
                    "renamed",
                    target_chapter.display_title,
                )
            )
        elif operation.operation == "move_volume":
            updated = await outline_service.move_volume(
                operation.target_id,
                after_volume_id=operation.after_item_id,
            )
            moved_volume = next(
                item
                for item in updated.volumes
                if item.volume_id == operation.target_id
            )
            changes.append(
                _change(
                    "volume",
                    moved_volume.volume_id,
                    "moved",
                    moved_volume.name,
                )
            )
        elif operation.operation == "move_chapter":
            updated = await outline_service.move_chapter(
                operation.target_id,
                str(operation.target_volume_id),
                after_chapter_id=operation.after_item_id,
            )
            moved_chapter = next(
                chapter
                for volume in updated.volumes
                for chapter in volume.chapters
                if chapter.chapter_id == operation.target_id
            )
            changes.append(
                _change(
                    "chapter",
                    moved_chapter.chapter_id,
                    "moved",
                    moved_chapter.display_title,
                )
            )
        else:
            if operation.chapter_status is None:
                raise ValueError("章节状态更新必须提供目标状态。")
            await outline_service.set_chapter_status(
                operation.target_id,
                operation.chapter_status,
            )
            chapter = next(
                item
                for item in await chapter_service.list_chapters()
                if item.id == operation.target_id
            )
            changes.append(
                _change("chapter", chapter.id, "status_updated", chapter.title)
            )
    return NovelStructureWriteOutput(
        previous_structure_version=previous,
        structure_version=await current_structure_version(
            chapter_service,
            outline_service,
        ),
        changes=changes,
        audit_ref=f"structure_write:{sha256_text(tool_input.idempotency_key)[:24]}",
        source_refs=["manuscript:manifest", "manuscript:outline"],
    )


def _validate_operation(
    operation: object, volume_ids: set[str], chapter_ids: set[str]
) -> None:
    from taichu.application.tools.models import UpdateStructureOperation

    item = UpdateStructureOperation.model_validate(operation)
    is_volume = item.operation in {"rename_volume", "move_volume"}
    if is_volume and item.target_id not in volume_ids:
        raise ValueError(f"目标卷“{item.target_id}”不存在。")
    if not is_volume and item.target_id not in chapter_ids:
        raise ValueError(f"目标章节“{item.target_id}”不存在。")
    if item.operation.startswith("rename_") and not (item.title or "").strip():
        raise ValueError("重命名操作必须提供新标题。")
    if item.operation == "move_volume" and (
        item.after_item_id is not None and item.after_item_id not in volume_ids
    ):
        raise ValueError("卷移动定位目标不存在。")
    if item.operation == "move_chapter":
        if item.target_volume_id not in volume_ids:
            raise ValueError("章节移动的目标卷不存在。")
        if item.after_item_id is not None and item.after_item_id not in chapter_ids:
            raise ValueError("章节移动定位目标不存在。")
    if item.operation == "set_chapter_status" and item.chapter_status is None:
        raise ValueError("章节状态更新必须提供目标状态。")


def _change(
    kind: Literal["volume", "chapter"],
    item_id: str,
    action: str,
    title: str,
) -> StructureChangeResult:
    return StructureChangeResult(
        kind=kind,
        item_id=item_id,
        action=action,
        title=title,
    )
