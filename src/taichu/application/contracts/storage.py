"""源数据存储契约。"""

from typing import Protocol, TypeAlias, runtime_checkable

StorageData: TypeAlias = dict[str, object]


@runtime_checkable
class StorageBackend(Protocol):
    """定义应用层所需的源数据存储能力。"""

    async def get(self, collection: str, key: str) -> StorageData | None:
        """读取单条数据。"""
        ...

    async def list(self, collection: str) -> list[StorageData]:
        """列出集合内的数据。"""
        ...

    async def put(
        self,
        collection: str,
        key: str,
        data: StorageData,
    ) -> None:
        """保存单条数据。"""
        ...

    async def delete(self, collection: str, key: str) -> bool:
        """删除单条数据。"""
        ...
