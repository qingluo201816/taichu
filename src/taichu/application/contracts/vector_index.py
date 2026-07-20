"""向量索引后端与清单仓储的跨层契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.retrieval.vector_index_models import (
    VectorIndexCollectionState,
    VectorIndexManifest,
    VectorIndexPoint,
    VectorIndexSearchHit,
    VectorIndexSearchRequest,
)


@runtime_checkable
class VectorIndexBackend(Protocol):
    """隔离应用层与 Qdrant 的最小索引行为。"""

    async def create_collection(
        self,
        collection_name: str,
        *,
        dimensions: int,
    ) -> None: ...

    async def upsert_points(
        self,
        collection_name: str,
        points: list[VectorIndexPoint],
    ) -> None: ...

    async def collection_state(
        self,
        collection_name: str,
    ) -> VectorIndexCollectionState | None: ...

    async def get_alias_target(self, alias_name: str) -> str | None: ...

    async def replace_alias(
        self,
        alias_name: str,
        collection_name: str | None,
    ) -> None: ...

    async def delete_collection(self, collection_name: str) -> None: ...

    async def search(
        self,
        request: VectorIndexSearchRequest,
    ) -> list[VectorIndexSearchHit]: ...


@runtime_checkable
class VectorIndexManifestRepository(Protocol):
    """保存 active 清单和按 index_id 留存的构建审计。"""

    async def load_active(self) -> VectorIndexManifest | None: ...

    async def save_active(self, manifest: VectorIndexManifest) -> None: ...

    async def delete_active(self) -> None: ...
