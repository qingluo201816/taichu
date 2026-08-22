"""不经过 Web 组合根的通用写作智能体评测 Runtime 工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_context_snapshot import (
    GeneralAgentContextSnapshotRepository,
)
from taichu.application.contracts.general_agent_capability_results import (
    GeneralAgentCapabilityResultRepository,
)
from taichu.application.contracts.general_agent_effects import (
    GeneralAgentEffectRepository,
)
from taichu.application.contracts.general_agent_run import (
    GeneralAgentRunRepository,
)
from taichu.application.contracts.invocation_trace import (
    InvocationTraceRepository,
)
from taichu.application.contracts.llm import LLMGatewayContract
from taichu.application.contracts.llm_replay import LLMCallReplayRepository
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.capability_catalog import (
    CORE_TOOL_NAMES,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CapabilityCatalogSnapshot,
    CapabilityDescriptor,
    CapabilityKind,
    SubagentToolDependency,
)
from taichu.application.general_agent.context import ContextAssembler
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.faults import GeneralAgentFaultHook
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.services.agent_memory_service import AgentMemoryService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.subagents.registry import (
    SubagentNotFoundError,
    SubagentRegistry,
)
from taichu.application.tools.contract import ToolManifest, ToolPlugin
from taichu.application.tools.registry import ToolNotFoundError, ToolRegistry
from taichu.infrastructure.plugin_discovery import discover_subagents, discover_tools
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    ObservedSubagentRegistry,
    ObservedToolRegistry,
    StrictSyntheticInteractionObserver,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentCapabilityResultRepository,
)

_ISOLATED_DATABASE = re.compile(r"^taichu_eval_[a-f0-9]{32}$")


def production_capability_catalog_snapshot() -> CapabilityCatalogSnapshot:
    """从真实生产发现结果生成稳定能力身份，不注册或调用能力。"""
    tools = [
        plugin
        for plugin in discover_tools("taichu.application.tools")
        if plugin.manifest.name in CORE_TOOL_NAMES
    ]
    subagents = discover_subagents("taichu.application.subagents")
    tool_descriptors = tuple(
        CapabilityDescriptor(
            capability_id=plugin.manifest.name,
            kind=CapabilityKind.TOOL,
            manifest_identity=_manifest_identity(plugin.manifest),
            handler_identity=f"{plugin.run.__module__}:{plugin.run.__qualname__}",
        )
        for plugin in sorted(tools, key=lambda item: item.manifest.name)
    )
    subagent_descriptors = tuple(
        CapabilityDescriptor(
            capability_id=plugin.manifest.name,
            kind=CapabilityKind.SUBAGENT,
            manifest_identity=_manifest_identity(plugin.manifest),
            handler_identity=f"{plugin.run.__module__}:{plugin.run.__qualname__}",
        )
        for plugin in sorted(subagents, key=lambda item: item.manifest.name)
    )
    dependencies = tuple(
        SubagentToolDependency(
            subagent_id=plugin.manifest.name,
            tool_id=tool_name,
        )
        for plugin in sorted(subagents, key=lambda item: item.manifest.name)
        for tool_name in sorted(plugin.manifest.allowed_tools)
    )
    return CapabilityCatalogSnapshot.create(
        tools=tool_descriptors,
        subagents=subagent_descriptors,
        registration_dependencies=dependencies,
        discovered_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def _manifest_identity(manifest: Any) -> str:
    payload = manifest.model_dump(mode="python")
    for key in ("input_schema", "output_schema"):
        schema_type = payload.get(key)
        if isinstance(schema_type, type):
            payload[key] = f"{schema_type.__module__}:{schema_type.__qualname__}"
    return canonical_sha256(payload)


@dataclass(frozen=True)
class BenchmarkRuntimeDependencies:
    """由案例隔离控制面显式提供的生产 Runtime 依赖。"""

    workspace: Path
    database_name: str
    capability_context: CapabilityContext
    llm: LLMGatewayContract
    model_router: ModelRoleRouter
    trace_repository: InvocationTraceRepository | None
    run_repository: GeneralAgentRunRepository
    event_center: GeneralAgentEventCenter
    policy_service: InvocationPolicyService
    memory_service: AgentMemoryService
    context_assembler: ContextAssembler
    graph_checkpointer: BaseCheckpointSaver[Any]
    effect_repository: GeneralAgentEffectRepository
    context_snapshot_repository: GeneralAgentContextSnapshotRepository
    llm_replay_repository: LLMCallReplayRepository
    interaction_observer: StrictSyntheticInteractionObserver | None = None
    fault_hook: GeneralAgentFaultHook | None = None


@dataclass(frozen=True)
class IsolatedBenchmarkRuntime:
    """物理完整注册、案例 exposure 独立声明的评测 Runtime 组合结果。"""

    runtime: GeneralAgentRuntimeService
    tool_registry: ToolRegistry
    subagent_registry: SubagentRegistry
    allowed_capabilities: frozenset[str]
    workspace: Path
    database_name: str
    capability_result_repository: GeneralAgentCapabilityResultRepository

    @property
    def physical_capability_count(self) -> int:
        return len(self.tool_registry.list_manifests()) + len(
            self.subagent_registry.list_manifests()
        )


class GeneralAgentBenchmarkRuntimeFactory:
    """只在受控 workspace/database 中显式组合真实生产能力。"""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()

    def create(
        self,
        dependencies: BenchmarkRuntimeDependencies,
        *,
        allowed_capabilities: frozenset[str],
        tool_manifest_overrides: dict[str, ToolManifest] | None = None,
    ) -> IsolatedBenchmarkRuntime:
        workspace = dependencies.workspace.resolve()
        if not workspace.is_relative_to(self._workspace_root):
            raise ValueError("evaluation workspace 不属于受控 workspace root。")
        if not _ISOLATED_DATABASE.fullmatch(dependencies.database_name):
            raise ValueError("evaluation database 必须使用 taichu_eval_<32hex>。")
        self._validate_capability_isolation(
            dependencies.capability_context,
            workspace=workspace,
            database_name=dependencies.database_name,
        )

        tools = [
            plugin
            for plugin in discover_tools("taichu.application.tools")
            if plugin.manifest.name in CORE_TOOL_NAMES
        ]
        overrides = tool_manifest_overrides or {}
        unknown_overrides = set(overrides) - {
            plugin.manifest.name for plugin in tools
        }
        if unknown_overrides:
            raise ValueError(
                "评测 Tool Manifest 覆盖包含未知能力："
                + ", ".join(sorted(unknown_overrides))
            )
        originals = {
            plugin.manifest.name: plugin.manifest for plugin in tools
        }
        for name, override in overrides.items():
            original = originals[name]
            restored = override.model_copy(
                update={
                    "authorization_policy": original.authorization_policy,
                }
            )
            if restored != original:
                raise ValueError(
                    "评测 Tool Manifest 只允许隔离授权策略，"
                    f"不得改变生产能力合同：{name}。"
                )
        tools = [
            ToolPlugin(
                manifest=overrides.get(plugin.manifest.name, plugin.manifest),
                run=plugin.run,
                reconcile=plugin.reconcile,
            )
            for plugin in tools
        ]
        subagents = discover_subagents("taichu.application.subagents")
        physical_names = {
            plugin.manifest.name for plugin in tools
        } | {plugin.manifest.name for plugin in subagents}
        unknown = allowed_capabilities - physical_names
        if unknown:
            raise ValueError(
                "case exposure 包含未知能力："
                + ", ".join(sorted(unknown))
            )

        tool_registry = ToolRegistry(
            dependencies.capability_context,
            dependencies.trace_repository,
        )
        tool_registry.register_all(tools)
        exposed_tool_registry = _ExposedToolRegistry(
            tool_registry,
            allowed_capabilities,
        )
        runtime_tool_registry: Any = exposed_tool_registry
        if dependencies.interaction_observer is not None:
            runtime_tool_registry = ObservedToolRegistry(
                exposed_tool_registry,  # type: ignore[arg-type]
                observer=dependencies.interaction_observer,
                handler_identities={
                    plugin.manifest.name: (
                        f"{plugin.run.__module__}:{plugin.run.__qualname__}"
                    )
                    for plugin in tools
                },
            )
        exposed_subagent_names = {
            plugin.manifest.name
            for plugin in subagents
            if plugin.manifest.name in allowed_capabilities
        }
        subagent_allowed_tools = frozenset(
            tool_name
            for plugin in subagents
            if plugin.manifest.name in exposed_subagent_names
            for tool_name in plugin.manifest.allowed_tools
        )
        subagent_tool_registry: Any = _SubagentToolRegistry(
            tool_registry,
            subagent_allowed_tools,
        )
        if dependencies.interaction_observer is not None:
            subagent_tool_registry = ObservedToolRegistry(
                subagent_tool_registry,
                observer=dependencies.interaction_observer,
                handler_identities={
                    plugin.manifest.name: (
                        f"{plugin.run.__module__}:{plugin.run.__qualname__}"
                    )
                    for plugin in tools
                },
            )
        subagent_context = CapabilityContext(
            capabilities={
                **dependencies.capability_context.capabilities,
                "tool_registry": subagent_tool_registry,
            }
        )
        subagent_registry = SubagentRegistry(
            subagent_context,
            dependencies.trace_repository,
        )
        subagent_registry.register_all(subagents)
        capability_result_repository = (
            JsonGeneralAgentCapabilityResultRepository(
                workspace / "runtime" / "capability_results"
            )
        )
        capability_handler_identities = {
            **{
                ("tool", plugin.manifest.name): (
                    f"{plugin.run.__module__}:{plugin.run.__qualname__}"
                )
                for plugin in tools
            },
            **{
                ("subagent", plugin.manifest.name): (
                    f"{plugin.run.__module__}:{plugin.run.__qualname__}"
                )
                for plugin in subagents
            },
        }

        exposed_subagent_registry = _ExposedSubagentRegistry(
            subagent_registry,
            allowed_capabilities,
        )
        runtime_subagent_registry: Any = exposed_subagent_registry
        if dependencies.interaction_observer is not None:
            runtime_subagent_registry = ObservedSubagentRegistry(
                exposed_subagent_registry,  # type: ignore[arg-type]
                observer=dependencies.interaction_observer,
                handler_identities={
                    plugin.manifest.name: (
                        f"{plugin.run.__module__}:{plugin.run.__qualname__}"
                    )
                    for plugin in subagents
                },
            )
        orchestrator = OrchestratorAgent(
            llm=dependencies.llm,
            model_router=dependencies.model_router,
            tool_registry=runtime_tool_registry,
            subagent_registry=runtime_subagent_registry,
            trace_repository=dependencies.trace_repository,
        )
        executor = DynamicDagExecutor(
            tool_registry=runtime_tool_registry,
            subagent_registry=runtime_subagent_registry,
            policy_service=dependencies.policy_service,
            capability_result_repository=capability_result_repository,
            capability_handler_identities=capability_handler_identities,
            graph_checkpointer=dependencies.graph_checkpointer,
            effect_repository=dependencies.effect_repository,
            fault_hook=dependencies.fault_hook,
        )
        runtime = GeneralAgentRuntimeService(
            repository=dependencies.run_repository,
            event_center=dependencies.event_center,
            orchestrator=orchestrator,
            executor=executor,
            policy_service=dependencies.policy_service,
            memory_service=dependencies.memory_service,
            context_assembler=dependencies.context_assembler,
            capability_result_repository=capability_result_repository,
            graph_checkpointer=dependencies.graph_checkpointer,
            effect_repository=dependencies.effect_repository,
            context_snapshot_repository=dependencies.context_snapshot_repository,
            llm_replay_repository=dependencies.llm_replay_repository,
            fault_hook=dependencies.fault_hook,
        )
        return IsolatedBenchmarkRuntime(
            runtime=runtime,
            tool_registry=tool_registry,
            subagent_registry=subagent_registry,
            allowed_capabilities=allowed_capabilities,
            workspace=workspace,
            database_name=dependencies.database_name,
            capability_result_repository=capability_result_repository,
        )

    @staticmethod
    def _validate_capability_isolation(
        context: CapabilityContext,
        *,
        workspace: Path,
        database_name: str,
    ) -> None:
        for capability_name, capability in context.capabilities.items():
            attributes = getattr(capability, "__dict__", {})
            for attribute_name in (
                "_assets_root",
                "_project_assets_dir",
                "_source_root",
            ):
                candidate = attributes.get(attribute_name)
                if isinstance(candidate, Path) and not candidate.resolve().is_relative_to(
                    workspace
                ):
                    raise ValueError(
                        f"能力 {capability_name} 引用了案例 workspace 外路径。"
                    )
            backend = attributes.get("_backend")
            if (
                capability_name == "external_research_service"
                and backend is not None
                and type(backend).__name__ == "DuckDuckGoExternalResearchBackend"
            ):
                raise ValueError("评测 Runtime 禁止使用联网外部研究 backend。")
            database = attributes.get("_database")
            configured_database = getattr(database, "name", None)
            if (
                capability_name in {"knowledge_repository", "knowledge_service"}
                and isinstance(configured_database, str)
                and configured_database != database_name
            ):
                raise ValueError("评测知识仓储未绑定隔离 database。")


class _ExposedToolRegistry(ToolRegistry):
    """保留物理注册表，只缩小本案例 Runtime 的可见与可调用面。"""

    def __init__(
        self,
        delegate: ToolRegistry,
        allowed: frozenset[str],
    ) -> None:
        self._delegate = delegate
        self._allowed = allowed

    def list_manifests(self):  # type: ignore[no-untyped-def]
        return [
            item
            for item in self._delegate.list_manifests()
            if item.name in self._allowed
        ]

    def get_manifest(self, name: str):  # type: ignore[no-untyped-def]
        if name not in self._allowed:
            raise ToolNotFoundError(name)
        return self._delegate.get_manifest(name)

    async def invoke(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        if name not in self._allowed:
            raise ToolNotFoundError(name)
        return await self._delegate.invoke(name, *args, **kwargs)

    async def reconcile(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        if name not in self._allowed:
            raise ToolNotFoundError(name)
        return await self._delegate.reconcile(name, *args, **kwargs)


class _SubagentToolRegistry(_ExposedToolRegistry):
    """注册时展示完整物理目录，调用时仍执行当前案例 exposure 门禁。"""

    def list_manifests(self):  # type: ignore[no-untyped-def]
        return self._delegate.list_manifests()


class _ExposedSubagentRegistry:
    """对子 Agent 使用与 Tool 相同的案例 exposure 门禁。"""

    def __init__(
        self,
        delegate: SubagentRegistry,
        allowed: frozenset[str],
    ) -> None:
        self._delegate = delegate
        self._allowed = allowed

    def list_manifests(self):  # type: ignore[no-untyped-def]
        return [
            item
            for item in self._delegate.list_manifests()
            if item.name in self._allowed
        ]

    def get_manifest(self, name: str):  # type: ignore[no-untyped-def]
        if name not in self._allowed:
            raise SubagentNotFoundError(name)
        return self._delegate.get_manifest(name)

    async def invoke(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        if name not in self._allowed:
            raise SubagentNotFoundError(name)
        return await self._delegate.invoke(name, *args, **kwargs)
