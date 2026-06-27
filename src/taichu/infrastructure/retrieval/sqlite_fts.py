"""SQLite FTS retrieval backend for generated projections."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from pathlib import Path

from taichu.application.contracts.retrieval import RetrievalQuery
from taichu.domain.models.retrieval import (
    RetrievalHit,
    RetrievalReason,
    RetrievalSourceType,
)
from taichu.domain.models.source_ref import SourceRef
from taichu.domain.rules.fact_scope import RetrievalScopeName


class SqliteFTSRetrievalBackend:
    """Query generated SQLite projection and return SourceRef-backed hits."""

    def __init__(self, assets_root: Path) -> None:
        self._db_path = assets_root / "generated" / "sqlite" / "taichu.db"

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        """Search fact-scope projection."""
        return await asyncio.to_thread(self._search_sync, query)

    def _search_sync(self, query: RetrievalQuery) -> list[RetrievalHit]:
        text = query.text.strip()
        if not text or not _allows_fact_scope(query.scopes):
            return []
        if not self._db_path.exists():
            return []

        limit = max(query.limit, 1)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            exact_rows = self._exact_rows(connection, text)
            fts_rows = self._fts_rows(connection, text, limit * 3)
        finally:
            connection.close()

        merged = _merge_rows(exact_rows, fts_rows)
        return [
            _row_to_hit(row, score, reason) for row, score, reason in merged[:limit]
        ]

    def _exact_rows(
        self,
        connection: sqlite3.Connection,
        text: str,
    ) -> list[sqlite3.Row]:
        normalized = _normalize(text)
        rows = connection.execute(
            """
            SELECT *
            FROM retrieval_documents
            ORDER BY source_type, title, id
            """
        ).fetchall()
        matched: list[sqlite3.Row] = []
        for row in rows:
            exact_terms = json.loads(row["exact_terms"])
            if normalized in exact_terms:
                matched.append(row)
        return matched

    def _fts_rows(
        self,
        connection: sqlite3.Connection,
        text: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        try:
            rows = connection.execute(
                """
                SELECT d.*, bm25(retrieval_fts) AS rank
                FROM retrieval_fts
                JOIN retrieval_documents d ON d.id = retrieval_fts.doc_id
                WHERE retrieval_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_phrase(text), limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        if rows:
            return rows

        like_pattern = f"%{text}%"
        return connection.execute(
            """
            SELECT *
            FROM retrieval_documents
            WHERE title LIKE ? OR text LIKE ?
            ORDER BY source_type, title, id
            LIMIT ?
            """,
            (like_pattern, like_pattern, limit),
        ).fetchall()


def _allows_fact_scope(scopes: frozenset[str]) -> bool:
    return not scopes or RetrievalScopeName.FACT.value in scopes


def _merge_rows(
    exact_rows: list[sqlite3.Row],
    fts_rows: list[sqlite3.Row],
) -> list[tuple[sqlite3.Row, float, RetrievalReason]]:
    merged: dict[str, tuple[sqlite3.Row, float, RetrievalReason]] = {}
    for row in exact_rows:
        merged[row["id"]] = (row, 1.0, RetrievalReason.EXACT)
    for row in fts_rows:
        if row["id"] in merged:
            existing = merged[row["id"]]
            merged[row["id"]] = (
                existing[0],
                max(existing[1], 1.15),
                RetrievalReason.HYBRID,
            )
            continue
        merged[row["id"]] = (row, 0.7, RetrievalReason.FTS)
    return sorted(
        merged.values(),
        key=lambda item: (-item[1], item[0]["source_type"], item[0]["id"]),
    )


def _row_to_hit(
    row: sqlite3.Row,
    score: float,
    reason: RetrievalReason,
) -> RetrievalHit:
    source_ref = SourceRef.model_validate(json.loads(row["source_ref_json"]))
    return RetrievalHit(
        source_type=RetrievalSourceType(row["source_type"]),
        source_id=row["source_id"],
        excerpt=row["excerpt"],
        score=score,
        reason=reason,
        source_ref=source_ref,
    )


def _fts_phrase(text: str) -> str:
    escaped = text.replace('"', '""')
    return f'"{escaped}"'


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
