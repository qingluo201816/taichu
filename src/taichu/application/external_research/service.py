"""受 Tool 权限门禁保护的外部研究应用服务。"""

from taichu.application.contracts.external_research import (
    ExternalResearchBackend,
)
from taichu.application.external_research.models import (
    ExternalDocument,
    ExternalSearchResult,
)


class ExternalResearchService:
    """统一外部搜索和来源读取，不负责签发访问授权。"""

    def __init__(self, backend: ExternalResearchBackend) -> None:
        self._backend = backend

    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ExternalSearchResult]:
        return await self._backend.search(query, max_results=max_results)

    async def read(self, url: str) -> ExternalDocument:
        return await self._backend.read(url)
