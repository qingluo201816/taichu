"""Readable source asset export use cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from taichu.application.contracts.knowledge_repository import (
    KnowledgeCardQuery,
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.chapter import ChapterManifest
from taichu.domain.models.export import ExportBundle, ExportFile
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
)

_WORKSPACE_JSONL_FILES = (
    "ai_cards.jsonl",
    "ideas.jsonl",
    "pending_facts.jsonl",
    "chapter_issues.jsonl",
    "chapter_summaries.jsonl",
    "writing_ai_runs.jsonl",
)
_KNOWLEDGE_PAGE_SIZE = 200
_ALL_KNOWLEDGE_LIFECYCLES = frozenset(StructuredKnowledgeLifecycle)


class ExportService:
    """Build a readable export bundle from source assets."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        knowledge_repository: StructuredKnowledgeRepository,
    ) -> None:
        self._storage = storage
        self._knowledge_repository = knowledge_repository

    async def build_bundle(self) -> ExportBundle:
        """Return current source assets as readable export files."""
        await self._storage.ensure_skeleton()
        created_at = _now_iso()
        files: list[ExportFile] = []

        metadata = await self._storage.read_metadata()
        files.append(
            ExportFile(
                path="source/metadata.yaml",
                media_type="text/yaml",
                content=_format_simple_yaml(metadata),
            )
        )

        manifest = ChapterManifest.model_validate(await self._storage.read_manifest())
        files.append(
            ExportFile(
                path="source/manuscripts/manifest.json",
                media_type="application/json",
                content=_json_text(manifest.model_dump(mode="json")),
            )
        )

        for chapter in sorted(manifest.chapters, key=lambda item: item.order):
            markdown = await self._storage.read_chapter_markdown(chapter.markdown_path)
            files.append(
                ExportFile(
                    path=f"source/{chapter.markdown_path}",
                    media_type="text/markdown",
                    content=markdown,
                )
            )

        knowledge_cards = await self._list_all_knowledge_cards()
        files.append(
            ExportFile(
                path="knowledge/knowledge_cards.json",
                media_type="application/json",
                content=_json_text(
                    {
                        "schema_version": "taichu_export_v2",
                        "created_at": created_at,
                        "cards": [
                            card.model_dump(mode="json") for card in knowledge_cards
                        ],
                    }
                ),
            )
        )

        for filename in _WORKSPACE_JSONL_FILES:
            records = await self._storage.list_workspace_records(filename)
            files.append(
                ExportFile(
                    path=f"source/workspace/{filename}",
                    media_type="application/x-jsonlines",
                    content=_jsonl_text(records),
                )
            )

        return ExportBundle(
            id=f"export_{uuid4().hex}",
            schema_version="taichu_export_v2",
            created_at=created_at,
            files=files,
        )

    async def _list_all_knowledge_cards(self) -> list[StructuredKnowledgeCard]:
        cards: list[StructuredKnowledgeCard] = []
        offset = 0
        while True:
            page = await self._knowledge_repository.list_cards(
                KnowledgeCardQuery(
                    lifecycles=_ALL_KNOWLEDGE_LIFECYCLES,
                    offset=offset,
                    limit=_KNOWLEDGE_PAGE_SIZE,
                )
            )
            cards.extend(page.cards)
            offset += len(page.cards)
            if offset >= page.total:
                return cards
            if not page.cards:
                raise RuntimeError("知识库分页返回空页，无法完成导出。")


def _json_text(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _jsonl_text(records: list[dict[str, object]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


def _format_simple_yaml(data: dict[str, object]) -> str:
    lines = [f"{key}: {_format_scalar(value)}" for key, value in data.items()]
    return "\n".join(lines) + ("\n" if lines else "")


def _format_scalar(value: object) -> str:
    if value == "":
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
