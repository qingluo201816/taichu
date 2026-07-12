"""Persistence boundary for the single-novel knowledge sedimentation frontier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class KnowledgeSedimentationProgress:
    """The latest chapter whose review range the author has accepted."""

    last_accepted_chapter_id: str | None = None
    updated_at: str | None = None


@runtime_checkable
class KnowledgeSedimentationProgressRepository(Protocol):
    """Storage contract for the one global, monotonically advancing frontier."""

    async def get_progress(self) -> KnowledgeSedimentationProgress:
        ...

    async def advance_to(self, chapter_id: str) -> KnowledgeSedimentationProgress:
        ...


class InMemoryKnowledgeSedimentationProgressRepository:
    """Small non-persistent adapter for isolated application tests."""

    def __init__(self) -> None:
        self._progress = KnowledgeSedimentationProgress()

    async def get_progress(self) -> KnowledgeSedimentationProgress:
        return self._progress

    async def advance_to(self, chapter_id: str) -> KnowledgeSedimentationProgress:
        self._progress = KnowledgeSedimentationProgress(last_accepted_chapter_id=chapter_id)
        return self._progress
