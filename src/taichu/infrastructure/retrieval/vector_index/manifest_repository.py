"""向量索引清单的原子文件仓储。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from taichu.application.retrieval.vector_index_models import VectorIndexManifest


class JsonVectorIndexManifestRepository:
    def __init__(self, project_assets_dir: Path) -> None:
        self._root = (
            project_assets_dir
            / "generated"
            / "vector_indexes"
            / "knowledge_cards"
        )
        self._active_path = self._root / "active_manifest.json"
        self._write_lock = asyncio.Lock()

    async def load_active(self) -> VectorIndexManifest | None:
        return await asyncio.to_thread(self._load_active_sync)

    async def save_active(self, manifest: VectorIndexManifest) -> None:
        if not manifest.manifest_checksum:
            raise VectorIndexManifestStoreError("向量索引清单尚未完成校验和。")
        async with self._write_lock:
            await asyncio.to_thread(self._save_active_sync, manifest)

    async def delete_active(self) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._delete_active_sync)

    def _load_active_sync(self) -> VectorIndexManifest | None:
        if not self._active_path.exists():
            return None
        try:
            raw: Any = json.loads(self._active_path.read_text(encoding="utf-8"))
            return VectorIndexManifest.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise VectorIndexManifestStoreError(
                "向量索引 active 清单损坏或校验失败。"
            ) from error

    def _save_active_sync(self, manifest: VectorIndexManifest) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        history_path = self._root / f"{manifest.index_id}.json"
        _atomic_write(history_path, content)
        _atomic_write(self._active_path, content)

    def _delete_active_sync(self) -> None:
        if self._active_path.exists():
            self._active_path.unlink()


class VectorIndexManifestStoreError(RuntimeError):
    """清单缺失以外的读取、写入或校验失败。"""


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise VectorIndexManifestStoreError("向量索引清单写入失败。") from error
