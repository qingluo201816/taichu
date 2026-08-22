"""需求 1.1、1.8、1.11、1.13、1.16、1.17、1.19、1.23 与 2.1-2.5。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_json_bytes,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BudgetObservation,
    CapabilityCatalogSnapshot,
    CapabilityDescriptor,
    CapabilityKind,
    CaseCategory,
    CaseSpec,
    FixtureRef,
    PathKind,
    ResourceBudget,
    SyntheticTrackSpec,
    ValueAvailability,
)


def _budget() -> ResourceBudget:
    return ResourceBudget(
        max_node_executions=6,
        max_replans=0,
        max_capability_calls=2,
        max_model_calls=3,
        max_total_tokens=2_000,
        max_runtime_ms=10_000,
    )


def test_resource_budget_rejects_missing_or_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        ResourceBudget(
            max_node_executions=0,
            max_replans=-1,
            max_capability_calls=0,
            max_model_calls=1,
            max_total_tokens=1,
            max_runtime_ms=1,
        )

    with pytest.raises(ValidationError):
        ResourceBudget.model_validate(
            {
                "max_node_executions": 1,
                "max_replans": 0,
                "max_capability_calls": 0,
                "max_model_calls": 1,
                "max_total_tokens": 1,
            }
        )


def test_budget_observation_keeps_unavailable_values_explicit() -> None:
    missing = BudgetObservation(
        limit=3,
        actual=None,
        availability=ValueAvailability.MISSING,
        within_limit=None,
        evidence_refs=(),
    )
    assert missing.actual is None
    assert missing.within_limit is None

    with pytest.raises(ValidationError):
        BudgetObservation(
            limit=3,
            actual=0,
            availability=ValueAvailability.MISSING,
            within_limit=True,
            evidence_refs=(),
        )


def test_capability_catalog_rejects_duplicate_ids_and_unknown_dependencies() -> None:
    tool = CapabilityDescriptor(
        capability_id="read_manuscript",
        kind=CapabilityKind.TOOL,
        manifest_identity="manifest:read_manuscript",
        handler_identity="handler:read_manuscript",
    )
    with pytest.raises(ValidationError):
        CapabilityCatalogSnapshot(
            tools=(tool, tool),
            subagents=(),
            registration_dependencies=(),
            canonical_hash="0" * 64,
            discovered_at="2026-07-27T00:00:00Z",
        )

    with pytest.raises(ValidationError):
        CapabilityCatalogSnapshot(
            tools=(tool,),
            subagents=(),
            registration_dependencies=(
                {
                    "subagent_id": "missing_subagent",
                    "tool_id": "read_manuscript",
                },
            ),
            canonical_hash="0" * 64,
            discovered_at="2026-07-27T00:00:00Z",
        )


def test_case_contract_rejects_unknown_capability_reference() -> None:
    catalog = CapabilityCatalogSnapshot.create(
        tools=(
            CapabilityDescriptor(
                capability_id="read_manuscript",
                kind=CapabilityKind.TOOL,
                manifest_identity="manifest:read_manuscript",
                handler_identity="handler:read_manuscript",
            ),
        ),
        subagents=(),
        registration_dependencies=(),
        discovered_at="2026-07-27T00:00:00Z",
    )
    case = CaseSpec(
        case_id="fact_lookup",
        name="事实查询",
        purpose="验证正文读取",
        category=CaseCategory.FACT_QUESTION,
        tags=frozenset({"事实", "读取"}),
        applicable_tracks=frozenset({"synthetic"}),
        path_kind=PathKind.SINGLE_CAPABILITY,
        targets=("正文读取",),
        user_request="主角在哪里？",
        fixture_snapshot_id=f"fixture_{'1' * 64}",
        required_capabilities=frozenset({"unknown_tool"}),
        allowed_capabilities=frozenset({"unknown_tool"}),
        forbidden_capabilities=frozenset(),
        budgets=_budget(),
    )

    with pytest.raises(ValueError, match="unknown_tool"):
        case.validate_capabilities(catalog)


def test_models_are_frozen_and_canonical_serialization_is_deterministic() -> None:
    track = SyntheticTrackSpec(
        rule_set_id="strict_core",
        gateway_identity="synthetic",
    )
    with pytest.raises(ValidationError):
        track.gateway_identity = "changed"  # type: ignore[misc]

    left = canonical_json_bytes(
        {
            "track": track,
            "tags": frozenset({"乙", "甲"}),
            "nested": {"b": 2, "a": 1},
        }
    )
    right = canonical_json_bytes(
        {
            "nested": {"a": 1, "b": 2},
            "tags": frozenset({"甲", "乙"}),
            "track": track,
        }
    )
    assert left == right
    assert json.loads(left)["tags"] == ["乙", "甲"]


def test_stable_identifiers_and_fixture_hash_are_strict() -> None:
    FixtureRef(
        fixture_id="core_novel",
        snapshot_id=f"fixture_{'a' * 64}",
    )
    with pytest.raises(ValidationError):
        FixtureRef(fixture_id="Core Novel", snapshot_id="fixture_not-a-hash")
