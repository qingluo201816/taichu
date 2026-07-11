"""LLM-backed adapter for the semantic evaluation judge contract."""

from __future__ import annotations

from taichu.application.contracts.evaluation_judge import (
    EvaluationJudgeResponse,
)
from taichu.application.contracts.llm import LLMContract, LLMModelIdentity


class LLMEvaluationJudgeAdapter:
    """Expose one configured LLM runtime as an isolated judge."""

    def __init__(self, llm: LLMContract, *, configured: bool) -> None:
        self._llm = llm
        self._configured = configured

    @property
    def available(self) -> bool:
        """Return whether the runtime was actually configured."""
        return self._configured

    @property
    def model_identity(self) -> LLMModelIdentity:
        """Return the adapter-reported runtime identity."""
        return self._llm.model_identity

    async def complete(self, prompt: str) -> EvaluationJudgeResponse:
        """Execute one text request and retain its raw response."""
        if not self.available:
            raise EvaluationJudgeUnavailableError("语义裁判当前不可用。")
        raw_response = await self._llm.complete(prompt)
        return EvaluationJudgeResponse(
            raw_response=raw_response,
            model_identity=self.model_identity,
            token_usage=None,
        )


class EvaluationJudgeUnavailableError(RuntimeError):
    """Raised before a semantic call when no judge runtime is configured."""
