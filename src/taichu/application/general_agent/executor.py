"""按依赖和并发上限执行一次动态能力 DAG。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from time import perf_counter
from typing import Annotated, Any, TypedDict
from uuid import NAMESPACE_URL, uuid4, uuid5

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from taichu.application.contracts.general_agent_effects import (
    GeneralAgentEffectRepository,
)
from taichu.application.general_agent.models import (
    GeneralAgentHumanRequest,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.checkpoint_namespace import (
    NamespacedCheckpointSaver,
)
from taichu.application.general_agent.recovery import EffectRecord, EffectStatus
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
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolReconciliationStatus,
    ToolSideEffect,
)
from taichu.application.tools.registry import ToolRegistry

CheckpointCallback = Callable[
    [GeneralAgentRun, str],
    Awaitable[GeneralAgentRun],
]
FaultInjector = Callable[[str, EffectRecord], None]


def _merge_mapping(
    current: dict[str, dict[str, Any]],
    update: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {**current, **update}


class _DynamicDagState(TypedDict, total=False):
    run: dict[str, Any]
    node_results: Annotated[dict[str, dict[str, Any]], _merge_mapping]
    human_requests: Annotated[dict[str, dict[str, Any]], _merge_mapping]


class DynamicDagExecutor:
    """仅调度注册表中的真实 Tool 与专业子 Agent。"""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        subagent_registry: SubagentRegistry,
        policy_service: InvocationPolicyService,
        graph_checkpointer: BaseCheckpointSaver[Any] | None = None,
        effect_repository: GeneralAgentEffectRepository | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._subagent_registry = subagent_registry
        self._policy_service = policy_service
        self._graph_checkpointer = graph_checkpointer or InMemorySaver()
        self._effect_repository = effect_repository or _InMemoryEffectRepository()
        self._fault_injector = fault_injector

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
        if not run.plan.nodes:
            return run.model_copy(
                update={
                    "status": GeneralAgentRunStatus.VERIFYING,
                    "updated_at": now_iso(),
                }
            )
        graph = self._build_graph(run)
        config = {
            "recursion_limit": max(20, len(run.plan.nodes) * 3 + 10),
            "max_concurrency": run.limits.max_concurrency,
            "configurable": {
                "thread_id": run.run_id,
            },
        }
        graph_state = await graph.aget_state(config)
        if graph_state.next:
            result = await graph.ainvoke(None, config=config)
        elif graph_state.values:
            result = graph_state.values
        else:
            result = await graph.ainvoke(
                {
                    "run": run.model_dump(mode="json"),
                    "node_results": {
                        item.node_id: item.model_dump(mode="json")
                        for item in _current_runs(run).values()
                    },
                    "human_requests": {},
                },
                config=config,
            )
        for payload in result.get("node_results", {}).values():
            run = _replace_node_run(run, GeneralAgentNodeRun.model_validate(payload))
        requests = [
            GeneralAgentHumanRequest.model_validate(payload)
            for payload in result.get("human_requests", {}).values()
        ]
        if requests:
            run = run.model_copy(
                update={
                    "status": GeneralAgentRunStatus.WAITING_HUMAN,
                    "pending_human_request": requests[0],
                    "updated_at": now_iso(),
                }
            )
            return await checkpoint(run, "waiting_human_after_capability_checkpoint")
        run = await checkpoint(
            run.model_copy(update={"updated_at": now_iso()}),
            "capability_dag_projected",
        )
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
                existing_item = existing[key]
                if existing_item.attempt_id is None:
                    replacement = existing_item.model_copy(
                        update={"attempt_id": _attempt_id(run, node.node_id)}
                    )
                    items[items.index(existing_item)] = replacement
                continue
            items.append(
                GeneralAgentNodeRun(
                    node_id=node.node_id,
                    plan_revision=run.plan_revision,
                    kind=node.kind,
                    capability_name=node.capability_name,
                    objective=node.objective,
                    dependencies=node.dependencies,
                    attempt_id=_attempt_id(run, node.node_id),
                )
            )
        return run.model_copy(update={"node_runs": items})

    def _build_graph(self, run: GeneralAgentRun):
        assert run.plan is not None
        graph = StateGraph(_DynamicDagState)
        child_ids = {
            dependency for node in run.plan.nodes for dependency in node.dependencies
        }
        for node in run.plan.nodes:
            graph.add_node(node.node_id, self._graph_node(node))
            if node.dependencies:
                graph.add_edge(node.dependencies, node.node_id)
            else:
                graph.add_edge(START, node.node_id)
        for node in run.plan.nodes:
            if node.node_id not in child_ids:
                graph.add_edge(node.node_id, END)
        return graph.compile(
            checkpointer=NamespacedCheckpointSaver(
                self._graph_checkpointer,
                namespace=f"capability_dag_{run.plan_revision}",
            )
        )

    def _graph_node(self, plan_node: GeneralAgentPlanNode):
        async def execute(state: _DynamicDagState) -> _DynamicDagState:
            run = GeneralAgentRun.model_validate(state["run"])
            for payload in state.get("node_results", {}).values():
                run = _replace_node_run(
                    run,
                    GeneralAgentNodeRun.model_validate(payload),
                )
            item = _current_runs(run)[plan_node.node_id]
            if item.status in {
                GeneralAgentNodeStatus.SUCCESS,
                GeneralAgentNodeStatus.FAILED,
                GeneralAgentNodeStatus.SKIPPED,
            }:
                return {"node_results": {item.node_id: item.model_dump(mode="json")}}
            blocked = self._blocked_by_dependency(run, item, plan_node)
            if blocked is not None:
                return {
                    "node_results": {blocked.node_id: blocked.model_dump(mode="json")}
                }
            approval = self._first_write_approval(
                run,
                [item],
                {plan_node.node_id: plan_node},
            )
            if approval is not None:
                waiting, request = approval
                return {
                    "node_results": {waiting.node_id: waiting.model_dump(mode="json")},
                    "human_requests": {
                        waiting.node_id: request.model_dump(mode="json")
                    },
                }
            running = item.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.RUNNING,
                    "started_at": item.started_at or now_iso(),
                    "error_type": None,
                    "error_message": None,
                }
            )
            result, human_request = await self._execute_node(
                run,
                running,
                plan_node,
            )
            update: _DynamicDagState = {
                "node_results": {result.node_id: result.model_dump(mode="json")}
            }
            if human_request is not None:
                update["human_requests"] = {
                    result.node_id: human_request.model_dump(mode="json")
                }
            return update

        return execute

    def _blocked_by_dependency(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        plan_node: GeneralAgentPlanNode,
    ) -> GeneralAgentNodeRun | None:
        current = _current_runs(run)
        blockers = [
            dependency
            for dependency in item.dependencies
            if current[dependency].status is not GeneralAgentNodeStatus.SUCCESS
            and not (
                plan_node.continue_on_failure
                and current[dependency].status
                in {GeneralAgentNodeStatus.FAILED, GeneralAgentNodeStatus.SKIPPED}
            )
        ]
        if not blockers:
            return None
        return item.model_copy(
            update={
                "status": GeneralAgentNodeStatus.SKIPPED,
                "finished_at": now_iso(),
                "error_type": "UpstreamDependencyUnavailable",
                "error_message": "上游节点未成功，未执行：" + "、".join(blockers),
            }
        )

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
    ) -> tuple[GeneralAgentNodeRun, GeneralAgentHumanRequest | None]:
        timer = perf_counter()
        try:
            resolved_input = self._prepare_input(run, plan_node)
            external_grant_id = await self._external_grant(run, item, resolved_input)
            if item.kind is GeneralAgentNodeKind.TOOL and item.authorization_approved:
                item = await self._renew_author_grant(run, item, resolved_input)
            elif item.authorization_grant_id:
                resolved_input["author_grant_id"] = item.authorization_grant_id
            invocation = self._invocation_context(
                run,
                item,
                external_grant_id=external_grant_id,
            )
            if item.kind is GeneralAgentNodeKind.TOOL:
                manifest = self._tool_registry.get_manifest(item.capability_name)
                if manifest.side_effect in {
                    ToolSideEffect.WRITE,
                    ToolSideEffect.HIGH_RISK_WRITE,
                }:
                    return await self._execute_write_tool(
                        run,
                        item,
                        resolved_input,
                        invocation,
                        timer=timer,
                    )
                envelope = await self._tool_registry.invoke(
                    item.capability_name, resolved_input, invocation
                )
            else:
                envelope = await self._subagent_registry.invoke(
                    item.capability_name,
                    resolved_input,
                    invocation,
                )
            return (
                item.model_copy(
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
                ),
                None,
            )
        except InjectedProcessTermination:
            raise
        except Exception as error:  # noqa: BLE001
            return (
                item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.FAILED,
                        "finished_at": now_iso(),
                        "duration_ms": max(0, round((perf_counter() - timer) * 1000)),
                        "error_type": type(error).__name__,
                        "error_message": _runtime_error_message(error)[:2_000],
                    }
                ),
                None,
            )

    async def _execute_write_tool(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        resolved_input: dict[str, Any],
        invocation: InvocationContext,
        *,
        timer: float,
    ) -> tuple[GeneralAgentNodeRun, GeneralAgentHumanRequest | None]:
        effect_id = _effect_id(run, item.node_id)
        latest = await self._effect_repository.latest(effect_id)
        if latest is not None and latest.status in {
            EffectStatus.SUCCEEDED,
            EffectStatus.RECONCILED,
        }:
            return self._successful_write_result(
                item,
                resolved_input,
                output=latest.output,
                effect_id=effect_id,
                effect_status=latest.status,
                reason="复用已落盘的副作用成功证据。",
                timer=timer,
            )
        if latest is not None and latest.status in {
            EffectStatus.STARTED,
            EffectStatus.UNKNOWN,
        }:
            reconciliation = await self._tool_registry.reconcile(
                item.capability_name,
                resolved_input,
                invocation,
            )
            if reconciliation.status is ToolReconciliationStatus.SUCCEEDED:
                record = await self._append_effect(
                    run,
                    item,
                    resolved_input,
                    status=EffectStatus.RECONCILED,
                    output=reconciliation.output,
                    evidence=reconciliation.evidence,
                    reason=reconciliation.reason,
                )
                return self._successful_write_result(
                    item,
                    resolved_input,
                    output=reconciliation.output,
                    effect_id=record.effect_id,
                    effect_status=record.status,
                    reason=reconciliation.reason or "真实资源对账确认写入已生效。",
                    timer=timer,
                )
            if reconciliation.status is ToolReconciliationStatus.UNKNOWN:
                record = await self._append_effect(
                    run,
                    item,
                    resolved_input,
                    status=EffectStatus.REQUIRES_HUMAN,
                    evidence=reconciliation.evidence,
                    reason=reconciliation.reason,
                )
                waiting = item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.WAITING_HUMAN,
                        "resolved_input": resolved_input,
                        "effect_id": record.effect_id,
                        "effect_status": record.status,
                        "reconciliation_reason": reconciliation.reason,
                        "duplicate_execution_protected": True,
                        "error_type": "SideEffectRequiresHuman",
                        "error_message": (
                            reconciliation.reason
                            or "真实写入结果无法自动确认，已阻止重复执行。"
                        ),
                    }
                )
                request = GeneralAgentHumanRequest(
                    request_id=f"human_{uuid4().hex}",
                    kind="effect_reconciliation",
                    prompt=(
                        "写入请求发出后服务中断，系统无法自动确认真实资源是否已变化。"
                        "已停止自动重试，请先核对资源状态。"
                    ),
                    node_id=item.node_id,
                    tool_name=item.capability_name,
                    input_sha256=canonical_input_hash(resolved_input),
                    input_summary={},
                    resource_scopes=_resource_scopes(
                        item.capability_name, resolved_input
                    ),
                    created_at=now_iso(),
                )
                return waiting, request
        if latest is None:
            await self._append_effect(
                run,
                item,
                resolved_input,
                status=EffectStatus.PREPARED,
                reason="确定输入、授权和资源范围已冻结。",
            )
        started = await self._append_effect(
            run,
            item,
            resolved_input,
            status=EffectStatus.STARTED,
            reason=(
                "真实写入即将开始。"
                if latest is None
                else "对账确认未生效，按原确定输入安全重试。"
            ),
        )
        try:
            envelope = await self._tool_registry.invoke(
                item.capability_name,
                resolved_input,
                invocation,
            )
            if self._fault_injector is not None:
                self._fault_injector("after_write_before_effect_success", started)
            output = envelope.output.model_dump(mode="json")
            record = await self._append_effect(
                run,
                item,
                resolved_input,
                status=EffectStatus.SUCCEEDED,
                output=output,
                evidence={
                    "source_refs": envelope.source_refs,
                    "artifact_refs": envelope.artifact_refs,
                    "trace_id": envelope.trace_id,
                },
                reason="真实写入和返回结果均已落盘。",
            )
            return (
                item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.SUCCESS,
                        "resolved_input": resolved_input,
                        "output": output,
                        "source_refs": envelope.source_refs,
                        "artifact_refs": envelope.artifact_refs,
                        "trace_id": envelope.trace_id,
                        "effect_id": record.effect_id,
                        "effect_status": record.status,
                        "duplicate_execution_protected": True,
                        "finished_at": now_iso(),
                        "duration_ms": max(0, round((perf_counter() - timer) * 1000)),
                        "error_type": None,
                        "error_message": None,
                    }
                ),
                None,
            )
        except InjectedProcessTermination:
            raise
        except Exception as error:
            reconciliation = await self._tool_registry.reconcile(
                item.capability_name,
                resolved_input,
                invocation,
            )
            if reconciliation.status is ToolReconciliationStatus.SUCCEEDED:
                record = await self._append_effect(
                    run,
                    item,
                    resolved_input,
                    status=EffectStatus.RECONCILED,
                    output=reconciliation.output,
                    evidence=reconciliation.evidence,
                    reason=reconciliation.reason,
                )
                return self._successful_write_result(
                    item,
                    resolved_input,
                    output=reconciliation.output,
                    effect_id=record.effect_id,
                    effect_status=record.status,
                    reason=reconciliation.reason,
                    timer=timer,
                )
            status = (
                EffectStatus.FAILED
                if reconciliation.status is ToolReconciliationStatus.NOT_APPLIED
                else EffectStatus.UNKNOWN
            )
            await self._append_effect(
                run,
                item,
                resolved_input,
                status=status,
                evidence=reconciliation.evidence,
                reason=reconciliation.reason or str(error),
            )
            raise

    async def _append_effect(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        resolved_input: dict[str, Any],
        *,
        status: EffectStatus,
        output: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        reason: str = "",
    ) -> EffectRecord:
        idempotency_key = resolved_input.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise DynamicDagExecutionError("写入工具缺少稳定幂等键。")
        record = EffectRecord(
            event_id=f"effect_event_{uuid4().hex}",
            effect_id=_effect_id(run, item.node_id),
            attempt_id=item.attempt_id or _attempt_id(run, item.node_id),
            run_id=run.run_id,
            plan_revision=run.plan_revision,
            node_id=item.node_id,
            tool_name=item.capability_name,
            status=status,
            input_sha256=canonical_input_hash(resolved_input),
            idempotency_key=idempotency_key,
            resource_scopes=(
                item.authorization_resource_scopes
                or _resource_scopes(item.capability_name, resolved_input)
            ),
            authorization_reference=item.authorization_grant_id,
            output=output or {},
            evidence=evidence or {},
            reason=reason,
            created_at=now_iso(),
        )
        await self._effect_repository.append(record)
        return record

    def _successful_write_result(
        self,
        item: GeneralAgentNodeRun,
        resolved_input: dict[str, Any],
        *,
        output: dict[str, Any],
        effect_id: str,
        effect_status: EffectStatus,
        reason: str,
        timer: float,
    ) -> tuple[GeneralAgentNodeRun, None]:
        refs = output.get("source_refs", [])
        source_refs = (
            [value for value in refs if isinstance(value, str)]
            if isinstance(refs, list)
            else []
        )
        return (
            item.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.SUCCESS,
                    "resolved_input": resolved_input,
                    "output": output,
                    "source_refs": source_refs,
                    "effect_id": effect_id,
                    "effect_status": effect_status,
                    "reconciliation_reason": reason,
                    "duplicate_execution_protected": True,
                    "finished_at": now_iso(),
                    "duration_ms": max(0, round((perf_counter() - timer) * 1000)),
                    "error_type": None,
                    "error_message": None,
                }
            ),
            None,
        )

    async def _external_grant(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        resolved_input: dict[str, Any],
    ) -> str | None:
        if not self._requires_external(item):
            return None
        if not run.external_access_allowed:
            raise DynamicDagExecutionError("本次任务没有外部研究许可。")
        reference = await self._policy_service.issue_external_access(
            task_id=run.task_id,
            user_intent_ref=run.user_goal,
            allowed_tools=frozenset(
                {"search_external_sources", "read_external_source"}
            ),
        )
        if item.kind is GeneralAgentNodeKind.SUBAGENT:
            resolved_input["external_access_grant_id"] = reference.grant_id
        return reference.grant_id

    async def _renew_author_grant(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        resolved_input: dict[str, Any],
    ) -> GeneralAgentNodeRun:
        """按作者已确认的冻结输入和原资源范围签发本次进程内授权。"""
        scopes = item.authorization_resource_scopes or _resource_scopes(
            item.capability_name,
            resolved_input,
        )
        grant = await self._policy_service.issue_author_write(
            task_id=run.task_id,
            tool_name=item.capability_name,
            input_payload=resolved_input,
            resource_scopes=tuple(scopes),
            second_confirmation=item.authorization_second_confirmation,
        )
        resolved_input["author_grant_id"] = grant.grant_id
        return item.model_copy(
            update={
                "authorization_grant_id": grant.grant_id,
                "authorization_resource_scopes": scopes,
            }
        )

    def _invocation_context(
        self,
        run: GeneralAgentRun,
        item: GeneralAgentNodeRun,
        *,
        external_grant_id: str | None,
    ) -> InvocationContext:
        context_envelope = (
            run.context_snapshot.envelope if run.context_snapshot is not None else None
        )
        invocation_scope = (
            dict(context_envelope.scope)
            if context_envelope is not None
            else run.scope.model_dump(mode="json")
        )
        if context_envelope is not None:
            invocation_scope["runtime_memory_notice"] = (
                "运行记忆只用于延续任务上下文，不是小说事实；涉及事实必须重新取证。"
            )
            invocation_scope["runtime_memories"] = [
                memory.model_dump(mode="json")
                for memory in context_envelope.runtime_memories
            ]
            if context_envelope.digest is not None:
                invocation_scope["context_digest"] = context_envelope.digest.model_dump(
                    mode="json"
                )
        return InvocationContext(
            task_id=run.task_id,
            run_id=run.run_id,
            caller_type="orchestrator",
            caller_name="general_writing_orchestrator",
            phase=f"dag:{item.node_id}",
            user_goal=(
                context_envelope.current_goal
                if context_envelope is not None
                else run.user_goal
            ),
            author_constraints=(
                context_envelope.author_constraints
                if context_envelope is not None
                else run.author_constraints
            ),
            scope=invocation_scope,
            external_access_grant_id=external_grant_id,
            budget=InvocationBudget(
                max_input_chars=(
                    max(120_000, context_envelope.total_char_count)
                    if context_envelope is not None
                    else 120_000
                ),
                max_tool_calls=run.limits.max_total_tool_calls,
            ),
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


def _attempt_id(run: GeneralAgentRun, node_id: str) -> str:
    value = uuid5(
        NAMESPACE_URL,
        f"taichu:{run.run_id}:{run.plan_revision}:{node_id}:attempt",
    )
    return f"attempt_{value.hex}"


def _effect_id(run: GeneralAgentRun, node_id: str) -> str:
    value = uuid5(
        NAMESPACE_URL,
        f"taichu:{run.run_id}:{run.plan_revision}:{node_id}:effect",
    )
    return f"effect_{value.hex}"


class _InMemoryEffectRepository:
    """仅供未注入持久仓储的隔离单元测试使用。"""

    def __init__(self) -> None:
        self._records: list[EffectRecord] = []

    async def append(self, record: EffectRecord) -> None:
        self._records.append(record)

    async def latest(self, effect_id: str) -> EffectRecord | None:
        matches = [item for item in self._records if item.effect_id == effect_id]
        return matches[-1] if matches else None

    async def list_effects(self, run_id: str) -> list[EffectRecord]:
        return [item for item in self._records if item.run_id == run_id]

    async def delete_run(self, run_id: str) -> bool:
        before = len(self._records)
        self._records = [item for item in self._records if item.run_id != run_id]
        return len(self._records) != before


class DynamicDagExecutionError(RuntimeError):
    """动态执行图无法继续推进。"""


class InjectedProcessTermination(RuntimeError):
    """只用于故障注入，要求 Runtime 保留活动状态并模拟进程终止。"""
