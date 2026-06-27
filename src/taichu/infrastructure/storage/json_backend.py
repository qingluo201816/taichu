"""基于 JSON 文件的源数据存储实现。"""

from __future__ import annotations

import asyncio
import builtins
import json
import re
from pathlib import Path

from taichu.application.contracts.storage import StorageData

_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_-]+$")


class JsonStorageBackend:
    """将集合和记录保存为 UTF-8 JSON 文件。"""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    async def get(
        self,
        collection: str,
        key: str,
    ) -> StorageData | None:
        """读取单条 JSON 数据。"""
        return await asyncio.to_thread(self._get_sync, collection, key)

    async def list(self, collection: str) -> builtins.list[StorageData]:
        """列出集合内的 JSON 数据。"""
        return await asyncio.to_thread(self._list_sync, collection)

    async def put(
        self,
        collection: str,
        key: str,
        data: StorageData,
    ) -> None:
        """原子写入单条 JSON 数据。"""
        await asyncio.to_thread(self._put_sync, collection, key, data)

    async def delete(self, collection: str, key: str) -> bool:
        """删除单条 JSON 数据。"""
        return await asyncio.to_thread(
            self._delete_sync,
            collection,
            key,
        )

    def _collection_dir(self, collection: str) -> Path:
        safe_collection = self._validate_segment(collection, "collection")
        return self._base_dir / safe_collection

    def _key_path(self, collection: str, key: str) -> Path:
        safe_key = self._validate_segment(key, "key")
        return self._collection_dir(collection) / f"{safe_key}.json"

    @staticmethod
    def _validate_segment(value: str, label: str) -> str:
        if not _SAFE_SEGMENT.fullmatch(value):
            raise ValueError(
                f"{label} must contain only letters, numbers, '_' or '-'"
            )
        return value

    def _get_sync(
        self,
        collection: str,
        key: str,
    ) -> StorageData | None:
        path = self._key_path(collection, key)
        if not path.exists():
            return None
        return self._read_object(path)

    def _list_sync(self, collection: str) -> builtins.list[StorageData]:
        directory = self._collection_dir(collection)
        if not directory.exists():
            return []
        return [
            self._read_object(path)
            for path in sorted(directory.glob("*.json"))
        ]

    def _put_sync(
        self,
        collection: str,
        key: str,
        data: StorageData,
    ) -> None:
        path = self._key_path(collection, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _delete_sync(self, collection: str, key: str) -> bool:
        path = self._key_path(collection, key)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def _read_object(path: Path) -> StorageData:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Stored JSON must be an object: {path}")
        return data
