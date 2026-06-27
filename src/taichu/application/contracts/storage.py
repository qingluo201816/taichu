"""源数据存储契约。"""

from typing import Protocol, TypeAlias, runtime_checkable

StorageData: TypeAlias = dict[str, object]


@runtime_checkable
class StorageContract(Protocol):
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


StorageBackend = StorageContract


@runtime_checkable
class ProjectAssetStorageContract(Protocol):
    """单本小说 project_assets 文件资产访问契约。"""

    async def ensure_skeleton(self) -> None:
        """创建 source/generated 最小目录和空主记录文件。"""
        ...

    async def read_metadata(self) -> StorageData:
        """读取 source/metadata.yaml。"""
        ...

    async def write_metadata(self, data: StorageData) -> None:
        """写入 source/metadata.yaml。"""
        ...

    async def read_manifest(self) -> StorageData:
        """读取 source/manuscripts/manifest.json。"""
        ...

    async def write_manifest(self, data: StorageData) -> None:
        """写入 source/manuscripts/manifest.json。"""
        ...

    async def write_chapter_markdown(
        self,
        relative_path: str,
        content: str,
    ) -> None:
        """写入章节 Markdown，路径相对 source 根目录。"""
        ...

    async def read_chapter_markdown(self, relative_path: str) -> str:
        """读取章节 Markdown，路径相对 source 根目录。"""
        ...

    async def clear_generated(self) -> None:
        """清空并重建 generated 空目录骨架。"""
        ...
