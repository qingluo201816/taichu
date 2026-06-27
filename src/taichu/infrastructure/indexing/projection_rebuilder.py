"""SQLite retrieval projection rebuilt from source facts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from taichu.domain.models.chapter import ChapterManifest
from taichu.domain.models.knowledge import KnowledgeCard, KnowledgeCardStatus
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)

_KNOWLEDGE_CATEGORIES = (
    "characters",
    "worldbuilding",
    "techniques",
    "locations",
    "factions",
    "items",
    "events",
    "foreshadows",
)


class SqliteProjectionRebuilder:
    """Rebuild generated SQLite retrieval projection from source assets."""

    def __init__(self, assets_root: Path) -> None:
        self._assets_root = assets_root
        self._source_root = assets_root / "source"
        self._sqlite_root = assets_root / "generated" / "sqlite"
        self.db_path = self._sqlite_root / "taichu.db"

    async def rebuild(self) -> None:
        """Recreate the SQLite projection from Chapter and Knowledge facts."""
        await asyncio.to_thread(self._rebuild_sync)

    def _rebuild_sync(self) -> None:
        self._sqlite_root.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            self.db_path.unlink()
        temporary_path = self.db_path.with_suffix(".db.tmp")
        if temporary_path.exists():
            temporary_path.unlink()

        documents = [
            *self._chapter_documents(),
            *self._knowledge_documents(),
        ]

        connection = sqlite3.connect(temporary_path)
        try:
            _create_schema(connection)
            connection.executemany(
                """
                INSERT INTO retrieval_documents (
                    id,
                    source_type,
                    source_id,
                    title,
                    excerpt,
                    text,
                    exact_terms,
                    source_ref_json,
                    source_path,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        document.id,
                        document.source_type,
                        document.source_id,
                        document.title,
                        document.excerpt,
                        document.text,
                        json.dumps(
                            sorted(document.exact_terms),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            document.source_ref.model_dump(mode="json"),
                            ensure_ascii=False,
                        ),
                        document.source_ref.path,
                        document.updated_at,
                    )
                    for document in documents
                ],
            )
            connection.executemany(
                """
                INSERT INTO retrieval_fts (doc_id, title, text)
                VALUES (?, ?, ?)
                """,
                [
                    (document.id, document.title, document.text)
                    for document in documents
                ],
            )
            connection.commit()
        finally:
            connection.close()

        temporary_path.replace(self.db_path)

    def _chapter_documents(self) -> list["_ProjectionDocument"]:
        manifest_path = self._source_root / "manuscripts" / "manifest.json"
        if not manifest_path.exists():
            return []

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ChapterManifest.model_validate(manifest_data)
        documents: list[_ProjectionDocument] = []
        for chapter in manifest.chapters:
            source_path = self._resolve_source_path(chapter.markdown_path)
            if not source_path.exists():
                continue
            markdown = source_path.read_text(encoding="utf-8")
            source_hash = _sha256(markdown)
            for paragraph_index, paragraph in enumerate(_split_paragraphs(markdown)):
                excerpt = _compact_excerpt(paragraph)
                if not excerpt:
                    continue
                source_ref = SourceRef(
                    source_type=SourceRefSourceType.CHAPTER,
                    source_id=chapter.id,
                    path=_source_ref_path(self._source_root, source_path),
                    chapter_id=chapter.id,
                    anchor_type=SourceAnchorType.PARAGRAPH,
                    paragraph_start=paragraph_index,
                    excerpt=excerpt,
                    excerpt_hash=_sha256(excerpt),
                    source_hash=source_hash,
                    created_at=_now_iso(),
                )
                documents.append(
                    _ProjectionDocument(
                        id=f"chapter:{chapter.id}:{paragraph_index}",
                        source_type="chapter",
                        source_id=chapter.id,
                        title=chapter.title,
                        excerpt=excerpt,
                        text=paragraph,
                        exact_terms=_identity_terms(
                            [chapter.title, _heading_text(paragraph)]
                        ),
                        source_ref=source_ref,
                        updated_at=chapter.updated_at,
                    )
                )
        return documents

    def _knowledge_documents(self) -> list["_ProjectionDocument"]:
        documents: list[_ProjectionDocument] = []
        for category in _KNOWLEDGE_CATEGORIES:
            category_root = self._source_root / "knowledge" / category
            if not category_root.exists():
                continue
            for path in sorted(category_root.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                card = KnowledgeCard.model_validate(data)
                if card.status is not KnowledgeCardStatus.CONFIRMED:
                    continue
                documents.extend(self._knowledge_card_documents(card, path))
        return documents

    def _knowledge_card_documents(
        self,
        card: KnowledgeCard,
        path: Path,
    ) -> list["_ProjectionDocument"]:
        source_text = json.dumps(
            card.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        source_hash = _sha256(source_text)
        source_ref_path = _source_ref_path(self._source_root, path)
        created_at = _now_iso()

        documents: list[_ProjectionDocument] = []
        identity_text = "\n".join([card.name, *card.aliases]).strip()
        if identity_text:
            documents.append(
                self._knowledge_document(
                    card=card,
                    document_id=f"knowledge:{card.id}:identity",
                    field_path="name",
                    excerpt=identity_text,
                    text=identity_text,
                    source_ref_path=source_ref_path,
                    source_hash=source_hash,
                    created_at=created_at,
                    exact_terms=_identity_terms([card.name, *card.aliases]),
                )
            )

        documents.append(
            self._knowledge_document(
                card=card,
                document_id=f"knowledge:{card.id}:summary",
                field_path="summary",
                excerpt=card.summary,
                text="\n".join([card.name, card.summary]).strip(),
                source_ref_path=source_ref_path,
                source_hash=source_hash,
                created_at=created_at,
                exact_terms=_identity_terms([card.name, *card.aliases]),
            )
        )

        for field_path, value in _flatten_fields(card.fields):
            documents.append(
                self._knowledge_document(
                    card=card,
                    document_id=f"knowledge:{card.id}:{field_path}",
                    field_path=f"fields.{field_path}",
                    excerpt=value,
                    text="\n".join([card.name, value]).strip(),
                    source_ref_path=source_ref_path,
                    source_hash=source_hash,
                    created_at=created_at,
                    exact_terms=_identity_terms([card.name, *card.aliases]),
                )
            )
        return documents

    def _knowledge_document(
        self,
        *,
        card: KnowledgeCard,
        document_id: str,
        field_path: str,
        excerpt: str,
        text: str,
        source_ref_path: str,
        source_hash: str,
        created_at: str,
        exact_terms: set[str],
    ) -> "_ProjectionDocument":
        compact_excerpt = _compact_excerpt(excerpt) or card.name
        source_ref = SourceRef(
            source_type=SourceRefSourceType.KNOWLEDGE,
            source_id=card.id,
            path=source_ref_path,
            anchor_type=SourceAnchorType.KNOWLEDGE_FIELD,
            field_path=field_path,
            excerpt=compact_excerpt,
            excerpt_hash=_sha256(compact_excerpt),
            source_hash=source_hash,
            created_at=created_at,
        )
        return _ProjectionDocument(
            id=document_id,
            source_type="knowledge",
            source_id=card.id,
            title=card.name,
            excerpt=compact_excerpt,
            text=text,
            exact_terms=exact_terms,
            source_ref=source_ref,
            updated_at=card.updated_at,
        )

    def _resolve_source_path(self, source_path: str) -> Path:
        normalized = source_path.replace("\\", "/")
        pure_path = PurePosixPath(normalized)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise ValueError("source path must stay inside source root")
        if pure_path.parts[:2] == ("project_assets", "source"):
            pure_path = PurePosixPath(*pure_path.parts[2:])
        path = (self._source_root / Path(*pure_path.parts)).resolve()
        source_root = self._source_root.resolve()
        if not path.is_relative_to(source_root):
            raise ValueError("源资产路径必须位于源资产目录内")
        if "generated" in path.parts:
            raise ValueError("源资产路径不能指向派生数据")
        return path


class _ProjectionDocument:
    def __init__(
        self,
        *,
        id: str,
        source_type: str,
        source_id: str,
        title: str,
        excerpt: str,
        text: str,
        exact_terms: set[str],
        source_ref: SourceRef,
        updated_at: str,
    ) -> None:
        self.id = id
        self.source_type = source_type
        self.source_id = source_id
        self.title = title
        self.excerpt = excerpt
        self.text = text
        self.exact_terms = exact_terms
        self.source_ref = source_ref
        self.updated_at = updated_at


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE retrieval_documents (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            text TEXT NOT NULL,
            exact_terms TEXT NOT NULL,
            source_ref_json TEXT NOT NULL,
            source_path TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE retrieval_fts USING fts5(
            doc_id UNINDEXED,
            title,
            text,
            tokenize = 'unicode61'
        );
        """
    )


def _split_paragraphs(markdown: str) -> list[str]:
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", markdown.strip())
        if paragraph.strip()
    ]


def _flatten_fields(
    fields: dict[str, Any],
    prefix: str = "",
) -> Iterable[tuple[str, str]]:
    for key, value in fields.items():
        field_path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _flatten_fields(value, field_path)
        elif isinstance(value, list):
            compact = "；".join(str(item) for item in value if item is not None)
            if compact:
                yield field_path, compact
        elif value is not None:
            yield field_path, str(value)


def _source_ref_path(source_root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(source_root.resolve()).as_posix()
    return f"project_assets/source/{relative}"


def _identity_terms(values: Iterable[str | None]) -> set[str]:
    return {
        normalized
        for value in values
        if value
        for normalized in [_normalize(value)]
        if normalized
    }


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _heading_text(paragraph: str) -> str | None:
    if paragraph.startswith("#"):
        return paragraph.lstrip("#").strip()
    return None


def _compact_excerpt(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
