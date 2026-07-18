"""通用写作助手顶层 LangGraph、生命周期和恢复服务。"""

from __future__ import annotations

import asyncio
import builtins
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from taichu.application.contracts.general_agent_run import GeneralAgentRunRepository
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.models import (
    GeneralAgentConversation,
    GeneralAgentHumanRequest,
    GeneralAgentLifecycleEvent,
    GeneralAgentMessage,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentRunLimits,
    GeneralAgentRunStatus,
    GeneralAgentScope,
)
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.invocations.models import now_iso
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)

_ACTIVE_STATUSES = {
    GeneralAgentRunStatus.INIT,
    GeneralAgentRunStatus.CLARIFYING,
    GeneralAgentRunStatus.PLANNING,
    GeneralAgentRunStatus.EXECUTING,
    GeneralAgentRunStatus.VERIFYING,
    GeneralAgentRunStatus.REPLANNING,
}
_TERMINAL_STATUSES = {
    GeneralAgentRunStatus.COMPLETED,
    GeneralAgentRunStatus.CANCELLED,
}


class _RuntimeGraphState(TypedDict, total=False):
    run: dict[str, Any]
    replan_guidance: str


class GeneralAgentRuntimeService:
    """用独立业务状态承载高层编排 Agent 的完整执行循环。"""

    def __init__(
        self,
        *,
        repository: GeneralAgentRunRepository,
        event_center: GeneralAgentEventCenter,
        orchestrator: OrchestratorAgent,
        executor: DynamicDagExecutor,
        policy_service: InvocationPolicyService,
    ) -> None:
        self._repository = repository
        self._event_center = event_center
        self._orchestrator = orchestrator
        self._executor = executor
        self._policy_service = policy_service
        self._tasks: dict[str, asyncio.Task[GeneralAgentRun]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._shutting_down = False
        self._graph = self._build_graph()

    async def create_run(
        self,
        *,
        user_goal: str,
        conversation_id: str | None = None,
        scope: GeneralAgentScope | None = None,
        author_constraints: list[str] | None = None,
        external_access_allowed: bool = False,
        limits: GeneralAgentRunLimits | None = None,
    ) -> GeneralAgentRun:
        goal = user_goal.strip()
        if not goal:
            raise GeneralAgentRuntimeError("任务目标不能为空。")
        timestamp = datetime.now(UTC)
        run_id = f"general_run_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        resolved_conversation_id = (
            conversation_id.strip()
            if conversation_id is not None
            else (
                f"general_conversation_{timestamp.strftime('%Y%m%d_%H%M%S')}_"
                f"{uuid4().hex[:6]}"
            )
        )
        if not resolved_conversation_id:
            raise GeneralAgentRuntimeError("对话标识不能为空。")
        created_at = timestamp.isoformat().replace("+00:00", "Z")
        conversation_lock = self._conversation_locks.setdefault(
            resolved_conversation_id,
            asyncio.Lock(),
        )
        async with conversation_lock:
            messages = await self._messages_for_new_turn(
                resolved_conversation_id,
                goal=goal,
                created_at=created_at,
                existing_conversation=conversation_id is not None,
            )
            run = GeneralAgentRun(
                run_id=run_id,
                task_id=resolved_conversation_id,
                user_goal=goal,
                scope=scope or GeneralAgentScope(),
                author_constraints=author_constraints or [],
                external_access_allowed=external_access_allowed,
                limits=limits or GeneralAgentRunLimits(),
                messages=messages,
                lifecycle_events=[
                    GeneralAgentLifecycleEvent(
                        status=GeneralAgentRunStatus.INIT,
                        reason="任务已创建。",
                        created_at=created_at,
                    )
                ],
                created_at=created_at,
                updated_at=created_at,
                started_at=created_at,
            )
            return await self._checkpoint(run, "run_created")

    async def run(
        self,
        *,
        user_goal: str,
        conversation_id: str | None = None,
        scope: GeneralAgentScope | None = None,
        author_constraints: list[str] | None = None,
        external_access_allowed: bool = False,
        limits: GeneralAgentRunLimits | None = None,
    ) -> GeneralAgentRun:
        run = await self.create_run(
            user_goal=user_goal,
            conversation_id=conversation_id,
            scope=scope,
            author_constraints=author_constraints,
            external_access_allowed=external_access_allowed,
            limits=limits,
        )
        return await self._execute_run(run.run_id)

    async def start(
        self,
        *,
        user_goal: str,
        conversation_id: str | None = None,
        scope: GeneralAgentScope | None = None,
        author_constraints: list[str] | None = None,
        external_access_allowed: bool = False,
        limits: GeneralAgentRunLimits | None = None,
    ) -> GeneralAgentRun:
        run = await self.create_run(
            user_goal=user_goal,
            conversation_id=conversation_id,
            scope=scope,
            author_constraints=author_constraints,
            external_access_allowed=external_access_allowed,
            limits=limits,
        )
        self._start_background(run.run_id)
        return run

    async def resume(
        self,
        run_id: str,
        *,
        answer: str = "",
        approve: bool | None = None,
        second_confirmation: bool = False,
    ) -> GeneralAgentRun:
        run = await self._require_run(run_id)
        if run.status in _TERMINAL_STATUSES:
            raise GeneralAgentRuntimeError("已结束的任务不能恢复。")
        request = run.pending_human_request
        if request is not None and request.kind == "clarification":
            if not answer.strip():
                raise GeneralAgentRuntimeError("恢复澄清任务必须提供作者回答。")
            run = run.model_copy(
                update={
                    "messages": [
                        *run.messages,
                        GeneralAgentMessage(
                            role="user",
                            content=answer.strip(),
                            created_at=now_iso(),
                        ),
                    ],
                    "pending_human_request": None,
                    "plan": None,
                }
            )
            run = _transition(run, GeneralAgentRunStatus.REPLANNING, "作者已补充信息。")
        elif request is not None and request.kind == "write_authorization":
            if approve is None:
                raise GeneralAgentRuntimeError("恢复写入任务必须明确批准或拒绝。")
            run = await self._resolve_write_authorization(
                run,
                request,
                approve=approve,
                second_confirmation=second_confirmation,
            )
        elif run.status in {
            GeneralAgentRunStatus.FAILED,
            GeneralAgentRunStatus.TIMEOUT,
        }:
            node_runs = [
                item.model_copy(
                    update={
                        "status": GeneralAgentNodeStatus.PENDING,
                        "started_at": None,
                        "finished_at": None,
                        "error_type": None,
                        "error_message": None,
                    }
                )
                if item.plan_revision == run.plan_revision
                and item.status
                in {
                    GeneralAgentNodeStatus.RUNNING,
                    GeneralAgentNodeStatus.FAILED,
                    GeneralAgentNodeStatus.WAITING_HUMAN,
                }
                else item
                for item in run.node_runs
            ]
            has_retryable_nodes = any(
                item.plan_revision == run.plan_revision
                and item.status
                in {
                    GeneralAgentNodeStatus.RUNNING,
                    GeneralAgentNodeStatus.FAILED,
                    GeneralAgentNodeStatus.WAITING_HUMAN,
                }
                for item in run.node_runs
            )
            target = (
                GeneralAgentRunStatus.EXECUTING
                if run.plan is not None and has_retryable_nodes
                else GeneralAgentRunStatus.REPLANNING
            )
            run = run.model_copy(
                update={
                    "node_runs": node_runs,
                    "errors": [],
                }
            )
            run = await self._refresh_author_grants(run)
            run = _transition(run, target, "作者请求从最近检查点恢复。")
        else:
            raise GeneralAgentRuntimeError("当前任务不处于可恢复状态。")
        run = await self._checkpoint(run, "run_resumed")
        return await self._execute_run(run_id)

    async def cancel(self, run_id: str) -> GeneralAgentRun:
        run = await self._require_run(run_id)
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        if run.status in _TERMINAL_STATUSES:
            return run
        run = _transition(run, GeneralAgentRunStatus.CANCELLED, "作者取消任务。")
        run = run.model_copy(update={"finished_at": now_iso(), "resumable": False})
        return await self._checkpoint(run, "run_cancelled")

    async def get(self, run_id: str) -> GeneralAgentRun:
        return await self._require_run(run_id)

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[builtins.list[GeneralAgentRun], int]:
        return await self._repository.list_runs(
            page=page,
            page_size=page_size,
            status=status,
        )

    async def list_conversations(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[builtins.list[GeneralAgentConversation], int]:
        runs = await self._all_runs()
        grouped: dict[str, builtins.list[GeneralAgentRun]] = {}
        for run in runs:
            grouped.setdefault(run.task_id, []).append(run)

        conversations: builtins.list[GeneralAgentConversation] = []
        for conversation_id, items in grouped.items():
            ordered = sorted(items, key=lambda item: (item.created_at, item.run_id))
            first = ordered[0]
            latest = ordered[-1]
            conversations.append(
                GeneralAgentConversation(
                    conversation_id=conversation_id,
                    title=first.user_goal,
                    status=latest.status,
                    turn_count=len(ordered),
                    latest_run_id=latest.run_id,
                    created_at=first.created_at,
                    updated_at=max(item.updated_at for item in ordered),
                )
            )

        conversations.sort(
            key=lambda item: (item.updated_at, item.conversation_id),
            reverse=True,
        )
        start = (page - 1) * page_size
        return conversations[start : start + page_size], len(conversations)

    async def get_conversation(
        self, conversation_id: str
    ) -> builtins.list[GeneralAgentRun]:
        runs = [run for run in await self._all_runs() if run.task_id == conversation_id]
        if not runs:
            raise GeneralAgentConversationNotFoundError(conversation_id)
        return sorted(runs, key=lambda item: (item.created_at, item.run_id))

    async def delete_conversation(self, conversation_id: str) -> int:
        runs = await self.get_conversation(conversation_id)
        if any(
            (task := self._tasks.get(run.run_id)) is not None and not task.done()
            for run in runs
        ):
            raise GeneralAgentRuntimeError("对话中仍有任务正在运行，请先停止当前任务。")
        deleted_count = 0
        for run in runs:
            if await self.delete(run.run_id):
                deleted_count += 1
        return deleted_count

    async def delete(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            raise GeneralAgentRuntimeError("运行中的任务不能删除，请先取消。")
        deleted = await self._repository.delete(run_id)
        if deleted:
            await self._event_center.delete_snapshot(run_id)
        return deleted

    async def _messages_for_new_turn(
        self,
        conversation_id: str,
        *,
        goal: str,
        created_at: str,
        existing_conversation: bool,
    ) -> builtins.list[GeneralAgentMessage]:
        if not existing_conversation:
            return [
                GeneralAgentMessage(
                    role="user",
                    content=goal,
                    created_at=created_at,
                )
            ]

        previous_runs = await self.get_conversation(conversation_id)
        latest = previous_runs[-1]
        if (
            latest.status in _ACTIVE_STATUSES
            or latest.status is GeneralAgentRunStatus.WAITING_HUMAN
        ):
            raise GeneralAgentRuntimeError(
                "当前对话仍有任务正在处理，请等待完成或先处理待确认内容。"
            )

        messages = list(latest.messages)
        if latest.final_answer.strip() and not (
            messages
            and messages[-1].role == "assistant"
            and messages[-1].content == latest.final_answer
        ):
            messages.append(
                GeneralAgentMessage(
                    role="assistant",
                    content=latest.final_answer,
                    created_at=latest.finished_at or latest.updated_at,
                )
            )
        messages.append(
            GeneralAgentMessage(
                role="user",
                content=goal,
                created_at=created_at,
            )
        )
        return messages

    async def _all_runs(self) -> builtins.list[GeneralAgentRun]:
        runs, _ = await self._repository.list_runs(
            page=1,
            page_size=100_000,
            status="all",
        )
        return runs

    async def recover_interrupted(self) -> int:
        runs, _ = await self._repository.list_runs(
            page=1,
            page_size=10_000,
            status="all",
        )
        recovered = 0
        for run in runs:
            if run.status not in _ACTIVE_STATUSES:
                continue
            node_runs = []
            for item in run.node_runs:
                updates: dict[str, Any] = {}
                if item.status is GeneralAgentNodeStatus.RUNNING:
                    updates.update(
                        {
                            "status": GeneralAgentNodeStatus.PENDING,
                            "started_at": None,
                            "finished_at": None,
                            "error_type": None,
                            "error_message": None,
                        }
                    )
                if (
                    item.plan_revision == run.plan_revision
                    and item.authorization_approved
                    and item.status is not GeneralAgentNodeStatus.SUCCESS
                ):
                    updates["authorization_grant_id"] = None
                node_runs.append(item.model_copy(update=updates) if updates else item)
            updated = run.model_copy(
                update={
                    "node_runs": node_runs,
                    "errors": [*run.errors, "服务重启中断了执行，可从最近检查点恢复。"],
                }
            )
            updated = _transition(
                updated,
                GeneralAgentRunStatus.FAILED,
                "服务重启后已封存最近检查点。",
            )
            await self._checkpoint(updated, "interrupted_recovered")
            recovered += 1
        return recovered

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _resolve_write_authorization(
        self,
        run: GeneralAgentRun,
        request: GeneralAgentHumanRequest,
        *,
        approve: bool,
        second_confirmation: bool,
    ) -> GeneralAgentRun:
        if request.node_id is None or request.tool_name is None:
            raise GeneralAgentRuntimeError("写入授权请求缺少目标节点。")
        node = _find_current_node(run, request.node_id)
        if not approve:
            updated = node.model_copy(
                update={
                    "status": GeneralAgentNodeStatus.SKIPPED,
                    "finished_at": now_iso(),
                    "error_type": "AuthorRejected",
                    "error_message": "作者拒绝了持久化修改。",
                }
            )
            run = _replace_node(run, updated)
            run = run.model_copy(update={"pending_human_request": None})
            return _transition(
                run,
                GeneralAgentRunStatus.EXECUTING,
                "作者拒绝写入，继续收敛其余结果。",
            )
        if request.second_confirmation_required and not second_confirmation:
            raise GeneralAgentRuntimeError("该高风险写入需要二次确认。")
        grant = await self._policy_service.issue_author_write(
            task_id=run.task_id,
            tool_name=request.tool_name,
            input_payload=node.resolved_input,
            resource_scopes=tuple(request.resource_scopes),
            second_confirmation=second_confirmation,
        )
        updated = node.model_copy(
            update={
                "status": GeneralAgentNodeStatus.PENDING,
                "authorization_grant_id": grant.grant_id,
                "authorization_approved": True,
                "authorization_second_confirmation": second_confirmation,
                "authorization_resource_scopes": request.resource_scopes,
            }
        )
        run = _replace_node(run, updated)
        run = run.model_copy(update={"pending_human_request": None})
        return _transition(
            run,
            GeneralAgentRunStatus.EXECUTING,
            "作者已授权本次确定输入的写入。",
        )

    async def _refresh_author_grants(
        self,
        run: GeneralAgentRun,
    ) -> GeneralAgentRun:
        """根据检查点中的作者决定重签进程内授权，不扩大原作用范围。"""
        result = run
        for node in run.node_runs:
            if (
                node.plan_revision != run.plan_revision
                or not node.authorization_approved
                or node.status is GeneralAgentNodeStatus.SUCCESS
            ):
                continue
            scopes = tuple(node.authorization_resource_scopes) or (
                f"tool:{node.capability_name}",
            )
            grant = await self._policy_service.issue_author_write(
                task_id=run.task_id,
                tool_name=node.capability_name,
                input_payload=node.resolved_input,
                resource_scopes=scopes,
                second_confirmation=node.authorization_second_confirmation,
            )
            result = _replace_node(
                result,
                node.model_copy(update={"authorization_grant_id": grant.grant_id}),
            )
        return result

    def _start_background(self, run_id: str) -> None:
        current = self._tasks.get(run_id)
        if current is not None and not current.done():
            raise GeneralAgentRuntimeError("该任务已经在运行。")
        task = asyncio.create_task(self._execute_run(run_id))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._task_finished(run_id, completed))

    def _task_finished(
        self,
        run_id: str,
        task: asyncio.Task[GeneralAgentRun],
    ) -> None:
        self._tasks.pop(run_id, None)
        if not task.cancelled():
            task.exception()

    async def _execute_run(self, run_id: str) -> GeneralAgentRun:
        lock = self._locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            run = await self._require_run(run_id)
            try:
                async with asyncio.timeout(run.limits.max_runtime_seconds):
                    result = await self._graph.ainvoke(
                        {"run": run.model_dump(mode="json")},
                        config={"recursion_limit": 20},
                    )
                return GeneralAgentRun.model_validate(result["run"])
            except asyncio.CancelledError:
                if self._shutting_down:
                    raise
                latest = await self._require_run(run_id)
                if latest.status is not GeneralAgentRunStatus.CANCELLED:
                    latest = _transition(
                        latest,
                        GeneralAgentRunStatus.CANCELLED,
                        "运行任务被取消。",
                    ).model_copy(update={"finished_at": now_iso(), "resumable": False})
                    await self._checkpoint(latest, "run_cancelled")
                raise
            except TimeoutError:
                latest = await self._require_run(run_id)
                latest = _transition(
                    latest,
                    GeneralAgentRunStatus.TIMEOUT,
                    "任务超过运行时限。",
                ).model_copy(update={"finished_at": now_iso(), "resumable": True})
                return await self._checkpoint(latest, "run_timed_out")
            except Exception as error:  # noqa: BLE001
                latest = await self._require_run(run_id)
                latest = latest.model_copy(
                    update={"errors": [*latest.errors, str(error)[:2_000]]}
                )
                latest = _transition(
                    latest,
                    GeneralAgentRunStatus.FAILED,
                    f"运行失败：{type(error).__name__}",
                ).model_copy(update={"finished_at": now_iso(), "resumable": True})
                return await self._checkpoint(latest, "run_failed")

    def _build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(_RuntimeGraphState)
        graph.add_node("initialize", self._initialize_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute_dag", self._execute_dag_node)
        graph.add_node("verify", self._verify_node)
        graph.add_edge(START, "initialize")
        graph.add_conditional_edges(
            "initialize",
            self._route_after_initialize,
            {"plan": "plan", "execute": "execute_dag", "verify": "verify", "end": END},
        )
        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"execute": "execute_dag", "end": END},
        )
        graph.add_conditional_edges(
            "execute_dag",
            self._route_after_execute,
            {"verify": "verify", "end": END},
        )
        graph.add_conditional_edges(
            "verify",
            self._route_after_verify,
            {"plan": "plan", "end": END},
        )
        return graph.compile()

    async def _initialize_node(self, state: _RuntimeGraphState) -> _RuntimeGraphState:
        run = GeneralAgentRun.model_validate(state["run"])
        if run.status in {
            GeneralAgentRunStatus.INIT,
            GeneralAgentRunStatus.CLARIFYING,
            GeneralAgentRunStatus.PLANNING,
            GeneralAgentRunStatus.REPLANNING,
        }:
            run = _transition(run, GeneralAgentRunStatus.PLANNING, "开始高层规划。")
        run = await self._checkpoint(run, "runtime_initialized")
        return {**state, "run": run.model_dump(mode="json")}

    def _route_after_initialize(self, state: _RuntimeGraphState) -> str:
        status = GeneralAgentRun.model_validate(state["run"]).status
        if status is GeneralAgentRunStatus.PLANNING:
            return "plan"
        if status is GeneralAgentRunStatus.EXECUTING:
            return "execute"
        if status is GeneralAgentRunStatus.VERIFYING:
            return "verify"
        return "end"

    async def _plan_node(self, state: _RuntimeGraphState) -> _RuntimeGraphState:
        run = GeneralAgentRun.model_validate(state["run"])
        plan = await self._orchestrator.plan(
            run,
            replan_guidance=state.get("replan_guidance", ""),
        )
        if plan.requires_clarification:
            run = run.model_copy(
                update={
                    "plan": plan,
                    "pending_human_request": GeneralAgentHumanRequest(
                        request_id=f"human_{uuid4().hex}",
                        kind="clarification",
                        prompt=plan.clarification_question,
                        created_at=now_iso(),
                    ),
                }
            )
            run = _transition(
                run,
                GeneralAgentRunStatus.WAITING_HUMAN,
                "高层编排 Agent 需要作者补充信息。",
            )
            run = await self._checkpoint(run, "waiting_clarification")
            return {"run": run.model_dump(mode="json"), "replan_guidance": ""}
        run = run.model_copy(
            update={
                "plan": plan,
                "plan_revision": run.plan_revision + 1,
                "pending_human_request": None,
            }
        )
        run = _transition(run, GeneralAgentRunStatus.EXECUTING, "动态执行计划已生成。")
        run = await self._checkpoint(run, "plan_created")
        return {"run": run.model_dump(mode="json"), "replan_guidance": ""}

    def _route_after_plan(self, state: _RuntimeGraphState) -> str:
        status = GeneralAgentRun.model_validate(state["run"]).status
        return "execute" if status is GeneralAgentRunStatus.EXECUTING else "end"

    async def _execute_dag_node(self, state: _RuntimeGraphState) -> _RuntimeGraphState:
        run = GeneralAgentRun.model_validate(state["run"])
        run = _transition(run, GeneralAgentRunStatus.EXECUTING, "执行动态能力图。")
        run = await self._checkpoint(run, "dag_execution_started")
        run = await self._executor.execute(run, checkpoint=self._checkpoint)
        run = await self._checkpoint(run, "dag_execution_finished")
        return {**state, "run": run.model_dump(mode="json")}

    def _route_after_execute(self, state: _RuntimeGraphState) -> str:
        status = GeneralAgentRun.model_validate(state["run"]).status
        return "verify" if status is GeneralAgentRunStatus.VERIFYING else "end"

    async def _verify_node(self, state: _RuntimeGraphState) -> _RuntimeGraphState:
        run = GeneralAgentRun.model_validate(state["run"])
        run = _transition(run, GeneralAgentRunStatus.VERIFYING, "校验执行结果。")
        run = await self._checkpoint(run, "verification_started")
        blocking_failures = _blocking_failed_nodes(run)
        if blocking_failures and run.replan_count < run.limits.max_replans:
            issues = _execution_failure_issues(blocking_failures)
            run = run.model_copy(
                update={
                    "replan_count": run.replan_count + 1,
                    "verification_issues": issues,
                    "final_answer": "",
                }
            )
            run = _transition(
                run,
                GeneralAgentRunStatus.REPLANNING,
                "执行步骤失败，进入有限自动修复。",
            )
            run = await self._checkpoint(run, "execution_recovery_requested")
            return {
                "run": run.model_dump(mode="json"),
                "replan_guidance": _execution_replan_guidance(issues),
            }
        verification = await self._orchestrator.verify(run)
        if verification.should_replan and run.replan_count < run.limits.max_replans:
            run = run.model_copy(
                update={
                    "replan_count": run.replan_count + 1,
                    "verification_issues": verification.issues,
                    "final_answer": verification.final_answer,
                }
            )
            run = _transition(
                run,
                GeneralAgentRunStatus.REPLANNING,
                "结果未通过校验，进入有限重规划。",
            )
            run = await self._checkpoint(run, "replanning_requested")
            return {
                "run": run.model_dump(mode="json"),
                "replan_guidance": verification.replan_guidance,
            }
        final_status = (
            GeneralAgentRunStatus.FAILED
            if blocking_failures or verification.outcome == "failed"
            else GeneralAgentRunStatus.COMPLETED
        )
        run = run.model_copy(
            update={
                "verification_issues": verification.issues,
                "final_answer": verification.final_answer,
                "finished_at": now_iso(),
                "resumable": final_status is GeneralAgentRunStatus.FAILED,
            }
        )
        run = _transition(run, final_status, "任务结果已收敛。")
        run = await self._checkpoint(run, "verification_finished")
        return {"run": run.model_dump(mode="json"), "replan_guidance": ""}

    def _route_after_verify(self, state: _RuntimeGraphState) -> str:
        status = GeneralAgentRun.model_validate(state["run"]).status
        return "plan" if status is GeneralAgentRunStatus.REPLANNING else "end"

    async def _checkpoint(
        self, run: GeneralAgentRun, event_type: str
    ) -> GeneralAgentRun:
        updated = run.model_copy(
            update={
                "checkpoint_revision": run.checkpoint_revision + 1,
                "updated_at": now_iso(),
            }
        )
        await self._repository.save(updated)
        await self._event_center.publish(event_type=event_type, run=updated)
        return updated

    async def _require_run(self, run_id: str) -> GeneralAgentRun:
        run = await self._repository.get(run_id)
        if run is None:
            raise GeneralAgentRunNotFoundError(run_id)
        return run


def _transition(
    run: GeneralAgentRun,
    status: GeneralAgentRunStatus,
    reason: str,
) -> GeneralAgentRun:
    if run.status is status and run.lifecycle_events:
        return run.model_copy(update={"updated_at": now_iso()})
    event = GeneralAgentLifecycleEvent(
        status=status,
        reason=reason,
        created_at=now_iso(),
    )
    return run.model_copy(
        update={
            "status": status,
            "lifecycle_events": [*run.lifecycle_events, event],
            "updated_at": event.created_at,
        }
    )


def _find_current_node(run: GeneralAgentRun, node_id: str) -> GeneralAgentNodeRun:
    for item in run.node_runs:
        if item.plan_revision == run.plan_revision and item.node_id == node_id:
            return item
    raise GeneralAgentRuntimeError(f"待授权节点“{node_id}”不存在。")


def _replace_node(
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
    raise GeneralAgentRuntimeError(f"运行节点“{replacement.node_id}”不存在。")


def _blocking_failed_nodes(run: GeneralAgentRun) -> list[GeneralAgentNodeRun]:
    if run.plan is None:
        return []
    plan_nodes = {node.node_id: node for node in run.plan.nodes}
    return [
        node
        for node in run.node_runs
        if node.plan_revision == run.plan_revision
        and node.status is GeneralAgentNodeStatus.FAILED
        and not plan_nodes[node.node_id].continue_on_failure
    ]


def _execution_failure_issues(
    nodes: list[GeneralAgentNodeRun],
) -> list[str]:
    return [
        (
            f"{node.capability_name}（节点 {node.node_id}）执行失败："
            f"{node.error_message or node.error_type or '未知错误'}"
        )
        for node in nodes
    ]


def _execution_replan_guidance(issues: list[str]) -> str:
    return (
        "上一版计划已在真实运行时校验或能力执行中失败。"
        "请根据失败位置和真实能力输入输出 Schema 重新规划；"
        "不要假定失败节点已经成功，也不要重复原错误交接地址。失败详情："
        + "；".join(issues)
    )


class GeneralAgentRuntimeError(RuntimeError):
    """通用 Runtime 请求无法按当前状态执行。"""


class GeneralAgentRunNotFoundError(GeneralAgentRuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"通用写作助手任务“{run_id}”不存在。")


class GeneralAgentConversationNotFoundError(GeneralAgentRuntimeError):
    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"通用写作助手对话“{conversation_id}”不存在。")
