"""第 1—6 条最小路由、检索占坑与外研行为合同。"""

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
from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedInvocation,
    ObservedNode,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionStatus,
    DataflowIdentityObservation,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    CallCountAssertionSpec,
    CallTopologyAssertionSpec,
    DataflowIdentityAssertionSpec,
    FinalClaimsAssertionSpec,
    AuthoredSuiteSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"


def _suite_payload() -> dict[str, object]:
    return json.loads(_SUITE_PATH.read_text(encoding="utf-8"))


def _case_payloads() -> dict[str, dict[str, object]]:
    return {
        item["case_id"]: item
        for item in _suite_payload()["cases"][:6]  # type: ignore[index]
    }


def _assertions(case: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["assertion_id"]: item
        for item in case["behavior_assertions"]  # type: ignore[index]
    }


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
        known_fixture_refs=(item["asset_id"] for item in manifest["scenario_assets"]),
        referenced_claim_ids=referenced_claim_ids,
    )
    return suite, catalog


def _owner(
    suite: AuthoredSuiteSpec,
    case: AuthoredCaseSpec,
) -> EvidenceOwner:
    return EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id=f"benchmark_case_{case.case_id.encode().hex()[:32]:0<32}",
        run_id=f"general_run_20260730_{case.case_id}",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )


def _records(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
) -> tuple[EvidenceRecord, ...]:
    records = []
    for requirement in case.required_evidence:
        payload = {
            "evidence_id": requirement.evidence_id,
            "observed": True,
        }
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
    suite: AuthoredSuiteSpec,
    case: AuthoredCaseSpec,
    *,
    final_text: str,
    final_source_refs: tuple[str, ...] = (),
    nodes: tuple[ObservedNode, ...] = (),
    invocations: tuple[ObservedInvocation, ...] = (),
) -> CaseObservation:
    owner = _owner(suite, case)
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=case.user_request_raw,
        plan={"nodes": [item.node_id for item in nodes]},
        nodes=nodes,
        invocations=invocations,
        final_answer=ObservedFinalAnswer.create(
            text=final_text,
            source_refs=final_source_refs,
        ),
        artifacts=(),
        resource_snapshots=(),
        recovery_decisions=(),
        terminal=ObservedTerminalState(
            run_status="completed",
            stop_reason="goal_satisfied",
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
        evidence_records=_records(case, owner),
    )


def _script_final_answer(case: AuthoredCaseSpec) -> str:
    for step in reversed(case.scripted_steps):
        response = step.response or {}
        final_answer = response.get("final_answer")
        if isinstance(final_answer, str):
            return final_answer
        direct_response = response.get("direct_response")
        if isinstance(direct_response, str):
            return direct_response
    raise AssertionError(f"{case.case_id} 缺少最终回答。")


def test_cases_1_6_declare_behavior_not_only_artifact_presence() -> None:
    cases = _case_payloads()

    assert set(_assertions(cases["direct_answer_current_request"])) == {
        "a1_answer_claim",
        "a1_artifact",
        "a1_zero",
    }
    assert set(_assertions(cases["single_manuscript_search"])) == {
        "a2_artifact",
        "a2_claims",
        "a2_count_search",
        "a2_flow_search_answer",
        "a2_source",
    }
    assert set(_assertions(cases["structure_coverage_read"])) == {
        "a3_artifact",
        "a3_claims",
        "a3_count_coverage",
        "a3_count_manuscript",
        "a3_count_structure",
        "a3_flow_coverage_answer",
        "a3_flow_manuscript_answer",
        "a3_flow_structure_answer",
        "a3_source",
        "a3_topology_coverage_read",
        "a3_topology_structure_read",
    }
    assert set(_assertions(cases["single_knowledge_retrieval"])) == {
        "a4_artifact",
        "a4_claims",
        "a4_count_retrieval",
        "a4_flow_retrieval_answer",
        "a4_source",
    }
    assert set(_assertions(cases["knowledge_catalog_identity_read"])) == {
        "a5_artifact",
        "a5_claims",
        "a5_count_catalog",
        "a5_count_read",
        "a5_count_resolve",
        "a5_flow_catalog_resolve",
        "a5_flow_read_answer",
        "a5_flow_resolve_read",
        "a5_source",
        "a5_topology_catalog_resolve",
        "a5_topology_resolve_read",
    }
    assert set(_assertions(cases["external_research_grounded"])) == {
        "a6_artifact",
        "a6_claims",
        "a6_count_read",
        "a6_count_research",
        "a6_count_search",
        "a6_flow_read_research",
        "a6_flow_research_answer",
        "a6_flow_search_read",
        "a6_source",
        "a6_topology_search_read",
    }


def test_cases_2_6_keep_rag_placeholder_without_freezing_retrieval_implementation() -> (
    None
):
    cases = tuple(_case_payloads().values())

    assert cases[0]["scenario"]["rag_placeholder"] is False  # type: ignore[index]
    assert all(
        case["scenario"]["rag_placeholder"] is True  # type: ignore[index]
        for case in cases[1:]
    )
    serialized = json.dumps(cases, ensure_ascii=False)
    for implementation_detail in (
        "向量模型",
        "向量数据库",
        "Graph RAG",
        "Agentic RAG",
        "MongoDB",
    ):
        assert implementation_detail not in serialized


def test_case_5_plan_binds_catalog_identity_into_the_actual_card_read() -> None:
    case = _case_payloads()["knowledge_catalog_identity_read"]
    plan = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    nodes = {item["node_id"]: item for item in plan}

    assert nodes["resolve_lamp"]["input_bindings"] == [
        {
            "source_node_id": "list_catalog",
            "source_path": "items.0.knowledge_type",
            "target_path": "knowledge_type",
        },
        {
            "source_node_id": "list_catalog",
            "source_path": "items.0.name",
            "target_path": "name",
        },
    ]
    assert nodes["read_lamp_card"]["input_data"] == {"card_ids": []}
    assert nodes["read_lamp_card"]["input_bindings"] == [
        {
            "source_node_id": "resolve_lamp",
            "source_path": "matches.0.card_id",
            "target_path": "card_ids.0",
        }
    ]


def test_case_2_search_is_scoped_to_the_requested_stable_chapter_id() -> None:
    case = _case_payloads()["single_manuscript_search"]
    plan = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]

    assert plan == [
        {
            "node_id": "search_fixture",
            "kind": "tool",
            "capability_name": "retrieve_story_context",
            "objective": "检索归潮灯描写。",
            "input_data": {
                "query": "归潮灯 chapter_001",
            },
        }
    ]


def test_cases_1_6_claims_are_independent_catalog_truth() -> None:
    suite_payload = _suite_payload()
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=suite_payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    referenced_claim_ids = tuple(
        dict.fromkeys(
            claim_id
            for case in suite.cases[:6]
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
        known_fixture_refs=(item["asset_id"] for item in manifest["scenario_assets"]),
        referenced_claim_ids=referenced_claim_ids,
    )

    assert {
        "conflict_opposing_goals_first",
        "external_fixture_not_real_world",
        "external_lighthouse_memory_temporarily_stored",
        "knowledge_tide_lamp_item_confirmed",
        "manuscript_three_bells_across_chapters",
        "manuscript_tide_lamp_reveals_hidden_door",
    } <= {item.claim_id for item in catalog.claims}
    assert all(
        "response" not in claim.model_dump(mode="json")
        and "scripted_response" not in claim.model_dump(mode="json")
        for claim in catalog.claims
    )


def test_cases_2_6_dataflow_uses_only_typed_oracle_identity_fields() -> None:
    payload = _suite_payload()
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    allowed_fields = {
        "content_sha256",
        "output_sha256",
        "input_sha256",
        "source_ref",
        "artifact_ref",
        "result_id",
        "preview_sha256",
        "resource_id",
        "revision",
        "claim_id",
    }

    flows = [
        assertion
        for case in suite.cases[1:6]
        for assertion in case.behavior_assertions
        if isinstance(assertion, DataflowIdentityAssertionSpec)
    ]
    assert flows
    assert {item.identity_field for item in flows} <= allowed_fields


@pytest.mark.parametrize(
    ("case_id", "wrong_known_claim"),
    (
        (
            "direct_answer_current_request",
            "归潮灯记忆规则处于确认态。",
        ),
        (
            "single_manuscript_search",
            "第一章和第二章都出现三声钟鸣。",
        ),
        (
            "structure_coverage_read",
            "归潮灯亮起微光后照出墙后暗门。",
        ),
        (
            "single_knowledge_retrieval",
            "归潮灯亮起微光后照出墙后暗门。",
        ),
        (
            "knowledge_catalog_identity_read",
            "归潮灯记忆规则处于确认态。",
        ),
        (
            "external_research_grounded",
            "合成外部资料称灯塔记忆会暂存在与潮汐相连的封闭空间。",
        ),
    ),
)
def test_cases_1_6_wrong_answer_cannot_pass_from_script_protocol(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_id: str,
    wrong_known_claim: str,
) -> None:
    suite, catalog = suite_catalog
    case = next(item for item in suite.cases if item.case_id == case_id)
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, FinalClaimsAssertionSpec)
    )
    oracle = TypedOracle(catalog=catalog)

    correct = oracle.evaluate(
        assertion,
        _observation(
            suite,
            case,
            final_text=_script_final_answer(case),
        ),
    )
    wrong = oracle.evaluate(
        assertion,
        _observation(suite, case, final_text=wrong_known_claim),
    )

    assert correct.status is AssertionStatus.PASSED
    assert wrong.status is AssertionStatus.FAILED


def test_case_2_unconsumed_or_out_of_scope_hit_cannot_pass(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[1]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, DataflowIdentityAssertionSpec)
    )
    output_sha256 = canonical_sha256(
        {
            "chapter_id": "chapter_001",
            "excerpt": "归潮灯亮起微光，照出墙后暗门",
        }
    )
    invocation = ObservedInvocation(
        call_id="call_search_chapter_001",
        parent_call_id=None,
        node_id="search_fixture",
        capability_kind="tool",
        capability_name="search_manuscript",
        status="completed",
        input_sha256=canonical_sha256(
            {"query": "归潮灯", "chapter_ids": ["chapter_001"]}
        ),
        output_sha256=output_sha256,
        source_refs=("manuscript:chapter_001:0-100",),
        artifact_refs=(),
    )
    observation = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        final_source_refs=("manuscript:chapter_001:0-100",),
        invocations=(invocation,),
    )
    oracle = TypedOracle(catalog=catalog)
    consumed = AssertionEvaluationContext(
        dataflow_identities=(
            DataflowIdentityObservation(
                producer="search_manuscript",
                consumer="final_answer",
                identity_field="output_sha256",
                producer_identity=output_sha256,
                consumer_identity=output_sha256,
                source_refs=("manuscript:chapter_001:0-100",),
            ),
        )
    )

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

    wrong_scope = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        final_source_refs=("manuscript:chapter_002:0-100",),
        invocations=(invocation,),
    )
    assert (
        oracle.evaluate(assertion, wrong_scope, context=consumed).status
        is AssertionStatus.INVALID
    )


def test_case_5_identity_mismatch_and_missing_read_are_detected(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[4]
    catalog_node = ObservedNode(
        node_id="list_catalog",
        plan_revision=1,
        capability_kind="tool",
        capability_name="list_knowledge_catalog",
        status="completed",
        dependencies=(),
    )
    resolve_node = ObservedNode(
        node_id="resolve_lamp",
        plan_revision=1,
        capability_kind="tool",
        capability_name="resolve_knowledge_identity",
        status="completed",
        dependencies=("list_catalog",),
    )
    read_node = ObservedNode(
        node_id="read_lamp_card",
        plan_revision=1,
        capability_kind="tool",
        capability_name="read_knowledge_cards",
        status="completed",
        dependencies=("resolve_lamp",),
    )
    invocations = tuple(
        ObservedInvocation(
            call_id=f"call_{name}",
            parent_call_id=None,
            node_id=node_id,
            capability_kind="tool",
            capability_name=name,
            status="completed",
            input_sha256=canonical_sha256({"name": name}),
            output_sha256=canonical_sha256({"name": name, "completed": True}),
            source_refs=("knowledge:fixture_item_tide_lamp",),
            artifact_refs=(),
        )
        for name, node_id in (
            ("list_knowledge_catalog", "list_catalog"),
            ("resolve_knowledge_identity", "resolve_lamp"),
            ("read_knowledge_cards", "read_lamp_card"),
        )
    )
    observation = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        final_source_refs=("knowledge:fixture_item_tide_lamp",),
        nodes=(catalog_node, resolve_node, read_node),
        invocations=invocations,
    )
    oracle = TypedOracle(catalog=catalog)

    count_assertions = tuple(
        item
        for item in case.behavior_assertions
        if isinstance(item, CallCountAssertionSpec)
    )
    topology_assertions = tuple(
        item
        for item in case.behavior_assertions
        if isinstance(item, CallTopologyAssertionSpec)
    )
    assert all(
        oracle.evaluate(item, observation).status is AssertionStatus.PASSED
        for item in (*count_assertions, *topology_assertions)
    )

    resolve_read = next(
        item
        for item in case.behavior_assertions
        if item.assertion_id == "a5_flow_resolve_read"
    )
    mismatch = AssertionEvaluationContext(
        dataflow_identities=(
            DataflowIdentityObservation(
                producer="resolve_knowledge_identity",
                consumer="read_knowledge_cards",
                identity_field="resource_id",
                producer_identity="fixture_item_tide_lamp",
                consumer_identity="fixture_rule_tide_lamp",
                source_refs=("knowledge:fixture_item_tide_lamp",),
            ),
        )
    )
    assert (
        oracle.evaluate(resolve_read, observation, context=mismatch).status
        is AssertionStatus.FAILED
    )

    missing_read = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        final_source_refs=("knowledge:fixture_item_tide_lamp",),
        nodes=(catalog_node, resolve_node),
        invocations=invocations[:2],
    )
    read_count = next(
        item
        for item in count_assertions
        if item.capability_name == "read_knowledge_cards"
    )
    assert oracle.evaluate(read_count, missing_read).status is AssertionStatus.FAILED
