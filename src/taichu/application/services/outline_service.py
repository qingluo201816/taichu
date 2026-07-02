"""MVP writing outline use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models import (
    OutlineChapter,
    OutlineVolume,
    WritingOutline,
)
from taichu.domain.models.chapter import (
    Chapter,
    ChapterManifest,
    ChapterStatus,
    Volume,
)


class OutlineService:
    """Manage the persistent volume and chapter tree."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def get_outline(self) -> WritingOutline:
        """Read the outline, bootstrapping from the legacy manifest if needed."""
        await self._storage.ensure_skeleton()
        outline = WritingOutline.model_validate(await self._storage.read_outline())
        if outline.volumes:
            normalized = _normalize_outline(outline)
            await self._move_existing_outline_paths(outline, normalized)
            if normalized.model_dump(mode="json") != outline.model_dump(mode="json"):
                await self._storage.write_outline(normalized.model_dump(mode="json"))
                await self._sync_manifest_from_outline(normalized)
            return normalized

        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        if not manifest.chapters:
            return outline

        bootstrapped = _outline_from_manifest(manifest)
        normalized = _normalize_outline(bootstrapped)
        await self._move_existing_outline_paths(bootstrapped, normalized)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def create_volume(self, name: str) -> WritingOutline:
        """Create an empty volume and make it current."""
        outline = await self.get_outline()
        volume_id = f"volume-{uuid4().hex}"
        next_order = max((volume.order for volume in outline.volumes), default=0) + 1
        updated = outline.model_copy(
            update={
                "volumes": [
                    *outline.volumes,
                    OutlineVolume(
                        volume_id=volume_id,
                        name=name.strip() or f"第{next_order}卷",
                        order=next_order,
                    ),
                ],
                "current_volume_id": volume_id,
                "updated_at": _now_iso(),
            }
        )
        normalized = _normalize_outline(updated)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def rename_volume(self, volume_id: str, name: str) -> WritingOutline:
        """Rename a volume by stable id."""
        outline = await self.get_outline()
        old_outline = outline
        volumes = [
            volume.model_copy(update={"name": name.strip() or volume.name})
            if volume.volume_id == volume_id
            else volume
            for volume in outline.volumes
        ]
        if all(volume.volume_id != volume_id for volume in outline.volumes):
            raise OutlineNotFoundError(f"卷“{volume_id}”不存在")
        updated = outline.model_copy(
            update={"volumes": volumes, "updated_at": _now_iso()}
        )
        normalized = _normalize_outline(updated)
        await self._move_existing_outline_paths(old_outline, normalized)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def delete_volume(self, volume_id: str) -> WritingOutline:
        """Remove a volume and archive all Markdown files owned by it."""
        outline = await self.get_outline()
        target = _find_volume(outline, volume_id)
        for chapter in _ordered_chapters(target):
            await self._storage.move_chapter_markdown(
                chapter.markdown_path,
                _deleted_chapter_markdown_path(target, chapter),
            )
        volumes = [
            volume for volume in outline.volumes if volume.volume_id != volume_id
        ]
        current_chapter_id = _current_chapter_after_volume_delete(
            outline,
            volume_id,
            volumes,
        )
        updated = outline.model_copy(
            update={
                "volumes": volumes,
                "current_chapter_id": current_chapter_id,
                "updated_at": _now_iso(),
            }
        )
        normalized = _normalize_outline(updated)
        normalized = normalized.model_copy(
            update={"current_volume_id": _current_volume_id(normalized)}
        )
        await self._move_existing_outline_paths(outline, normalized)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def create_chapter(
        self,
        volume_id: str,
        display_title: str | None = None,
        *,
        after_chapter_id: str | None = None,
    ) -> WritingOutline:
        """Create a blank chapter in the target volume."""
        outline = await self.get_outline()
        old_outline = outline
        target = _find_volume(outline, volume_id)
        chapter_id = f"chapter-{uuid4().hex}"
        target_chapters = _ordered_chapters(target)
        insert_index = len(target_chapters)
        if after_chapter_id is not None:
            for index, chapter in enumerate(target_chapters):
                if chapter.chapter_id == after_chapter_id:
                    insert_index = index + 1
                    break
            else:
                raise OutlineNotFoundError(f"章节“{after_chapter_id}”不属于目标卷")
        chapter = OutlineChapter(
            chapter_id=chapter_id,
            display_title=display_title or "第0章",
            order=0,
            markdown_path="manuscripts/chapters/chapter_pending.md",
        )
        next_chapters = [
            *target_chapters[:insert_index],
            chapter,
            *target_chapters[insert_index:],
        ]
        next_chapters = _with_local_order(next_chapters)
        volumes = [
            target.model_copy(update={"chapters": next_chapters})
            if volume.volume_id == volume_id
            else volume
            for volume in outline.volumes
        ]
        updated = outline.model_copy(
            update={
                "volumes": volumes,
                "current_volume_id": volume_id,
                "current_chapter_id": chapter_id,
                "updated_at": _now_iso(),
            }
        )
        normalized = _normalize_outline(updated)
        await self._move_existing_outline_paths(old_outline, normalized)
        new_chapter = _find_outline_chapter(normalized, chapter_id)
        await self._storage.write_chapter_markdown(new_chapter.markdown_path, "")
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def rename_chapter(
        self,
        chapter_id: str,
        display_title: str,
    ) -> WritingOutline:
        """Rename a chapter by stable id."""
        outline = await self.get_outline()
        old_outline = outline
        found = False
        volumes: list[OutlineVolume] = []
        for volume in outline.volumes:
            chapters = _ordered_chapters(volume)
            next_chapters: list[OutlineChapter] = []
            for chapter in chapters:
                if chapter.chapter_id == chapter_id:
                    found = True
                    next_chapters.append(
                        chapter.model_copy(update={"display_title": display_title})
                    )
                else:
                    next_chapters.append(chapter)
            volumes.append(volume.model_copy(update={"chapters": next_chapters}))
        if not found:
            raise OutlineNotFoundError(f"章节“{chapter_id}”不存在")
        updated = outline.model_copy(
            update={"volumes": volumes, "updated_at": _now_iso()}
        )
        normalized = _normalize_outline(updated)
        await self._move_existing_outline_paths(old_outline, normalized)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def delete_chapter(self, chapter_id: str) -> WritingOutline:
        """Remove a chapter from the outline and archive its Markdown."""
        outline = await self.get_outline()
        target_volume: OutlineVolume | None = None
        deleted_chapter: OutlineChapter | None = None
        for volume in outline.volumes:
            for chapter in volume.chapters:
                if chapter.chapter_id == chapter_id:
                    target_volume = volume
                    deleted_chapter = chapter
                    break
            if deleted_chapter is not None:
                break
        if target_volume is None or deleted_chapter is None:
            raise OutlineNotFoundError(f"章节“{chapter_id}”不存在")

        await self._storage.move_chapter_markdown(
            deleted_chapter.markdown_path,
            _deleted_chapter_markdown_path(target_volume, deleted_chapter),
        )
        remaining_chapters = [
            chapter
            for chapter in _ordered_chapters(target_volume)
            if chapter.chapter_id != chapter_id
        ]
        volumes = [
            target_volume.model_copy(update={"chapters": remaining_chapters})
            if volume.volume_id == target_volume.volume_id
            else volume
            for volume in outline.volumes
        ]
        updated = outline.model_copy(
            update={
                "volumes": volumes,
                "current_chapter_id": _current_chapter_after_chapter_delete(
                    outline,
                    chapter_id,
                    deleted_chapter.order,
                    volumes,
                ),
                "updated_at": _now_iso(),
            }
        )
        normalized = _normalize_outline(updated)
        normalized = normalized.model_copy(
            update={
                "current_volume_id": _current_volume_id(normalized),
            }
        )
        await self._move_existing_outline_paths(outline, normalized)
        await self._storage.write_outline(normalized.model_dump(mode="json"))
        await self._sync_manifest_from_outline(normalized)
        return normalized

    async def _sync_manifest_volume(
        self,
        volume_id: str,
        name: str,
        order: int,
    ) -> None:
        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        volumes = list(manifest.volumes)
        if all(volume.id != volume_id for volume in volumes):
            volumes.append(Volume(id=volume_id, title=name, order=order))
        updated = manifest.model_copy(
            update={"volumes": volumes, "updated_at": _now_iso()}
        )
        await self._storage.write_manifest(updated.model_dump(mode="json"))

    async def _rename_manifest_volume(self, volume_id: str, name: str) -> None:
        if not name:
            return
        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        volumes = [
            volume.model_copy(update={"title": name})
            if volume.id == volume_id
            else volume
            for volume in manifest.volumes
        ]
        updated = manifest.model_copy(
            update={"volumes": volumes, "updated_at": _now_iso()}
        )
        await self._storage.write_manifest(updated.model_dump(mode="json"))

    async def _append_manifest_chapter(
        self,
        volume: OutlineVolume,
        chapter: OutlineChapter,
    ) -> None:
        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        volumes = list(manifest.volumes)
        if all(item.id != volume.volume_id for item in volumes):
            volumes.append(
                Volume(id=volume.volume_id, title=volume.name, order=volume.order)
            )
        now = _now_iso()
        manifest_order = max((item.order for item in manifest.chapters), default=0) + 1
        chapters = [item for item in manifest.chapters if item.id != chapter.chapter_id]
        chapters.append(
            Chapter(
                id=chapter.chapter_id,
                volume_id=volume.volume_id,
                title=chapter.display_title,
                order=manifest_order,
                markdown_path=chapter.markdown_path,
                status=ChapterStatus.DRAFT,
                word_count=0,
                created_at=now,
                updated_at=now,
            )
        )
        updated = manifest.model_copy(
            update={
                "current_chapter_id": chapter.chapter_id,
                "volumes": volumes,
                "chapters": chapters,
                "updated_at": now,
            }
        )
        await self._storage.write_manifest(updated.model_dump(mode="json"))

    async def _rename_manifest_chapter(
        self,
        chapter_id: str,
        display_title: str,
    ) -> None:
        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        chapters = [
            chapter.model_copy(update={"title": display_title})
            if chapter.id == chapter_id
            else chapter
            for chapter in manifest.chapters
        ]
        updated = manifest.model_copy(
            update={"chapters": chapters, "updated_at": _now_iso()}
        )
        await self._storage.write_manifest(updated.model_dump(mode="json"))

    async def _sync_manifest_from_outline(self, outline: WritingOutline) -> None:
        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        existing_by_id = {chapter.id: chapter for chapter in manifest.chapters}
        now = _now_iso()
        volumes = [
            Volume(id=volume.volume_id, title=volume.name, order=volume.order)
            for volume in sorted(outline.volumes, key=lambda item: item.order)
        ]
        chapters: list[Chapter] = []
        global_order = 1
        for volume in sorted(outline.volumes, key=lambda item: item.order):
            for outline_chapter in _ordered_chapters(volume):
                existing = existing_by_id.get(outline_chapter.chapter_id)
                if existing is None:
                    chapters.append(
                        Chapter(
                            id=outline_chapter.chapter_id,
                            volume_id=volume.volume_id,
                            title=outline_chapter.display_title,
                            order=global_order,
                            markdown_path=outline_chapter.markdown_path,
                            status=ChapterStatus.DRAFT,
                            word_count=0,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    chapters.append(
                        existing.model_copy(
                            update={
                                "volume_id": volume.volume_id,
                                "title": outline_chapter.display_title,
                                "order": global_order,
                                "markdown_path": outline_chapter.markdown_path,
                                "updated_at": now,
                            }
                        )
                    )
                global_order += 1
        updated = manifest.model_copy(
            update={
                "current_chapter_id": outline.current_chapter_id,
                "volumes": volumes,
                "chapters": chapters,
                "updated_at": now,
            }
        )
        await self._storage.write_manifest(updated.model_dump(mode="json"))

    async def _move_existing_outline_paths(
        self,
        old_outline: WritingOutline,
        new_outline: WritingOutline,
    ) -> None:
        old_by_id = _outline_chapter_map(old_outline)
        moves: list[tuple[str, str]] = []
        for chapter in _outline_chapters_in_order(new_outline):
            old_chapter = old_by_id.get(chapter.chapter_id)
            if (
                old_chapter is None
                or old_chapter.markdown_path == chapter.markdown_path
            ):
                continue
            moves.append((old_chapter.markdown_path, chapter.markdown_path))
        temporary_moves: list[tuple[str, str]] = []
        for source_path, target_path in moves:
            temporary_path = _temporary_chapter_markdown_path(target_path)
            await self._storage.move_chapter_markdown(source_path, temporary_path)
            temporary_moves.append((temporary_path, target_path))
        for temporary_path, target_path in temporary_moves:
            await self._storage.move_chapter_markdown(temporary_path, target_path)


class OutlineNotFoundError(LookupError):
    """Raised when an outline volume or chapter cannot be found."""


def _find_volume(outline: WritingOutline, volume_id: str) -> OutlineVolume:
    for volume in outline.volumes:
        if volume.volume_id == volume_id:
            return volume
    raise OutlineNotFoundError(f"卷“{volume_id}”不存在")


def _find_outline_chapter(
    outline: WritingOutline,
    chapter_id: str,
) -> OutlineChapter:
    for chapter in _outline_chapters_in_order(outline):
        if chapter.chapter_id == chapter_id:
            return chapter
    raise OutlineNotFoundError(f"章节“{chapter_id}”不存在")


def _ordered_chapters(volume: OutlineVolume) -> list[OutlineChapter]:
    return sorted(volume.chapters, key=lambda item: item.order)


def _with_local_order(chapters: list[OutlineChapter]) -> list[OutlineChapter]:
    return [
        chapter.model_copy(update={"order": index})
        for index, chapter in enumerate(chapters, start=1)
    ]


def _outline_chapters_in_order(outline: WritingOutline) -> list[OutlineChapter]:
    chapters: list[OutlineChapter] = []
    for volume in sorted(outline.volumes, key=lambda item: item.order):
        chapters.extend(_ordered_chapters(volume))
    return chapters


def _outline_chapter_map(outline: WritingOutline) -> dict[str, OutlineChapter]:
    return {
        chapter.chapter_id: chapter
        for chapter in _outline_chapters_in_order(outline)
    }


def _normalize_outline(outline: WritingOutline) -> WritingOutline:
    normalized_volumes: list[OutlineVolume] = []
    chapter_order = 1
    for volume_order, volume in enumerate(
        sorted(outline.volumes, key=lambda item: item.order),
        start=1,
    ):
        normalized_volume = volume.model_copy(update={"order": volume_order})
        normalized_chapters: list[OutlineChapter] = []
        for chapter in _ordered_chapters(volume):
            display_title = _chapter_display_title(
                chapter_order,
                chapter.display_title,
            )
            normalized_chapters.append(
                chapter.model_copy(
                    update={
                        "display_title": display_title,
                        "order": chapter_order,
                        "markdown_path": _chapter_markdown_path(
                            normalized_volume,
                            chapter_order,
                            display_title,
                        ),
                    }
                )
            )
            chapter_order += 1
        normalized_volumes.append(
            normalized_volume.model_copy(update={"chapters": normalized_chapters})
        )

    chapter_ids = {
        chapter.chapter_id
        for volume in normalized_volumes
        for chapter in volume.chapters
    }
    current_chapter_id = (
        outline.current_chapter_id
        if outline.current_chapter_id in chapter_ids
        else _first_chapter_id(normalized_volumes)
    )
    volume_ids = {volume.volume_id for volume in normalized_volumes}
    current_volume_id = (
        outline.current_volume_id if outline.current_volume_id in volume_ids else None
    )
    if current_volume_id is None and current_chapter_id is not None:
        current_volume_id = _volume_id_for_chapter(
            normalized_volumes,
            current_chapter_id,
        )
    if current_volume_id is None:
        current_volume_id = (
            normalized_volumes[0].volume_id if normalized_volumes else None
        )
    return outline.model_copy(
        update={
            "volumes": normalized_volumes,
            "current_volume_id": current_volume_id,
            "current_chapter_id": current_chapter_id,
        }
    )


def _outline_from_manifest(manifest: ChapterManifest) -> WritingOutline:
    manifest_volumes = sorted(manifest.volumes, key=lambda item: item.order)
    default_volume_id = manifest_volumes[0].id if manifest_volumes else "volume-default"
    volume_meta_by_id: dict[str, tuple[str, int]] = {
        volume.id: (volume.title, index)
        for index, volume in enumerate(manifest_volumes, start=1)
    }
    volume_chapters_by_id: dict[str, list[OutlineChapter]] = {
        volume_id: [] for volume_id in volume_meta_by_id
    }
    if not volume_meta_by_id:
        volume_meta_by_id[default_volume_id] = ("第一卷", 1)
        volume_chapters_by_id[default_volume_id] = []
    for index, chapter in enumerate(
        sorted(manifest.chapters, key=lambda item: item.order),
        start=1,
    ):
        volume_id = chapter.volume_id or default_volume_id
        if volume_id not in volume_meta_by_id:
            order = len(volume_meta_by_id) + 1
            volume_meta_by_id[volume_id] = (f"第{order}卷", order)
            volume_chapters_by_id[volume_id] = []
        volume_chapters_by_id[volume_id].append(
            OutlineChapter(
                chapter_id=chapter.id,
                display_title=_chapter_display_title(index, chapter.title),
                order=index,
                markdown_path=chapter.markdown_path,
            )
        )
    volumes = sorted(
        (
            OutlineVolume(
                volume_id=volume_id,
                name=name,
                order=order,
                chapters=volume_chapters_by_id[volume_id],
            )
            for volume_id, (name, order) in volume_meta_by_id.items()
        ),
        key=lambda item: item.order,
    )
    current_chapter_id = manifest.current_chapter_id or _first_chapter_id(volumes)
    return WritingOutline(
        volumes=volumes,
        current_volume_id=(
            _volume_id_for_chapter(volumes, current_chapter_id)
            if current_chapter_id
            else volumes[0].volume_id
        ),
        current_chapter_id=current_chapter_id,
        updated_at=manifest.updated_at,
    )


def _chapter_display_title(order: int, title: str) -> str:
    body = _chapter_title_body(title)
    prefix = f"第{order}章"
    if not body:
        return prefix
    return f"{prefix} {body}"


def _chapter_title_body(title: str) -> str:
    stripped = title.strip()
    return re.sub(
        r"^第[0-9零〇一二三四五六七八九十百千万两]+章[\s\u3000:：、-]*",
        "",
        stripped,
    ).strip()


def _chapter_markdown_path(
    volume: OutlineVolume,
    order: int,
    display_title: str,
) -> str:
    return (
        f"manuscripts/chapters/{_volume_directory_name(volume)}/"
        f"{_chapter_file_name(order, display_title)}"
    )


def _deleted_chapter_markdown_path(
    volume: OutlineVolume,
    chapter: OutlineChapter,
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz").lower()
    return (
        f"manuscripts/deleted_chapters/{_volume_directory_name(volume)}/"
        f"deleted_{timestamp}_{_chapter_file_name(chapter.order, chapter.display_title)}"
    )


def _chapter_file_name(order: int, display_title: str) -> str:
    body = _safe_path_segment(_chapter_title_body(display_title), "")
    if not body:
        return f"chapter_{order:03d}.md"
    return f"chapter_{order:03d}_{body}.md"


def _volume_directory_name(volume: OutlineVolume) -> str:
    return f"volume_{volume.order:03d}_{_safe_path_segment(volume.name, '未命名卷')}"


def _safe_path_segment(text: str, fallback: str) -> str:
    cleaned = re.sub(
        r"[^\w\u3400-\u4dbf\u4e00-\u9fff.-]+",
        "_",
        text.strip(),
        flags=re.UNICODE,
    )
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    if cleaned in {"", ".", ".."}:
        cleaned = fallback
    return cleaned[:64] or fallback


def _temporary_chapter_markdown_path(target_path: str) -> str:
    parent = PurePosixPath(target_path).parent.as_posix()
    return f"{parent}/chapter_reorder_{uuid4().hex}.md"


def _current_chapter_after_chapter_delete(
    outline: WritingOutline,
    deleted_chapter_id: str,
    deleted_order: int,
    volumes: list[OutlineVolume],
) -> str | None:
    if outline.current_chapter_id != deleted_chapter_id:
        return outline.current_chapter_id
    remaining = [
        chapter
        for volume in sorted(volumes, key=lambda item: item.order)
        for chapter in _ordered_chapters(volume)
    ]
    next_chapter = next(
        (chapter for chapter in remaining if chapter.order > deleted_order),
        None,
    )
    if next_chapter is not None:
        return next_chapter.chapter_id
    return remaining[-1].chapter_id if remaining else None


def _current_chapter_after_volume_delete(
    outline: WritingOutline,
    deleted_volume_id: str,
    volumes: list[OutlineVolume],
) -> str | None:
    remaining_ids = {
        chapter.chapter_id
        for volume in volumes
        for chapter in volume.chapters
    }
    if (
        outline.current_volume_id != deleted_volume_id
        and outline.current_chapter_id in remaining_ids
    ):
        return outline.current_chapter_id
    remaining = [
        chapter
        for volume in sorted(volumes, key=lambda item: item.order)
        for chapter in _ordered_chapters(volume)
    ]
    return remaining[0].chapter_id if remaining else None


def _first_chapter_id(volumes: list[OutlineVolume]) -> str | None:
    for volume in sorted(volumes, key=lambda item: item.order):
        chapters = _ordered_chapters(volume)
        if chapters:
            return chapters[0].chapter_id
    return None


def _volume_id_for_chapter(
    volumes: list[OutlineVolume],
    chapter_id: str,
) -> str | None:
    for volume in volumes:
        if any(chapter.chapter_id == chapter_id for chapter in volume.chapters):
            return volume.volume_id
    return None


def _current_volume_id(outline: WritingOutline) -> str | None:
    if outline.current_chapter_id is None:
        return outline.current_volume_id
    for volume in outline.volumes:
        if any(
            chapter.chapter_id == outline.current_chapter_id
            for chapter in volume.chapters
        ):
            return volume.volume_id
    return outline.current_volume_id


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
