"""Import the first 3 real Taichu novel chapters for RC dogfooding.

This is a temporary root-level helper, not a product import feature.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from taichu.application.services.import_service import ImportService  # noqa: E402
from taichu.config import settings  # noqa: E402
from taichu.domain.models.chapter import ChapterManifest  # noqa: E402
from taichu.infrastructure.storage.markdown_backend import (  # noqa: E402
    ProjectAssetStorageBackend,
)

DEFAULT_CHAPTER_COUNT = 3
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
class ChapterSlice:
    """A bounded real-novel import preview."""

    text: str
    headings: list[str]


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
        help="Number of chapters to import. Defaults to 3.",
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
    start = matches[0].start()
    end = matches[count].start() if len(matches) > count else len(text)
    selected = text[start:end].strip() + "\n"
    headings = [match.group(1).strip() for match in matches[:count]]
    return ChapterSlice(text=selected, headings=headings)


async def import_chapters(
    *,
    source_path: Path,
    assets_root: Path,
    chapter_slice: ChapterSlice,
    append: bool,
) -> None:
    """Import through the application service so source manifests stay valid."""
    storage = ProjectAssetStorageBackend(assets_root)
    await storage.ensure_skeleton()
    manifest = ChapterManifest.model_validate(await storage.read_manifest())
    if manifest.chapters and not append:
        existing = ", ".join(chapter.id for chapter in manifest.chapters[:5])
        raise RuntimeError(
            "project_assets already contains chapters "
            f"({existing}). Re-run with --append to append anyway."
        )
    batch = await ImportService(storage).import_text(
        chapter_slice.text,
        source_name=source_path.name,
        max_chapters=len(chapter_slice.headings),
    )
    print(batch.model_dump_json(indent=2))


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
    print("Detected chapters:")
    for index, heading in enumerate(chapter_slice.headings, start=1):
        print(f"  {index}. {heading}")

    if args.dry_run:
        print("Dry run only; no project_assets files were changed.")
        return

    await import_chapters(
        source_path=source_path,
        assets_root=assets_root,
        chapter_slice=chapter_slice,
        append=args.append,
    )


if __name__ == "__main__":
    asyncio.run(async_main())
