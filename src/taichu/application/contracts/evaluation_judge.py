"""Semantic evaluation judge boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from taichu.application.contracts.llm import LLMModelIdentity


class EvaluationJudgeResponse(BaseModel):
    """Raw response plus metadata returned by one judge transport call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_response: str
    model_identity: LLMModelIdentity
    token_usage: dict[str, int] | None = None


@runtime_checkable
class EvaluationJudge(Protocol):
    """One isolated text-to-JSON semantic judge capability."""

    @property
    def available(self) -> bool:
        """Whether the runtime is configured before a task is accepted."""
        ...

    @property
    def model_identity(self) -> LLMModelIdentity:
        """Return the actual runtime identity."""
        ...

    async def complete(self, prompt: str) -> EvaluationJudgeResponse:
        """Execute one judge request without mutating application state."""
        ...
