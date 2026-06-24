"""存储层抽象：定义存储接口，v0.1 使用 JSON 文件实现。

未来换 SQLite / PostgreSQL / ChromaDB 只需新增实现类，不改接口。
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class StorageBackend(ABC):
    """存储后端抽象接口。"""

    @abstractmethod
    def get(self, collection: str, key: str) -> dict | None: ...

    @abstractmethod
    def list(self, collection: str) -> list[dict]: ...

    @abstractmethod
    def put(self, collection: str, key: str, data: dict) -> None: ...

    @abstractmethod
    def delete(self, collection: str, key: str) -> bool: ...


class JsonStorageBackend(StorageBackend):
    """JSON 文件存储实现。

    每个 collection 对应 data/ 下一个子目录，每个 key 对应一个 .json 文件。
    """

    def __init__(self, base_dir: str = "data"):
        self._base = Path(base_dir)

    def _collection_dir(self, collection: str) -> Path:
        dir_path = self._base / collection
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _key_path(self, collection: str, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._collection_dir(collection) / f"{safe_key}.json"

    def get(self, collection: str, key: str) -> dict | None:
        path = self._key_path(collection, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, collection: str) -> list[dict]:
        dir_path = self._collection_dir(collection)
        results = []
        for f in sorted(dir_path.glob("*.json")):
            results.append(json.loads(f.read_text(encoding="utf-8")))
        return results

    def put(self, collection: str, key: str, data: dict) -> None:
        path = self._key_path(collection, key)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, collection: str, key: str) -> bool:
        path = self._key_path(collection, key)
        if not path.exists():
            return False
        path.unlink()
        return True
