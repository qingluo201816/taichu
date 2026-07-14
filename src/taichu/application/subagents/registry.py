"""专业子 Agent 的注册、权限校验和统一调用入口。"""

import asyncio
from collections.abc import Iterable
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel

from taichu.application.artifacts.models import IntermediateArtifactRecord
from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.intermediate_artifact import (
    IntermediateArtifactRepository,
)
from taichu.application.contracts.invocation_trace import InvocationTraceRepository
from taichu.application.invocations.models import (
    InvocationContext,
    InvocationEnvelope,
    InvocationStatus,
    InvocationTraceRecord,
    now_iso,
)
from taichu.application.services.invocation_policy_service import (
    canonical_input_hash,
)
from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentPlugin,
)
from taichu.application.tools.registry import ToolRegistry


class SubagentRegistry:
    """管理真实专业能力，不复用 Workflow 的 Graph 生命周期。"""

    def __init__(
        self,
        context: CapabilityContext,
        trace_repository: InvocationTraceRepository | None = None,
    ) -> None:
        self._context = context
        self._trace_repository = trace_repository
        self._plugins: dict[str, SubagentPlugin] = {}

    def register(self, plugin: SubagentPlugin) -> None:
        manifest = plugin.manifest
        if manifest.name in self._plugins:
            raise DuplicateSubagentError(manifest.name)
        missing = manifest.required_capabilities - self._context.capabilities.keys()
        if missing:
            raise SubagentRegistrationError(
                f"专业子智能体“{manifest.name}”缺少能力：{', '.join(sorted(missing))}"
            )
        registry = self._context.require("tool_registry", ToolRegistry)
        known_tools = {item.name for item in registry.list_manifests()}
        unknown_tools = manifest.allowed_tools - known_tools
        if unknown_tools:
            raise SubagentRegistrationError(
                f"专业子智能体“{manifest.name}”声明了未知工具："
                f"{', '.join(sorted(unknown_tools))}"
            )
        self._plugins[manifest.name] = plugin

    def register_all(self, plugins: Iterable[SubagentPlugin]) -> None:
        for plugin in plugins:
            self.register(plugin)

    def list_manifests(self) -> list[SubagentManifest]:
        return [self._plugins[name].manifest for name in sorted(self._plugins)]

    def get_manifest(self, name: str) -> SubagentManifest:
        if name not in self._plugins:
            raise SubagentNotFoundError(name)
        return self._plugins[name].manifest

    async def invoke(
        self,
        name: str,
        input_data: BaseModel | dict[str, object],
        invocation: InvocationContext,
    ) -> InvocationEnvelope[BaseModel]:
        if name not in self._plugins:
            raise SubagentNotFoundError(name)
        plugin = self._plugins[name]
        manifest = plugin.manifest
        parsed_input = manifest.input_schema.model_validate(input_data)
        started_at = now_iso()
        timer = perf_counter()
        try:
            async with asyncio.timeout(manifest.limits.timeout_seconds):
                raw_output = await plugin.run(
                    parsed_input,
                    invocation,
                    self._context,
                )
            output = manifest.output_schema.model_validate(raw_output)
            if len(output.model_dump_json()) > manifest.limits.max_output_chars:
                raise SubagentInvocationError(f"专业子智能体“{name}”输出超过字符预算。")
            finished_at = now_iso()
            duration_ms = max(0, round((perf_counter() - timer) * 1000))
            trace_id = f"trace_{uuid4().hex}"
            source_refs = _source_refs(output)
            artifact_id = f"artifact_{uuid4().hex}"
            await self._artifact_repository().save(
                IntermediateArtifactRecord(
                    artifact_id=artifact_id,
                    artifact_type=str(getattr(output, "artifact_type", manifest.name)),
                    producer=name,
                    task_id=invocation.task_id,
                    run_id=invocation.run_id,
                    call_id=invocation.call_id,
                    input_sha256=canonical_input_hash(parsed_input),
                    content_sha256=canonical_input_hash(output),
                    payload=output.model_dump(mode="json"),
                    source_refs=source_refs,
                    created_at=finished_at,
                )
            )
            await self._append_trace(
                InvocationTraceRecord(
                    trace_id=trace_id,
                    capability_type="subagent",
                    capability_name=name,
                    task_id=invocation.task_id,
                    run_id=invocation.run_id,
                    call_id=invocation.call_id,
                    parent_call_id=invocation.parent_call_id,
                    caller_type=invocation.caller_type,
                    caller_name=invocation.caller_name,
                    status=InvocationStatus.COMPLETED,
                    input_sha256=canonical_input_hash(parsed_input),
                    input_char_count=len(parsed_input.model_dump_json()),
                    output_char_count=len(output.model_dump_json()),
                    source_count=len(source_refs),
                    model_role=manifest.model_role,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )
            )
            return InvocationEnvelope[BaseModel](
                invocation_id=invocation.call_id,
                capability_type="subagent",
                capability_name=name,
                status=InvocationStatus.COMPLETED,
                output=output,
                source_refs=source_refs,
                artifact_refs=[artifact_id],
                trace_id=trace_id,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
            )
        except TimeoutError as error:
            await self._append_failure(
                manifest,
                parsed_input,
                invocation,
                started_at,
                timer,
                InvocationStatus.TIMED_OUT,
                error,
            )
            raise SubagentInvocationTimeoutError(name) from error
        except Exception as error:
            await self._append_failure(
                manifest,
                parsed_input,
                invocation,
                started_at,
                timer,
                InvocationStatus.FAILED,
                error,
            )
            raise

    async def _append_failure(
        self,
        manifest: SubagentManifest,
        parsed_input: BaseModel,
        invocation: InvocationContext,
        started_at: str,
        timer: float,
        status: InvocationStatus,
        error: Exception,
    ) -> None:
        await self._append_trace(
            InvocationTraceRecord(
                trace_id=f"trace_{uuid4().hex}",
                capability_type="subagent",
                capability_name=manifest.name,
                task_id=invocation.task_id,
                run_id=invocation.run_id,
                call_id=invocation.call_id,
                parent_call_id=invocation.parent_call_id,
                caller_type=invocation.caller_type,
                caller_name=invocation.caller_name,
                status=status,
                input_sha256=canonical_input_hash(parsed_input),
                input_char_count=len(parsed_input.model_dump_json()),
                model_role=manifest.model_role,
                started_at=started_at,
                finished_at=now_iso(),
                duration_ms=max(0, round((perf_counter() - timer) * 1000)),
                error_type=type(error).__name__,
                error_message=str(error)[:500],
            )
        )

    async def _append_trace(self, record: InvocationTraceRecord) -> None:
        if self._trace_repository is None:
            return
        try:
            await self._trace_repository.append(record)
        except Exception:  # noqa: BLE001
            return

    def _artifact_repository(self) -> IntermediateArtifactRepository:
        value = self._context.capabilities.get("artifact_repository")
        if not isinstance(value, IntermediateArtifactRepository):
            raise TypeError("专业子 Agent 缺少中间产物仓储。")
        return value


class SubagentRegistrationError(ValueError):
    """专业子 Agent 未通过能力或 Tool 权限校验。"""


class DuplicateSubagentError(SubagentRegistrationError):
    def __init__(self, name: str) -> None:
        super().__init__(f"专业子智能体“{name}”已经注册。")


class SubagentNotFoundError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"专业子智能体“{name}”不存在。")


class SubagentInvocationError(RuntimeError):
    """专业子 Agent 调用违反统一技术契约。"""


class SubagentInvocationTimeoutError(TimeoutError):
    def __init__(self, name: str) -> None:
        super().__init__(f"专业子智能体“{name}”执行超时。")


def _source_refs(output: BaseModel) -> list[str]:
    value = getattr(output, "source_refs", None)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
