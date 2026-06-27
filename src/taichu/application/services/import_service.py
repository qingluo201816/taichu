"""Bounded corpus importer for manuscript chapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.chapter import Chapter, ChapterManifest, ChapterStatus
from taichu.domain.models.import_batch import ImportBatch

_TITLE_LINE = re.compile(
    r"^(?:#{1,6}\s*)?"
    r"(第[一二三四五六七八九十百千万零〇两0-9]+章(?:\s|[：:、-]|$)[^\n]*)$"
)


@dataclass(frozen=True)
class _ParsedChapter:
    title: str
    body: str


class ImportService:
    """Import a small TXT/Markdown corpus into source manuscripts."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def import_text(
        self,
        text: str,
        *,
        source_name: str,
        max_chapters: int = 5,
    ) -> ImportBatch:
        """Split a bounded corpus and write chapter Markdown plus manifest."""
        if max_chapters < 1:
            raise ValueError("max_chapters must be at least 1")
        all_chapters = _split_chapters(text)
        if not all_chapters:
            raise ValueError("no chapters found in import text")
        if len(all_chapters) > max_chapters:
            raise ImportLimitExceededError(
                found=len(all_chapters),
                limit=max_chapters,
            )
        parsed_chapters = all_chapters

        await self._storage.ensure_skeleton()
        manifest = ChapterManifest.model_validate(
            await self._storage.read_manifest()
        )
        existing_chapters = list(manifest.chapters)
        next_order = _next_order(existing_chapters)
        next_index = _next_chapter_index(existing_chapters)

        timestamp = _now_iso()
        imported: list[Chapter] = []
        for offset, parsed in enumerate(parsed_chapters):
            chapter_id = f"chapter_{next_index + offset:03d}"
            markdown_path = f"manuscripts/chapters/{chapter_id}.md"
            markdown = _format_chapter_markdown(parsed)
            chapter = Chapter(
                id=chapter_id,
                title=parsed.title,
                order=next_order + offset,
                markdown_path=markdown_path,
                status=ChapterStatus.ACTIVE,
                word_count=_count_non_space(markdown),
                created_at=timestamp,
                updated_at=timestamp,
            )
            await self._storage.write_chapter_markdown(
                markdown_path,
                markdown,
            )
            imported.append(chapter)

        updated_manifest = ChapterManifest(
            schema_version=manifest.schema_version,
            current_chapter_id=(
                manifest.current_chapter_id or imported[0].id
            ),
            volumes=manifest.volumes,
            chapters=[*existing_chapters, *imported],
            updated_at=timestamp,
        )
        await self._storage.write_manifest(
            updated_manifest.model_dump(mode="json")
        )

        return ImportBatch(
            id=f"import_{timestamp}",
            source_name=source_name,
            chapter_ids=[chapter.id for chapter in imported],
            chapter_count=len(imported),
            skipped_chapter_count=0,
            created_at=timestamp,
        )


class ImportLimitExceededError(ValueError):
    """Raised when an import batch exceeds the explicit MVP chapter limit."""

    def __init__(self, *, found: int, limit: int) -> None:
        super().__init__(
            f"Import contains {found} chapters; limit is {limit}. "
            "Split the corpus and import a smaller batch."
        )


def _split_chapters(text: str) -> list[_ParsedChapter]:
    current_title: str | None = None
    current_body: list[str] = []
    chapters: list[_ParsedChapter] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _TITLE_LINE.match(line)
        if match:
            if current_title is not None:
                chapters.append(
                    _ParsedChapter(
                        title=current_title,
                        body="\n".join(current_body).strip(),
                    )
                )
            current_title = match.group(1).strip()
            current_body = []
            continue
        if current_title is not None:
            current_body.append(raw_line.rstrip())

    if current_title is not None:
        chapters.append(
            _ParsedChapter(
                title=current_title,
                body="\n".join(current_body).strip(),
            )
        )
    return chapters


def _format_chapter_markdown(chapter: _ParsedChapter) -> str:
    body = chapter.body.strip()
    if body:
        return f"# {chapter.title}\n\n{body}\n"
    return f"# {chapter.title}\n"


def _next_order(chapters: list[Chapter]) -> int:
    if not chapters:
        return 0
    return max(chapter.order for chapter in chapters) + 1


def _next_chapter_index(chapters: list[Chapter]) -> int:
    numbers: list[int] = []
    for chapter in chapters:
        match = re.fullmatch(r"chapter_(\d+)", chapter.id)
        if match:
            numbers.append(int(match.group(1)))
    if not numbers:
        return 1
    return max(numbers) + 1


def _count_non_space(text: str) -> int:
    return len(re.findall(r"\S", text))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
