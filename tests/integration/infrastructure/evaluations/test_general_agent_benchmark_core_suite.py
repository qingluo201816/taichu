"""需求 1.1、2.1、11.2：37 个权威案例、密封夹具与真实能力路径。"""

from __future__ import annotations

import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    CORE_SUBAGENT_NAMES,
    CORE_TOOL_NAMES,
    derive_capability_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_authored_suite,
    load_fixture_manifest,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeCard
from taichu.application.general_agent.models import (
    GeneralAgentPlanDraft,
    GeneralAgentVerification,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")


def test_core_suite_has_all_case_scripts_and_sealed_fixture_partitions() -> None:
    suite_path = _ROOT / "suite.json"
    assert suite_path.is_file()
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert len(cases) == 37
    assert [case["case_id"] for case in cases] == payload["case_order"]
    assert len(payload["case_order"]) == len(set(payload["case_order"]))
    assert [
        case["case_id"] for case in cases if not case["scripted_steps"]
    ] == ["context_unsafe_compression_refusal"]
    assert all(case["user_request"] == case["user_request_raw"] for case in cases)
    fixture = _ROOT / "fixtures" / "core_novel"
    required = {
        "fixture-manifest.json",
        "manuscripts/chapters/chapter_001.md",
        "manuscripts/chapters/chapter_002.md",
        "knowledge/confirmed_cards.json",
        "conversation/seed.json",
        "runtime_memory/seed.json",
        "external_sources/manifest.json",
    }
    assert required <= {
        path.relative_to(fixture).as_posix()
        for path in fixture.rglob("*")
        if path.is_file()
    }


def test_every_invocation_expectation_is_declared_by_its_primary_case() -> None:
    catalog_snapshot = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        _ROOT / "suite.json",
        expected_capability_catalog_hash=catalog_snapshot.canonical_hash,
    )
    catalog = derive_capability_catalog(suite, catalog_snapshot)
    declared = {
        (
            case.case_id,
            item.type,
            item.name,
            item.min_calls,
            item.max_calls,
            item.expected_outcome,
        )
        for case in suite.cases
        for item in case.required_invocations
    }
    derived = {
        (
            item.case_id,
            item.kind,
            item.capability_name,
            item.min_calls,
            item.max_calls,
            item.expected_outcome,
        )
        for item in catalog.invocation_expectations
    }
    assert declared == derived


def test_suite_and_fixture_hashes_match_current_production_catalog() -> None:
    catalog_snapshot = production_capability_catalog_snapshot()
    assert {item.capability_id for item in catalog_snapshot.tools} == CORE_TOOL_NAMES
    assert {
        item.capability_id for item in catalog_snapshot.subagents
    } == CORE_SUBAGENT_NAMES
    suite = load_authored_suite(
        _ROOT / "suite.json",
        expected_capability_catalog_hash=catalog_snapshot.canonical_hash,
    )
    catalog = derive_capability_catalog(suite, catalog_snapshot)
    fixture = load_fixture_manifest(
        _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
    )
    assert suite.fixture.snapshot_id == fixture.snapshot_id
    assert len(suite.cases) == 37
    assert len(catalog.invocation_expectations) == 35
    assert catalog.production_catalog_hash == catalog_snapshot.canonical_hash


def test_long_current_request_is_an_authored_expanded_input_not_a_short_proxy() -> None:
    catalog_snapshot = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        _ROOT / "suite.json",
        expected_capability_catalog_hash=catalog_snapshot.canonical_hash,
    )
    case = next(
        item
        for item in suite.cases
        if item.case_id == "context_long_current_request_preserved"
    )

    assert case.user_request_expansion is not None
    assert len(case.user_request_raw) >= 12_000
    assert case.user_request == case.user_request_raw
    assert "  双空格" in case.user_request_raw
    assert "\n密封压力计划中的关键事实必须保持。" in case.user_request_raw


def test_every_scripted_capability_is_registered_in_the_production_catalog() -> None:
    catalog = production_capability_catalog_snapshot()
    tool_names = {item.capability_id for item in catalog.tools}
    subagent_names = {item.capability_id for item in catalog.subagents}
    suite = load_authored_suite(
        _ROOT / "suite.json",
        expected_capability_catalog_hash=catalog.canonical_hash,
    )

    scripted_capabilities = {
        (step.kind.value, step.name)
        for case in suite.cases
        for step in case.scripted_steps
        if step.kind.value in {"tool", "subagent"}
    }
    assert scripted_capabilities == {("tool", name) for name in tool_names} | {
        ("subagent", name) for name in subagent_names
    }


def test_fixture_knowledge_is_current_confirmed_schema_without_forbidden_fields() -> (
    None
):
    path = _ROOT / "fixtures" / "core_novel" / "knowledge" / "confirmed_cards.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    cards = [StructuredKnowledgeCard.model_validate(item) for item in payload]
    assert len(cards) == 4
    assert all(card.lifecycle == "confirmed" for card in cards)
    forbidden = {
        "body",
        "tags",
        "fields",
        "confidence",
        "source_refs",
        "relations",
        "foreshadow",
        "personality",
        "motivation",
        "appearance",
        "importance",
    }
    assert all(not forbidden.intersection(item) for item in payload)


def test_every_executable_synthetic_case_has_real_runtime_model_steps() -> None:
    payload = json.loads((_ROOT / "suite.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    for case in payload["cases"]:
        steps = case["scripted_steps"]
        if not steps:
            expected_terminal = case["expected_terminal"]
            if (
                expected_terminal["run_status"] != "safe_failure"
                or expected_terminal["reason_code"] != "unsafe_context"
                or expected_terminal["resumable"] is not False
                or case["required_invocations"]
            ):
                problems.append(
                    f"{case['case_id']}:preplan-safe-failure-contract"
                )
            continue
        plan = steps[0]
        parsed_plan = None
        try:
            if plan["kind"] != "model":
                raise ValueError("首步不是 model")
            if {"path": "/phase", "expected": "plan"} not in plan["matchers"]:
                raise ValueError("首步不是 plan")
            parsed_plan = GeneralAgentPlanDraft.model_validate(plan.get("response"))
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"{case['case_id']}:plan:{error}")
        if parsed_plan is None or not parsed_plan.nodes:
            continue
        expected_terminal = case["expected_terminal"]
        if expected_terminal["run_status"] == "write_rejected":
            denial = steps[-1]
            try:
                if denial["kind"] != "human":
                    raise ValueError("拒绝终态的末步不是 human")
                if {
                    "path": "/approved",
                    "expected": False,
                } not in denial["matchers"]:
                    raise ValueError("拒绝终态没有明确的拒绝决定")
            except (KeyError, TypeError, ValueError) as error:
                problems.append(f"{case['case_id']}:denial:{error}")
            continue
        verify = steps[-1]
        try:
            if verify["kind"] != "model":
                raise ValueError("末步不是 model")
            if {"path": "/phase", "expected": "verify"} not in verify["matchers"]:
                raise ValueError("末步不是 verify")
            GeneralAgentVerification.model_validate(verify.get("response"))
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"{case['case_id']}:verify:{error}")

    assert problems == []
