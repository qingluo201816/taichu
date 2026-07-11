"""Knowledge-extraction Agent run persistence boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from taichu.application.agents.models.agent_run import AgentRun


@runtime_checkable
class AgentRunRepository(Protocol):
    """Application-facing access to persisted knowledge-extraction runs."""

    async def write_run(self, run: AgentRun) -> AgentRun:
        """Persist one complete run snapshot."""
        ...

    async def get_run(self, run_id: str) -> AgentRun | None:
        """Read one run by its server-generated identifier."""
        ...

    async def delete_run(self, run_id: str) -> bool:
        """Delete one persisted run."""
        ...

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[AgentRun], int]:
        """List runs newest first with pagination."""
        ...

    async def find_run_for_candidate(self, candidate_id: str) -> AgentRun | None:
        """Find the run containing one review item."""
        ...
