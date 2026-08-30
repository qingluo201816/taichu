"""Semantic evaluation judge boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from taichu.application.contracts.llm import LLMModelIdentity


class EvaluationJudgeResponse(BaseModel):
    """Validated structured result plus independent transport audit metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output: BaseModel
    raw_response: str | None = None
    model_identity: LLMModelIdentity
    token_usage: dict[str, int] | None = None


@runtime_checkable
class EvaluationJudge(Protocol):
    """One isolated native structured-output semantic judge capability."""

    @property
    def available(self) -> bool:
        """Whether the runtime is configured before a task is accepted."""
        ...

    @property
    def model_identity(self) -> LLMModelIdentity:
        """Return the actual runtime identity."""
        ...

    async def complete(
        self,
        prompt: str,
        *,
        output_schema: type[BaseModel],
    ) -> EvaluationJudgeResponse:
        """Execute one native structured-output request without mutating state."""
        ...
