"""需求 7.1-7.23：评测关联事实、反向索引与对称查询。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark.correlation import (
    CorrelationSubjectKind,
    CorrelationSubjectRef,
    EvaluationCorrelationRecord,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.correlation_repository import (
    CorrelationAsymmetryError,
    JsonEvaluationCorrelationRepository,
)


def _record() -> EvaluationCorrelationRecord:
    return EvaluationCorrelationRecord.create(
        subjects=(
            CorrelationSubjectRef(
                kind=CorrelationSubjectKind.SUITE_RUN,
                stable_id="benchmark_run_alpha",
            ),
            CorrelationSubjectRef(
                kind=CorrelationSubjectKind.CASE_EXECUTION,
                stable_id="benchmark_case_alpha",
            ),
            CorrelationSubjectRef(
                kind=CorrelationSubjectKind.CAPABILITY_INVOCATION,
                stable_id="call_alpha",
            ),
        ),
        mechanism_gate_refs=("mechanism_memory",),
    )


def test_record_identity_is_deterministic_and_immutable() -> None:
    first = _record()
    second = EvaluationCorrelationRecord.create(
        subjects=tuple(reversed(first.subjects)),
        mechanism_gate_refs=("mechanism_memory",),
    )
    assert first.relation_id == second.relation_id
    assert first.content_hash == second.content_hash


def test_query_from_any_endpoint_returns_same_relation_closure(tmp_path: Path) -> None:
    repository = JsonEvaluationCorrelationRepository(tmp_path / "correlations")
    record = repository.append(_record())
    closures = [
        repository.read_closure(subject)
        for subject in record.subjects
    ]
    assert all(closure == closures[0] for closure in closures)
    assert {item.stable_id for item in closures[0]} == {
        "benchmark_run_alpha",
        "benchmark_case_alpha",
        "call_alpha",
    }


def test_tampered_reverse_index_is_reported_as_asymmetry(tmp_path: Path) -> None:
    repository = JsonEvaluationCorrelationRepository(tmp_path / "correlations")
    record = repository.append(_record())
    subject = record.subjects[0]
    index_path = repository.subject_index_path(subject)
    index_path.write_text(
        json.dumps({"subject": subject.model_dump(), "relation_ids": []}),
        encoding="utf-8",
    )
    with pytest.raises(CorrelationAsymmetryError):
        repository.read_closure(record.subjects[1])


def test_same_relation_id_cannot_be_rebound_to_different_subjects(
    tmp_path: Path,
) -> None:
    repository = JsonEvaluationCorrelationRepository(tmp_path / "correlations")
    record = repository.append(_record())
    forged = record.model_copy(
        update={
            "subjects": (
                CorrelationSubjectRef(
                    kind=CorrelationSubjectKind.ISSUE,
                    stable_id="issue_other",
                ),
            )
        }
    )
    with pytest.raises(ValueError):
        repository.append(forged)
