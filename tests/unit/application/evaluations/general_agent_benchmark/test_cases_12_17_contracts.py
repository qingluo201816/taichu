"""第 12—17 条预览、授权、拒绝与持久化行为合同。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ClaimCatalog,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.models import TrackKind
from taichu.application.evaluations.general_agent_benchmark.observations import (
    EvidenceKind,
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    EvidenceSelector,
    ObservedArtifact,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedInvocation,
    ObservedResourceSnapshot,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionStatus,
    AuthorizationEffectObservation,
    DataflowIdentityObservation,
    ResourceDiffObservation,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    ArtifactContractAssertionSpec,
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
    AuthorizationEffectAssertionSpec,
    DataflowIdentityAssertionSpec,
    FinalClaimsAssertionSpec,
    ResourceDiffAssertionSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
_PERSISTENCE_FIXTURE_PATH = (
    _ROOT / "fixtures" / "core_novel" / "persistence" / "cases_12_17.json"
)

_CASE_IDS = (
    "manuscript_preview_only",
    "manuscript_patch_authorized_resume",
    "structure_create_update",
    "structure_delete_second_confirmation",
    "knowledge_create_update",
    "write_authorization_denied",
)

_EXPECTED_FINALS = {
    "manuscript_preview_only": (
        "正文补丁预览已生成。预览后第一章正文完全不变。"
    ),
    "manuscript_patch_authorized_resume": (
        "作者批准后应用了同一份补丁预览。"
        "第一章最终正文包含第四声钟鸣贴着海雾传来。"
    ),
    "structure_create_update": (
        "旧档案馆结构项使用创建返回的身份和版本完成重命名。"
        "其他结构项保持不变。"
    ),
    "structure_delete_second_confirmation": (
        "二次确认后只归档目标结构项。其他结构项保持不变。"
    ),
    "knowledge_create_update": (
        "旧档案馆地点卡使用创建返回的身份和修订值完成更新。"
        "最终地点卡保持确认态。"
    ),
    "write_authorization_denied": (
        "已按你的决定拒绝写入，本次没有修改正文。"
    ),
}


def _suite_payload() -> dict[str, object]:
    return json.loads(_SUITE_PATH.read_text(encoding="utf-8"))


def _cases() -> dict[str, dict[str, object]]:
    return {
        item["case_id"]: item
        for item in _suite_payload()["cases"][11:17]  # type: ignore[index]
    }


def _assertions(case: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["assertion_id"]: item
        for item in case["behavior_assertions"]  # type: ignore[index]
    }


def test_cases_12_17_declare_full_behavior_contracts() -> None:
    cases = _cases()

    assert set(_assertions(cases["manuscript_preview_only"])) == {
        "a12_artifact",
        "a12_claims",
        "a12_count_apply",
        "a12_count_preview",
        "a12_flow_preview_answer",
        "a12_manuscript_unchanged",
        "a12_source",
    }
    assert set(_assertions(cases["manuscript_patch_authorized_resume"])) == {
        "a13_artifact",
        "a13_auth",
        "a13_claims",
        "a13_count_apply",
        "a13_count_preview",
        "a13_flow_apply_answer",
        "a13_flow_preview_apply",
        "a13_human",
        "a13_manuscript_updated",
        "a13_source",
        "a13_topology_preview_apply",
    }
    assert set(_assertions(cases["structure_create_update"])) == {
        "a14_artifact",
        "a14_auth",
        "a14_claims",
        "a14_count_create",
        "a14_count_update",
        "a14_flow_create_update_id",
        "a14_flow_create_update_version",
        "a14_flow_update_answer",
        "a14_human",
        "a14_source",
        "a14_structure_target_only",
        "a14_topology_create_update",
    }
    assert set(_assertions(cases["structure_delete_second_confirmation"])) == {
        "a15_artifact",
        "a15_auth",
        "a15_claims",
        "a15_count_delete",
        "a15_human",
        "a15_source",
        "a15_structure_deleted",
    }
    assert set(_assertions(cases["knowledge_create_update"])) == {
        "a16_artifact",
        "a16_auth",
        "a16_claims",
        "a16_count_create",
        "a16_count_update",
        "a16_flow_create_update_id",
        "a16_flow_create_update_revision",
        "a16_flow_update_answer",
        "a16_human",
        "a16_knowledge_created",
        "a16_source",
        "a16_topology_create_update",
    }
    assert set(_assertions(cases["write_authorization_denied"])) == {
        "a17_artifact",
        "a17_auth",
        "a17_claims",
        "a17_count_apply",
        "a17_count_preview",
        "a17_human",
        "a17_manuscript_unchanged",
        "a17_source",
    }


def test_case_13_applies_every_field_from_the_confirmed_preview() -> None:
    case = _cases()["manuscript_patch_authorized_resume"]
    nodes = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    apply_node = nodes[1]

    assert apply_node["dependencies"] == ["authorized_preview_node"]
    assert apply_node["input_data"] == {}
    assert apply_node["input_bindings"] == [
        {
            "source_node_id": "authorized_preview_node",
            "source_path": "patch_id",
            "target_path": "patch_id",
        },
        {
            "source_node_id": "authorized_preview_node",
            "source_path": "chapter_id",
            "target_path": "chapter_id",
        },
        {
            "source_node_id": "authorized_preview_node",
            "source_path": "base_content_sha256",
            "target_path": "base_content_sha256",
        },
        {
            "source_node_id": "authorized_preview_node",
            "source_path": "expected_content_sha256",
            "target_path": "expected_content_sha256",
        },
        {
            "source_node_id": "authorized_preview_node",
            "source_path": "normalized_operations",
            "target_path": "operations",
        },
    ]


def test_cases_14_and_16_keep_dynamic_followup_placeholders_and_dataflow() -> None:
    cases = _cases()
    structure_plan = cases["structure_create_update"]["scripted_steps"][4][  # type: ignore[index]
        "response"
    ]["nodes"][0]
    knowledge_plan = cases["knowledge_create_update"]["scripted_steps"][4][  # type: ignore[index]
        "response"
    ]["nodes"][0]

    assert structure_plan["input_data"]["expected_structure_version"] == "f" * 64
    assert structure_plan["input_data"]["operations"][0]["target_id"] == (
        "fixture_created_structure_item_id"
    )
    assert knowledge_plan["input_data"]["card_id"] == (
        "fixture_created_knowledge_card_id"
    )
    assert knowledge_plan["input_data"]["expected_updated_at"] == (
        "fixture_created_knowledge_updated_at"
    )
    assert {
        item["identity_field"]
        for item in cases["structure_create_update"]["behavior_assertions"]  # type: ignore[index]
        if item["kind"] == "dataflow_identity"
        and item["consumer"] == "update_novel_structure"
    } == {"resource_id", "revision"}
    assert {
        item["identity_field"]
        for item in cases["knowledge_create_update"]["behavior_assertions"]  # type: ignore[index]
        if item["kind"] == "dataflow_identity"
        and item["consumer"] == "update_confirmed_knowledge"
    } == {"resource_id", "revision"}


def test_case_15_requires_confirmation_before_the_only_delete_call() -> None:
    case = _cases()["structure_delete_second_confirmation"]
    steps = case["scripted_steps"]  # type: ignore[index]

    assert [item["kind"] for item in steps] == ["model", "human", "tool", "model"]
    assert steps[1]["name"] == "write_authorization"
    assert steps[1]["matchers"] == [{"path": "/approved", "expected": True}]
    assert steps[2]["name"] == "delete_novel_structure_items"
    assert case["required_invocations"][0]["partial_order"] == (  # type: ignore[index]
        "after:write_authorization"
    )


def test_case_17_runs_preview_then_denied_authorization_without_apply() -> None:
    case = _cases()["write_authorization_denied"]
    plan_nodes = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    steps = case["scripted_steps"]  # type: ignore[index]

    assert [item["capability_name"] for item in plan_nodes] == [
        "preview_manuscript_patch",
        "apply_manuscript_patch",
    ]
    assert plan_nodes[1]["dependencies"] == ["denied_preview_node"]
    assert plan_nodes[1]["input_data"] == {}
    assert len(plan_nodes[1]["input_bindings"]) == 5
    assert [item["kind"] for item in steps] == ["model", "tool", "human"]
    assert steps[-1]["name"] == "write_authorization"
    assert steps[-1]["matchers"] == [{"path": "/approved", "expected": False}]
    assert {item["name"] for item in case["required_invocations"]} == {  # type: ignore[index]
        "preview_manuscript_patch"
    }


def test_cases_12_17_use_independent_persistence_truth_and_resources() -> None:
    fixture = json.loads(_PERSISTENCE_FIXTURE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = {item["asset_id"]: item for item in manifest["scenario_assets"]}

    assert fixture["schema"] == (
        "taichu.general_agent_benchmark.persistence_fixture@1"
    )
    assert set(fixture["cases"]) == set(_CASE_IDS)
    assert assets["resource_snapshot_manuscript_chapter_001"][
        "manifest_paths"
    ] == ["manuscripts/chapters/chapter_001.md"]
    assert assets["resource_snapshot_novel_structure"]["manifest_paths"] == [
        "persistence/cases_12_17.json"
    ]
    assert assets["resource_snapshot_confirmed_knowledge"]["manifest_paths"] == [
        "knowledge/confirmed_cards.json",
        "persistence/cases_12_17.json",
    ]
    assert all(
        "resource_snapshot_persistence_contracts"
        in case["scenario"]["fixture_refs"]  # type: ignore[index]
        for case in _cases().values()
    )


@pytest.fixture(scope="module")
def suite_catalog() -> tuple[AuthoredSuiteSpec, ClaimCatalog]:
    payload = _suite_payload()
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    referenced_claim_ids = tuple(
        dict.fromkeys(
            claim_id
            for case in suite.cases
            for assertion in case.behavior_assertions
            if isinstance(assertion, FinalClaimsAssertionSpec)
            for claim_id in (
                *assertion.required_claim_refs,
                *assertion.forbidden_claim_refs,
            )
        )
    )
    catalog = load_claim_catalog(
        _CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(
            item["asset_id"] for item in manifest["scenario_assets"]
        ),
        referenced_claim_ids=referenced_claim_ids,
    )
    return suite, catalog


def _owner(suite: AuthoredSuiteSpec, case: AuthoredCaseSpec) -> EvidenceOwner:
    return EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id=f"benchmark_case_{case.case_id.encode().hex()[:32]:0<32}",
        run_id=f"general_run_20260730_{case.case_id}",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )


def _required_records(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
) -> list[EvidenceRecord]:
    records = []
    for requirement in case.required_evidence:
        payload = {"evidence_id": requirement.evidence_id, "observed": True}
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
    return records


def _effect_records(
    owner: EvidenceOwner,
    count: int,
) -> list[EvidenceRecord]:
    records = []
    for index in range(count):
        payload = {"effect_index": index, "status": "succeeded"}
        records.append(
            EvidenceRecord(
                ref=EvidenceRef(
                    evidence_id=f"effect_{index}",
                    kind=EvidenceKind.EFFECT,
                    selector=EvidenceSelector.OUTCOME,
                    owner=owner,
                    record_id=f"effect_record_{index}",
                    content_sha256=canonical_sha256(payload),
                ),
                payload=payload,
            )
        )
    return records


def _observation(
    suite: AuthoredSuiteSpec,
    case: AuthoredCaseSpec,
    *,
    final_text: str | None = None,
    invocations: tuple[ObservedInvocation, ...] = (),
    artifacts: tuple[ObservedArtifact, ...] = (),
    resource_snapshots: tuple[ObservedResourceSnapshot, ...] = (),
    effect_count: int = 0,
) -> object:
    owner = _owner(suite, case)
    records = [
        *_required_records(case, owner),
        *_effect_records(owner, effect_count),
    ]
    text = final_text or _EXPECTED_FINALS[case.case_id]
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=case.user_request_raw,
        plan={"case_id": case.case_id},
        nodes=(),
        invocations=invocations,
        final_answer=ObservedFinalAnswer.create(
            text=text,
            source_refs=tuple(
                dict.fromkeys(
                    ref for invocation in invocations for ref in invocation.source_refs
                )
            ),
        ),
        artifacts=artifacts,
        resource_snapshots=resource_snapshots,
        recovery_decisions=(),
        terminal=ObservedTerminalState(
            run_status=case.expected_terminal.run_status,
            stop_reason=case.expected_terminal.reason_code,
            resumable=case.expected_terminal.resumable,
            pending_human_kind=case.expected_terminal.pending_human_kind,
        ),
        budget=ObservedBudgetUsage(
            node_executions=0,
            capability_calls=len(invocations),
            model_calls=1,
            total_tokens=128,
            runtime_ms=20,
            context_tokens=64,
        ),
        script_protocol_deviations=(),
        evidence_records=tuple(records),
    )


def _invocation(name: str) -> ObservedInvocation:
    return ObservedInvocation(
        call_id=f"call_{name}",
        parent_call_id=None,
        node_id=f"node_{name}",
        capability_kind="tool",
        capability_name=name,
        status="completed",
        input_sha256=canonical_sha256({"input": name}),
        output_sha256=canonical_sha256({"output": name}),
        source_refs=(f"source:{name}",),
    )


def _resource_pair(
    snapshot_ref: str,
    *,
    changed: bool,
) -> tuple[ObservedResourceSnapshot, ObservedResourceSnapshot]:
    before_payload = {"snapshot_ref": snapshot_ref, "state": "before"}
    after_payload = (
        {"snapshot_ref": snapshot_ref, "state": "after"}
        if changed
        else before_payload
    )
    return (
        ObservedResourceSnapshot(
            snapshot_ref=snapshot_ref,
            phase="before",
            content_sha256=canonical_sha256(before_payload),
            payload=before_payload,
        ),
        ObservedResourceSnapshot(
            snapshot_ref=snapshot_ref,
            phase="after",
            content_sha256=canonical_sha256(after_payload),
            payload=after_payload,
        ),
    )


@pytest.mark.parametrize("case_offset", (11, 12, 13, 14, 15, 16))
def test_cases_12_17_wrong_known_answer_fails_claim_oracle(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, FinalClaimsAssertionSpec)
    )
    oracle = TypedOracle(catalog=catalog)

    correct = oracle.evaluate(assertion, _observation(suite, case))
    wrong = oracle.evaluate(
        assertion,
        _observation(
            suite,
            case,
            final_text="归潮灯亮起微光后照出墙后暗门。",
        ),
    )

    assert correct.status is AssertionStatus.PASSED
    assert wrong.status is AssertionStatus.FAILED


@pytest.mark.parametrize(
    ("case_offset", "assertion_id", "producer", "consumer", "identity"),
    (
        (
            12,
            "a13_flow_preview_apply",
            "preview_manuscript_patch",
            "apply_manuscript_patch",
            "preview_sha256",
        ),
        (
            13,
            "a14_flow_create_update_id",
            "create_novel_structure_items",
            "update_novel_structure",
            "resource_id",
        ),
        (
            13,
            "a14_flow_create_update_version",
            "create_novel_structure_items",
            "update_novel_structure",
            "revision",
        ),
        (
            15,
            "a16_flow_create_update_id",
            "create_confirmed_knowledge",
            "update_confirmed_knowledge",
            "resource_id",
        ),
        (
            15,
            "a16_flow_create_update_revision",
            "create_confirmed_knowledge",
            "update_confirmed_knowledge",
            "revision",
        ),
    ),
)
def test_successful_writes_without_causal_consumption_are_invalid(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
    assertion_id: str,
    producer: str,
    consumer: str,
    identity: str,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, DataflowIdentityAssertionSpec)
        and item.assertion_id == assertion_id
    )
    invocations = (_invocation(producer), _invocation(consumer))
    observation = _observation(suite, case, invocations=invocations)
    consumed = AssertionEvaluationContext(
        dataflow_identities=(
            DataflowIdentityObservation(
                producer=producer,
                consumer=consumer,
                identity_field=identity,
                producer_identity=f"identity:{assertion_id}",
                consumer_identity=f"identity:{assertion_id}",
            ),
        )
    )
    oracle = TypedOracle(catalog=catalog)

    assert (
        oracle.evaluate(assertion, observation, context=consumed).status
        is AssertionStatus.PASSED
    )
    assert (
        oracle.evaluate(
            assertion,
            observation,
            context=AssertionEvaluationContext(),
        ).status
        is AssertionStatus.INVALID
    )


@pytest.mark.parametrize(
    ("case_offset", "changed"),
    (
        (11, False),
        (12, True),
        (13, True),
        (14, True),
        (15, True),
        (16, False),
    ),
)
def test_resource_contracts_require_real_before_after_diffs(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
    changed: bool,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, ResourceDiffAssertionSpec)
    )
    snapshots = _resource_pair(assertion.resource_snapshot_ref, changed=changed)
    actual_change = assertion.expected_change
    positive_diff = ResourceDiffObservation(
        resource_snapshot_ref=assertion.resource_snapshot_ref,
        actual_change=actual_change,
        before_sha256=snapshots[0].content_sha256,
        after_sha256=snapshots[1].content_sha256,
        target_refs=("target",) if changed else (),
        changed_refs=("target",) if changed else (),
        protected_refs=("protected",),
        protected_changed_refs=(),
    )
    positive = _observation(
        suite,
        case,
        resource_snapshots=snapshots,
    )
    oracle = TypedOracle(catalog=catalog)

    assert (
        oracle.evaluate(
            assertion,
            positive,
            context=AssertionEvaluationContext(resource_diffs=(positive_diff,)),
        ).status
        is AssertionStatus.PASSED
    )

    wrong_snapshots = _resource_pair(
        assertion.resource_snapshot_ref,
        changed=not changed,
    )
    wrong_change = "updated" if not changed else "unchanged"
    wrong_diff = ResourceDiffObservation(
        resource_snapshot_ref=assertion.resource_snapshot_ref,
        actual_change=wrong_change,
        before_sha256=wrong_snapshots[0].content_sha256,
        after_sha256=wrong_snapshots[1].content_sha256,
        changed_refs=("target",) if not changed else (),
        protected_changed_refs=(),
    )
    wrong = _observation(
        suite,
        case,
        resource_snapshots=wrong_snapshots,
    )
    assert (
        oracle.evaluate(
            assertion,
            wrong,
            context=AssertionEvaluationContext(resource_diffs=(wrong_diff,)),
        ).status
        is AssertionStatus.FAILED
    )


@pytest.mark.parametrize(
    ("case_offset", "decision", "expected_effect_count"),
    (
        (12, "approved", 1),
        (13, "approved", 2),
        (14, "confirmed", 1),
        (15, "approved", 2),
        (16, "denied", 0),
    ),
)
def test_authorization_effects_reject_wrong_effect_counts(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
    decision: str,
    expected_effect_count: int,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, AuthorizationEffectAssertionSpec)
    )
    positive = _observation(
        suite,
        case,
        effect_count=expected_effect_count,
    )
    positive_context = AssertionEvaluationContext(
        authorizations=(
            AuthorizationEffectObservation(
                decision_ref=assertion.decision_ref,
                decision=decision,  # type: ignore[arg-type]
                effect_count=expected_effect_count,
                requested_target_ref="target",
                effected_target_refs=(
                    ("target",) if expected_effect_count else ()
                ),
            ),
        )
    )
    wrong_count = 1 if expected_effect_count == 0 else 0
    wrong = _observation(suite, case, effect_count=wrong_count)
    wrong_context = AssertionEvaluationContext(
        authorizations=(
            AuthorizationEffectObservation(
                decision_ref=assertion.decision_ref,
                decision=decision,  # type: ignore[arg-type]
                effect_count=wrong_count,
                requested_target_ref="target",
                effected_target_refs=(("target",) if wrong_count else ()),
            ),
        )
    )
    oracle = TypedOracle(catalog=catalog)

    assert (
        oracle.evaluate(assertion, positive, context=positive_context).status
        is AssertionStatus.PASSED
    )
    assert (
        oracle.evaluate(assertion, wrong, context=wrong_context).status
        is AssertionStatus.FAILED
    )


@pytest.mark.parametrize("case_offset", (12, 13, 14, 15, 16))
def test_human_boundary_requires_a_persisted_intervention_artifact(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, ArtifactContractAssertionSpec)
        and item.artifact_kind == "human_intervention"
    )
    payload = {"decision": "observed", "case_id": case.case_id}
    artifact = ObservedArtifact(
        artifact_id=f"human_{case.case_id}",
        artifact_kind="human_intervention",
        producer_node_id=None,
        content_sha256=canonical_sha256(payload),
        payload=payload,
    )
    oracle = TypedOracle(catalog=catalog)

    assert (
        oracle.evaluate(
            assertion,
            _observation(suite, case, artifacts=(artifact,)),
        ).status
        is AssertionStatus.PASSED
    )
    assert (
        oracle.evaluate(assertion, _observation(suite, case)).status
        is AssertionStatus.FAILED
    )
