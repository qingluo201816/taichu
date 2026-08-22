"""评测拥有的稳定关联主题与不可变关系。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)


class CorrelationSubjectKind(StrEnum):
    SUITE_RUN = "suite_run"
    CASE_EXECUTION = "case_execution"
    CAPABILITY_INVOCATION = "capability_invocation"
    ISSUE = "issue"
    FIRST_LIVE_ARTIFACT = "first_live_artifact"
    COMPARISON = "comparison"


class CorrelationSubjectRef(BenchmarkModel):
    kind: CorrelationSubjectKind
    stable_id: str = Field(min_length=1, max_length=300)

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.stable_id}"


class EvaluationCorrelationRecord(BenchmarkModel):
    relation_id: str = Field(pattern=r"^correlation_[a-f0-9]{64}$")
    subjects: tuple[CorrelationSubjectRef, ...] = Field(min_length=2)
    mechanism_gate_refs: tuple[StableId, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def _subjects_are_unique(self) -> EvaluationCorrelationRecord:
        keys = [subject.key for subject in self.subjects]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("关联主题必须按稳定 key 排序且不得重复。")
        return self

    @staticmethod
    def _payload(
        *,
        subjects: tuple[CorrelationSubjectRef, ...],
        mechanism_gate_refs: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "subjects": subjects,
            "mechanism_gate_refs": tuple(sorted(mechanism_gate_refs)),
        }

    @classmethod
    def create(
        cls,
        *,
        subjects: tuple[CorrelationSubjectRef, ...],
        mechanism_gate_refs: tuple[str, ...],
    ) -> EvaluationCorrelationRecord:
        ordered_subjects = tuple(sorted(subjects, key=lambda item: item.key))
        ordered_gates = tuple(sorted(mechanism_gate_refs))
        digest = canonical_sha256(
            cls._payload(
                subjects=ordered_subjects,
                mechanism_gate_refs=ordered_gates,
            )
        )
        return cls(
            relation_id=f"correlation_{digest}",
            subjects=ordered_subjects,
            mechanism_gate_refs=ordered_gates,
            content_hash=digest,
        )

    def verify_identity(self) -> None:
        digest = canonical_sha256(
            self._payload(
                subjects=self.subjects,
                mechanism_gate_refs=self.mechanism_gate_refs,
            )
        )
        if digest != self.content_hash or self.relation_id != f"correlation_{digest}":
            raise ValueError("评测关联 identity/content hash 不一致。")
