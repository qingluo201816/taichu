"""LLM 调用遥测仓储契约。"""

from typing import Literal, Protocol

from taichu.application.models.llm_usage import (
    LLMCallRecord,
    LLMUsagePage,
    LLMUsageQuery,
    LLMUsageSummary,
    LLMTokenTrendPoint,
)


class LLMUsageRepository(Protocol):
    """保存和查询非小说事实的模型调用遥测。"""

    async def append(self, record: LLMCallRecord) -> None:
        ...

    async def get(self, call_id: str) -> LLMCallRecord | None:
        ...

    async def list_calls(self, query: LLMUsageQuery) -> LLMUsagePage:
        ...

    async def summarize(self, query: LLMUsageQuery) -> LLMUsageSummary:
        ...

    async def token_trend(
        self, query: LLMUsageQuery, bucket: Literal["hour", "day"]
    ) -> list[LLMTokenTrendPoint]:
        ...
