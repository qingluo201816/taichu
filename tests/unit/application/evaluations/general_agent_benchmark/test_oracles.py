"""需求 2.3—2.6、10.3、10.7—10.9：确定性 Typed Oracle。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ClaimCatalog,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    ObservedArtifact,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedInvocation,
    ObservedNode,
    ObservedResourceSnapshot,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionStatus,
    AuthorizationEffectObservation,
    CheckpointAvailabilityObservation,
    ClaimNormalizationInput,
    ClaimNormalizer,
    ClaimProjectionStatus,
    ContextCarrierObservation,
    ContextPreservationObservation,
    DataflowIdentityObservation,
    MemoryCarrierObservation,
    ObservedSourceClaim,
    ObservedSourceProjection,
    RecoveryReuseObservation,
    ResourceDiffObservation,
    ResultContractEquivalenceObservation,
    ResultContractProjection,
    SourceProjectionKind,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    ArtifactContractAssertionSpec,
    AuthoredCaseSpec,
    AuthorizationEffectAssertionSpec,
    CallCountAssertionSpec,
    CallTopologyAssertionSpec,
    CheckpointAvailabilityAssertionSpec,
    ContextPreservationAssertionSpec,
    DataflowIdentityAssertionSpec,
    FinalClaimsAssertionSpec,
    MemoryCarrierAbsenceAssertionSpec,
    RecoveryReuseAssertionSpec,
    ResourceDiffAssertionSpec,
    ResultContractEquivalenceAssertionSpec,
    ZeroCapabilityOrSideEffectAssertionSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"


@pytest.fixture(scope="module")
def case_owner_catalog() -> tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog]:
    suite_payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=suite_payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    case = suite.cases[0]
    owner = EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id=f"benchmark_case_{'a' * 32}",
        run_id="general_run_20260730_150000_oracle",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    catalog = load_claim_catalog(
        _CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(item["asset_id"] for item in manifest["scenario_assets"]),
    )
    return case, owner, catalog


def _records(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    *,
    script_response: str = "脚本响应甲",
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for requirement in case.required_evidence:
        payload = {
            "evidence_id": requirement.evidence_id,
            "observed": True,
        }
        if requirement.probe.kind == "script_protocol":
            payload["script_response"] = script_response
        records.append(
            EvidenceRecord(
                ref=EvidenceRef(
                    evidence_id=requirement.evidence_id,
                    kind=requirement.probe.kind,
                    selector=requirement.probe.selector,
                    owner=owner,
                    record_id=f"record_{requirement.evidence_id}",
                    content_sha256=canonical_sha256(payload),
                ),
                payload=payload,
            )
        )
    return tuple(records)


def _observation(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    *,
    final_text: str,
    final_source_refs: tuple[str, ...] = (),
    nodes: tuple[ObservedNode, ...] = (),
    invocations: tuple[ObservedInvocation, ...] = (),
    artifacts: tuple[ObservedArtifact, ...] = (),
    resource_snapshots: tuple[ObservedResourceSnapshot, ...] = (),
    records: tuple[EvidenceRecord, ...] | None = None,
) -> CaseObservation:
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=case.user_request_raw,
        plan={"route": "direct", "nodes": [item.node_id for item in nodes]},
        nodes=nodes,
        invocations=invocations,
        final_answer=ObservedFinalAnswer.create(
            text=final_text,
            source_refs=final_source_refs,
        ),
        artifacts=artifacts,
        resource_snapshots=resource_snapshots,
        recovery_decisions=(),
        terminal=ObservedTerminalState(
            run_status="completed",
            stop_reason="direct_answer",
            resumable=False,
            pending_human_kind=None,
        ),
        budget=ObservedBudgetUsage(
            node_executions=len(nodes),
            capability_calls=len(invocations),
            model_calls=1,
            total_tokens=128,
            runtime_ms=20,
            context_tokens=64,
        ),
        script_protocol_deviations=(),
        evidence_records=records if records is not None else _records(case, owner),
    )


def _final_claims(
    *required: str,
    forbidden: tuple[str, ...] = (),
) -> FinalClaimsAssertionSpec:
    return FinalClaimsAssertionSpec(
        kind="final_claims",
        assertion_id="oracle_final_claims",
        description="最终回答必须符合独立 ClaimCatalog。",
        required_claim_refs=required,
        forbidden_claim_refs=forbidden,
        normalizer_ref="claim_text",
    )


def _source_claim(
    catalog: ClaimCatalog,
    claim_id: str,
    *,
    span: str,
    required_binding: bool = True,
) -> ObservedSourceClaim:
    claim = catalog.claim(claim_id)
    return ObservedSourceClaim(
        claim_id=claim.claim_id,
        subject=claim.subject,
        predicate=claim.predicate,
        object=claim.object,
        polarity=claim.polarity,
        text_span=span,
        required_binding=required_binding,
        source_refs=("fixture_source_tide_lamp",),
    )


def test_direct_answer_positive_and_real_counterexample_are_distinct(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    oracle = TypedOracle(catalog=catalog)
    assertion = _final_claims(
        "route_direct",
        "capability_none",
        forbidden=("tide_lamp_memory_temporarily_stored",),
    )
    positive = _observation(
        case,
        owner,
        final_text="  本轮直接回答， 不调用工具或子智能体！ ",
    )
    negative = _observation(
        case,
        owner,
        final_text="归潮灯会把共同记忆暂存在潮汐回廊。",
    )

    passed = oracle.evaluate(assertion, positive)
    failed = oracle.evaluate(assertion, negative)

    assert passed.status is AssertionStatus.PASSED
    assert passed.claim_projection is not None
    assert passed.claim_projection.status is ClaimProjectionStatus.VALID
    assert {item.claim_id for item in passed.claim_projection.observed_claims} >= {
        "route_direct",
        "capability_none",
    }
    assert failed.status is AssertionStatus.FAILED
    assert failed.claim_projection is not None
    assert {item.claim_id for item in failed.claim_projection.observed_claims} == {
        "tide_lamp_memory_temporarily_stored"
    }


def test_evidence_consumption_requires_actual_output_identity_and_source_binding(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    output_sha256 = canonical_sha256({"claim": "tide_lamp_memory_temporarily_stored"})
    invocation = ObservedInvocation(
        call_id="call_tide_lamp",
        parent_call_id=None,
        node_id="retrieve_tide_lamp",
        capability_kind="tool",
        capability_name="retrieve_knowledge",
        status="completed",
        input_sha256=canonical_sha256({"query": "归潮灯"}),
        output_sha256=output_sha256,
        source_refs=("fixture_source_tide_lamp",),
        artifact_refs=(),
    )
    observation = _observation(
        case,
        owner,
        final_text="潮灯会暂存共同记忆。",
        final_source_refs=("fixture_source_tide_lamp",),
        invocations=(invocation,),
    )
    claim_input = ClaimNormalizationInput(
        observed_text=observation.final_answer.text,
        observed_source_projection=(
            ObservedSourceProjection(
                origin=SourceProjectionKind.INVOCATION,
                producer_id=invocation.call_id,
                content_sha256=output_sha256,
                source_refs=invocation.source_refs,
                claims=(
                    _source_claim(
                        catalog,
                        "tide_lamp_memory_temporarily_stored",
                        span="潮灯会暂存共同记忆",
                    ),
                ),
            ),
        ),
        normalizer_id="claim_text",
        version="1",
    )
    dataflow = DataflowIdentityObservation(
        producer="retrieve_knowledge",
        consumer="final_answer",
        identity_field="content_sha256",
        producer_identity=output_sha256,
        consumer_identity=output_sha256,
        source_refs=("fixture_source_tide_lamp",),
    )
    context = AssertionEvaluationContext(
        claim_normalization_input=claim_input,
        dataflow_identities=(dataflow,),
    )
    oracle = TypedOracle(catalog=catalog)

    claim_result = oracle.evaluate(
        _final_claims("tide_lamp_memory_temporarily_stored"),
        observation,
        context=context,
    )
    flow_result = oracle.evaluate(
        DataflowIdentityAssertionSpec(
            kind="dataflow_identity",
            assertion_id="oracle_evidence_flow",
            description="Tool 真实结果必须进入最终回答。",
            producer="retrieve_knowledge",
            consumer="final_answer",
            identity_field="content_sha256",
        ),
        observation,
        context=context,
    )

    assert claim_result.status is AssertionStatus.PASSED
    assert flow_result.status is AssertionStatus.PASSED

    missing_binding = context.model_copy(update={"dataflow_identities": ()})
    assert (
        oracle.evaluate(
            DataflowIdentityAssertionSpec(
                kind="dataflow_identity",
                assertion_id="oracle_missing_flow",
                description="缺少真实交接证据不得当作普通缺失。",
                producer="retrieve_knowledge",
                consumer="final_answer",
                identity_field="content_sha256",
            ),
            observation,
            context=missing_binding,
        ).status
        is AssertionStatus.INVALID
    )

    wrong_final = _observation(
        case,
        owner,
        final_text="归潮灯不会暂存共同记忆。",
        final_source_refs=("fixture_source_tide_lamp",),
        invocations=(invocation,),
    )
    assert (
        oracle.evaluate(
            _final_claims("tide_lamp_memory_temporarily_stored"),
            wrong_final,
        ).status
        is AssertionStatus.FAILED
    )


def test_revision_claims_must_agree_with_real_resource_diff(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    before = ObservedResourceSnapshot(
        snapshot_ref="revision_draft",
        phase="before",
        content_sha256=canonical_sha256(
            {"target": "左臂挥剑", "protected": "潮声未变"}
        ),
        payload={"target": "左臂挥剑", "protected": "潮声未变"},
    )
    after = ObservedResourceSnapshot(
        snapshot_ref="revision_draft",
        phase="after",
        content_sha256=canonical_sha256(
            {"target": "右手挥剑", "protected": "潮声未变"}
        ),
        payload={"target": "右手挥剑", "protected": "潮声未变"},
    )
    observation = _observation(
        case,
        owner,
        final_text=("修订稿修复了目标问题，受保护的非目标内容保持不变。"),
        resource_snapshots=(before, after),
    )
    diff = ResourceDiffObservation(
        resource_snapshot_ref="revision_draft",
        actual_change="updated",
        before_sha256=before.content_sha256,
        after_sha256=after.content_sha256,
        target_refs=("target",),
        changed_refs=("target",),
        protected_refs=("protected",),
        protected_changed_refs=(),
    )
    context = AssertionEvaluationContext(resource_diffs=(diff,))
    oracle = TypedOracle(catalog=catalog)

    claims = oracle.evaluate(
        _final_claims("protected_content_preserved", "revision_target_fixed"),
        observation,
    )
    resource = oracle.evaluate(
        ResourceDiffAssertionSpec(
            kind="resource_diff",
            assertion_id="oracle_revision_diff",
            description="修订必须真实更新目标且保护非目标内容。",
            resource_snapshot_ref="revision_draft",
            expected_change="updated",
        ),
        observation,
        context=context,
    )

    assert claims.status is AssertionStatus.PASSED
    assert resource.status is AssertionStatus.PASSED

    false_diff = diff.model_copy(
        update={
            "actual_change": "unchanged",
            "after_sha256": before.content_sha256,
            "changed_refs": (),
        }
    )
    assert (
        oracle.evaluate(
            ResourceDiffAssertionSpec(
                kind="resource_diff",
                assertion_id="oracle_revision_false_claim",
                description="文字声称修复不能覆盖实际资源未变。",
                resource_snapshot_ref="revision_draft",
                expected_change="updated",
            ),
            observation.model_copy(
                update={
                    "resource_snapshots": (
                        before,
                        before.model_copy(update={"phase": "after"}),
                    )
                }
            ),
            context=AssertionEvaluationContext(resource_diffs=(false_diff,)),
        ).status
        is AssertionStatus.FAILED
    )


def test_script_response_changes_do_not_change_fact_projection(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    oracle = TypedOracle(catalog=catalog)
    assertion = _final_claims("route_direct", "capability_none")
    first = _observation(
        case,
        owner,
        final_text="本轮直接回答，不调用工具或子智能体。",
        records=_records(case, owner, script_response="脚本预置正确答案"),
    )
    second = _observation(
        case,
        owner,
        final_text="本轮直接回答，不调用工具或子智能体。",
        records=_records(case, owner, script_response="脚本完全不同"),
    )

    first_result = oracle.evaluate(assertion, first)
    second_result = oracle.evaluate(assertion, second)

    assert first.observation_sha256 != second.observation_sha256
    assert first_result.claim_projection == second_result.claim_projection
    assert first_result.status is second_result.status is AssertionStatus.PASSED
    with pytest.raises(ValidationError):
        ClaimNormalizationInput.model_validate(
            {
                "observed_text": "本轮直接回答",
                "observed_source_projection": [],
                "normalizer_id": "claim_text",
                "version": "1",
                "scripted_response": "不得进入 Oracle 输入",
            }
        )


def test_missing_or_corrupt_evidence_and_ambiguous_claims_are_invalid(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    incomplete = _observation(
        case,
        owner,
        final_text="本轮直接回答。",
        records=_records(case, owner)[:-1],
    )
    assert (
        TypedOracle(catalog=catalog)
        .evaluate(_final_claims("route_direct"), incomplete)
        .status
        is AssertionStatus.INVALID
    )

    source_payload = catalog.model_dump(
        mode="json",
        by_alias=True,
        exclude={"content_hash"},
    )
    claims = list(source_payload["claims"])
    conflict = dict(claims[0])
    conflict.update(
        {
            "claim_id": "route_direct_conflict",
            "subject": "runtime_route",
            "predicate": "uses",
            "object": "search_route",
            "polarity": "positive",
            "canonical_forms": ["本轮直接回答"],
            "aliases": [],
        }
    )
    claims.append(conflict)
    claims.sort(key=lambda item: item["claim_id"])
    source_payload["claims"] = claims
    ambiguous_catalog = ClaimCatalog.model_validate(
        {
            **source_payload,
            "content_hash": canonical_sha256(source_payload),
        }
    )
    projection = ClaimNormalizer(
        catalog=ambiguous_catalog,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ).normalize(
        ClaimNormalizationInput(
            observed_text="本轮直接回答。",
            observed_source_projection=(),
            normalizer_id="claim_text",
            version="1",
        )
    )

    assert projection.status is ClaimProjectionStatus.AMBIGUOUS
    ambiguous_result = TypedOracle(catalog=ambiguous_catalog).evaluate(
        _final_claims("route_direct"),
        _observation(case, owner, final_text="本轮直接回答。"),
    )
    assert ambiguous_result.status is AssertionStatus.INVALID


def test_enumerated_assertion_families_use_typed_observations(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    output_hash = canonical_sha256({"result": "ok"})
    invocations = (
        ObservedInvocation(
            call_id="call_prepare",
            node_id="prepare",
            capability_kind="tool",
            capability_name="prepare_scene",
            status="completed",
            input_sha256=canonical_sha256({"request": "scene"}),
            output_sha256=output_hash,
        ),
    )
    nodes = (
        ObservedNode(
            node_id="prepare",
            plan_revision=1,
            capability_kind="tool",
            capability_name="prepare_scene",
            status="completed",
            dependencies=(),
        ),
        ObservedNode(
            node_id="draft",
            plan_revision=1,
            capability_kind="subagent",
            capability_name="draft_scene",
            status="completed",
            dependencies=("prepare",),
        ),
    )
    observation = _observation(
        case,
        owner,
        final_text="本轮直接回答。",
        nodes=nodes,
        invocations=invocations,
    )
    contract = ResultContractProjection(
        claim_ids=("route_direct",),
        capability_names=("prepare_scene",),
        topology_edges=("prepare>draft",),
        protected_fact_refs=("fact_anchor",),
        artifact_contracts=("final_answer",),
        resource_diff_sha256=canonical_sha256({"change": "none"}),
    )
    context = AssertionEvaluationContext(
        authorizations=(
            AuthorizationEffectObservation(
                decision_ref="decision_write_denied",
                decision="denied",
                effect_count=0,
                requested_target_ref="manuscript_target",
                effected_target_refs=(),
                preview_sha256=None,
                applied_input_sha256=None,
            ),
        ),
        memory_carriers=tuple(
            MemoryCarrierObservation(
                memory_seed_ref="memory_seed_rejected",
                state=state,
                carrier="final",
                sentinel_ref=f"sentinel_{state}",
                occurrence_count=0,
            )
            for state in ("stale", "rejected", "superseded")
        ),
        recovery_reuse=(
            RecoveryReuseObservation(
                fault_plan_ref="fault_after_plan",
                plan_before_sha256=observation.plan_sha256,
                plan_after_sha256=observation.plan_sha256,
                successful_node_reexecutions=0,
                duplicate_side_effects=0,
                reused_result_ids=("result_accepted",),
                retried_successful_result_ids=(),
            ),
        ),
        checkpoint_availability=(
            CheckpointAvailabilityObservation(
                fault_plan_ref="fault_checkpoint_integrity",
                status="available",
                selected_checkpoint_id="checkpoint-2",
                recovery_action="resume",
                automatic_restart_count=0,
                effect_state="settled",
            ),
        ),
        context_preservation=(
            ContextPreservationObservation(
                pressure_plan_ref="pressure_long_history",
                carriers=tuple(
                    ContextCarrierObservation(
                        carrier=carrier,
                        before_sha256=canonical_sha256(
                            {"carrier": carrier, "phase": "before"}
                        ),
                        after_sha256=canonical_sha256(
                            {"carrier": carrier, "phase": "before"}
                        ),
                        preserved=True,
                        protected_refs=("fact_anchor",),
                    )
                    for carrier in (
                        "stable_memory",
                        "working_memory",
                        "history_memory",
                        "current_request",
                    )
                ),
                current_request_before_sha256=observation.user_request_sha256,
                current_request_after_sha256=observation.user_request_sha256,
            ),
        ),
        result_contract_equivalences=(
            ResultContractEquivalenceObservation(
                pressure_plan_ref="pressure_equivalence",
                baseline=contract,
                candidate=contract,
            ),
        ),
    )
    oracle = TypedOracle(catalog=catalog)

    assertions = (
        CallCountAssertionSpec(
            kind="call_count",
            assertion_id="oracle_call_count",
            description="能力调用次数精确。",
            capability_name="prepare_scene",
            min_calls=1,
            max_calls=1,
        ),
        CallTopologyAssertionSpec(
            kind="call_topology",
            assertion_id="oracle_call_topology",
            description="准备节点先于草稿节点。",
            predecessor="prepare_scene",
            successor="draft_scene",
            relation="before",
        ),
        ArtifactContractAssertionSpec(
            kind="artifact_contract",
            assertion_id="oracle_artifact",
            description="最终回答存在。",
            artifact_kind="final_answer",
            disposition="required",
        ),
        AuthorizationEffectAssertionSpec(
            kind="authorization_effect",
            assertion_id="oracle_authorization",
            description="拒绝后没有 Effect。",
            decision_ref="decision_write_denied",
            expected_effect_count=0,
        ),
        MemoryCarrierAbsenceAssertionSpec(
            kind="memory_carrier_absence",
            assertion_id="oracle_memory",
            description="无效记忆载体全部缺席。",
            memory_seed_ref="memory_seed_rejected",
            forbidden_states=("stale", "rejected", "superseded"),
        ),
        RecoveryReuseAssertionSpec(
            kind="recovery_reuse",
            assertion_id="oracle_recovery",
            description="成功节点不得重跑。",
            fault_plan_ref="fault_after_plan",
            max_successful_node_reexecutions=0,
        ),
        CheckpointAvailabilityAssertionSpec(
            kind="checkpoint_availability",
            assertion_id="oracle_checkpoint",
            description="只恢复有效修订。",
            fault_plan_ref="fault_checkpoint_integrity",
            allow_safe_failure=True,
        ),
        ContextPreservationAssertionSpec(
            kind="context_preservation",
            assertion_id="oracle_context",
            description="受保护载体保持。",
            pressure_plan_ref="pressure_long_history",
            protected_carriers=(
                "stable_memory",
                "working_memory",
                "history_memory",
                "current_request",
            ),
        ),
        ResultContractEquivalenceAssertionSpec(
            kind="result_contract_equivalence",
            assertion_id="oracle_equivalence",
            description="压力前后结果合同等价。",
            pressure_plan_ref="pressure_equivalence",
            comparison="semantic_contract",
        ),
    )

    results = tuple(
        oracle.evaluate(assertion, observation, context=context)
        for assertion in assertions
    )

    assert all(result.status is AssertionStatus.PASSED for result in results)


def test_zero_capability_and_side_effect_assertion_checks_both_dimensions(
    case_owner_catalog: tuple[AuthoredCaseSpec, EvidenceOwner, ClaimCatalog],
) -> None:
    case, owner, catalog = case_owner_catalog
    assertion = ZeroCapabilityOrSideEffectAssertionSpec(
        kind="zero_capability_or_side_effect",
        assertion_id="oracle_zero",
        description="能力调用与副作用都必须为零。",
        require_zero_capability_calls=True,
        require_zero_side_effects=True,
    )
    oracle = TypedOracle(catalog=catalog)
    clean = _observation(case, owner, final_text="本轮直接回答。")
    invocation = ObservedInvocation(
        call_id="call_unnecessary",
        node_id=None,
        capability_kind="tool",
        capability_name="retrieve_knowledge",
        status="completed",
        input_sha256=canonical_sha256({"query": "不必要"}),
        output_sha256=canonical_sha256({"result": "unused"}),
    )
    called = _observation(
        case,
        owner,
        final_text="本轮直接回答。",
        invocations=(invocation,),
    )

    assert oracle.evaluate(assertion, clean).status is AssertionStatus.PASSED
    assert oracle.evaluate(assertion, called).status is AssertionStatus.FAILED
