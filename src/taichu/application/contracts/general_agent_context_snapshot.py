"""通用写作助手上下文快照历史仓储契约。"""

from typing import Protocol

from taichu.application.general_agent.models import GeneralAgentContextSnapshot


class GeneralAgentContextSnapshotRepository(Protocol):
    async def save(self, snapshot: GeneralAgentContextSnapshot) -> None: ...

    async def list_for_run(self, run_id: str) -> list[GeneralAgentContextSnapshot]: ...

    async def delete_run(self, run_id: str) -> None: ...
