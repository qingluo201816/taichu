"""通用 Runtime 记忆的可重建词法索引。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from taichu.application.agent_memory.models import AgentMemoryEntry, memory_now_iso

_WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


class JsonAgentMemoryLexicalIndex:
    """索引损坏或过期时从记忆 JSON 自动重建。"""

    def __init__(self, project_assets_dir: Path) -> None:
        self._root = project_assets_dir / "generated" / "agent_memory_indexes"
        self._path = self._root / "lexical_index.json"

    async def scores(
        self,
        entries: list[AgentMemoryEntry],
        *,
        query_text: str,
    ) -> dict[str, float]:
        return await asyncio.to_thread(self._scores_sync, entries, query_text)

    async def rebuild(self, entries: list[AgentMemoryEntry]) -> str:
        return await asyncio.to_thread(self._rebuild_sync, entries)

    def _scores_sync(
        self,
        entries: list[AgentMemoryEntry],
        query_text: str,
    ) -> dict[str, float]:
        snapshot_hash = _entries_snapshot_hash(entries)
        try:
            payload = self._load_sync()
            if payload.get("source_snapshot_sha256") != snapshot_hash:
                raise AgentMemoryIndexError("运行记忆索引已过期。")
        except AgentMemoryIndexError:
            self._rebuild_sync(entries)
            payload = self._load_sync()

        query_terms = _terms(query_text)
        records = payload.get("records")
        assert isinstance(records, list)
        scores: dict[str, float] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            memory_id = record.get("memory_id")
            indexed_terms = record.get("terms")
            if not isinstance(memory_id, str) or not isinstance(indexed_terms, list):
                continue
            term_set = {item for item in indexed_terms if isinstance(item, str)}
            if not query_terms:
                scores[memory_id] = 0.0
                continue
            intersection = len(query_terms & term_set)
            union = len(query_terms | term_set)
            scores[memory_id] = intersection / union if union else 0.0
        return scores

    def _rebuild_sync(self, entries: list[AgentMemoryEntry]) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        snapshot_hash = _entries_snapshot_hash(entries)
        payload = {
            "lifecycle": "draft",
            "generated_at": memory_now_iso(),
            "source_snapshot_sha256": snapshot_hash,
            "record_count": len(entries),
            "records": [
                {
                    "memory_id": entry.memory_id,
                    "content_sha256": entry.content_sha256,
                    "terms": sorted(
                        _terms(
                            " ".join(
                                [
                                    entry.kind.value,
                                    entry.content,
                                    *entry.source_refs,
                                    *entry.artifact_refs,
                                ]
                            )
                        )
                    ),
                }
                for entry in sorted(entries, key=lambda item: item.memory_id)
            ],
        }
        temporary = self._path.with_name(
            f".{self._path.name}.{uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)
        return snapshot_hash

    def _load_sync(self) -> dict[str, Any]:
        if not self._path.exists():
            raise AgentMemoryIndexError("运行记忆索引尚未生成。")
        try:
            payload: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AgentMemoryIndexError("运行记忆索引已损坏。") from error
        if (
            not isinstance(payload, dict)
            or payload.get("lifecycle") != "draft"
            or not isinstance(payload.get("records"), list)
            or not isinstance(payload.get("source_snapshot_sha256"), str)
        ):
            raise AgentMemoryIndexError("运行记忆索引结构不正确。")
        return payload


class AgentMemoryIndexError(ValueError):
    """可重建索引缺失、损坏或过期。"""


def _entries_snapshot_hash(entries: list[AgentMemoryEntry]) -> str:
    canonical = [
        {
            "memory_id": entry.memory_id,
            "content_sha256": entry.content_sha256,
            "updated_at": entry.updated_at,
            "deleted_at": entry.deleted_at,
        }
        for entry in sorted(entries, key=lambda item: item.memory_id)
    ]
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _terms(value: str) -> set[str]:
    terms: set[str] = set()
    for match in _WORD_PATTERN.findall(value.lower()):
        if all("\u4e00" <= character <= "\u9fff" for character in match):
            terms.update(match)
            terms.update(match[index : index + 2] for index in range(len(match) - 1))
        else:
            terms.add(match)
    return terms
