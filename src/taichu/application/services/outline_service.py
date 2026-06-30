"""MVP writing outline use cases."""

from __future__ import annotations

from datetime import UTC, datetime
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
            return _sort_outline(outline)

        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        if not manifest.chapters:
            return outline

        volume_id = "volume-default"
        chapters = [
            OutlineChapter(
                chapter_id=chapter.id,
                display_title=_display_title(chapter.title),
                order=index + 1,
                markdown_path=chapter.markdown_path,
            )
            for index, chapter in enumerate(
                sorted(manifest.chapters, key=lambda item: item.order)
            )
        ]
        bootstrapped = WritingOutline(
            volumes=[
                OutlineVolume(
                    volume_id=volume_id,
                    name="第一卷",
                    order=1,
                    chapters=chapters,
                )
            ],
            current_volume_id=volume_id,
            current_chapter_id=manifest.current_chapter_id or chapters[0].chapter_id,
            updated_at=_now_iso(),
        )
        await self._storage.write_outline(bootstrapped.model_dump(mode="json"))
        return bootstrapped

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
        await self._storage.write_outline(updated.model_dump(mode="json"))
        await self._sync_manifest_volume(volume_id, name.strip() or f"第{next_order}卷", next_order)
        return _sort_outline(updated)

    async def rename_volume(self, volume_id: str, name: str) -> WritingOutline:
        """Rename a volume by stable id."""
        outline = await self.get_outline()
        volumes = [
            volume.model_copy(update={"name": name.strip() or volume.name})
            if volume.volume_id == volume_id
            else volume
            for volume in outline.volumes
        ]
        if all(volume.volume_id != volume_id for volume in outline.volumes):
            raise OutlineNotFoundError(f"卷“{volume_id}”不存在")
        updated = outline.model_copy(update={"volumes": volumes, "updated_at": _now_iso()})
        await self._storage.write_outline(updated.model_dump(mode="json"))
        await self._rename_manifest_volume(volume_id, name.strip())
        return _sort_outline(updated)

    async def create_chapter(
        self,
        volume_id: str,
        display_title: str | None = None,
    ) -> WritingOutline:
        """Create a blank chapter in the target volume."""
        outline = await self.get_outline()
        target = _find_volume(outline, volume_id)
        chapter_id = f"chapter-{uuid4().hex}"
        next_order = max((chapter.order for chapter in target.chapters), default=0) + 1
        title = display_title.strip() if display_title else f"第{next_order}章 未命名"
        chapter = OutlineChapter(
            chapter_id=chapter_id,
            display_title=_display_title(title),
            order=next_order,
            markdown_path=f"manuscripts/chapters/{volume_id}/{chapter_id}.md",
        )
        await self._storage.write_chapter_markdown(chapter.markdown_path, "")
        volumes = [
            volume.model_copy(update={"chapters": [*volume.chapters, chapter]})
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
        await self._storage.write_outline(updated.model_dump(mode="json"))
        await self._append_manifest_chapter(target, chapter)
        return _sort_outline(updated)

    async def rename_chapter(
        self,
        chapter_id: str,
        display_title: str,
    ) -> WritingOutline:
        """Rename a chapter by stable id."""
        outline = await self.get_outline()
        found = False
        volumes: list[OutlineVolume] = []
        for volume in outline.volumes:
            chapters: list[OutlineChapter] = []
            for chapter in volume.chapters:
                if chapter.chapter_id == chapter_id:
                    found = True
                    chapters.append(
                        chapter.model_copy(
                            update={"display_title": _display_title(display_title)}
                        )
                    )
                else:
                    chapters.append(chapter)
            volumes.append(volume.model_copy(update={"chapters": chapters}))
        if not found:
            raise OutlineNotFoundError(f"章节“{chapter_id}”不存在")
        updated = outline.model_copy(update={"volumes": volumes, "updated_at": _now_iso()})
        await self._storage.write_outline(updated.model_dump(mode="json"))
        await self._rename_manifest_chapter(chapter_id, _display_title(display_title))
        return _sort_outline(updated)

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
        chapters = [
            item
            for item in manifest.chapters
            if item.id != chapter.chapter_id
        ]
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


class OutlineNotFoundError(LookupError):
    """Raised when an outline volume or chapter cannot be found."""


def _find_volume(outline: WritingOutline, volume_id: str) -> OutlineVolume:
    for volume in outline.volumes:
        if volume.volume_id == volume_id:
            return volume
    raise OutlineNotFoundError(f"卷“{volume_id}”不存在")


def _sort_outline(outline: WritingOutline) -> WritingOutline:
    volumes = [
        volume.model_copy(
            update={"chapters": sorted(volume.chapters, key=lambda item: item.order)}
        )
        for volume in sorted(outline.volumes, key=lambda item: item.order)
    ]
    return outline.model_copy(update={"volumes": volumes})


def _display_title(title: str) -> str:
    title = title.strip() or "未命名章节"
    return re.sub(r"第0+(\d+)章", r"第\1章", title)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
