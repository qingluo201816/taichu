"""Chapter manifest and manuscript read use cases."""

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.chapter import Chapter, ChapterManifest


@dataclass(frozen=True)
class ChapterContent:
    """A chapter record with its Markdown body."""

    chapter: Chapter
    markdown: str


class ChapterService:
    """Application use cases for manuscript chapters."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def ensure_project_skeleton(self) -> None:
        """Ensure source/generated skeleton files exist for active root."""
        await self._storage.ensure_skeleton()

    async def get_manifest(self) -> ChapterManifest:
        """Return the current chapter manifest."""
        await self._storage.ensure_skeleton()
        return ChapterManifest.model_validate(
            await self._storage.read_manifest()
        )

    async def list_chapters(self) -> list[Chapter]:
        """List chapters in manifest order."""
        manifest = await self.get_manifest()
        return sorted(manifest.chapters, key=lambda chapter: chapter.order)

    async def read_chapter(self, chapter_id: str) -> ChapterContent:
        """Read one chapter by its stable id."""
        chapter = await self._find_chapter(chapter_id)
        markdown = await self._storage.read_chapter_markdown(
            chapter.markdown_path
        )
        return ChapterContent(chapter=chapter, markdown=markdown)

    async def save_chapter(
        self,
        chapter_id: str,
        markdown: str,
    ) -> ChapterContent:
        """Persist chapter Markdown and update manifest metadata."""
        manifest = await self.get_manifest()
        updated_at = _now_iso()
        updated_chapters: list[Chapter] = []
        saved_chapter: Chapter | None = None

        for chapter in manifest.chapters:
            if chapter.id != chapter_id:
                updated_chapters.append(chapter)
                continue
            saved_chapter = chapter.model_copy(
                update={
                    "word_count": _count_non_space(markdown),
                    "updated_at": updated_at,
                }
            )
            updated_chapters.append(saved_chapter)

        if saved_chapter is None:
            raise ChapterNotFoundError(chapter_id)

        await self._storage.write_chapter_markdown(
            saved_chapter.markdown_path,
            markdown,
        )
        updated_manifest = ChapterManifest(
            schema_version=manifest.schema_version,
            current_chapter_id=chapter_id,
            volumes=manifest.volumes,
            chapters=updated_chapters,
            updated_at=updated_at,
        )
        await self._storage.write_manifest(
            updated_manifest.model_dump(mode="json")
        )
        return ChapterContent(chapter=saved_chapter, markdown=markdown)

    async def clear_generated_projection_stub(self) -> None:
        """Empty generated projections without touching source assets."""
        await self._storage.clear_generated()

    async def _find_chapter(self, chapter_id: str) -> Chapter:
        for chapter in await self.list_chapters():
            if chapter.id == chapter_id:
                return chapter
        raise ChapterNotFoundError(chapter_id)


class ChapterNotFoundError(LookupError):
    """Raised when a chapter id is absent from the manifest."""

    def __init__(self, chapter_id: str) -> None:
        super().__init__(f"章节“{chapter_id}”不存在")


def _count_non_space(text: str) -> int:
    return len(re.findall(r"\S", text))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
