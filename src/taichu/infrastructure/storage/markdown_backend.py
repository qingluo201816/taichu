"""Markdown and manifest storage for project_assets."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from threading import Lock
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from taichu.application.contracts.storage import StorageData

_CHAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

_SOURCE_DIRS = (
    "manuscripts/chapters",
    "knowledge/characters",
    "knowledge/worldbuilding",
    "knowledge/techniques",
    "knowledge/locations",
    "knowledge/factions",
    "knowledge/items",
    "knowledge/events",
    "knowledge/foreshadows",
    "workspace",
)

_GENERATED_DIRS = (
    "sqlite",
    "search_index",
    "vector_store",
    "embedding_cache",
    "exports",
    "temp",
)

_WORKSPACE_FILES = (
    "ai_cards.jsonl",
    "ideas.jsonl",
    "pending_facts.jsonl",
    "chapter_issues.jsonl",
    "chapter_summaries.jsonl",
)


class ProjectAssetStorageBackend:
    """File-system implementation for the single active project_assets root."""

    def __init__(self, assets_root: Path) -> None:
        self._assets_root = assets_root
        self._source_root = assets_root / "source"
        self._generated_root = assets_root / "generated"
        self._workspace_locks = {
            filename: Lock() for filename in _WORKSPACE_FILES
        }

    async def ensure_skeleton(self) -> None:
        """Create source/generated directories and empty main records."""
        await asyncio.to_thread(self._ensure_skeleton_sync)

    async def read_metadata(self) -> StorageData:
        """Read metadata.yaml, creating the skeleton if needed."""
        return await asyncio.to_thread(self._read_metadata_sync)

    async def write_metadata(self, data: StorageData) -> None:
        """Write metadata.yaml using the MVP simple YAML subset."""
        await asyncio.to_thread(self._write_metadata_sync, data)

    async def read_manifest(self) -> StorageData:
        """Read manuscripts/manifest.json, creating it if needed."""
        return await asyncio.to_thread(self._read_manifest_sync)

    async def write_manifest(self, data: StorageData) -> None:
        """Write manuscripts/manifest.json atomically."""
        await asyncio.to_thread(self._write_manifest_sync, data)

    async def write_chapter_markdown(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        """Write a chapter Markdown file below source/manuscripts/chapters."""
        await asyncio.to_thread(
            self._write_chapter_markdown_sync,
            relative_path,
            content,
        )

    async def read_chapter_markdown(self, relative_path: str) -> str:
        """Read a chapter Markdown file below source/manuscripts/chapters."""
        return await asyncio.to_thread(
            self._read_chapter_markdown_sync,
            relative_path,
        )

    async def append_workspace_record(
        self,
        filename: str,
        data: StorageData,
    ) -> None:
        """Append one JSON object to a workspace JSONL source file."""
        await asyncio.to_thread(
            self._append_workspace_record_sync,
            filename,
            data,
        )

    async def list_workspace_records(
        self,
        filename: str,
    ) -> list[StorageData]:
        """Read JSON objects from a workspace JSONL source file."""
        return await asyncio.to_thread(
            self._list_workspace_records_sync,
            filename,
        )

    async def rewrite_workspace_records(
        self,
        filename: str,
        records: list[StorageData],
    ) -> None:
        """Atomically rewrite a workspace JSONL source file."""
        await asyncio.to_thread(
            self._rewrite_workspace_records_sync,
            filename,
            records,
        )

    async def clear_generated(self) -> None:
        """Delete generated contents and recreate empty generated dirs."""
        await asyncio.to_thread(self._clear_generated_sync)

    def _ensure_skeleton_sync(self) -> None:
        for directory in _SOURCE_DIRS:
            (self._source_root / directory).mkdir(parents=True, exist_ok=True)
        self._ensure_generated_dirs()

        metadata_path = self._source_root / "metadata.yaml"
        if not metadata_path.exists():
            self._write_metadata_sync(
                {
                    "schema_version": "1",
                    "title": "",
                }
            )

        manifest_path = self._manifest_path
        if not manifest_path.exists():
            self._write_manifest_sync(self._empty_manifest())

        workspace_root = self._source_root / "workspace"
        for filename in _WORKSPACE_FILES:
            path = workspace_root / filename
            if not path.exists():
                path.write_text("", encoding="utf-8")

        editor_state = workspace_root / "editor_state.json"
        if not editor_state.exists():
            editor_state.write_text("{}\n", encoding="utf-8")

    def _read_metadata_sync(self) -> StorageData:
        self._ensure_skeleton_sync()
        return self._parse_simple_yaml(
            (self._source_root / "metadata.yaml").read_text(
                encoding="utf-8"
            )
        )

    def _write_metadata_sync(self, data: StorageData) -> None:
        self._source_root.mkdir(parents=True, exist_ok=True)
        metadata_path = self._source_root / "metadata.yaml"
        metadata_path.write_text(
            self._format_simple_yaml(data),
            encoding="utf-8",
        )

    def _read_manifest_sync(self) -> StorageData:
        self._ensure_skeleton_sync()
        data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Chapter manifest must be a JSON object")
        return data

    def _write_manifest_sync(self, data: StorageData) -> None:
        manifest_path = self._manifest_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(manifest_path)

    def _write_chapter_markdown_sync(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        path = self._resolve_safe_chapter_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _read_chapter_markdown_sync(self, relative_path: str) -> str:
        path = self._resolve_safe_chapter_path(relative_path)
        return path.read_text(encoding="utf-8")

    def _append_workspace_record_sync(
        self,
        filename: str,
        data: StorageData,
    ) -> None:
        self._ensure_skeleton_sync()
        path = self._resolve_safe_workspace_jsonl(filename)
        line = json.dumps(data, ensure_ascii=False) + "\n"
        with self._workspace_locks[filename]:
            current_text = path.read_text(encoding="utf-8")
            self._replace_workspace_text(path, current_text + line)

    def _list_workspace_records_sync(
        self,
        filename: str,
    ) -> list[StorageData]:
        self._ensure_skeleton_sync()
        path = self._resolve_safe_workspace_jsonl(filename)
        records: list[StorageData] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(
                    f"Workspace JSONL line must be an object: "
                    f"{filename}:{line_number}"
                )
            records.append(data)
        return records

    def _rewrite_workspace_records_sync(
        self,
        filename: str,
        records: list[StorageData],
    ) -> None:
        self._ensure_skeleton_sync()
        path = self._resolve_safe_workspace_jsonl(filename)
        text = "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in records
        )
        with self._workspace_locks[filename]:
            self._replace_workspace_text(path, text)

    def _clear_generated_sync(self) -> None:
        if self._generated_root.exists():
            shutil.rmtree(self._generated_root)
        self._ensure_generated_dirs()

    def _ensure_generated_dirs(self) -> None:
        self._generated_root.mkdir(parents=True, exist_ok=True)
        for directory in _GENERATED_DIRS:
            (self._generated_root / directory).mkdir(
                parents=True,
                exist_ok=True,
            )
        gitkeep = self._generated_root / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("\n", encoding="utf-8")

    def _resolve_safe_chapter_path(self, relative_path: str) -> Path:
        if "\\" in relative_path:
            raise ValueError("chapter path must use '/' separators")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("chapter path must stay inside source root")
        if len(path.parts) != 3 or path.parts[:2] != (
            "manuscripts",
            "chapters",
        ):
            raise ValueError(
                "chapter path must be manuscripts/chapters/<id>.md"
            )
        if path.suffix != ".md":
            raise ValueError("chapter path must end with .md")
        chapter_id = path.stem
        if not _CHAPTER_ID.fullmatch(chapter_id):
            raise ValueError("chapter id contains unsafe characters")
        return self._source_root / Path(*path.parts)

    def _resolve_safe_workspace_jsonl(self, filename: str) -> Path:
        if filename not in _WORKSPACE_FILES:
            raise ValueError("workspace filename is not part of the contract")
        if not filename.endswith(".jsonl"):
            raise ValueError("workspace record file must be JSONL")
        return self._source_root / "workspace" / filename

    @staticmethod
    def _replace_workspace_text(path: Path, text: str) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(text, encoding="utf-8")
        temporary_path.replace(path)

    @property
    def _manifest_path(self) -> Path:
        return self._source_root / "manuscripts" / "manifest.json"

    @staticmethod
    def _empty_manifest() -> StorageData:
        return {
            "schema_version": "1",
            "current_chapter_id": None,
            "volumes": [],
            "chapters": [],
            "updated_at": _now_iso(),
        }

    @staticmethod
    def _parse_simple_yaml(text: str) -> StorageData:
        data: StorageData = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            data[key.strip()] = _parse_scalar(value.strip())
        return data

    @staticmethod
    def _format_simple_yaml(data: StorageData) -> str:
        lines = [
            f"{key}: {_format_scalar(value)}"
            for key, value in data.items()
        ]
        return "\n".join(lines) + "\n"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_scalar(value: str) -> object:
    if value == '""':
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    if value.isdigit():
        return int(value)
    return value


def _format_scalar(value: Any) -> str:
    if value == "":
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
