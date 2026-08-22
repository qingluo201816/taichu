"""需求 1.2、1.8、2.6、3.4、14.1、14.2：能力覆盖单一来源。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark import (
    capability_catalog as capability_catalog_module,
)
from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    ActualCapabilityInvocation,
    CORE_SUBAGENT_NAMES,
    CORE_TOOL_NAMES,
    audit_core_catalog,
    derive_capability_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CapabilityCatalogSnapshot,
    CapabilityKind,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
    load_authored_suite,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)

_SUITE_PATH = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
)


def _suite_and_snapshot() -> tuple[
    AuthoredSuiteSpec,
    CapabilityCatalogSnapshot,
]:
    snapshot = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=snapshot.canonical_hash,
    )
    return suite, snapshot


def _replace_invocation(
    suite: AuthoredSuiteSpec,
    capability_name: str,
    **changes: object,
) -> AuthoredSuiteSpec:
    cases = []
    replaced = False
    for case in suite.cases:
        invocations = []
        for invocation in case.required_invocations:
            if not replaced and invocation.name == capability_name:
                invocation = invocation.model_copy(update=changes)
                replaced = True
            invocations.append(invocation)
        cases.append(
            case.model_copy(update={"required_invocations": tuple(invocations)})
        )
    assert replaced is True
    return suite.model_copy(update={"cases": tuple(cases)})


def _without_invocations(
    suite: AuthoredSuiteSpec,
    capability_name: str,
) -> AuthoredSuiteSpec:
    return suite.model_copy(
        update={
            "cases": tuple(
                case.model_copy(
                    update={
                        "required_invocations": tuple(
                            invocation
                            for invocation in case.required_invocations
                            if invocation.name != capability_name
                        )
                    }
                )
                for case in suite.cases
            )
        }
    )


def _replace_snapshot_descriptor(
    snapshot: CapabilityCatalogSnapshot,
    capability_name: str,
    **changes: object,
) -> CapabilityCatalogSnapshot:
    tools = tuple(
        descriptor.model_copy(update=changes)
        if descriptor.capability_id == capability_name
        else descriptor
        for descriptor in snapshot.tools
    )
    subagents = tuple(
        descriptor.model_copy(update=changes)
        if descriptor.capability_id == capability_name
        else descriptor
        for descriptor in snapshot.subagents
    )
    return CapabilityCatalogSnapshot.create(
        tools=tools,
        subagents=subagents,
        registration_dependencies=snapshot.registration_dependencies,
        discovered_at=snapshot.discovered_at,
    )


def test_catalog_is_derived_from_suite_invocations_in_stable_case_order() -> None:
    suite, snapshot = _suite_and_snapshot()

    catalog = derive_capability_catalog(suite, snapshot)

    expected_case_ids: dict[tuple[CapabilityKind, str], list[str]] = {}
    expected_invocations = []
    for case in suite.cases:
        for invocation in case.required_invocations:
            key = (invocation.type, invocation.name)
            case_ids = expected_case_ids.setdefault(key, [])
            if case.case_id not in case_ids:
                case_ids.append(case.case_id)
            expected_invocations.append(
                (
                    case.case_id,
                    invocation.type,
                    invocation.name,
                    invocation.min_calls,
                    invocation.max_calls,
                    invocation.expected_outcome,
                    invocation.parent,
                    invocation.partial_order,
                )
            )

    assert catalog.case_count == 37
    assert catalog.production_catalog_hash == snapshot.canonical_hash
    assert len(catalog.capabilities) == 28
    assert len(catalog.invocation_expectations) == 35
    assert [(item.kind, item.capability_name) for item in catalog.capabilities] == list(
        expected_case_ids
    )
    assert all(
        item.primary_case_id == expected_case_ids[(item.kind, item.capability_name)][0]
        and item.covered_case_ids
        == tuple(expected_case_ids[(item.kind, item.capability_name)])
        for item in catalog.capabilities
    )
    assert [
        (
            item.case_id,
            item.kind,
            item.capability_name,
            item.min_calls,
            item.max_calls,
            item.expected_outcome,
            item.parent,
            item.partial_order,
        )
        for item in catalog.invocation_expectations
    ] == expected_invocations
    assert (
        Counter(
            (item.kind, item.capability_name)
            for item in catalog.invocation_expectations
        )[(CapabilityKind.TOOL, "preview_manuscript_patch")]
        == 3
    )

    rediscovered = snapshot.model_copy(update={"discovered_at": "2099-01-01T00:00:00Z"})
    assert derive_capability_catalog(suite, rediscovered).canonical_hash == (
        catalog.canonical_hash
    )


def test_catalog_contains_exactly_current_production_core_capabilities() -> None:
    suite, snapshot = _suite_and_snapshot()
    catalog = derive_capability_catalog(suite, snapshot)

    assert len(CORE_TOOL_NAMES) == 16
    assert len(CORE_SUBAGENT_NAMES) == 12
    assert {
        item.capability_name
        for item in catalog.capabilities
        if item.kind is CapabilityKind.TOOL
    } == CORE_TOOL_NAMES
    assert {
        item.capability_name
        for item in catalog.capabilities
        if item.kind is CapabilityKind.SUBAGENT
    } == CORE_SUBAGENT_NAMES
    assert all(item.manifest_identity for item in catalog.capabilities)
    assert all(item.handler_identity for item in catalog.capabilities)


def test_derive_catalog_rejects_unknown_capability() -> None:
    suite, snapshot = _suite_and_snapshot()

    unknown = _replace_invocation(
        suite,
        "retrieve_story_context",
        name="unknown_capability",
    )
    with pytest.raises(ValueError, match="未知能力.*unknown_capability"):
        derive_capability_catalog(unknown, snapshot)


def test_derive_catalog_rejects_kind_conflict() -> None:
    suite, snapshot = _suite_and_snapshot()
    kind_conflict = _replace_invocation(
        suite,
        "retrieve_story_context",
        type=CapabilityKind.SUBAGENT,
    )
    with pytest.raises(ValueError, match="kind 冲突.*retrieve_story_context"):
        derive_capability_catalog(kind_conflict, snapshot)


def test_derive_catalog_rejects_missing_handler_and_snapshot_identity_tampering() -> (
    None
):
    suite, snapshot = _suite_and_snapshot()
    missing_handler = snapshot.model_copy(
        update={
            "tools": tuple(
                descriptor.model_copy(update={"handler_identity": ""})
                if descriptor.capability_id == "retrieve_story_context"
                else descriptor
                for descriptor in snapshot.tools
            )
        }
    )
    with pytest.raises(ValueError, match="缺少 handler identity.*retrieve_story_context"):
        derive_capability_catalog(suite, missing_handler)

    tampered = snapshot.model_copy(
        update={
            "tools": tuple(
                descriptor.model_copy(
                    update={"manifest_identity": "changed-schema-identity"}
                )
                if descriptor.capability_id == "retrieve_story_context"
                else descriptor
                for descriptor in snapshot.tools
            )
        }
    )
    with pytest.raises(ValueError, match="快照内容身份漂移"):
        derive_capability_catalog(suite, tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_identity", "changed-schema-identity"),
        (
            "handler_identity",
            "taichu.application.tools.retrieve_story_context:changed_handler",
        ),
    ],
)
def test_derive_catalog_rejects_schema_or_handler_identity_drift(
    field: str,
    value: str,
) -> None:
    suite, snapshot = _suite_and_snapshot()
    drifted = _replace_snapshot_descriptor(
        snapshot,
        "retrieve_story_context",
        **{field: value},
    )

    with pytest.raises(ValueError, match="Suite 绑定的生产能力目录身份已漂移"):
        derive_capability_catalog(suite, drifted)


def test_derive_catalog_rejects_uncovered_production_core_capability() -> None:
    suite, snapshot = _suite_and_snapshot()
    uncovered = _without_invocations(suite, "retrieve_story_context")

    with pytest.raises(
        ValueError,
        match="生产核心能力无案例覆盖.*retrieve_story_context",
    ):
        derive_capability_catalog(uncovered, snapshot)


def test_case_track_and_invocation_authority_constants_are_removed() -> None:
    assert not hasattr(capability_catalog_module, "_CASE_IDS")
    assert not hasattr(capability_catalog_module, "_SYNTHETIC_ONLY")
    assert not hasattr(capability_catalog_module, "CORE_CASES")
    assert not hasattr(capability_catalog_module, "_PRIMARY_CASE_BY_CAPABILITY")
    assert not hasattr(capability_catalog_module, "CORE_CAPABILITY_COVERAGE")
    assert not hasattr(
        capability_catalog_module,
        "CORE_INVOCATION_EXPECTATIONS",
    )


def test_allowed_or_manifest_membership_is_not_runtime_coverage_evidence() -> None:
    suite, snapshot = _suite_and_snapshot()
    catalog = derive_capability_catalog(suite, snapshot)
    report = audit_core_catalog(catalog=catalog, actual_invocations=())
    assert report.case_count == 37
    assert report.catalog_capability_count == 28
    assert report.covered_capability_count == 0
    assert report.complete is False

    observations = tuple(
        ActualCapabilityInvocation(
            case_id=item.case_id,
            call_id=f"call-{index}",
            kind=item.kind,
            capability_name=item.capability_name,
            outcome="completed",
        )
        for index, item in enumerate(catalog.invocation_expectations)
    )
    report = audit_core_catalog(
        catalog=catalog,
        actual_invocations=observations,
    )
    assert report.covered_capability_count == 28
    assert report.complete is True


def test_failed_or_unknown_invocations_do_not_count_as_actual_coverage() -> None:
    suite, snapshot = _suite_and_snapshot()
    catalog = derive_capability_catalog(suite, snapshot)
    report = audit_core_catalog(
        catalog=catalog,
        actual_invocations=(
            ActualCapabilityInvocation(
                case_id="single_manuscript_search",
                call_id="call-failed",
                kind="tool",
                capability_name="retrieve_story_context",
                outcome="failed",
            ),
            ActualCapabilityInvocation(
                case_id="single_manuscript_search",
                call_id="call-unknown",
                kind="tool",
                capability_name="not_registered",
                outcome="completed",
            ),
        ),
    )
    assert report.covered_capability_count == 0
    assert report.complete is False
