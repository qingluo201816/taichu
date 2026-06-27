"""应用层依赖的稳定契约。"""

from taichu.application.contracts.indexer import IndexerContract
from taichu.application.contracts.llm import LLMContract
from taichu.application.contracts.retrieval import (
    RetrievalBackend,
    RetrievalContract,
    RetrievalQuery,
    RetrievalResult,
)
from taichu.application.contracts.storage import (
    ProjectAssetStorageContract,
    StorageBackend,
    StorageContract,
    StorageData,
)

__all__ = [
    "IndexerContract",
    "LLMContract",
    "RetrievalBackend",
    "RetrievalContract",
    "RetrievalQuery",
    "RetrievalResult",
    "ProjectAssetStorageContract",
    "StorageBackend",
    "StorageContract",
    "StorageData",
]
