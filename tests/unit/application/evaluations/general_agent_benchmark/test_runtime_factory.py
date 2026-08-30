"""需求 10.1、10.4、10.8、10.13、10.21、10.30：独立评测 Runtime 组合。"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    CORE_SUBAGENT_NAMES,
    CORE_TOOL_NAMES,
)
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.faults import (
    GeneralAgentFaultContext,
    GeneralAgentFaultPoint,
)
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.tools.registry import ToolNotFoundError
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    BenchmarkRuntimeDependencies,
    GeneralAgentBenchmarkRuntimeFactory,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentContextSnapshotRepository,
    JsonGeneralAgentEffectRepository,
)
from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository
from taichu.infrastructure.plugin_discovery import discover_subagents, discover_tools


def _dependencies(workspace: Path) -> BenchmarkRuntimeDependencies:
    tools = discover_tools("taichu.application.tools")
    subagents = discover_subagents("taichu.application.subagents")
    capability_names = set().union(
        *(plugin.manifest.required_capabilities for plugin in tools),
        *(plugin.manifest.required_capabilities for plugin in subagents),
    )
    capabilities = {name: MagicMock(name=name) for name in capability_names}
    llm = capabilities["llm"]
    return BenchmarkRuntimeDependencies(
        workspace=workspace,
        database_name="taichu_eval_0123456789abcdef0123456789abcdef",
        capability_context=CapabilityContext(capabilities=capabilities),
        llm=llm,
        model_router=ModelRoleRouter("synthetic-model"),
        trace_repository=None,
        run_repository=MagicMock(name="run_repository"),
        event_center=GeneralAgentEventCenter(),
        policy_service=InvocationPolicyService(),
        memory_service=MagicMock(name="memory_service"),
        context_assembler=MagicMock(name="context_assembler"),
        graph_checkpointer=InMemorySaver(),
        effect_repository=JsonGeneralAgentEffectRepository(workspace),
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(
            workspace
        ),
        llm_replay_repository=JsonLLMCallReplayRepository(workspace),
    )


class _NoopFaultHook:
    def on_fault_point(
        self,
        *,
        point: GeneralAgentFaultPoint,
        context: GeneralAgentFaultContext,
    ) -> None:
        return None


def test_factory_registers_full_production_catalog_before_case_exposure(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "case_001"
    workspace.mkdir(parents=True)
    factory = GeneralAgentBenchmarkRuntimeFactory(workspace_root=workspace_root)

    bundle = factory.create(
        _dependencies(workspace),
        allowed_capabilities=frozenset(
            {"read_manuscript", "canon_evidence"}
        ),
    )

    assert {item.name for item in bundle.tool_registry.list_manifests()} == (
        CORE_TOOL_NAMES
    )
    assert {item.name for item in bundle.subagent_registry.list_manifests()} == (
        CORE_SUBAGENT_NAMES
    )
    assert bundle.allowed_capabilities == frozenset(
        {"read_manuscript", "canon_evidence"}
    )
    assert bundle.physical_capability_count == 28
    assert bundle.runtime is not None
    assert isinstance(bundle.capability_result_repository.store, InMemoryStore)
    assert (
        bundle.runtime._capability_result_repository
        is bundle.capability_result_repository
    )
    assert (
        bundle.runtime._executor.capability_result_repository
        is bundle.capability_result_repository
    )
    assert not (workspace / "runtime" / "capability_results").exists()
    runtime_tools = bundle.runtime._orchestrator._tool_registry.list_manifests()
    runtime_subagents = (
        bundle.runtime._orchestrator._subagent_registry.list_manifests()
    )
    assert {item.name for item in runtime_tools} == {"read_manuscript"}
    assert {item.name for item in runtime_subagents} == {"canon_evidence"}
    subagent_tools = bundle.subagent_registry._context.capabilities[
        "tool_registry"
    ]
    assert subagent_tools.get_manifest("retrieve_story_context").name == (
        "retrieve_story_context"
    )
    with pytest.raises(ToolNotFoundError, match="search_external_sources"):
        subagent_tools.get_manifest("search_external_sources")
    assert bundle.runtime._fault_hook is None
    assert bundle.runtime._executor.fault_hook is None


def test_factory_injects_one_generic_fault_hook_without_case_identifier(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "case_001"
    workspace.mkdir(parents=True)
    factory = GeneralAgentBenchmarkRuntimeFactory(workspace_root=workspace_root)
    hook = _NoopFaultHook()
    dependencies = BenchmarkRuntimeDependencies(
        **{
            **vars(_dependencies(workspace)),
            "fault_hook": hook,
        }
    )

    bundle = factory.create(
        dependencies,
        allowed_capabilities=frozenset({"read_manuscript"}),
    )

    assert bundle.runtime._fault_hook is hook
    assert bundle.runtime._executor.fault_hook is hook


def test_factory_has_no_active_app_or_global_switch_dependency(tmp_path: Path) -> None:
    source = inspect.getsource(GeneralAgentBenchmarkRuntimeFactory)
    assert "create_app" not in source
    assert "app.state" not in source
    assert "os.environ" not in source
    assert "Settings" not in source
    assert set(inspect.signature(GeneralAgentBenchmarkRuntimeFactory).parameters) == {
        "workspace_root"
    }

    factory = GeneralAgentBenchmarkRuntimeFactory(
        workspace_root=tmp_path / "workspaces"
    )
    outside = tmp_path / "activity" / "case_001"
    outside.mkdir(parents=True)
    with pytest.raises(ValueError, match="workspace"):
        factory.create(
            _dependencies(outside),
            allowed_capabilities=frozenset({"read_manuscript"}),
        )


def test_factory_rejects_invalid_database_or_unknown_exposure(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "case_001"
    workspace.mkdir(parents=True)
    factory = GeneralAgentBenchmarkRuntimeFactory(workspace_root=workspace_root)

    invalid_database = _dependencies(workspace)
    invalid_database = invalid_database.__class__(
        **{
            **vars(invalid_database),
            "database_name": "taichu",
        }
    )
    with pytest.raises(ValueError, match="database"):
        factory.create(
            invalid_database,
            allowed_capabilities=frozenset({"read_manuscript"}),
        )

    with pytest.raises(ValueError, match="unknown_capability"):
        factory.create(
            _dependencies(workspace),
            allowed_capabilities=frozenset({"unknown_capability"}),
        )
