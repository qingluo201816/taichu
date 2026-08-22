"""评测关联仓储的应用端口。"""

from __future__ import annotations

from typing import Protocol

from taichu.application.evaluations.general_agent_benchmark.correlation import (
    CorrelationSubjectRef,
    EvaluationCorrelationRecord,
)


class EvaluationCorrelationRepository(Protocol):
    def append(
        self,
        record: EvaluationCorrelationRecord,
    ) -> EvaluationCorrelationRecord: ...

    def read_closure(
        self,
        subject: CorrelationSubjectRef,
    ) -> tuple[CorrelationSubjectRef, ...]: ...
