"""从隔离案例的真实业务事实源采集资源快照。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    ObservedResourceSnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.resource_observation import (
    ResourceStateItem,
    ResourceStatePayload,
)


async def capture_case_resource_state(
    *,
    workspace: Path,
    knowledge_repository: StructuredKnowledgeRepository,
) -> tuple[ResourceStateItem, ...]:
    """读取 Markdown/结构事实与 MongoDB confirmed 卡，不读取派生运行目录。"""

    resolved_workspace = workspace.resolve(strict=True)
    source_root = (resolved_workspace / "source").resolve(strict=True)
    manuscript_root = (source_root / "manuscripts").resolve(strict=True)
    if not manuscript_root.is_relative_to(source_root):
        raise ValueError("正文资源根越过隔离 source 边界。")

    resources: list[ResourceStateItem] = []
    for path in sorted(manuscript_root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"资源快照禁止符号链接：{path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source_root).as_posix()
        if relative == "manuscripts/outline.json":
            resources.extend(_structure_items(path))
        resources.append(
            ResourceStateItem(
                resource_ref=_manuscript_resource_ref(relative),
                state="present",
                content_sha256=_resource_content_sha256(path),
            )
        )

    cards = await knowledge_repository.list_confirmed_cards()
    for card in sorted(cards, key=lambda item: item.id):
        resources.append(
            ResourceStateItem(
                resource_ref=f"knowledge:{card.id}",
                state="present",
                content_sha256=canonical_sha256(
                    card.model_dump(mode="json")
                ),
            )
        )
    return tuple(sorted(resources, key=lambda item: item.resource_ref))


def seal_resource_snapshot(
    *,
    snapshot_ref: str,
    phase: Literal["before", "after"],
    resources: tuple[ResourceStateItem, ...],
    target_refs: tuple[str, ...] = (),
) -> ObservedResourceSnapshot:
    """把已读取的资源状态和实际目标集合封存成 owner 外的内容寻址快照。"""

    targets = tuple(sorted(set(target_refs)))
    resource_refs = {item.resource_ref for item in resources}
    protected = tuple(sorted(resource_refs - set(targets)))
    payload = ResourceStatePayload(
        schema="taichu.general_agent_benchmark.resource_state@1",
        resources=resources,
        target_refs=targets,
        protected_refs=protected,
    ).model_dump(mode="json", by_alias=True)
    return ObservedResourceSnapshot(
        snapshot_ref=snapshot_ref,
        phase=phase,
        content_sha256=canonical_sha256(payload),
        payload=payload,
    )


def _manuscript_resource_ref(relative: str) -> str:
    path = Path(relative)
    if (
        len(path.parts) >= 3
        and path.parts[:2] == ("manuscripts", "chapters")
        and path.suffix == ".md"
    ):
        return f"manuscript:{path.stem}"
    if relative == "manuscripts/manifest.json":
        return "manuscript:manifest"
    return f"manuscript_file:{relative}"


def _structure_items(path: Path) -> tuple[ResourceStateItem, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("结构资源无法形成规范快照。") from error
    volumes = payload.get("volumes")
    if not isinstance(volumes, list):
        raise ValueError("结构资源缺少 volumes 列表。")
    items: list[ResourceStateItem] = []
    for volume in volumes:
        if not isinstance(volume, dict):
            raise ValueError("结构卷必须是对象。")
        volume_id = volume.get("volume_id")
        if not isinstance(volume_id, str) or not volume_id:
            raise ValueError("结构卷缺少稳定 volume_id。")
        items.append(
            ResourceStateItem(
                resource_ref=f"structure:volume:{volume_id}",
                state="present",
                content_sha256=canonical_sha256(volume),
            )
        )
        chapters = volume.get("chapters", [])
        if not isinstance(chapters, list):
            raise ValueError("结构卷 chapters 必须是列表。")
        for chapter in chapters:
            if not isinstance(chapter, dict):
                raise ValueError("结构章节必须是对象。")
            chapter_id = chapter.get("chapter_id")
            if not isinstance(chapter_id, str) or not chapter_id:
                raise ValueError("结构章节缺少稳定 chapter_id。")
            items.append(
                ResourceStateItem(
                    resource_ref=f"structure:chapter:{chapter_id}",
                    state="present",
                    content_sha256=canonical_sha256(chapter),
                )
            )
    return tuple(items)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resource_content_sha256(path: Path) -> str:
    if path.suffix.lower() != ".md":
        return _file_sha256(path)
    try:
        normalized_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Markdown 资源无法读取：{path}") from error
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


__all__ = [
    "capture_case_resource_state",
    "seal_resource_snapshot",
]
