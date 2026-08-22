"""从活动 Suite 与生产能力快照派生能力覆盖目录。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CapabilityCatalogSnapshot,
    CapabilityDescriptor,
    CapabilityKind,
    Sha256,
    StableId,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
)


class CapabilityCoverageEntry(BenchmarkModel):
    """一个生产能力在活动 Suite 中的稳定反向覆盖投影。"""

    kind: CapabilityKind
    capability_name: StableId
    primary_case_id: StableId
    covered_case_ids: tuple[StableId, ...] = Field(min_length=1)
    manifest_identity: str = Field(min_length=1, max_length=500)
    handler_identity: str = Field(min_length=1, max_length=500)


class InvocationExpectation(BenchmarkModel):
    """从案例 required_invocations 原样投影出的调用合同。"""

    case_id: StableId
    kind: CapabilityKind
    capability_name: StableId
    min_calls: int = Field(ge=0)
    max_calls: int = Field(ge=0)
    expected_outcome: Literal["completed"]
    parent: str | None = None
    partial_order: str | None = None


class DerivedCapabilityCatalog(BenchmarkModel):
    """由两类权威输入确定性重建的能力目录。"""

    case_count: int = Field(ge=0)
    capabilities: tuple[CapabilityCoverageEntry, ...]
    invocation_expectations: tuple[InvocationExpectation, ...]
    production_catalog_hash: Sha256
    canonical_hash: Sha256

    @property
    def catalog_hash(self) -> str:
        return self.canonical_hash


class ActualCapabilityInvocation(BenchmarkModel):
    case_id: StableId
    call_id: str = Field(min_length=1)
    kind: CapabilityKind
    capability_name: StableId
    outcome: Literal[
        "completed",
        "failed",
        "timed_out",
        "denied",
        "cancelled",
    ]


class CatalogAuditReport(BenchmarkModel):
    case_count: int = Field(ge=0)
    catalog_capability_count: int = Field(ge=0)
    invocation_expectation_count: int = Field(ge=0)
    covered_capability_count: int = Field(ge=0)
    missing_capabilities: tuple[str, ...]
    complete: bool


CORE_TOOL_NAMES = frozenset(
    {
        "get_novel_structure",
        "get_knowledge_chapter_coverage",
        "read_manuscript",
        "retrieve_story_context",
        "list_knowledge_catalog",
        "resolve_knowledge_identity",
        "read_knowledge_cards",
        "search_external_sources",
        "read_external_source",
        "preview_manuscript_patch",
        "apply_manuscript_patch",
        "create_novel_structure_items",
        "update_novel_structure",
        "delete_novel_structure_items",
        "create_confirmed_knowledge",
        "update_confirmed_knowledge",
    }
)

CORE_SUBAGENT_NAMES = frozenset(
    {
        "canon_evidence",
        "external_research",
        "narrative_summary",
        "worldbuilding",
        "character",
        "story_architecture",
        "scene_planning",
        "drafting",
        "consistency_reviewer",
        "narrative_reviewer",
        "style_reviewer",
        "revision",
    }
)


def derive_capability_catalog(
    suite: AuthoredSuiteSpec,
    production_capability_snapshot: CapabilityCatalogSnapshot,
) -> DerivedCapabilityCatalog:
    """按案例顺序聚合调用合同，并绑定生产 manifest/handler 身份。"""

    descriptors = _validate_production_snapshot(
        suite=suite,
        snapshot=production_capability_snapshot,
    )
    cases_by_id = {case.case_id: case for case in suite.cases}
    if len(cases_by_id) != len(suite.cases) or frozenset(cases_by_id) != frozenset(
        suite.case_order
    ):
        raise ValueError("Suite 案例与 case_order 不一致，不能派生能力目录。")

    coverage: dict[
        tuple[CapabilityKind, str],
        list[str],
    ] = {}
    invocation_expectations: list[InvocationExpectation] = []

    for case_id in suite.case_order:
        case = cases_by_id[case_id]
        for invocation in case.required_invocations:
            descriptor = descriptors.get(invocation.name)
            if descriptor is None:
                raise ValueError(
                    "Suite required_invocations 引用了未知能力："
                    f"{invocation.type.value}:{invocation.name}。"
                )
            if descriptor.kind is not invocation.type:
                raise ValueError(
                    "Suite required_invocations 与生产能力 kind 冲突："
                    f"{invocation.name} 声明为 {invocation.type.value}，"
                    f"生产 Manifest 为 {descriptor.kind.value}。"
                )
            key = (descriptor.kind, descriptor.capability_id)
            case_ids = coverage.setdefault(key, [])
            if case.case_id not in case_ids:
                case_ids.append(case.case_id)
            invocation_expectations.append(
                InvocationExpectation(
                    case_id=case.case_id,
                    kind=invocation.type,
                    capability_name=invocation.name,
                    min_calls=invocation.min_calls,
                    max_calls=invocation.max_calls,
                    expected_outcome=invocation.expected_outcome,
                    parent=invocation.parent,
                    partial_order=invocation.partial_order,
                )
            )

    expected_core = {
        (CapabilityKind.TOOL, capability_name) for capability_name in CORE_TOOL_NAMES
    } | {
        (CapabilityKind.SUBAGENT, capability_name)
        for capability_name in CORE_SUBAGENT_NAMES
    }
    missing_coverage = expected_core - set(coverage)
    if missing_coverage:
        missing = ", ".join(
            f"{kind.value}:{capability_name}"
            for kind, capability_name in sorted(
                missing_coverage,
                key=lambda item: (item[0].value, item[1]),
            )
        )
        raise ValueError(f"生产核心能力无案例覆盖：{missing}。")

    capabilities = tuple(
        CapabilityCoverageEntry(
            kind=kind,
            capability_name=capability_name,
            primary_case_id=case_ids[0],
            covered_case_ids=tuple(case_ids),
            manifest_identity=descriptors[capability_name].manifest_identity,
            handler_identity=descriptors[capability_name].handler_identity,
        )
        for (kind, capability_name), case_ids in coverage.items()
    )
    payload = {
        "production_catalog_hash": production_capability_snapshot.canonical_hash,
        "capabilities": capabilities,
        "invocation_expectations": tuple(invocation_expectations),
    }
    return DerivedCapabilityCatalog(
        case_count=len(suite.cases),
        capabilities=capabilities,
        invocation_expectations=tuple(invocation_expectations),
        production_catalog_hash=production_capability_snapshot.canonical_hash,
        canonical_hash=canonical_sha256(payload),
    )


def _validate_production_snapshot(
    *,
    suite: AuthoredSuiteSpec,
    snapshot: CapabilityCatalogSnapshot,
) -> dict[str, CapabilityDescriptor]:
    descriptors = snapshot.tools + snapshot.subagents
    descriptor_ids = [descriptor.capability_id for descriptor in descriptors]
    if len(descriptor_ids) != len(set(descriptor_ids)):
        raise ValueError("生产能力快照包含重复 capability_id。")

    for descriptor in descriptors:
        if not descriptor.manifest_identity.strip():
            raise ValueError(
                f"生产能力缺少 manifest/schema identity：{descriptor.capability_id}。"
            )
        if not descriptor.handler_identity.strip():
            raise ValueError(
                f"生产能力缺少 handler identity：{descriptor.capability_id}。"
            )

    actual_snapshot_hash = canonical_sha256(
        {
            "tools": snapshot.tools,
            "subagents": snapshot.subagents,
            "registration_dependencies": snapshot.registration_dependencies,
        }
    )
    if actual_snapshot_hash != snapshot.canonical_hash:
        raise ValueError(
            "生产能力快照内容身份漂移：声明 hash 与实际 "
            "manifest/schema/handler 内容不一致。"
        )

    descriptors_by_id = {
        descriptor.capability_id: descriptor for descriptor in descriptors
    }
    _validate_core_capabilities(descriptors_by_id)
    if suite.capability_catalog_hash != actual_snapshot_hash:
        raise ValueError(
            "Suite 绑定的生产能力目录身份已漂移；"
            "manifest/schema/handler 变化必须产生新的 Suite 执行身份。"
        )
    return descriptors_by_id


def _validate_core_capabilities(
    descriptors: dict[str, CapabilityDescriptor],
) -> None:
    expected = {
        capability_name: CapabilityKind.TOOL for capability_name in CORE_TOOL_NAMES
    } | {
        capability_name: CapabilityKind.SUBAGENT
        for capability_name in CORE_SUBAGENT_NAMES
    }
    missing = sorted(set(expected) - set(descriptors))
    if missing:
        raise ValueError("生产 Manifest 缺少核心能力：" + ", ".join(missing) + "。")
    conflicts = sorted(
        (
            capability_name,
            kind,
            descriptors[capability_name].kind,
        )
        for capability_name, kind in expected.items()
        if descriptors[capability_name].kind is not kind
    )
    if conflicts:
        details = ", ".join(
            f"{name}={actual.value}（期望 {expected_kind.value}）"
            for name, expected_kind, actual in conflicts
        )
        raise ValueError(f"生产核心能力 kind 冲突：{details}。")


def audit_core_catalog(
    *,
    catalog: DerivedCapabilityCatalog,
    actual_invocations: tuple[ActualCapabilityInvocation, ...],
) -> CatalogAuditReport:
    expected = {(item.kind, item.capability_name) for item in catalog.capabilities}
    observed = {
        (item.kind, item.capability_name)
        for item in actual_invocations
        if item.outcome == "completed"
    }
    missing = sorted(f"{kind.value}:{name}" for kind, name in expected - observed)
    return CatalogAuditReport(
        case_count=catalog.case_count,
        catalog_capability_count=len(expected),
        invocation_expectation_count=len(catalog.invocation_expectations),
        covered_capability_count=len(expected & observed),
        missing_capabilities=tuple(missing),
        complete=not missing,
    )
