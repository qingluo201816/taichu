"""知识检索契约。"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from taichu.domain.models.retrieval import RetrievalHit


@dataclass(frozen=True)
class RetrievalQuery:
    """当前唯一小说内的检索请求。"""

    text: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    limit: int = 10


@dataclass(frozen=True)
class RetrievalResult:
    """与具体检索实现无关的标准结果。"""

    id: str
    type: str
    title: str
    content: str
    source: str
    score: float | None = None


@runtime_checkable
class RetrievalContract(Protocol):
    """定义关键词、语义或混合检索的统一接口。"""

    async def search(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        """检索当前唯一小说的相关内容。"""
        ...


RetrievalBackend = RetrievalContract
