"""卷章写入工具的只读副作用对账。"""

from __future__ import annotations

from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.outline_service import OutlineService
from taichu.application.tools._shared import sha256_text
from taichu.application.tools._structure import current_structure_version
from taichu.application.tools.contract import (
    ToolReconciliationResult,
    ToolReconciliationStatus,
)
from taichu.application.tools.models import (
    CreateNovelStructureItemsInput,
    DeleteNovelStructureItemsInput,
    NovelStructureWriteOutput,
    StructureChangeResult,
    UpdateNovelStructureInput,
)


async def reconcile_created_items(
    tool_input: CreateNovelStructureItemsInput,
    chapter_service: ChapterService,
    outline_service: OutlineService,
) -> ToolReconciliationResult:
    outline = await outline_service.get_outline()
    current_version = await current_structure_version(chapter_service, outline_service)
    evidence = {
        "expected_structure_version": tool_input.expected_structure_version,
        "actual_structure_version": current_version,
    }
    if current_version == tool_input.expected_structure_version:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="卷章结构仍是写入前版本。",
        )
    changes: list[StructureChangeResult] = []
    for item in tool_input.items:
        if item.kind == "volume":
            matches = [
                volume for volume in outline.volumes if volume.name == item.title
            ]
            if len(matches) != 1:
                return _unknown(evidence, "无法唯一确认待创建卷是否由本次写入产生。")
            changes.append(
                StructureChangeResult(
                    kind="volume",
                    item_id=matches[0].volume_id,
                    action="created",
                    title=matches[0].name,
                )
            )
            continue
        volume = next(
            (entry for entry in outline.volumes if entry.volume_id == item.volume_id),
            None,
        )
        if volume is None:
            return _unknown(evidence, "待创建章节的目标卷不存在。")
        matches = [
            chapter
            for chapter in volume.chapters
            if chapter.display_title == item.title
            or chapter.display_title.endswith(item.title)
        ]
        if len(matches) != 1:
            return _unknown(evidence, "无法唯一确认待创建章节是否由本次写入产生。")
        changes.append(
            StructureChangeResult(
                kind="chapter",
                item_id=matches[0].chapter_id,
                action="created",
                title=matches[0].display_title,
            )
        )
    return _succeeded(
        previous=tool_input.expected_structure_version,
        current=current_version,
        changes=changes,
        audit_prefix="structure_write",
        idempotency_key=tool_input.idempotency_key,
        evidence=evidence,
        reason="所有待创建卷章均能在当前结构中唯一定位。",
    )


async def reconcile_updated_items(
    tool_input: UpdateNovelStructureInput,
    chapter_service: ChapterService,
    outline_service: OutlineService,
) -> ToolReconciliationResult:
    outline = await outline_service.get_outline()
    current_version = await current_structure_version(chapter_service, outline_service)
    evidence = {
        "expected_structure_version": tool_input.expected_structure_version,
        "actual_structure_version": current_version,
    }
    if current_version == tool_input.expected_structure_version:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="卷章结构仍是写入前版本。",
        )
    volumes = {volume.volume_id: volume for volume in outline.volumes}
    chapters = {
        chapter.chapter_id: (volume, chapter)
        for volume in outline.volumes
        for chapter in volume.chapters
    }
    chapter_records = {item.id: item for item in await chapter_service.list_chapters()}
    changes: list[StructureChangeResult] = []
    for operation in tool_input.operations:
        if operation.operation == "rename_volume":
            volume = volumes.get(operation.target_id)
            if volume is None or volume.name != operation.title:
                return _unknown(evidence, "目标卷名称与授权结果不一致。")
            changes.append(_change("volume", volume.volume_id, "renamed", volume.name))
        elif operation.operation == "rename_chapter":
            pair = chapters.get(operation.target_id)
            if pair is None or not pair[1].display_title.endswith(str(operation.title)):
                return _unknown(evidence, "目标章节名称与授权结果不一致。")
            changes.append(
                _change("chapter", pair[1].chapter_id, "renamed", pair[1].display_title)
            )
        elif operation.operation == "move_volume":
            if not _is_after(
                [volume.volume_id for volume in outline.volumes],
                operation.target_id,
                operation.after_item_id,
            ):
                return _unknown(evidence, "目标卷位置与授权结果不一致。")
            volume = volumes[operation.target_id]
            changes.append(_change("volume", volume.volume_id, "moved", volume.name))
        elif operation.operation == "move_chapter":
            target_volume = volumes.get(str(operation.target_volume_id))
            if target_volume is None or not _is_after(
                [chapter.chapter_id for chapter in target_volume.chapters],
                operation.target_id,
                operation.after_item_id,
            ):
                return _unknown(evidence, "目标章节位置与授权结果不一致。")
            chapter = chapters[operation.target_id][1]
            changes.append(
                _change("chapter", chapter.chapter_id, "moved", chapter.display_title)
            )
        else:
            chapter = chapter_records.get(operation.target_id)
            if chapter is None or chapter.status != operation.chapter_status:
                return _unknown(evidence, "目标章节状态与授权结果不一致。")
            changes.append(
                _change("chapter", chapter.id, "status_updated", chapter.title)
            )
    return _succeeded(
        previous=tool_input.expected_structure_version,
        current=current_version,
        changes=changes,
        audit_prefix="structure_write",
        idempotency_key=tool_input.idempotency_key,
        evidence=evidence,
        reason="所有卷章更新均与授权后的目标状态一致。",
    )


async def reconcile_deleted_items(
    tool_input: DeleteNovelStructureItemsInput,
    chapter_service: ChapterService,
    outline_service: OutlineService,
) -> ToolReconciliationResult:
    outline = await outline_service.get_outline()
    current_version = await current_structure_version(chapter_service, outline_service)
    evidence = {
        "expected_structure_version": tool_input.expected_structure_version,
        "actual_structure_version": current_version,
    }
    if current_version == tool_input.expected_structure_version:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="卷章结构仍是删除前版本。",
        )
    volume_ids = {volume.volume_id for volume in outline.volumes}
    chapter_ids = {
        chapter.chapter_id for volume in outline.volumes for chapter in volume.chapters
    }
    for target in tool_input.targets:
        existing = volume_ids if target.kind == "volume" else chapter_ids
        if target.target_id in existing:
            return _unknown(evidence, "仍有待归档目标存在，无法证明批量删除完整生效。")
    changes = [
        _change(target.kind, target.target_id, "archived", target.target_id)
        for target in tool_input.targets
    ]
    return _succeeded(
        previous=tool_input.expected_structure_version,
        current=current_version,
        changes=changes,
        audit_prefix="structure_delete",
        idempotency_key=tool_input.idempotency_key,
        evidence=evidence,
        reason="所有授权归档目标都已退出当前有效卷章结构。",
    )


def _succeeded(
    *,
    previous: str,
    current: str,
    changes: list[StructureChangeResult],
    audit_prefix: str,
    idempotency_key: str,
    evidence: dict[str, object],
    reason: str,
) -> ToolReconciliationResult:
    output = NovelStructureWriteOutput(
        previous_structure_version=previous,
        structure_version=current,
        changes=changes,
        audit_ref=f"{audit_prefix}:{sha256_text(idempotency_key)[:24]}",
        source_refs=["manuscript:manifest", "manuscript:outline"],
    )
    return ToolReconciliationResult(
        status=ToolReconciliationStatus.SUCCEEDED,
        output=output.model_dump(mode="json"),
        evidence=evidence,
        reason=reason,
    )


def _unknown(evidence: dict[str, object], reason: str) -> ToolReconciliationResult:
    return ToolReconciliationResult(
        status=ToolReconciliationStatus.UNKNOWN,
        evidence=evidence,
        reason=reason,
    )


def _change(kind: str, item_id: str, action: str, title: str) -> StructureChangeResult:
    return StructureChangeResult(
        kind=kind,  # type: ignore[arg-type]
        item_id=item_id,
        action=action,
        title=title,
    )


def _is_after(values: list[str], target: str, after: str | None) -> bool:
    if target not in values:
        return False
    target_index = values.index(target)
    if after is None:
        return target_index == 0
    return after in values and target_index == values.index(after) + 1
