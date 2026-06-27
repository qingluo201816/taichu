"""Application service for rebuildable generated projections."""

from taichu.application.contracts.indexer import IndexerContract
from taichu.application.contracts.storage import ProjectAssetStorageContract


class IndexService:
    """Rebuild generated retrieval projections from source assets."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        indexer: IndexerContract,
    ) -> None:
        self._storage = storage
        self._indexer = indexer

    async def clear_generated(self) -> None:
        """Clear generated projections without touching source assets."""
        await self._storage.clear_generated()

    async def rebuild_generated_projection(self) -> None:
        """Clear generated data and rebuild projection from source facts."""
        await self._storage.clear_generated()
        await self._indexer.rebuild()
