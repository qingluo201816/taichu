"""Markdown and manifest storage for project_assets."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
import re
from threading import Lock, get_ident
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from taichu.application.contracts.storage import StorageData

_CHAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MANUSCRIPT_PATH_SEGMENT = re.compile(
    r"^[\w\u3400-\u4dbf\u4e00-\u9fff][\w\u3400-\u4dbf\u4e00-\u9fff.-]*$",
    re.UNICODE,
)
_SOURCE_DIRS = (
    "manuscripts/chapters",
    "manuscripts/deleted_chapters",
    "workspace",
)

_WORKSPACE_FILES = (
    "ai_cards.jsonl",
    "ideas.jsonl",
    "pending_facts.jsonl",
    "chapter_issues.jsonl",
    "chapter_summaries.jsonl",
    "writing_ai_runs.jsonl",
    "inbox_ideas.jsonl",
    "inbox_pending_facts.jsonl",
    "inbox_issues.jsonl",
    "inbox_decisions.jsonl",
)


class ProjectAssetStorageBackend:
    """File-system implementation for the single active project_assets root."""

    def __init__(self, assets_root: Path) -> None:
        self._assets_root = assets_root
        self._source_root = assets_root / "source"
        self._workspace_locks = {filename: Lock() for filename in _WORKSPACE_FILES}

    async def ensure_skeleton(self) -> None:
        """Create source directories and empty main records."""
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

    async def read_outline(self) -> StorageData:
        """Read manuscripts/outline.json, creating it if needed."""
        return await asyncio.to_thread(self._read_outline_sync)

    async def write_outline(self, data: StorageData) -> None:
        """Write manuscripts/outline.json atomically."""
        await asyncio.to_thread(self._write_outline_sync, data)

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

    async def move_chapter_markdown(
        self,
        source_relative_path: str,
        target_relative_path: str,
    ) -> None:
        """Move a chapter Markdown file to another safe manuscript path."""
        await asyncio.to_thread(
            self._move_chapter_markdown_sync,
            source_relative_path,
            target_relative_path,
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

    async def compare_and_swap_workspace_record(
        self,
        filename: str,
        item_id: str,
        expected_revision: int,
        updates: StorageData,
    ) -> StorageData:
        """Atomically compare and swap one revisioned workspace record."""
        return await asyncio.to_thread(
            self._compare_and_swap_workspace_record_sync,
            filename,
            item_id,
            expected_revision,
            updates,
        )

    async def read_preferences(self) -> StorageData:
        """Read workspace/settings_preferences.json."""
        return await asyncio.to_thread(self._read_preferences_sync)

    async def write_preferences(self, data: StorageData) -> None:
        """Write workspace/settings_preferences.json atomically."""
        await asyncio.to_thread(self._write_preferences_sync, data)

    def _ensure_skeleton_sync(self) -> None:
        for directory in _SOURCE_DIRS:
            (self._source_root / directory).mkdir(parents=True, exist_ok=True)

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

        outline_path = self._outline_path
        if not outline_path.exists():
            self._write_outline_sync(self._empty_outline())

        workspace_root = self._source_root / "workspace"
        for filename in _WORKSPACE_FILES:
            path = workspace_root / filename
            if not path.exists():
                path.write_text("", encoding="utf-8")

        editor_state = workspace_root / "editor_state.json"
        if not editor_state.exists():
            editor_state.write_text("{}\n", encoding="utf-8")

        preferences_path = workspace_root / "settings_preferences.json"
        if not preferences_path.exists():
            preferences_path.write_text(
                json.dumps(self._default_preferences(), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )

    def _read_metadata_sync(self) -> StorageData:
        self._ensure_skeleton_sync()
        return self._parse_simple_yaml(
            (self._source_root / "metadata.yaml").read_text(encoding="utf-8")
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

    def _read_outline_sync(self) -> StorageData:
        self._ensure_skeleton_sync()
        data = json.loads(self._outline_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Writing outline must be a JSON object")
        return data

    def _write_outline_sync(self, data: StorageData) -> None:
        outline_path = self._outline_path
        outline_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = outline_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(outline_path)

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

    def _move_chapter_markdown_sync(
        self,
        source_relative_path: str,
        target_relative_path: str,
    ) -> None:
        source_path = self._resolve_safe_chapter_path(source_relative_path)
        target_path = self._resolve_safe_chapter_move_target_path(target_relative_path)
        if source_path == target_path:
            return
        if not source_path.exists():
            raise FileNotFoundError(source_relative_path)
        if target_path.exists():
            raise FileExistsError(target_relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(target_path)
        self._remove_empty_manuscript_dirs(source_path.parent)

    def _append_workspace_record_sync(
        self,
        filename: str,
        data: StorageData,
    ) -> None:
        self._ensure_skeleton_sync()
        path = self._resolve_safe_workspace_jsonl(filename)
        line = json.dumps(data, ensure_ascii=False) + "\n"
        with self._workspace_locks[filename]:
            with self._workspace_file_lease(path):
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
                    f"Workspace JSONL line must be an object: {filename}:{line_number}"
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
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        )
        with self._workspace_locks[filename]:
            with self._workspace_file_lease(path):
                self._replace_workspace_text(path, text)

    def _compare_and_swap_workspace_record_sync(
        self,
        filename: str,
        item_id: str,
        expected_revision: int,
        updates: StorageData,
    ) -> StorageData:
        from taichu.application.contracts.storage import (
            WorkspaceRecordRevisionConflictError,
        )

        self._ensure_skeleton_sync()
        path = self._resolve_safe_workspace_jsonl(filename)
        with self._workspace_locks[filename]:
            with self._workspace_file_lease(path):
                records = self._list_workspace_records_sync_unlocked(path, filename)
                found: StorageData | None = None
                rewritten: list[StorageData] = []
                for record in records:
                    if record.get("id") != item_id:
                        rewritten.append(record)
                        continue
                    if found is not None:
                        raise ValueError(
                            f"Workspace record id is not unique: {item_id}"
                        )
                    current_revision = int(record.get("revision", 0))
                    if current_revision != expected_revision:
                        raise WorkspaceRecordRevisionConflictError(current_revision)
                    candidate = {
                        **record,
                        "links": record.get("links", []),
                        **updates,
                        "revision": current_revision + 1,
                    }
                    found = candidate
                    rewritten.append(candidate)
                if found is None:
                    raise KeyError(item_id)
                text = "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in rewritten
                )
                self._replace_workspace_text(path, text)
                return found

    @staticmethod
    def _list_workspace_records_sync_unlocked(
        path: Path,
        filename: str,
    ) -> list[StorageData]:
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
                    f"Workspace JSONL line must be an object: {filename}:{line_number}"
                )
            records.append(data)
        return records

    @staticmethod
    @contextmanager
    def _workspace_file_lease(path: Path):  # type: ignore[no-untyped-def]
        """用持久化租约串行化跨进程 JSONL read-modify-write。"""
        lease_path = path.with_name(f".{path.name}.lease")
        token = f"{os.getpid()}:{get_ident()}:{time.time_ns()}"
        deadline = time.monotonic() + 10
        while True:
            try:
                descriptor = os.open(
                    lease_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                try:
                    stale = time.time() - lease_path.stat().st_mtime > 30
                except FileNotFoundError:
                    continue
                if stale:
                    try:
                        lease_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Workspace file lease acquisition timed out: {path.name}"
                    )
                time.sleep(0.01)
                continue
            try:
                os.write(descriptor, token.encode("ascii"))
            finally:
                os.close(descriptor)
            break
        try:
            yield
        finally:
            try:
                if lease_path.read_text(encoding="ascii") == token:
                    lease_path.unlink()
            except FileNotFoundError:
                pass

    def _read_preferences_sync(self) -> StorageData:
        self._ensure_skeleton_sync()
        path = self._preferences_path
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Settings preferences must be a JSON object")
        return data

    def _write_preferences_sync(self, data: StorageData) -> None:
        self._ensure_skeleton_sync()
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self._replace_file_text(self._preferences_path, text)

    def _resolve_safe_chapter_path(self, relative_path: str) -> Path:
        if "\\" in relative_path:
            raise ValueError("chapter path must use '/' separators")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("chapter path must stay inside source root")
        valid_flat_path = len(path.parts) == 3 and path.parts[:2] == (
            "manuscripts",
            "chapters",
        )
        valid_volume_path = len(path.parts) == 4 and path.parts[:2] == (
            "manuscripts",
            "chapters",
        )
        if not (valid_flat_path or valid_volume_path):
            raise ValueError("chapter path must stay inside manuscripts/chapters")
        if path.suffix != ".md":
            raise ValueError("chapter path must end with .md")
        chapter_id = path.stem
        if valid_flat_path and not _CHAPTER_ID.fullmatch(chapter_id):
            raise ValueError("chapter id contains unsafe characters")
        if valid_volume_path and not _is_safe_manuscript_segment(chapter_id):
            raise ValueError("chapter id contains unsafe characters")
        if valid_volume_path and not _is_safe_manuscript_segment(path.parts[2]):
            raise ValueError("volume id contains unsafe characters")
        return self._source_root / Path(*path.parts)

    def _resolve_safe_deleted_chapter_path(self, relative_path: str) -> Path:
        if "\\" in relative_path:
            raise ValueError("chapter path must use '/' separators")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("chapter path must stay inside source root")
        valid_deleted_path = len(path.parts) == 4 and path.parts[:2] == (
            "manuscripts",
            "deleted_chapters",
        )
        if not valid_deleted_path:
            raise ValueError(
                "deleted chapter path must stay inside manuscripts/deleted_chapters"
            )
        if path.suffix != ".md":
            raise ValueError("chapter path must end with .md")
        chapter_id = path.stem
        if not _is_safe_manuscript_segment(chapter_id):
            raise ValueError("chapter id contains unsafe characters")
        if not _is_safe_manuscript_segment(path.parts[2]):
            raise ValueError("volume id contains unsafe characters")
        return self._source_root / Path(*path.parts)

    def _remove_empty_manuscript_dirs(self, directory: Path) -> None:
        roots = (
            self._source_root / "manuscripts" / "chapters",
            self._source_root / "manuscripts" / "deleted_chapters",
        )
        for root in roots:
            try:
                directory.relative_to(root)
            except ValueError:
                continue
            current = directory
            while current != root:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent
            return

    def _resolve_safe_chapter_move_target_path(self, relative_path: str) -> Path:
        path = PurePosixPath(relative_path)
        if len(path.parts) >= 2 and path.parts[:2] == (
            "manuscripts",
            "deleted_chapters",
        ):
            return self._resolve_safe_deleted_chapter_path(relative_path)
        return self._resolve_safe_chapter_path(relative_path)

    def _resolve_safe_workspace_jsonl(self, filename: str) -> Path:
        if filename not in _WORKSPACE_FILES:
            raise ValueError("workspace filename is not part of the contract")
        if not filename.endswith(".jsonl"):
            raise ValueError("workspace record file must be JSONL")
        return self._source_root / "workspace" / filename

    @staticmethod
    def _replace_workspace_text(path: Path, text: str) -> None:
        ProjectAssetStorageBackend._replace_file_text(path, text)

    @staticmethod
    def _replace_file_text(path: Path, text: str) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(text, encoding="utf-8")
        temporary_path.replace(path)

    @property
    def _manifest_path(self) -> Path:
        return self._source_root / "manuscripts" / "manifest.json"

    @property
    def _outline_path(self) -> Path:
        return self._source_root / "manuscripts" / "outline.json"

    @property
    def _preferences_path(self) -> Path:
        return self._source_root / "workspace" / "settings_preferences.json"

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
    def _empty_outline() -> StorageData:
        return {
            "volumes": [],
            "current_volume_id": None,
            "current_chapter_id": None,
            "updated_at": _now_iso(),
        }

    @staticmethod
    def _default_preferences() -> StorageData:
        return {
            "font_size": 18,
            "font_style": "serif",
            "editor_background": "dark",
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
        lines = [f"{key}: {_format_scalar(value)}" for key, value in data.items()]
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


def _is_safe_manuscript_segment(value: str) -> bool:
    return bool(_MANUSCRIPT_PATH_SEGMENT.fullmatch(value)) and value not in {".", ".."}
