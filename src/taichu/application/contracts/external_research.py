"""外部资料后端契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.external_research.models import (
    ExternalDocument,
    ExternalSearchResult,
)


@runtime_checkable
class ExternalResearchBackend(Protocol):
    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ExternalSearchResult]:
        ...

    async def read(self, url: str) -> ExternalDocument:
        ...
