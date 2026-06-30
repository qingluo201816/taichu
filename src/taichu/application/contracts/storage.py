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

    async def read_outline(self) -> StorageData:
        """读取 source/manuscripts/outline.json。"""
        ...

    async def write_outline(self, data: StorageData) -> None:
        """写入 source/manuscripts/outline.json。"""
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

    async def append_workspace_record(
        self,
        filename: str,
        data: StorageData,
    ) -> None:
        """向 source/workspace 下的 JSONL 主记录追加一条数据。"""
        ...

    async def list_workspace_records(
        self,
        filename: str,
    ) -> list[StorageData]:
        """读取 source/workspace 下的 JSONL 主记录。"""
        ...

    async def rewrite_workspace_records(
        self,
        filename: str,
        records: list[StorageData],
    ) -> None:
        """原子重写 source/workspace 下的 JSONL 主记录。"""
        ...

    async def write_knowledge_record(
        self,
        category: str,
        knowledge_id: str,
        data: StorageData,
    ) -> None:
        """原子写入 source/knowledge 下的 JSON 主记录。"""
        ...

    async def read_knowledge_record(
        self,
        category: str,
        knowledge_id: str,
    ) -> StorageData | None:
        """读取 source/knowledge 下的单条 JSON 主记录。"""
        ...

    async def list_knowledge_records(
        self,
        category: str | None = None,
    ) -> list[StorageData]:
        """列出 source/knowledge 下的 JSON 主记录。"""
        ...

    async def write_structured_knowledge_record(
        self,
        knowledge_type: str,
        knowledge_id: str,
        data: StorageData,
    ) -> None:
        """按知识类型写入结构化知识卡 JSON。"""
        ...

    async def read_structured_knowledge_record(
        self,
        knowledge_type: str,
        knowledge_id: str,
    ) -> StorageData | None:
        """按知识类型读取结构化知识卡 JSON。"""
        ...

    async def list_structured_knowledge_records(
        self,
        knowledge_type: str | None = None,
    ) -> list[StorageData]:
        """按知识类型列出结构化知识卡 JSON。"""
        ...

    async def read_preferences(self) -> StorageData:
        """读取 source/workspace/settings_preferences.json。"""
        ...

    async def write_preferences(self, data: StorageData) -> None:
        """写入 source/workspace/settings_preferences.json。"""
        ...

    async def clear_generated(self) -> None:
        """清空并重建 generated 空目录骨架。"""
        ...
