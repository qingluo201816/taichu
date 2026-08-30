"""需求 4.5、11.1、13.15：strict driver 只替换模型，能力走真实 Runtime。"""

from __future__ import annotations

from tests.fakes.capability_results import in_memory_capability_result_repository

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from taichu.application.capabilities import CapabilityContext
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import TypedOracle
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ScriptedMatcher,
    ScriptedStep,
    StrictScriptedDriver,
)
from taichu.application.evaluations.general_agent_benchmark.suite_artifact_builder import (
    build_synthetic_suite_artifact,
    stable_suite_drift_paths,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
    FinalClaimsAssertionSpec,
    load_authored_suite,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticSuiteRunner,
)
from taichu.application.external_research.service import ExternalResearchService
from taichu.application.general_agent.context import ContextAssembler
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.models import GeneralAgentRunStatus
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.services.agent_memory_service import AgentMemoryService
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.services.outline_service import OutlineService
from taichu.application.vector_graph.models import (
    VectorGraphEvidence,
    VectorGraphRetrievalResult,
    VectorGraphSourceType,
)
from taichu.application.vector_graph.service import VectorGraphRAGService
from taichu.application.subagents.canon_evidence import agent as canon_evidence
from taichu.application.subagents.external_research import agent as external_research
from taichu.application.subagents.contract import SubagentPlugin
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools import (
    apply_manuscript_patch,
    preview_manuscript_patch,
    read_external_source,
    retrieve_story_context,
    search_external_sources,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.registry import ToolRegistry
from tests.fakes.agent_memory import in_memory_agent_memory_repository
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    ObservedSubagentRegistry,
    ObservedToolRegistry,
    StrictSyntheticInteractionObserver,
    StrictSyntheticLLMGateway,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.fixture_external_research import (
    FixtureExternalResearchBackend,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
    _unsafe_context_terminal_observation,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentContextSnapshotRepository,
    JsonGeneralAgentEffectRepository,
    JsonGeneralAgentRunRepository,
)
from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository
from taichu.infrastructure.llm.adapter import GatewayChatModel
from taichu.infrastructure.storage.markdown_backend import (
    ProjectAssetStorageBackend,
)
from taichu.infrastructure.plugin_discovery import discover_tools


class _TraceRepository:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def append(self, record: object) -> None:
        self.records.append(record)


class _ChapterStoryContextService(VectorGraphRAGService):
    def __init__(self, chapter_service: ChapterService) -> None:
        self._chapters = chapter_service

    async def retrieve(self, query: str, *, top_k: int = 10) -> VectorGraphRetrievalResult:
        evidences = []
        for chapter in await self._chapters.list_chapters():
            content = (await self._chapters.read_chapter(chapter.id)).markdown
            if query.split()[0] not in content:
                continue
            evidences.append(
                VectorGraphEvidence(
                    source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
                    source_id=chapter.id,
                    source_ref=f"manuscript:{chapter.id}:0-{len(content)}",
                    title=chapter.title,
                    content=content,
                    content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    rank=len(evidences) + 1,
                    start_char=0,
                    end_char=len(content),
                    authority_verified=True,
                )
            )
        return VectorGraphRetrievalResult(
            query=query,
            evidences=evidences[:top_k],
            source_refs=[item.source_ref for item in evidences[:top_k]],
        )


def _handler_identities(
    tools: object,
    subagents: object,
) -> dict[tuple[str, str], str]:
    return {
        **{
            ("tool", manifest.name): f"test:tool:{manifest.name}"
            for manifest in tools.list_manifests()  # type: ignore[attr-defined]
        },
        **{
            ("subagent", manifest.name): f"test:subagent:{manifest.name}"
            for manifest in subagents.list_manifests()  # type: ignore[attr-defined]
        },
    }


def test_strict_gateway_runs_real_search_handler_and_preserves_runtime_audit(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_real_search_case(tmp_path))


def test_strict_gateway_runs_real_canon_subagent_and_persists_artifact_trace(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_real_canon_subagent_case(tmp_path / "subagent"))


def test_authorized_write_uses_real_handler_and_persists_effect_evidence(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_real_authorized_write_case(tmp_path / "write"))


def test_fixture_external_backend_never_uses_network_and_returns_sealed_source() -> (
    None
):
    root = Path(
        "tests/fixtures/evaluations/general_writing_agent_benchmark/"
        "fixtures/core_novel/external_sources"
    )
    backend = FixtureExternalResearchBackend(root)

    results = asyncio.run(backend.search("灯塔 记忆 民俗", max_results=2))
    document = asyncio.run(backend.read(results[0].url))

    assert len(results) == 1
    assert results[0].url.startswith("https://fixture.invalid/")
    assert document.title == "北岸灯塔民俗摘录"
    assert "记忆" in document.content


def test_external_subagent_uses_real_nested_tools_against_fixture_backend(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_real_external_case(tmp_path / "external"))


def test_checkpoint_case_recovers_same_run_without_rerunning_successful_tool(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_real_checkpoint_recovery_case(tmp_path / "recovery"))


def test_full_suite_is_stable_across_two_isolated_runtime_runs(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_full_suite_stability(tmp_path))


def test_unsafe_context_refusal_is_observed_from_production_runtime(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_unsafe_context_refusal(tmp_path / "unsafe-context"))


def test_workspace_cleanup_failure_invalidates_case_and_preserves_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_exercise_workspace_cleanup_failure(tmp_path, monkeypatch))


async def _exercise_workspace_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        Path("tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"),
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    runtime = SyntheticFixtureRuntime(
        sealed_fixture_root=Path(
            "tests/fixtures/evaluations/"
            "general_writing_agent_benchmark/fixtures/core_novel"
        ),
        workspaces_root=tmp_path,
    )

    def fail_cleanup(_handle: object) -> None:
        raise RuntimeError("模拟工作区清理失败")

    monkeypatch.setattr(
        runtime._controller,
        "cleanup_workspace",
        fail_cleanup,
    )
    runner = SyntheticSuiteRunner(
        runtime=runtime,
        runtime_config_identity="1" * 64,
        capability_catalog=catalog,
    )

    result = await runner.run(
        suite,
        requested_case_ids=(suite.cases[0].case_id,),
    )

    assert result.complete is False
    assert result.failed_case_count == 1
    assert result.cases[0].conclusion.value == "invalid"
    assert len(result.cases[0].gates) == 6
    assert result.cases[0].problems == ("runtime_error:ExceptionGroup",)
    assert tuple(tmp_path.glob("workspace_*"))


def _failed_case_summary(items: list[Any]) -> list[dict[str, object]]:
    return [
        {
            "case_id": item.case_id,
            "conclusion": item.conclusion.value,
            "problems": item.problems,
            "failed_conditions": [
                condition.model_dump(mode="json")
                for gate in item.gates
                for condition in gate.conditions
                if condition.status.value != "passed"
            ],
        }
        for item in items
    ]


async def _exercise_full_suite_stability(tmp_path: Path) -> None:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        Path("tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"),
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    oracle = _load_typed_oracle(suite)
    results = []
    roots = (tmp_path / "first", tmp_path / "second")
    for root in roots:
        runner = SyntheticSuiteRunner(
            runtime=SyntheticFixtureRuntime(
                sealed_fixture_root=Path(
                    "tests/fixtures/evaluations/"
                    "general_writing_agent_benchmark/fixtures/core_novel"
                ),
                workspaces_root=root,
            ),
            runtime_config_identity="1" * 64,
            capability_catalog=catalog,
            oracle=oracle,
        )
        results.append(await runner.run(suite))

    first, second = results
    failed_first = [item for item in first.cases if item.conclusion.value != "passed"]
    failed_second = [item for item in second.cases if item.conclusion.value != "passed"]
    assert first.complete is True, _failed_case_summary(failed_first)
    assert second.complete is True, _failed_case_summary(failed_second)
    assert first.case_count == second.case_count == 37
    assert first.passed_case_count == second.passed_case_count == 37
    assert first.failed_case_count == second.failed_case_count == 0
    assert all(
        len(case.gates) == 6
        and all(gate.status.value == "passed" for gate in case.gates)
        for result in results
        for case in result.cases
    )
    assert first.stable_result_hash == second.stable_result_hash
    built = build_synthetic_suite_artifact(suite=suite, result=first)
    assert built.complete_admission is True
    assert built.counts.total == built.counts.passed == 37
    assert built.counts.invalid == built.counts.failed == 0
    assert len(built.artifact.case_rows) == 37
    assert len(built.artifact.evidence_bundles) == 37
    assert all(
        bundle.details is not None
        and bundle.details.user_request_sha256 is not None
        and bundle.details.track is not None
        and bundle.details.track.value == "synthetic"
        and bundle.details.observation_sha256 is not None
        and bundle.details.terminal is not None
        for bundle in built.artifact.evidence_bundles
    )
    unsafe_bundle = next(
        bundle
        for bundle in built.artifact.evidence_bundles
        if bundle.identity.case_id == "context_unsafe_compression_refusal"
    )
    assert unsafe_bundle.details is not None
    assert unsafe_bundle.details.runtime_failure is not None
    assert unsafe_bundle.details.runtime_failure["run_status"] == "failed"
    assert unsafe_bundle.details.runtime_failure["resumable"] is False
    assert unsafe_bundle.details.runtime_failure["interaction_count"] == 0
    assert unsafe_bundle.details.runtime_failure["capability_result_count"] == 0
    assert unsafe_bundle.details.runtime_failure["effect_count"] == 0
    assert stable_suite_drift_paths(first, second) == ()
    partial = first.model_copy(
        update={
            "cases": first.cases[:1],
            "case_count": 1,
            "passed_case_count": 1,
            "failed_case_count": 0,
            "complete": False,
        }
    )
    partial_artifact = build_synthetic_suite_artifact(suite=suite, result=partial)
    assert partial_artifact.complete_admission is False
    assert partial_artifact.artifact.conclusion.value == "not_evaluated"
    assert partial_artifact.counts.total == partial_artifact.counts.passed == 1
    drifted_normalization = second.cases[0].normalization_artifact
    assert drifted_normalization is not None
    drifted_case = second.cases[0].model_copy(
        update={
            "normalization_artifact": drifted_normalization.model_copy(
                update={"normalization_hash": "f" * 64}
            )
        }
    )
    drifted = second.model_copy(
        update={
            "cases": (drifted_case, *second.cases[1:]),
            "stable_result_hash": "f" * 64,
        }
    )
    assert stable_suite_drift_paths(first, drifted) == (
        f"/cases/{drifted_case.case_id}/normalization_hash",
    )
    first_observation = first.cases[0].case_observation
    assert first_observation is not None
    conflicting_case = first.cases[0].model_copy(
        update={
            "case_observation": first_observation.model_copy(
                update={
                    "owner": first_observation.owner.model_copy(
                        update={"case_id": "wrong_case"}
                    )
                }
            )
        }
    )
    conflicting = first.model_copy(
        update={"cases": (conflicting_case, *first.cases[1:])}
    )
    conflicting_artifact = build_synthetic_suite_artifact(
        suite=suite,
        result=conflicting,
    )
    assert conflicting_artifact.complete_admission is False
    assert conflicting_artifact.artifact.conclusion.value == "invalid"
    assert conflicting_artifact.counts.invalid == 1
    assert (
        conflicting_artifact.artifact.case_rows[0].evidence_availability.value
        == "conflicting"
    )
    missing_case = first.cases[0].model_copy(
        update={"case_observation": None}
    )
    missing = first.model_copy(
        update={"cases": (missing_case, *first.cases[1:])}
    )
    missing_artifact = build_synthetic_suite_artifact(
        suite=suite,
        result=missing,
    )
    assert missing_artifact.complete_admission is False
    assert missing_artifact.artifact.conclusion.value == "invalid"
    assert missing_artifact.counts.invalid == 1
    assert tuple(
        item.normalization_artifact.normalization_hash
        for item in first.cases
        if item.normalization_artifact is not None
    ) == tuple(
        item.normalization_artifact.normalization_hash
        for item in second.cases
        if item.normalization_artifact is not None
    )
    assert _stable_suite_signature(first) == _stable_suite_signature(second)
    for root in roots:
        assert tuple(root.glob("workspace_*")) == ()


async def _exercise_unsafe_context_refusal(tmp_path: Path) -> None:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        Path("tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"),
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    case = next(
        item
        for item in suite.cases
        if item.case_id == "context_unsafe_compression_refusal"
    )
    runtime = SyntheticFixtureRuntime(
        sealed_fixture_root=Path(
            "tests/fixtures/evaluations/"
            "general_writing_agent_benchmark/fixtures/core_novel"
        ),
        workspaces_root=tmp_path,
    )

    observation = await runtime.execute(case)

    assert observation.run is not None
    assert observation.run.status is GeneralAgentRunStatus.FAILED
    assert observation.run.resumable is False
    assert observation.run.plan is None
    assert observation.run.node_runs == []
    assert observation.run.final_answer
    assert any(
        json.loads(error).get("reason_code") == "unsafe_context"
        for error in observation.run.errors
    )
    assert observation.interactions == ()
    assert observation.runtime_facts is not None
    assert observation.runtime_facts.invocations == ()
    assert observation.runtime_facts.effects == ()
    assert observation.runtime_facts.terminal.run_status == "safe_failure"
    assert observation.runtime_facts.terminal.stop_reason == "unsafe_context"
    assert observation.runtime_facts.terminal.resumable is False
    failure_artifact = next(
        item
        for item in observation.runtime_facts.artifacts
        if item.artifact_kind == "runtime_safe_failure"
    )
    assert failure_artifact.payload["run_status"] == "failed"
    assert failure_artifact.payload["resumable"] is False
    assert failure_artifact.payload["plan_present"] is False
    assert failure_artifact.payload["node_count"] == 0
    assert failure_artifact.payload["interaction_count"] == 0
    assert failure_artifact.payload["capability_result_count"] == 0
    assert failure_artifact.payload["effect_count"] == 0
    assert observation.runtime_facts.recovery_decisions
    assert observation.runtime_facts.recovery_decisions[0].action == "stop"
    assert (
        observation.runtime_facts.recovery_decisions[0].reason_code
        == "unsafe_context"
    )
    refusal = SimpleNamespace(
        reason_code="unsafe_context",
        run_status="safe_failure",
        resumable=False,
    )
    with pytest.raises(RuntimeError, match="只有生产 Runtime"):
        _unsafe_context_terminal_observation(
            observation.run.model_copy(update={"resumable": True}),
            refusal=refusal,
            interaction_count=0,
            capability_result_count=0,
            effect_count=0,
        )
    with pytest.raises(RuntimeError, match="只有生产 Runtime"):
        _unsafe_context_terminal_observation(
            observation.run.model_copy(
                update={"errors": ['{"reason_code":"ordinary_failure"}']}
            ),
            refusal=refusal,
            interaction_count=0,
            capability_result_count=0,
            effect_count=0,
        )
    for counts in (
        {"interaction_count": 1, "capability_result_count": 0, "effect_count": 0},
        {"interaction_count": 0, "capability_result_count": 1, "effect_count": 0},
        {"interaction_count": 0, "capability_result_count": 0, "effect_count": 1},
    ):
        with pytest.raises(RuntimeError, match="只有生产 Runtime"):
            _unsafe_context_terminal_observation(
                observation.run,
                refusal=refusal,
                **counts,
            )
    assert tuple(tmp_path.glob("workspace_*")) == ()


def _load_typed_oracle(suite: AuthoredSuiteSpec) -> TypedOracle:
    fixture_root = Path(
        "tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel"
    )
    fixture_manifest = __import__("json").loads(
        (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    claim_catalog = load_claim_catalog(
        Path(
            "tests/fixtures/evaluations/general_writing_agent_benchmark/"
            "claim-catalog.json"
        ),
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(
            item["asset_id"] for item in fixture_manifest["scenario_assets"]
        ),
        referenced_claim_ids=tuple(
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
        ),
    )
    return TypedOracle(catalog=claim_catalog)


def _stable_suite_signature(result: object) -> tuple[object, ...]:
    cases = getattr(result, "cases")
    return tuple(
        (
            case.case_id,
            case.conclusion.value,
            tuple(
                sorted(
                    (
                        invocation.kind.value,
                        invocation.capability_name,
                        invocation.handler_identity,
                        invocation.outcome,
                    )
                    for invocation in case.invocations
                )
            ),
            tuple(
                (
                    gate.gate_kind.value,
                    gate.status.value,
                    tuple(condition.condition_id for condition in gate.conditions),
                )
                for gate in case.gates
            ),
            case.protocol_error_code,
            case.problems,
        )
        for case in cases
    )


async def _exercise_real_checkpoint_recovery_case(tmp_path: Path) -> None:
    catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        Path("tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"),
        expected_capability_catalog_hash=catalog.canonical_hash,
    )
    base_case = next(
        item
        for item in suite.cases
        if item.case_id == "recovery_verification_interruption"
    )
    case = base_case.model_copy(
        update={
            "name": "检查点恢复",
            "user_request": "故障后从同一检查点恢复。",
            "user_request_raw": "故障后从同一检查点恢复。",
            "required_invocations": (),
            "scripted_steps": (
            ScriptedStep(
                step_id="checkpoint_plan",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(ScriptedMatcher(path="/phase", expected="plan"),),
                evidence_projection=("/phase",),
                response={
                    "rationale": "先读取小说结构，再验证同一运行恢复。",
                    "nodes": [
                        {
                            "node_id": "read_structure_before_fault",
                            "kind": "tool",
                            "capability_name": "get_novel_structure",
                            "objective": "读取当前小说结构。",
                            "input_data": {},
                        }
                    ],
                },
            ),
            ScriptedStep(
                step_id="checkpoint_structure",
                sequence=1,
                kind=InteractionKind.TOOL,
                name="get_novel_structure",
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected="get_novel_structure",
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
            ScriptedStep(
                step_id="checkpoint_verify_after_resume",
                sequence=2,
                kind=InteractionKind.MODEL,
                name="orchestrator_verify",
                matchers=(ScriptedMatcher(path="/phase", expected="verify"),),
                evidence_projection=("/phase",),
                response={
                    "outcome": "satisfied",
                    "final_answer": "同一运行已从检查点恢复。",
                    "issues": [],
                    "should_replan": False,
                },
            ),
            ),
        },
    )
    fixture_root = Path(
        "tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel"
    )
    runtime = SyntheticFixtureRuntime(
        sealed_fixture_root=fixture_root,
        workspaces_root=tmp_path,
    )

    observation = await runtime.execute(case)

    tools = [
        record
        for record in observation.interactions
        if record.interaction.kind is InteractionKind.TOOL
    ]
    recovery = observation.normalized_result["recovery"]
    assert observation.normalized_result["status"] == "completed"
    assert [record.interaction.name for record in tools] == ["get_novel_structure"]
    assert recovery["triggered_ordinals"] == (1,)
    assert recovery["decisions"]
    assert all(
        decision["action"] in {"resume", "reuse_result"}
        and decision["reason_code"]
        and decision["checkpoint_revision_present"] is True
        for decision in recovery["decisions"]
    )


async def _exercise_real_search_case(tmp_path: Path) -> None:
    fixture_chapter = Path(
        "tests/fixtures/evaluations/general_writing_agent_benchmark/"
        "fixtures/core_novel/manuscripts/chapters/chapter_001.md"
    ).read_text(encoding="utf-8")
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "第一章 潮痕",
    )
    chapter_id = outline.current_chapter_id or ""
    await chapter_service.save_chapter(chapter_id, fixture_chapter)

    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="plan_search",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(ScriptedMatcher(path="/phase", expected="plan"),),
                evidence_projection=("/phase",),
                response={
                    "rationale": "需要用真实正文检索定位归潮灯描写。",
                    "nodes": [
                        {
                            "node_id": "search_fixture",
                            "kind": "tool",
                            "capability_name": "retrieve_story_context",
                            "objective": "检索归潮灯描写。",
                            "input_data": {"query": "归潮灯"},
                        }
                    ],
                },
            ),
            ScriptedStep(
                step_id="real_search",
                sequence=1,
                kind=InteractionKind.TOOL,
                name="retrieve_story_context",
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected="retrieve_story_context",
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
            ScriptedStep(
                step_id="verify_search",
                sequence=2,
                kind=InteractionKind.MODEL,
                name="orchestrator_verify",
                matchers=(ScriptedMatcher(path="/phase", expected="verify"),),
                evidence_projection=("/phase",),
                response={
                    "outcome": "satisfied",
                    "final_answer": "第一章中已定位到归潮灯相关描写。",
                    "issues": [],
                    "should_replan": False,
                },
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    gateway = StrictSyntheticLLMGateway(driver)
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "outline_service": outline_service,
            "vector_graph_rag_service": _ChapterStoryContextService(chapter_service),
            "invocation_policy_service": policy,
        }
    )
    physical_tools = ToolRegistry(tool_context, traces)
    physical_tools.register(
        ToolPlugin(
            manifest=retrieve_story_context.manifest,
            run=retrieve_story_context.run,
        )
    )
    tools = ObservedToolRegistry(
        physical_tools,
        observer=observer,
        handler_identities={
            "retrieve_story_context": (
                f"{retrieve_story_context.run.__module__}:"
                f"{retrieve_story_context.run.__qualname__}"
            )
        },
    )
    subagents = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": GatewayChatModel(gateway, model_id="synthetic-model"),
                "model_role_router": ModelRoleRouter("synthetic-model"),
                "tool_registry": tools,
            }
        ),
        traces,
    )
    memory = AgentMemoryService(
        repository=in_memory_agent_memory_repository(tmp_path),
    )
    checkpoints = InMemorySaver()
    effects = JsonGeneralAgentEffectRepository(tmp_path)
    capability_results = in_memory_capability_result_repository(
        tmp_path / "runtime" / "capability_results"
    )
    runtime = GeneralAgentRuntimeService(
        repository=JsonGeneralAgentRunRepository(tmp_path),
        event_center=GeneralAgentEventCenter(),
        orchestrator=OrchestratorAgent(
            llm=GatewayChatModel(gateway, model_id="synthetic-model"),
            model_router=ModelRoleRouter("synthetic-model"),
            tool_registry=tools,
            subagent_registry=subagents,
            trace_repository=traces,
        ),
        executor=DynamicDagExecutor(
            tool_registry=tools,
            subagent_registry=subagents,
            policy_service=policy,
            capability_result_repository=capability_results,
            capability_handler_identities=_handler_identities(
                tools,
                subagents,
            ),
            effect_repository=effects,
        ),
        policy_service=policy,
        memory_service=memory,
        context_assembler=ContextAssembler(memory_service=memory),
        capability_result_repository=capability_results,
        graph_checkpointer=checkpoints,
        effect_repository=effects,
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(tmp_path),
        llm_replay_repository=JsonLLMCallReplayRepository(tmp_path),
    )

    run = await runtime.run(user_goal="第一章归潮灯亮起后照出了什么？")
    normalized = driver.finalize(
        script_identity=canonical_sha256(
            [step.model_dump(mode="json") for step in driver.steps]
        ),
        runtime_config_identity="1" * 64,
        normalized_result={
            "status": run.status.value,
            "capability_names": [
                item.interaction.name for item in observer.capability_records
            ],
        },
    )

    assert run.status.value == "completed"
    assert observer.capability_records[0].interaction.outcome == "completed"
    assert observer.capability_records[0].handler_identity.endswith(
        "retrieve_story_context:run"
    )
    assert any(
        getattr(record, "capability_name", "") == "retrieve_story_context"
        and getattr(record, "status", "") == "completed"
        for record in traces.records
    )
    assert run.checkpoint_revision > 0
    assert normalized.consumption_trace[1]["name"] == "retrieve_story_context"
    effect_rows = await effects.list_effects(run.run_id)
    assert effect_rows == []


async def _exercise_real_canon_subagent_case(tmp_path: Path) -> None:
    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="plan_canon",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(ScriptedMatcher(path="/phase", expected="plan"),),
                evidence_projection=("/phase",),
                response={
                    "rationale": "需要由小说事实证据子智能体核对固定上下文。",
                    "nodes": [
                        {
                            "node_id": "canon_fixture",
                            "kind": "subagent",
                            "capability_name": "canon_evidence",
                            "objective": "核对归潮灯规则。",
                            "input_data": {
                                "question": "归潮灯的规则是什么？",
                                "source_request": {
                                    "auto_collect": False,
                                    "direct_context": (
                                        "归潮灯只会照出被海雾抹去的旧航迹。"
                                    ),
                                },
                            },
                        }
                    ],
                },
            ),
            ScriptedStep(
                step_id="canon_model",
                sequence=1,
                kind=InteractionKind.MODEL,
                name="canon_evidence_model",
                matchers=(
                    ScriptedMatcher(
                        path="/phase",
                        expected="canon_evidence",
                    ),
                ),
                evidence_projection=("/phase",),
                response={
                    "answer": "归潮灯只会照出被海雾抹去的旧航迹。",
                    "confidence": "high",
                    "evidence": [],
                    "conflicting_evidence": [],
                    "unknowns": [],
                    "source_refs": [],
                    "warnings": [],
                },
            ),
            ScriptedStep(
                step_id="real_canon",
                sequence=2,
                kind=InteractionKind.SUBAGENT,
                name="canon_evidence",
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected="canon_evidence",
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
            ScriptedStep(
                step_id="verify_canon",
                sequence=3,
                kind=InteractionKind.MODEL,
                name="orchestrator_verify",
                matchers=(ScriptedMatcher(path="/phase", expected="verify"),),
                evidence_projection=("/phase",),
                response={
                    "outcome": "satisfied",
                    "final_answer": "归潮灯只会照出被海雾抹去的旧航迹。",
                    "issues": [],
                    "should_replan": False,
                },
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    gateway = StrictSyntheticLLMGateway(driver)
    traces = _TraceRepository()
    policy = InvocationPolicyService()
    allowed = canon_evidence.manifest.allowed_tools
    read_plugins = [
        plugin
        for plugin in discover_tools("taichu.application.tools")
        if plugin.manifest.name in allowed
    ]
    required_services = set().union(
        *(plugin.manifest.required_capabilities for plugin in read_plugins)
    )
    tool_context = CapabilityContext(
        capabilities={
            name: (
                policy if name == "invocation_policy_service" else MagicMock(name=name)
            )
            for name in required_services
        }
    )
    tools = ToolRegistry(tool_context, traces)
    for plugin in read_plugins:
        tools.register(plugin)
    physical_subagents = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": GatewayChatModel(gateway, model_id="synthetic-model"),
                "model_role_router": ModelRoleRouter(
                    "synthetic-model",
                    {"canon_evidence": "synthetic-model"},
                ),
                "tool_registry": tools,
                "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
                "invocation_trace_repository": traces,
            }
        ),
        traces,
    )
    physical_subagents.register(
        SubagentPlugin(
            manifest=canon_evidence.manifest,
            run=canon_evidence.run,
        )
    )
    subagents = ObservedSubagentRegistry(
        physical_subagents,
        observer=observer,
        handler_identities={
            "canon_evidence": (
                f"{canon_evidence.run.__module__}:{canon_evidence.run.__qualname__}"
            )
        },
    )
    memory = AgentMemoryService(
        repository=in_memory_agent_memory_repository(tmp_path),
    )
    checkpoints = InMemorySaver()
    effects = JsonGeneralAgentEffectRepository(tmp_path)
    capability_results = in_memory_capability_result_repository(
        tmp_path / "runtime" / "capability_results"
    )
    runtime = GeneralAgentRuntimeService(
        repository=JsonGeneralAgentRunRepository(tmp_path),
        event_center=GeneralAgentEventCenter(),
        orchestrator=OrchestratorAgent(
            llm=GatewayChatModel(gateway, model_id="synthetic-model"),
            model_router=ModelRoleRouter("synthetic-model"),
            tool_registry=tools,
            subagent_registry=subagents,
            trace_repository=traces,
        ),
        executor=DynamicDagExecutor(
            tool_registry=tools,
            subagent_registry=subagents,
            policy_service=policy,
            capability_result_repository=capability_results,
            capability_handler_identities=_handler_identities(
                tools,
                subagents,
            ),
            effect_repository=effects,
        ),
        policy_service=policy,
        memory_service=memory,
        context_assembler=ContextAssembler(memory_service=memory),
        capability_result_repository=capability_results,
        graph_checkpointer=checkpoints,
        effect_repository=effects,
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(tmp_path),
        llm_replay_repository=JsonLLMCallReplayRepository(tmp_path),
    )

    run = await runtime.run(user_goal="归潮灯的规则是什么？")
    normalization = driver.finalize(
        script_identity=canonical_sha256(
            [step.model_dump(mode="json") for step in driver.steps]
        ),
        runtime_config_identity="2" * 64,
        normalized_result={
            "status": run.status.value,
            "artifact_refs": run.node_runs[-1].artifact_refs,
        },
    )

    assert run.status.value == "completed"
    record = observer.capability_records[0]
    assert record.interaction.name == "canon_evidence"
    assert record.interaction.outcome == "completed"
    assert record.handler_identity.endswith("canon_evidence.agent:run")
    subagent_trace = next(
        trace
        for trace in traces.records
        if getattr(trace, "capability_name", "") == "canon_evidence"
        and getattr(trace, "capability_type", "") == "subagent"
    )
    assert getattr(subagent_trace, "status", "") == "completed"
    internal_llm_trace = next(
        trace
        for trace in traces.records
        if getattr(trace, "capability_type", "") == "llm"
        and getattr(trace, "caller_name", "") == "canon_evidence"
    )
    assert internal_llm_trace.parent_call_id == subagent_trace.call_id
    assert any(
        getattr(trace, "capability_name", "") == "canon_evidence"
        and getattr(trace, "status", "") == "completed"
        for trace in traces.records
    )
    assert run.node_runs[-1].artifact_refs
    assert normalization.consumption_trace[2]["name"] == "canon_evidence"


async def _exercise_real_authorized_write_case(tmp_path: Path) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "第一章 潮痕",
    )
    chapter_id = outline.current_chapter_id or ""
    original = "归潮灯在雾中亮起。"
    await chapter_service.save_chapter(chapter_id, original)
    base_hash = sha256_text(original)
    operations = [{"operation": "append", "text": "\n灯影照见旧航迹。"}]
    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="plan_write",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(ScriptedMatcher(path="/phase", expected="plan"),),
                evidence_projection=("/phase",),
                response={
                    "rationale": "先预览正文补丁，再等待作者授权后写入。",
                    "nodes": [
                        {
                            "node_id": "preview_patch",
                            "kind": "tool",
                            "capability_name": "preview_manuscript_patch",
                            "objective": "生成补丁预览。",
                            "input_data": {
                                "chapter_id": chapter_id,
                                "base_content_sha256": base_hash,
                                "operations": operations,
                            },
                        },
                        {
                            "node_id": "apply_patch",
                            "kind": "tool",
                            "capability_name": "apply_manuscript_patch",
                            "objective": "在作者授权后写入补丁。",
                            "dependencies": ["preview_patch"],
                            "input_data": {},
                            "input_bindings": [
                                {
                                    "source_node_id": "preview_patch",
                                    "source_path": "patch_id",
                                    "target_path": "patch_id",
                                },
                                {
                                    "source_node_id": "preview_patch",
                                    "source_path": "chapter_id",
                                    "target_path": "chapter_id",
                                },
                                {
                                    "source_node_id": "preview_patch",
                                    "source_path": "base_content_sha256",
                                    "target_path": "base_content_sha256",
                                },
                                {
                                    "source_node_id": "preview_patch",
                                    "source_path": "expected_content_sha256",
                                    "target_path": "expected_content_sha256",
                                },
                                {
                                    "source_node_id": "preview_patch",
                                    "source_path": "normalized_operations",
                                    "target_path": "operations",
                                },
                            ],
                        },
                    ],
                },
            ),
            ScriptedStep(
                step_id="real_preview",
                sequence=1,
                kind=InteractionKind.TOOL,
                name="preview_manuscript_patch",
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected="preview_manuscript_patch",
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
            ScriptedStep(
                step_id="real_authorization",
                sequence=2,
                kind=InteractionKind.HUMAN,
                name="write_authorization",
                matchers=(ScriptedMatcher(path="/approved", expected=True),),
                evidence_projection=("/approved",),
            ),
            ScriptedStep(
                step_id="real_apply",
                sequence=3,
                kind=InteractionKind.TOOL,
                name="apply_manuscript_patch",
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected="apply_manuscript_patch",
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
            ScriptedStep(
                step_id="verify_write",
                sequence=4,
                kind=InteractionKind.MODEL,
                name="orchestrator_verify",
                matchers=(ScriptedMatcher(path="/phase", expected="verify"),),
                evidence_projection=("/phase",),
                response={
                    "outcome": "satisfied",
                    "final_answer": "作者授权后已写入正文补丁。",
                    "issues": [],
                    "should_replan": False,
                },
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    gateway = StrictSyntheticLLMGateway(driver)
    traces = _TraceRepository()
    policy = InvocationPolicyService()
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "invocation_policy_service": policy,
        }
    )
    physical_tools = ToolRegistry(tool_context, traces)
    for module in (preview_manuscript_patch, apply_manuscript_patch):
        physical_tools.register(
            ToolPlugin(
                manifest=module.manifest,
                run=module.run,
                reconcile=getattr(module, "reconcile", None),
            )
        )
    tools = ObservedToolRegistry(
        physical_tools,
        observer=observer,
        handler_identities={
            module.manifest.name: (f"{module.run.__module__}:{module.run.__qualname__}")
            for module in (preview_manuscript_patch, apply_manuscript_patch)
        },
    )
    subagents = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": GatewayChatModel(gateway, model_id="synthetic-model"),
                "model_role_router": ModelRoleRouter("synthetic-model"),
                "tool_registry": tools,
            }
        ),
        traces,
    )
    memory = AgentMemoryService(
        repository=in_memory_agent_memory_repository(tmp_path),
    )
    checkpoints = InMemorySaver()
    effects = JsonGeneralAgentEffectRepository(tmp_path)
    capability_results = in_memory_capability_result_repository(
        tmp_path / "runtime" / "capability_results"
    )
    runtime = GeneralAgentRuntimeService(
        repository=JsonGeneralAgentRunRepository(tmp_path),
        event_center=GeneralAgentEventCenter(),
        orchestrator=OrchestratorAgent(
            llm=GatewayChatModel(gateway, model_id="synthetic-model"),
            model_router=ModelRoleRouter("synthetic-model"),
            tool_registry=tools,
            subagent_registry=subagents,
            trace_repository=traces,
        ),
        executor=DynamicDagExecutor(
            tool_registry=tools,
            subagent_registry=subagents,
            policy_service=policy,
            capability_result_repository=capability_results,
            capability_handler_identities=_handler_identities(
                tools,
                subagents,
            ),
            effect_repository=effects,
        ),
        policy_service=policy,
        memory_service=memory,
        context_assembler=ContextAssembler(memory_service=memory),
        capability_result_repository=capability_results,
        graph_checkpointer=checkpoints,
        effect_repository=effects,
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(tmp_path),
        llm_replay_repository=JsonLLMCallReplayRepository(tmp_path),
    )

    waiting = await runtime.run(user_goal="把灯影照见旧航迹追加到第一章。")
    assert waiting.status.value == "waiting_human"
    request = waiting.pending_human_request
    assert request is not None
    assert request.kind == "write_authorization"
    observer.record_human_decision(
        request=request,
        source_run_id=waiting.run_id,
        approved=True,
        second_confirmation=False,
    )
    completed = await runtime.resume(waiting.run_id, approve=True)
    driver.finalize(
        script_identity=canonical_sha256(
            [step.model_dump(mode="json") for step in driver.steps]
        ),
        runtime_config_identity="3" * 64,
        normalized_result={"status": completed.status.value},
    )

    assert completed.status.value == "completed"
    saved = await chapter_service.read_chapter(chapter_id)
    assert saved.markdown.endswith("灯影照见旧航迹。")
    records = observer.capability_records
    assert [record.interaction.name for record in records] == [
        "preview_manuscript_patch",
        "apply_manuscript_patch",
    ]
    effect_rows = await effects.list_effects(completed.run_id)
    assert effect_rows
    assert any(
        getattr(effect, "tool_name", "") == "apply_manuscript_patch"
        for effect in effect_rows
    )


async def _exercise_real_external_case(tmp_path: Path) -> None:
    suite_payload = __import__("json").loads(
        Path(
            "tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json"
        ).read_text(encoding="utf-8")
    )
    case = AuthoredCaseSpec.model_validate(
        next(
            item
            for item in suite_payload["cases"]
            if item["case_id"] == "external_research_grounded"
        )
    )
    driver = StrictScriptedDriver(case.scripted_steps)
    observer = StrictSyntheticInteractionObserver(driver)
    gateway = StrictSyntheticLLMGateway(driver)
    traces = _TraceRepository()
    policy = InvocationPolicyService()
    external_root = Path(
        "tests/fixtures/evaluations/general_writing_agent_benchmark/"
        "fixtures/core_novel/external_sources"
    )
    tool_context = CapabilityContext(
        capabilities={
            "external_research_service": ExternalResearchService(
                FixtureExternalResearchBackend(external_root)
            ),
            "invocation_policy_service": policy,
        }
    )
    physical_tools = ToolRegistry(tool_context, traces)
    for module in (search_external_sources, read_external_source):
        physical_tools.register(ToolPlugin(manifest=module.manifest, run=module.run))
    tools = ObservedToolRegistry(
        physical_tools,
        observer=observer,
        handler_identities={
            module.manifest.name: (f"{module.run.__module__}:{module.run.__qualname__}")
            for module in (search_external_sources, read_external_source)
        },
    )
    physical_subagents = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": GatewayChatModel(gateway, model_id="synthetic-model"),
                "model_role_router": ModelRoleRouter(
                    "synthetic-model",
                    {"external_research": "synthetic-model"},
                ),
                "tool_registry": tools,
                "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
                "invocation_trace_repository": traces,
            }
        ),
        traces,
    )
    physical_subagents.register(
        SubagentPlugin(
            manifest=external_research.manifest,
            run=external_research.run,
        )
    )
    subagents = ObservedSubagentRegistry(
        physical_subagents,
        observer=observer,
        handler_identities={
            "external_research": (
                f"{external_research.run.__module__}:"
                f"{external_research.run.__qualname__}"
            )
        },
    )
    memory = AgentMemoryService(
        repository=in_memory_agent_memory_repository(tmp_path),
    )
    checkpoints = InMemorySaver()
    effects = JsonGeneralAgentEffectRepository(tmp_path)
    capability_results = in_memory_capability_result_repository(
        tmp_path / "runtime" / "capability_results"
    )
    runtime = GeneralAgentRuntimeService(
        repository=JsonGeneralAgentRunRepository(tmp_path),
        event_center=GeneralAgentEventCenter(),
        orchestrator=OrchestratorAgent(
            llm=GatewayChatModel(gateway, model_id="synthetic-model"),
            model_router=ModelRoleRouter("synthetic-model"),
            tool_registry=tools,
            subagent_registry=subagents,
            trace_repository=traces,
        ),
        executor=DynamicDagExecutor(
            tool_registry=tools,
            subagent_registry=subagents,
            policy_service=policy,
            capability_result_repository=capability_results,
            capability_handler_identities=_handler_identities(
                tools,
                subagents,
            ),
            effect_repository=effects,
        ),
        policy_service=policy,
        memory_service=memory,
        context_assembler=ContextAssembler(memory_service=memory),
        capability_result_repository=capability_results,
        graph_checkpointer=checkpoints,
        effect_repository=effects,
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(tmp_path),
        llm_replay_repository=JsonLLMCallReplayRepository(tmp_path),
    )

    run = await runtime.run(
        user_goal=case.user_request,
        external_access_allowed=True,
    )
    driver.finalize(
        script_identity=canonical_sha256(
            [step.model_dump(mode="json") for step in driver.steps]
        ),
        runtime_config_identity="4" * 64,
        normalized_result={"status": run.status.value},
    )

    assert run.status.value == "completed"
    assert [record.interaction.name for record in observer.capability_records] == [
        "search_external_sources",
        "read_external_source",
        "external_research",
    ]
    subagent_trace = next(
        trace
        for trace in traces.records
        if getattr(trace, "capability_type", "") == "subagent"
    )
    nested = [
        trace
        for trace in traces.records
        if getattr(trace, "capability_type", "") == "tool"
    ]
    assert {trace.parent_call_id for trace in nested} == {subagent_trace.call_id}
    nested_llm = next(
        trace
        for trace in traces.records
        if getattr(trace, "capability_type", "") == "llm"
        and getattr(trace, "caller_name", "") == "external_research"
    )
    assert nested_llm.parent_call_id == subagent_trace.call_id
