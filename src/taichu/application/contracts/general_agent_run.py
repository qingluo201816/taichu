"""通用写作助手 Runtime 检查点仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.general_agent.models import GeneralAgentRun


@runtime_checkable
class GeneralAgentRunRepository(Protocol):
    async def save(self, run: GeneralAgentRun) -> GeneralAgentRun:
        ...

    async def get(self, run_id: str) -> GeneralAgentRun | None:
        ...

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[GeneralAgentRun], int]:
        ...

    async def delete(self, run_id: str) -> bool:
        ...
