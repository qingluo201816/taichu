"""第 7—11 条证据、多分支、流水线、审查与修订行为合同。"""

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
    AuthoredSuiteSpec,
    CallTopologyAssertionSpec,
    DataflowIdentityAssertionSpec,
    FinalClaimsAssertionSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
_COLLABORATION_FIXTURE_PATH = (
    _ROOT / "fixtures" / "core_novel" / "collaboration" / "cases_7_11.json"
)


def _suite_payload() -> dict[str, object]:
    return json.loads(_SUITE_PATH.read_text(encoding="utf-8"))


def _cases() -> dict[str, dict[str, object]]:
    return {
        item["case_id"]: item
        for item in _suite_payload()["cases"][6:11]  # type: ignore[index]
    }


def _assertions(case: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["assertion_id"]: item
        for item in case["behavior_assertions"]  # type: ignore[index]
    }


def test_cases_7_11_declare_full_behavior_contracts() -> None:
    cases = _cases()

    assert set(_assertions(cases["single_canon_evidence"])) == {
        "a7_artifact",
        "a7_claims",
        "a7_count_evidence",
        "a7_count_read",
        "a7_evidence_artifact",
        "a7_flow_evidence_answer",
        "a7_flow_source_evidence",
        "a7_source",
    }
    assert set(_assertions(cases["summary_world_character"])) == {
        "a8_artifact",
        "a8_claims",
        "a8_count_character",
        "a8_count_summary",
        "a8_count_world",
        "a8_evidence_artifact",
        "a8_flow_character_answer",
        "a8_flow_summary_character",
        "a8_flow_summary_world",
        "a8_flow_world_answer",
        "a8_source",
        "a8_topology_branches",
        "a8_topology_summary_character",
        "a8_topology_summary_world",
    }
    assert set(_assertions(cases["architecture_scene_draft"])) == {
        "a9_artifact",
        "a9_candidate_artifacts",
        "a9_claims",
        "a9_count_architecture",
        "a9_count_draft",
        "a9_count_scene",
        "a9_flow_architecture_scene",
        "a9_flow_draft_answer",
        "a9_flow_scene_draft",
        "a9_manuscript_unchanged",
        "a9_topology_architecture_scene",
        "a9_topology_scene_draft",
    }
    assert set(_assertions(cases["parallel_review_triad"])) == {
        "a10_artifact",
        "a10_claims",
        "a10_count_consistency",
        "a10_count_narrative",
        "a10_count_style",
        "a10_flow_consistency_answer",
        "a10_flow_narrative_answer",
        "a10_flow_style_answer",
        "a10_review_artifacts",
        "a10_topology_consistency_narrative",
        "a10_topology_consistency_style",
        "a10_topology_narrative_style",
    }
    assert set(_assertions(cases["revision_from_reviews"])) == {
        "a11_artifact",
        "a11_claims",
        "a11_count_revision",
        "a11_flow_revision_answer",
        "a11_manuscript_unchanged",
        "a11_revision_artifact",
        "a11_source",
    }


def test_case_7_reads_real_manuscript_before_evidence_generation() -> None:
    case = _cases()["single_canon_evidence"]
    required = {
        item["name"]: item
        for item in case["required_invocations"]  # type: ignore[index]
    }
    plan = case["scripted_steps"][0]["response"]["nodes"][0]  # type: ignore[index]

    assert required["read_manuscript"]["parent"] == "subagent:canon_evidence"
    assert required["read_manuscript"]["min_calls"] == 1
    assert required["read_manuscript"]["max_calls"] == 1
    assert plan["input_data"]["source_request"] == {
        "auto_collect": False,
        "chapter_ids": ["chapter_001", "chapter_002"],
    }


def test_case_8_uses_one_summary_as_two_independent_branch_inputs() -> None:
    case = _cases()["summary_world_character"]
    plan = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    nodes = {item["node_id"]: item for item in plan}

    assert nodes["analyze_world"]["dependencies"] == ["summarize_fixture"]
    assert nodes["analyze_character"]["dependencies"] == ["summarize_fixture"]
    assert nodes["analyze_world"]["input_bindings"] == [
        {
            "source_node_id": "summarize_fixture",
            "source_path": "summary",
            "target_path": "source_request.direct_context",
        }
    ]
    assert nodes["analyze_character"]["input_bindings"] == [
        {
            "source_node_id": "summarize_fixture",
            "source_path": "summary",
            "target_path": "source_request.direct_context",
        }
    ]
    branch_assertion = _assertions(case)["a8_topology_branches"]
    assert branch_assertion["relation"] == "independent"


def test_case_9_binds_architecture_to_scene_and_scene_to_draft() -> None:
    case = _cases()["architecture_scene_draft"]
    plan = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    nodes = {item["node_id"]: item for item in plan}

    assert nodes["scene_fixture"]["input_bindings"] == [
        {
            "source_node_id": "architecture_fixture",
            "source_path": "overview",
            "target_path": "source_request.direct_context",
        },
        {
            "source_node_id": "architecture_fixture",
            "source_path": "stage_goals",
            "target_path": "hard_constraints",
        },
    ]
    assert nodes["draft_fixture"]["input_bindings"] == [
        {
            "source_node_id": "scene_fixture",
            "source_path": "overview",
            "target_path": "source_request.direct_context",
        }
    ]


def test_case_10_requires_same_candidate_and_never_claims_physical_parallelism() -> (
    None
):
    case = _cases()["parallel_review_triad"]
    plan = case["scripted_steps"][0]["response"]["nodes"]  # type: ignore[index]
    texts = {item["input_data"]["text"] for item in plan}
    topology = tuple(
        item
        for item in case["behavior_assertions"]  # type: ignore[index]
        if item["kind"] == "call_topology"
    )

    assert texts == {"守档人挡住苏砚翻向缺页的手。"}
    assert topology
    assert {item["relation"] for item in topology} == {"independent"}
    assert "物理并发" not in json.dumps(case, ensure_ascii=False)


def test_case_11_keeps_three_review_refs_and_protected_non_target_text() -> None:
    case = _cases()["revision_from_reviews"]
    node = case["scripted_steps"][0]["response"]["nodes"][0]  # type: ignore[index]
    response = case["scripted_steps"][1]["response"]  # type: ignore[index]

    assert node["input_data"]["source_request"]["upstream_artifact_refs"] == [
        "artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "artifact_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "artifact_cccccccccccccccccccccccccccccccc",
    ]
    assert "窗外三声钟鸣仍与原稿一致。" in node["input_data"]["text"]
    assert "窗外三声钟鸣仍与原稿一致。" in response["text"]


def test_cases_7_11_use_independent_sealed_collaboration_truth() -> None:
    fixture = json.loads(_COLLABORATION_FIXTURE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = {item["asset_id"]: item for item in manifest["scenario_assets"]}

    assert fixture["schema"] == (
        "taichu.general_agent_benchmark.collaboration_fixture@1"
    )
    assert set(fixture["cases"]) == set(_cases())
    assert assets["resource_snapshot_collaboration_contracts"]["manifest_paths"] == [
        "collaboration/cases_7_11.json"
    ]
    assert all(
        "resource_snapshot_collaboration_contracts" in case["scenario"]["fixture_refs"]  # type: ignore[index]
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
            source_refs=tuple(
                dict.fromkeys(
                    ref for invocation in invocations for ref in invocation.source_refs
                )
            ),
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
    raise AssertionError(f"{case.case_id} 缺少最终回答。")


@pytest.mark.parametrize(
    "case_offset",
    (6, 7, 8, 9, 10),
)
def test_cases_7_11_wrong_known_answer_fails_typed_claim_oracle(
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
        _observation(
            suite,
            case,
            final_text="归潮灯亮起微光后照出墙后暗门。",
        ),
    )

    assert correct.status is AssertionStatus.PASSED
    assert wrong.status is AssertionStatus.FAILED


@pytest.mark.parametrize(
    ("case_offset", "producer", "consumer"),
    (
        (6, "canon_evidence", "final_answer"),
        (7, "worldbuilding", "final_answer"),
        (8, "drafting", "final_answer"),
        (9, "consistency_reviewer", "final_answer"),
        (10, "revision", "final_answer"),
    ),
)
def test_successful_call_without_output_consumption_is_invalid(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
    case_offset: int,
    producer: str,
    consumer: str,
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[case_offset]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, DataflowIdentityAssertionSpec)
        and item.producer == producer
        and item.consumer == consumer
    )
    output_sha256 = canonical_sha256({"capability": producer, "case": case.case_id})
    invocation = ObservedInvocation(
        call_id=f"call_{producer}",
        parent_call_id=None,
        node_id=f"node_{producer}",
        capability_kind="subagent",
        capability_name=producer,
        status="completed",
        input_sha256=canonical_sha256({"case": case.case_id}),
        output_sha256=output_sha256,
        source_refs=(f"artifact:{case.case_id}",),
        artifact_refs=(f"artifact_{case.case_id}",),
    )
    observation = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        invocations=(invocation,),
    )
    consumed = AssertionEvaluationContext(
        dataflow_identities=(
            DataflowIdentityObservation(
                producer=producer,
                consumer=consumer,
                identity_field="output_sha256",
                producer_identity=output_sha256,
                consumer_identity=output_sha256,
                source_refs=(f"artifact:{case.case_id}",),
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


def test_case_8_branch_topology_rejects_hidden_serial_dependency(
    suite_catalog: tuple[AuthoredSuiteSpec, ClaimCatalog],
) -> None:
    suite, catalog = suite_catalog
    case = suite.cases[7]
    assertion = next(
        item
        for item in case.behavior_assertions
        if isinstance(item, CallTopologyAssertionSpec)
        and item.assertion_id == "a8_topology_branches"
    )
    summary = ObservedNode(
        node_id="summarize_fixture",
        plan_revision=1,
        capability_kind="subagent",
        capability_name="narrative_summary",
        status="completed",
        dependencies=(),
    )
    world = ObservedNode(
        node_id="analyze_world",
        plan_revision=1,
        capability_kind="subagent",
        capability_name="worldbuilding",
        status="completed",
        dependencies=("summarize_fixture",),
    )
    independent_character = ObservedNode(
        node_id="analyze_character",
        plan_revision=1,
        capability_kind="subagent",
        capability_name="character",
        status="completed",
        dependencies=("summarize_fixture",),
    )
    serial_character = independent_character.model_copy(
        update={"dependencies": ("analyze_world",)}
    )
    oracle = TypedOracle(catalog=catalog)

    independent = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        nodes=(summary, world, independent_character),
    )
    serial = _observation(
        suite,
        case,
        final_text=_script_final_answer(case),
        nodes=(summary, world, serial_character),
    )

    assert oracle.evaluate(assertion, independent).status is AssertionStatus.PASSED
    assert oracle.evaluate(assertion, serial).status is AssertionStatus.FAILED
