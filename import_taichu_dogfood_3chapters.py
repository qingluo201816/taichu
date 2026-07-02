"""Import the first 100 real Taichu novel chapters for RC dogfooding.

This is a temporary root-level helper, not a product import feature.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from taichu.application.services.outline_service import OutlineService  # noqa: E402
from taichu.config import settings  # noqa: E402
from taichu.domain.models import WritingOutline  # noqa: E402
from taichu.domain.models.chapter import (  # noqa: E402
    ChapterManifest,
    ChapterStatus,
)
from taichu.infrastructure.storage.markdown_backend import (  # noqa: E402
    ProjectAssetStorageBackend,
)

DEFAULT_CHAPTER_COUNT = 100
DEFAULT_CHAPTERS_PER_VOLUME = 25
NOVEL_DIR_MARKER = "\u6821\u5bf9\u7248\u5168\u672c"
NOVEL_TITLE_MARKER = "\u300a\u592a\u521d\u300b"
CHAPTER_TITLE_PATTERN = re.compile(
    r"^[ \t\u3000]*"
    r"(\u7b2c[\u3007\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d"
    r"\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\u4e240-9\uff10-\uff19]"
    r"{1,8}\u7ae0[^\r\n]*)"
    r"[ \t\u3000]*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SourceChapter:
    """One parsed real-novel chapter from the source TXT."""

    heading: str
    body: str


@dataclass(frozen=True)
class ChapterSlice:
    """A bounded real-novel import batch."""

    chapters: list[SourceChapter]

    @property
    def headings(self) -> list[str]:
        """Return source headings for preview output."""
        return [chapter.heading for chapter in self.chapters]


def parse_args() -> argparse.Namespace:
    """Parse command line options for the temporary dogfood importer."""
    parser = argparse.ArgumentParser(
        description=(
            "Import the first chapters from the bundled real Taichu TXT into "
            "project_assets for MVP-0.1 RC dogfooding."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="TXT source file. Defaults to the bundled real Taichu TXT.",
    )
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=settings.project_assets_dir,
        help="project_assets root to write. Defaults to configured project_assets.",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=DEFAULT_CHAPTER_COUNT,
        help="Number of chapters to import. Defaults to 100.",
    )
    parser.add_argument(
        "--chapters-per-volume",
        type=int,
        default=DEFAULT_CHAPTERS_PER_VOLUME,
        help="Number of chapters per volume. Defaults to 25.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append even if the manifest already contains chapters.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview detected encoding and chapter headings without writing.",
    )
    return parser.parse_args()


def find_default_source() -> Path:
    """Find the bundled real Taichu TXT without hard-coding Chinese paths."""
    candidate_dirs = [
        path
        for path in REPO_ROOT.iterdir()
        if path.is_dir()
        and NOVEL_DIR_MARKER in path.name
        and NOVEL_TITLE_MARKER in path.name
    ]
    if not candidate_dirs:
        raise FileNotFoundError(
            "Could not find the bundled real Taichu novel directory."
        )
    txt_files = sorted(
        candidate_dirs[0].glob("*.txt"),
        key=lambda path: (-path.stat().st_size, path.name),
    )
    if not txt_files:
        raise FileNotFoundError("Could not find a TXT novel source file.")
    return txt_files[0]


def read_source_text(path: Path) -> tuple[str, str]:
    """Read TXT content with encodings seen in common Chinese novel dumps."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936"):
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        if "\ufffd" not in text:
            return text, encoding
    raise UnicodeDecodeError(
        "unknown",
        b"",
        0,
        1,
        "Could not decode source as utf-8 or gb18030-compatible text.",
    )


def take_first_chapters(text: str, count: int) -> ChapterSlice:
    """Slice the original text from chapter 1 through the requested count."""
    if count < 1:
        raise ValueError("--chapters must be at least 1")
    matches = list(CHAPTER_TITLE_PATTERN.finditer(text))
    if len(matches) < count:
        raise ValueError(
            f"Only found {len(matches)} chapter headings; need {count}."
        )
    chapters: list[SourceChapter] = []
    for index in range(count):
        match = matches[index]
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapters.append(
            SourceChapter(
                heading=match.group(1).strip(),
                body=text[match.end() : body_end].strip(),
            )
        )
    return ChapterSlice(chapters=chapters)


async def import_chapters(
    *,
    source_path: Path,
    assets_root: Path,
    chapter_slice: ChapterSlice,
    chapters_per_volume: int,
    append: bool,
) -> None:
    """Import into four ordered volumes through the outline service."""
    if chapters_per_volume < 1:
        raise ValueError("--chapters-per-volume must be at least 1")

    storage = ProjectAssetStorageBackend(assets_root)
    await storage.ensure_skeleton()
    outline_service = OutlineService(storage)
    existing_outline = await outline_service.get_outline()
    manifest = ChapterManifest.model_validate(await storage.read_manifest())
    if (manifest.chapters or existing_outline.volumes) and not append:
        existing = ", ".join(chapter.id for chapter in manifest.chapters[:5])
        raise RuntimeError(
            "project_assets already contains manuscript data "
            f"({existing}). Re-run with --append to append anyway."
        )

    previous_current_chapter_id = existing_outline.current_chapter_id
    imported_word_counts: dict[str, int] = {}
    imported_chapter_ids: list[str] = []
    volume_offset = len(existing_outline.volumes)

    for volume_index, volume_chapters in enumerate(
        chunked(chapter_slice.chapters, chapters_per_volume),
        start=1,
    ):
        outline = await outline_service.create_volume(
            volume_name(volume_offset + volume_index)
        )
        if outline.current_volume_id is None:
            raise RuntimeError("Failed to create import volume.")
        volume_id = outline.current_volume_id

        for source_chapter in volume_chapters:
            outline = await outline_service.create_chapter(
                volume_id,
                source_chapter.heading,
            )
            if outline.current_chapter_id is None:
                raise RuntimeError("Failed to create import chapter.")
            outline_chapter = find_outline_chapter(
                outline,
                outline.current_chapter_id,
            )
            markdown = format_chapter_markdown(
                outline_chapter.display_title,
                source_chapter.body,
            )
            await storage.write_chapter_markdown(
                outline_chapter.markdown_path,
                markdown,
            )
            imported_chapter_ids.append(outline_chapter.chapter_id)
            imported_word_counts[outline_chapter.chapter_id] = count_non_space(
                markdown
            )

    await sync_import_metadata(
        storage=storage,
        previous_current_chapter_id=previous_current_chapter_id,
        imported_chapter_ids=imported_chapter_ids,
        imported_word_counts=imported_word_counts,
    )
    volume_count = (len(chapter_slice.chapters) + chapters_per_volume - 1) // (
        chapters_per_volume
    )
    print(
        "\n".join(
            [
                "{",
                f'  "source_name": "{source_path.name}",',
                f'  "chapter_count": {len(imported_chapter_ids)},',
                f'  "volume_count": {volume_count},',
                f'  "chapters_per_volume": {chapters_per_volume}',
                "}",
            ]
        )
    )


async def async_main() -> None:
    """Run the temporary dogfood import."""
    args = parse_args()
    source_path = (args.source or find_default_source()).resolve()
    assets_root = args.assets_root.resolve()
    text, encoding = read_source_text(source_path)
    chapter_slice = take_first_chapters(text, args.chapters)

    print(f"Source: {source_path}")
    print(f"Encoding: {encoding}")
    print(f"Target assets: {assets_root}")
    print(
        "Import plan: "
        f"{args.chapters} chapters, "
        f"{args.chapters_per_volume} chapters per volume"
    )
    print("Detected chapters:")
    for index, heading in enumerate(chapter_slice.headings, start=1):
        volume_index = ((index - 1) // args.chapters_per_volume) + 1
        print(f"  {volume_name(volume_index)} / {index}. {heading}")

    if args.dry_run:
        print("Dry run only; no project_assets files were changed.")
        return

    await import_chapters(
        source_path=source_path,
        assets_root=assets_root,
        chapter_slice=chapter_slice,
        chapters_per_volume=args.chapters_per_volume,
        append=args.append,
    )


def chunked(chapters: list[SourceChapter], size: int) -> list[list[SourceChapter]]:
    """Split chapters into ordered volume batches."""
    return [chapters[index : index + size] for index in range(0, len(chapters), size)]


def volume_name(index: int) -> str:
    """Return the default Chinese volume name for a one-based index."""
    numerals = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return f"第{numerals.get(index, str(index))}卷"


def find_outline_chapter(outline: WritingOutline, chapter_id: str):
    """Find a chapter by id in an outline."""
    for volume in outline.volumes:
        for chapter in volume.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
    raise RuntimeError(f"Created chapter {chapter_id} is missing from outline.")


def format_chapter_markdown(title: str, body: str) -> str:
    """Write imported chapter Markdown with the normalized display title."""
    cleaned_body = body.strip()
    if cleaned_body:
        return f"# {title}\n\n{cleaned_body}\n"
    return f"# {title}\n"


def count_non_space(text: str) -> int:
    """Count manuscript characters consistently with the import service."""
    return len(re.findall(r"\S", text))


async def sync_import_metadata(
    *,
    storage: ProjectAssetStorageBackend,
    previous_current_chapter_id: str | None,
    imported_chapter_ids: list[str],
    imported_word_counts: dict[str, int],
) -> None:
    """Sync manifest and outline after imported Markdown content is written."""
    if not imported_chapter_ids:
        return

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    outline = WritingOutline.model_validate(await storage.read_outline())
    current_chapter_id = previous_current_chapter_id or imported_chapter_ids[0]
    current_volume_id = volume_id_for_chapter(outline, current_chapter_id)
    outline = outline.model_copy(
        update={
            "current_chapter_id": current_chapter_id,
            "current_volume_id": current_volume_id,
            "updated_at": now,
        }
    )
    await storage.write_outline(outline.model_dump(mode="json"))

    manifest = ChapterManifest.model_validate(await storage.read_manifest())
    chapters = []
    for chapter in manifest.chapters:
        if chapter.id in imported_word_counts:
            chapters.append(
                chapter.model_copy(
                    update={
                        "status": ChapterStatus.ACTIVE,
                        "word_count": imported_word_counts[chapter.id],
                        "updated_at": now,
                    }
                )
            )
        else:
            chapters.append(chapter)
    manifest = manifest.model_copy(
        update={
            "current_chapter_id": current_chapter_id,
            "chapters": chapters,
            "updated_at": now,
        }
    )
    await storage.write_manifest(manifest.model_dump(mode="json"))


def volume_id_for_chapter(
    outline: WritingOutline,
    chapter_id: str,
) -> str | None:
    """Find the volume that owns a chapter."""
    for volume in outline.volumes:
        if any(chapter.chapter_id == chapter_id for chapter in volume.chapters):
            return volume.volume_id
    return outline.current_volume_id


if __name__ == "__main__":
    asyncio.run(async_main())
