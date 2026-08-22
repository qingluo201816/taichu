"""LLM 调用回放资产仓储契约。"""

from typing import Protocol

from taichu.application.models.llm_replay import LLMCallReplayRecord


class LLMCallReplayRepository(Protocol):
    async def save(self, record: LLMCallReplayRecord) -> None: ...

    async def get(self, call_id: str) -> LLMCallReplayRecord | None: ...

    async def list_for_run(self, run_id: str) -> list[LLMCallReplayRecord]: ...

    async def delete_run(self, run_id: str) -> None: ...
