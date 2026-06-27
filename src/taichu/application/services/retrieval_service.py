"""Application service for evidence-backed retrieval."""

from taichu.application.contracts.retrieval import (
    RetrievalContract,
    RetrievalQuery,
)
from taichu.domain.models.retrieval import RetrievalHit


class RetrievalService:
    """Search the current novel through a retrieval contract."""

    def __init__(self, backend: RetrievalContract) -> None:
        self._backend = backend

    async def search(
        self,
        text: str,
        *,
        limit: int = 10,
        scopes: frozenset[str] | None = None,
    ) -> list[RetrievalHit]:
        """Return retrieval hits that carry original-source evidence."""
        if scopes is None:
            query = RetrievalQuery(text=text, limit=limit)
        else:
            query = RetrievalQuery(text=text, limit=limit, scopes=scopes)
        return await self._backend.search(query)
