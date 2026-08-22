"""需求 13.1-13.15：类型化工件、验证器、门禁与案例结论。"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from taichu.application.evaluations.general_agent_benchmark.models import (
    ArtifactDisposition,
    CapabilityArtifactSpec,
    CapabilityKind,
    CaseConclusion,
    ExpectedArtifact,
    FinalAnswerArtifactSpec,
    GateConditionResult,
    GateKind,
    GateResult,
    GateScope,
    GateStatus,
    HumanInterventionArtifactSpec,
    SourceReferenceArtifactSpec,
    VerifierId,
    VerifierResult,
    VerifierSpec,
    VerifierStatus,
    WriteCandidateArtifactSpec,
)


def _common(artifact_id: str, disposition: ArtifactDisposition) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "disposition": disposition,
        "identity_rules": ({"field": "content_hash", "required": True},),
        "verifier_instance_ids": ("verify_main",),
    }


def test_all_five_expected_artifact_types_validate_independently() -> None:
    artifacts: tuple[ExpectedArtifact, ...] = (
        FinalAnswerArtifactSpec(
            **_common("final_answer", ArtifactDisposition.REQUIRED),
            answer_contract="中文直接回答",
            allowed_languages=frozenset({"zh-CN"}),
            required_claim_ids=("claim_location",),
            forbidden_claim_ids=(),
        ),
        SourceReferenceArtifactSpec(
            **_common("source_refs", ArtifactDisposition.REQUIRED),
            allowed_fixture_source_ids=frozenset({"chapter_001"}),
            must_resolve=True,
            min_count=1,
            max_count=3,
            source_kinds=frozenset({"manuscript"}),
        ),
        CapabilityArtifactSpec(
            **_common("capability_output", ArtifactDisposition.REQUIRED),
            capability_name="read_manuscript",
            capability_kind=CapabilityKind.TOOL,
            artifact_kind="manuscript_excerpt",
        ),
        WriteCandidateArtifactSpec(
            **_common("write_candidate", ArtifactDisposition.FORBIDDEN),
            candidate_kind="manuscript_patch",
            target_fixture_refs=("chapter_001",),
            must_remain_uncommitted=True,
        ),
        HumanInterventionArtifactSpec(
            **_common("human_intervention", ArtifactDisposition.NOT_APPLICABLE),
            intervention_kind="write_authorization",
            expected_state="waiting_human",
            trigger_boundary="提交正文写入前",
            resource_scopes=("chapter_001",),
            requires_second_confirmation=True,
        ),
    )

    adapter = TypeAdapter(ExpectedArtifact)
    reparsed = [adapter.validate_python(item.model_dump()) for item in artifacts]
    assert [item.artifact_type for item in reparsed] == [
        "final_answer",
        "source_reference",
        "capability_artifact",
        "write_candidate",
        "human_intervention",
    ]


def test_artifact_unknown_fields_and_write_commit_escape_are_rejected() -> None:
    with pytest.raises(ValidationError):
        WriteCandidateArtifactSpec(
            **_common("write_candidate", ArtifactDisposition.REQUIRED),
            candidate_kind="knowledge_card",
            target_fixture_refs=("card_001",),
            must_remain_uncommitted=False,
        )

    payload = {
        **_common("final_answer", ArtifactDisposition.REQUIRED),
        "artifact_type": "final_answer",
        "answer_contract": "中文回答",
        "allowed_languages": ["zh-CN"],
        "required_claim_ids": [],
        "forbidden_claim_ids": [],
        "shell_command": "cmd /c echo unsafe",
    }
    with pytest.raises(ValidationError):
        TypeAdapter(ExpectedArtifact).validate_python(payload)


def test_verifier_spec_uses_closed_identity_and_typed_config() -> None:
    spec = VerifierSpec(
        instance_id="verify_answer",
        verifier_id=VerifierId.FINAL_ANSWER_CONTRACT,
        expected_artifact_ids=("final_answer",),
        required=True,
        config={
            "kind": "final_answer_contract",
            "require_non_empty": True,
        },
    )
    assert spec.config.kind == VerifierId.FINAL_ANSWER_CONTRACT

    with pytest.raises(ValidationError):
        VerifierSpec(
            instance_id="verify_answer",
            verifier_id=VerifierId.FINAL_ANSWER_CONTRACT,
            expected_artifact_ids=("final_answer",),
            required=True,
            config={
                "kind": "final_answer_contract",
                "require_non_empty": True,
                "command": "powershell.exe",
            },
        )


def test_verifier_result_and_gate_result_keep_evidence_and_failure_source() -> None:
    result = VerifierResult(
        instance_id="verify_answer",
        verifier_id=VerifierId.FINAL_ANSWER_CONTRACT,
        rule_identity="rule:answer",
        spec_hash="a" * 64,
        status=VerifierStatus.FAILED,
        expected_summary="包含地点事实",
        observed_summary="缺少地点事实",
        evidence_refs=("evidence_answer",),
        failure_categories=("verifier_failed",),
        error_code="ANSWER_CLAIM_MISSING",
        message_key="评测.最终回答.缺少断言",
        deterministic=True,
        started_at="2026-07-27T00:00:00Z",
        finished_at="2026-07-27T00:00:01Z",
    )
    gate = GateResult(
        scope=GateScope.CASE,
        gate_kind=GateKind.VERIFIER,
        status=GateStatus.FAILED,
        conditions=(
            GateConditionResult(
                condition_id="verify_answer",
                status=GateStatus.FAILED,
                expected="包含地点事实",
                observed="缺少地点事实",
                evidence_refs=result.evidence_refs,
            ),
        ),
        expected="全部必需校验器通过",
        observed="一个必需校验器失败",
        evidence_refs=result.evidence_refs,
        failure_categories=result.failure_categories,
    )
    assert gate.status is GateStatus.FAILED
    assert gate.evidence_refs == ("evidence_answer",)


@pytest.mark.parametrize(
    "value",
    ["passed", "failed", "invalid", "unfinished", "cancelled"],
)
def test_case_conclusion_is_closed(value: str) -> None:
    assert CaseConclusion(value).value == value

    with pytest.raises(ValueError):
        CaseConclusion("warning_pass")
