from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def extract_docx_images(document_path: Path, output_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    with zipfile.ZipFile(document_path) as archive:
        media_files = [
            name
            for name in archive.namelist()
            if name.startswith("word/media/")
            and Path(name).suffix.lower() in IMAGE_SUFFIXES
        ]
        for index, member in enumerate(media_files, start=1):
            suffix = Path(member).suffix.lower()
            target = output_dir / f"docx-image-{index:03d}{suffix}"
            with archive.open(member) as source, target.open("wb") as dest:
                dest.write(source.read())
            extracted.append(target)
    return extracted


def extract_pdf_images(document_path: Path, output_dir: Path) -> list[Path]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PDF 图片提取需要 PyMuPDF。可执行 `uv add PyMuPDF` 后重试，"
            "或先仅使用文本读取能力分析 PRD。"
        ) from exc

    extracted: list[Path] = []
    pdf = fitz.open(document_path)
    try:
        for page_index in range(pdf.page_count):
            page = pdf.load_page(page_index)
            images = page.get_images(full=True)
            for image_index, image in enumerate(images, start=1):
                xref = image[0]
                image_data = pdf.extract_image(xref)
                ext = str(image_data.get("ext", "png")).lower()
                target = output_dir / (
                    f"pdf-page-{page_index + 1:03d}-image-{image_index:03d}.{ext}"
                )
                target.write_bytes(image_data["image"])
                extracted.append(target)
    finally:
        pdf.close()
    return extracted


def write_manifest(
    document_path: Path,
    output_dir: Path,
    extracted: list[Path],
) -> Path:
    manifest: dict[str, Any] = {
        "source": str(document_path),
        "output_dir": str(output_dir),
        "count": len(extracted),
        "images": [str(path) for path in extracted],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 PRD 文档中提取嵌入图片")
    parser.add_argument("document", help="PRD 文档路径，支持 .docx 和 .pdf")
    parser.add_argument("--output", default="out/prd_images", help="输出目录")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document_path = Path(args.document)
    output_dir = Path(args.output)

    if not document_path.exists():
        raise SystemExit(f"文档不存在：{document_path}")
    if not document_path.is_file():
        raise SystemExit(f"路径不是文件：{document_path}")

    ensure_output_dir(output_dir)
    suffix = document_path.suffix.lower()
    if suffix == ".docx":
        extracted = extract_docx_images(document_path, output_dir)
    elif suffix == ".pdf":
        extracted = extract_pdf_images(document_path, output_dir)
    else:
        raise SystemExit("仅支持 .docx 和 .pdf 文档")

    manifest_path = write_manifest(document_path, output_dir, extracted)
    print(f"已提取图片 {len(extracted)} 张")
    print(f"清单文件：{manifest_path}")


if __name__ == "__main__":
    main()
