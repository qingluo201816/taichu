"""按依赖和并发上限执行一次动态能力 DAG。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from taichu.application.general_agent.models import (
    GeneralAgentHumanRequest,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.invocations.models import (
    InvocationBudget,
    InvocationContext,
    now_iso,
)
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
    canonical_input_hash,
)
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools.contract import ToolAuthorizationPolicy
from taichu.application.tools.registry import ToolRegistry

CheckpointCallback = Callable[
    [GeneralAgentRun, str],
    Awaitable[GeneralAgentRun],
]


class DynamicDagExecutor:
    """仅调度注册表中的真实 Tool 与专业子 Agent。"""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        subagent_registry: SubagentRegistry,
        policy_service: InvocationPolicyService,
    ) -> None:
        self._tool_registry = tool_registry
        self._subagent_registry = subagent_registry
        self._policy_service = policy_service

    async def execute(
        self,
        run: GeneralAgentRun,
        *,
        checkpoint: CheckpointCallback,
    ) -> GeneralAgentRun:
        if run.plan is None:
            raise DynamicDagExecutionError("通用 Runtime 没有可执行计划。")
        run = self._ensure_node_runs(run)
        run = await checkpoint(run, "dag_prepared")
        assert run.plan is not None
        plan_nodes = {node.node_id: node for node in run.plan.nodes}
        while True:
            current = _current_runs(run)
            pending = [
                item
                for item in current.values()
                if item.status is GeneralAgentNodeStatus.PENDING
            ]
            if not pending:
                break
            blocked = self._mark_blocked_nodes(run, plan_nodes)
            if blocked != run:
                run = blocked
                run = await checkpoint(run, "nodes_skipped")
                current = _current_runs(run)
                pending = [
                    item
                    for item in current.values()
                    if item.status is GeneralAgentNodeStatus.PENDING
                ]
                if not pending:
                    break
            ready = [
                item
                for item in pending
                if self._dependencies_satisfied(item, current, plan_nodes)
            ]
            if not ready:
                raise DynamicDagExecutionError(
                    "动态 DAG 没有可执行节点，依赖状态不一致。"
                )
            approval = self._first_write_approval(run, ready, plan_nodes)
            if approval is not None:
                node_run, human_request = approval
                run = _replace_node_run(run, node_run)
                run = run.model_copy(
                    update={
                        "status": GeneralAgentRunStatus.WAITING_HUMAN,
                        "pending_human_request": human_request,
                        "updated_at": now_iso(),
                    }
                )
                run = await checkpoint(run, "waiting_write_authorization")
                return run
            batch = ready[: run.limits.max_concurrency]
            running_items = [
                item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.RUNNING,
                        "started_at": now_iso(),
                        "error_type": None,
                        "error_message": None,
                    }
                )
                for item in batch
            ]
            for item in running_items:
                run = _replace_node_run(run, item)
            run = await checkpoint(run, "nodes_started")
            results = await asyncio.gather(
                *[
                    self._execute_node(run, item, plan_nodes[item.node_id])
                    for item in running_items
                ]
            )
            for result in results:
                run = _replace_node_run(run, result)
            run = run.model_copy(update={"updated_at": now_iso()})
            run = await checkpoint(run, "nodes_finished")
        return run.model_copy(
            update={
                "status": GeneralAgentRunStatus.VERIFYING,
                "updated_at": now_iso(),
            }
        )

    def _ensure_node_runs(self, run: GeneralAgentRun) -> GeneralAgentRun:
        if run.plan is None:
            return run
        existing = {(item.plan_revision, item.node_id): item for item in run.node_runs}
        items = list(run.node_runs)
        for node in run.plan.nodes:
            key = (run.plan_revision, node.node_id)
            if key in existing:
                continue
            items.append(
                GeneralAgentNodeRun(
                    node_id=node.node_id,
                    plan_revision=run.plan_revision,
                    kind=node.kind,
                    capability_name=node.capability_name,
                    objective=node.objective,
                    dependencies=node.dependencies,
                )
            )
        return run.model_copy(update={"node_runs": items})

    def _mark_blocked_nodes(
        self,
        run: GeneralAgentRun,
        plan_nodes: Mapping[str, GeneralAgentPlanNode],
    ) -> GeneralAgentRun:
        current = _current_runs(run)
        result = run
        for item in current.values():
            if item.status is not GeneralAgentNodeStatus.PENDING:
                continue
            failed_dependencies = [
                dependency
                for dependency in item.dependencies
                if current[dependency].status
                in {GeneralAgentNodeStatus.FAILED, GeneralAgentNodeStatus.SKIPPED}
                and not plan_nodes[dependency].continue_on_failure
            ]
            if not failed_dependencies:
                continue
            result = _replace_node_run(
                result,
                item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.SKIPPED,
                        "finished_at": now_iso(),
                        "error_type": "UpstreamDependencyFailed",
                        "error_message": (
                            "上游节点失败，未执行：" + "、".join(failed_dependencies)
                        ),
                    }
                ),
            )
        return result

    def _dependencies_satisfied(
        self,
        item: GeneralAgentNodeRun,
        current: Mapping[str, GeneralAgentNodeRun],
        plan_nodes: Mapping[str, GeneralAgentPlanNode],
    ) -> bool:
        for dependency in item.dependencies:
            status = current[dependency].status
            if status is GeneralAgentNodeStatus.SUCCESS:
                continue
            if (
                status
                in {GeneralAgentNodeStatus.FAILED, GeneralAgentNodeStatus.SKIPPED}
                and plan_nodes[dependency].continue_on_failure
            ):
                continue
            return False
        return True

    def _first_write_approval(
        self,
        run: GeneralAgentRun,
        ready: list[GeneralAgentNodeRun],
        plan_nodes: Mapping[str, GeneralAgentPlanNode],
    ) -> tuple[GeneralAgentNodeRun, GeneralAgentHumanRequest] | None:
        for item in ready:
            if item.kind is not GeneralAgentNodeKind.TOOL:
                continue
            manifest = self._tool_registry.get_manifest(item.capability_name)
            if manifest.authorization_policy is ToolAuthorizationPolicy.NONE:
                continue
            if item.authorization_grant_id:
                continue
            resolved_input = self._prepare_input(run, plan_nodes[item.node_id])
            if "idempotency_key" in manifest.input_schema.model_fields:
                resolved_input.setdefault(
                    "idempotency_key",
                    f"{run.run_id}:{run.plan_revision}:{item.node_id}",
                )
            updated = item.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.WAITING_HUMAN,
                    "resolved_input": resolved_input,
                }
            )
            scopes = _resource_scopes(item.capability_name, resolved_input)
            request = GeneralAgentHumanRequest(
                request_id=f"human_{uuid4().hex}",
                kind="write_authorization",
                prompt=(
                    f"通用写作助手准备调用“{item.capability_name}”执行持久化修改。"
                    "请核对输入与作用范围后决定是否授权。"
                ),
                node_id=item.node_id,
                tool_name=item.capability_name,
                input_sha256=canonical_input_hash(resolved_input),
                input_summary=resolved_input,
                resource_scopes=scopes,
                second_confirmation_required=(
                    manifest.authorization_policy
                    is ToolAuthorizationPolicy.SECOND_CONFIRMATION
                ),
                created_at=now_iso(),
            )
            return updated, request
        return None

    async def _execute_node(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        plan_node: GeneralAgentPlanNode,
    ) -> GeneralAgentNodeRun:
        timer = perf_counter()
        try:
            resolved_input = self._prepare_input(run, plan_node)
            external_grant_id: str | None = None
            if self._requires_external(item):
                if not run.external_access_allowed:
                    raise DynamicDagExecutionError("本次任务没有外部研究许可。")
                reference = await self._policy_service.issue_external_access(
                    task_id=run.task_id,
                    user_intent_ref=run.user_goal,
                    allowed_tools=frozenset(
                        {"search_external_sources", "read_external_source"}
                    ),
                )
                external_grant_id = reference.grant_id
                if item.kind is GeneralAgentNodeKind.SUBAGENT:
                    resolved_input["external_access_grant_id"] = reference.grant_id
            if item.authorization_grant_id:
                resolved_input["author_grant_id"] = item.authorization_grant_id
            invocation = InvocationContext(
                task_id=run.task_id,
                run_id=run.run_id,
                caller_type="orchestrator",
                caller_name="general_writing_orchestrator",
                phase=f"dag:{item.node_id}",
                user_goal=run.user_goal,
                author_constraints=run.author_constraints,
                scope=run.scope.model_dump(mode="json"),
                external_access_grant_id=external_grant_id,
                budget=InvocationBudget(
                    max_tool_calls=run.limits.max_total_tool_calls,
                ),
            )
            if item.kind is GeneralAgentNodeKind.TOOL:
                envelope = await self._tool_registry.invoke(
                    item.capability_name,
                    resolved_input,
                    invocation,
                )
            else:
                envelope = await self._subagent_registry.invoke(
                    item.capability_name,
                    resolved_input,
                    invocation,
                )
            return item.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.SUCCESS,
                    "resolved_input": resolved_input,
                    "output": envelope.output.model_dump(mode="json"),
                    "source_refs": envelope.source_refs,
                    "artifact_refs": envelope.artifact_refs,
                    "trace_id": envelope.trace_id,
                    "finished_at": now_iso(),
                    "duration_ms": max(0, round((perf_counter() - timer) * 1000)),
                    "error_type": None,
                    "error_message": None,
                }
            )
        except Exception as error:  # noqa: BLE001
            return item.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.FAILED,
                    "finished_at": now_iso(),
                    "duration_ms": max(0, round((perf_counter() - timer) * 1000)),
                    "error_type": type(error).__name__,
                    "error_message": _runtime_error_message(error)[:2_000],
                }
            )

    def _prepare_input(
        self,
        run: GeneralAgentRun,
        node: GeneralAgentPlanNode,
    ) -> dict[str, Any]:
        payload = deepcopy(node.input_data)
        current = _current_runs(run)
        for binding in node.input_bindings:
            try:
                source = current[binding.source_node_id].output
                value = _read_path(source, binding.source_path)
                _write_path(payload, binding.target_path, value)
            except DynamicDagExecutionError as error:
                raise DynamicDagExecutionError(
                    f"节点“{node.node_id}”的数据交接失败：从上游节点"
                    f"“{binding.source_node_id}”读取“{binding.source_path}”并写入"
                    f"“{binding.target_path}”时出错；{error}"
                ) from error
        if node.kind is GeneralAgentNodeKind.SUBAGENT:
            subagent_manifest = self._subagent_registry.get_manifest(
                node.capability_name
            )
            if "source_request" in subagent_manifest.input_schema.model_fields:
                source_request = payload.setdefault("source_request", {})
                if not isinstance(source_request, dict):
                    raise DynamicDagExecutionError("source_request 必须是对象。")
                artifact_refs: list[str] = []
                for dependency in node.dependencies:
                    artifact_refs.extend(current[dependency].artifact_refs)
                if artifact_refs:
                    existing = source_request.get("upstream_artifact_refs", [])
                    if not isinstance(existing, list):
                        raise DynamicDagExecutionError(
                            "upstream_artifact_refs 必须是数组。"
                        )
                    source_request["upstream_artifact_refs"] = list(
                        dict.fromkeys([*existing, *artifact_refs])
                    )
        if node.kind is GeneralAgentNodeKind.TOOL:
            tool_manifest = self._tool_registry.get_manifest(node.capability_name)
            if "idempotency_key" in tool_manifest.input_schema.model_fields:
                payload.setdefault(
                    "idempotency_key",
                    f"{run.run_id}:{run.plan_revision}:{node.node_id}",
                )
        return payload

    def _requires_external(self, item: GeneralAgentNodeRun) -> bool:
        if item.kind is GeneralAgentNodeKind.SUBAGENT:
            return item.capability_name == "external_research"
        return self._tool_registry.get_manifest(
            item.capability_name
        ).requires_external_access


def _current_runs(run: GeneralAgentRun) -> dict[str, GeneralAgentNodeRun]:
    return {
        item.node_id: item
        for item in run.node_runs
        if item.plan_revision == run.plan_revision
    }


def _replace_node_run(
    run: GeneralAgentRun,
    replacement: GeneralAgentNodeRun,
) -> GeneralAgentRun:
    items = list(run.node_runs)
    for index, item in enumerate(items):
        if (
            item.plan_revision == replacement.plan_revision
            and item.node_id == replacement.node_id
        ):
            items[index] = replacement
            return run.model_copy(update={"node_runs": items})
    items.append(replacement)
    return run.model_copy(update={"node_runs": items})


def _read_path(payload: Any, path: str) -> Any:
    current = payload
    parts = path.removeprefix("output.").split(".")
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise DynamicDagExecutionError(f"上游输出不存在字段“{path}”。")
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise DynamicDagExecutionError(f"上游输出数组越界：“{path}”。")
            current = current[index]
        else:
            raise DynamicDagExecutionError(f"无法读取上游输出路径“{path}”。")
    return deepcopy(current)


def _write_path(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise DynamicDagExecutionError(f"无法写入节点输入路径“{path}”。")
        current = child
    current[parts[-1]] = value


def _runtime_error_message(error: Exception) -> str:
    if not isinstance(error, ValidationError):
        return str(error)
    details: list[str] = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "输入"
        details.append(f"{location}：{item.get('msg', '不符合要求')}")
    return "能力输入未通过运行时校验：" + "；".join(details)


def _resource_scopes(tool_name: str, payload: Mapping[str, Any]) -> list[str]:
    scopes: list[str] = []
    for key in ("chapter_id", "card_id", "volume_id", "parent_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            scopes.append(f"{key}:{value}")
    for key in ("chapter_ids", "card_ids", "item_ids"):
        value = payload.get(key)
        if isinstance(value, list):
            scopes.extend(f"{key}:{item}" for item in value if isinstance(item, str))
    return scopes or [f"tool:{tool_name}"]


class DynamicDagExecutionError(RuntimeError):
    """动态执行图无法继续推进。"""
