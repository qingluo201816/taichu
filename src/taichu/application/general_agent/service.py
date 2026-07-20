"""通用写作助手顶层 LangGraph、生命周期和恢复服务。"""

from __future__ import annotations

import asyncio
import builtins
from datetime import UTC, datetime
import json
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from taichu.application.contracts.general_agent_run import GeneralAgentRunRepository
from taichu.application.contracts.general_agent_effects import (
    GeneralAgentEffectRepository,
)
from taichu.application.general_agent.context import (
    ContextAssembler,
    ContextAssemblyResult,
    ContextPhase,
)
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.executor import (
    DynamicDagExecutor,
    InjectedProcessTermination,
)
from taichu.application.general_agent.models import (
    GeneralAgentConversation,
    GeneralAgentContextCategoryStat,
    GeneralAgentCompressionStats,
    GeneralAgentHumanRequest,
    GeneralAgentExecutionPlan,
    GeneralAgentLifecycleEvent,
    GeneralAgentMessage,
    GeneralAgentPlanNode,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentRunLimits,
    GeneralAgentRunStatus,
    GeneralAgentScope,
)
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.general_agent.request_analysis import (
    explicit_chapter_orders,
    is_explicit_chapter_content_request,
)
from taichu.application.general_agent.recovery import (
    CheckpointIntegritySummary,
    EffectRecord,
    EffectSummary,
    GeneralAgentRecoverySnapshot,
)
from taichu.application.invocations.models import now_iso
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.agent_memory_service import AgentMemoryService

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
        memory_service: AgentMemoryService,
        context_assembler: ContextAssembler,
        graph_checkpointer: BaseCheckpointSaver[Any] | None = None,
        effect_repository: GeneralAgentEffectRepository | None = None,
    ) -> None:
        self._repository = repository
        self._event_center = event_center
        self._orchestrator = orchestrator
        self._executor = executor
        self._policy_service = policy_service
        self._memory_service = memory_service
        self._context_assembler = context_assembler
        self._graph_checkpointer = graph_checkpointer or InMemorySaver()
        self._effect_repository = effect_repository
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
        start_new_conversation: bool | None = None,
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
        if start_new_conversation is True and conversation_id is not None:
            raise GeneralAgentRuntimeError("开启新对话时不能复用已有会话标识。")
        if start_new_conversation is False and conversation_id is None:
            raise GeneralAgentRuntimeError("继续当前对话时缺少会话标识。")
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
            messages, parent_run_id, request_index = await self._messages_for_new_turn(
                resolved_conversation_id,
                goal=goal,
                created_at=created_at,
                existing_conversation=conversation_id is not None,
            )
            run = GeneralAgentRun(
                run_id=run_id,
                task_id=resolved_conversation_id,
                conversation_id=resolved_conversation_id,
                request_index=request_index,
                parent_run_id=parent_run_id,
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
            run = await self._checkpoint(run, "run_created")
            memory_ids = await self._memory_service.record_user_instructions(run)
            if memory_ids:
                run = _with_memory_refs(run, memory_ids)
                run = await self._checkpoint(run, "author_memories_recorded")
            return run

    async def run(
        self,
        *,
        user_goal: str,
        conversation_id: str | None = None,
        start_new_conversation: bool | None = None,
        scope: GeneralAgentScope | None = None,
        author_constraints: list[str] | None = None,
        external_access_allowed: bool = False,
        limits: GeneralAgentRunLimits | None = None,
    ) -> GeneralAgentRun:
        run = await self.create_run(
            user_goal=user_goal,
            conversation_id=conversation_id,
            start_new_conversation=start_new_conversation,
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
        start_new_conversation: bool | None = None,
        scope: GeneralAgentScope | None = None,
        author_constraints: list[str] | None = None,
        external_access_allowed: bool = False,
        limits: GeneralAgentRunLimits | None = None,
    ) -> GeneralAgentRun:
        run = await self.create_run(
            user_goal=user_goal,
            conversation_id=conversation_id,
            start_new_conversation=start_new_conversation,
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
        source_run = await self._require_run(run_id)
        if source_run.status in _TERMINAL_STATUSES:
            raise GeneralAgentRuntimeError("已结束的任务不能恢复。")
        conversation_lock = self._conversation_locks.setdefault(
            source_run.conversation_id,
            asyncio.Lock(),
        )
        async with conversation_lock:
            conversation_runs = await self.get_conversation(source_run.conversation_id)
            if conversation_runs[-1].run_id != source_run.run_id:
                raise GeneralAgentRuntimeError("该轮待处理内容已经由后续轮次接续。")

            request = source_run.pending_human_request
            if request is not None and request.kind == "clarification":
                reply = answer.strip()
                if not reply:
                    raise GeneralAgentRuntimeError("提交澄清回答时必须提供作者回答。")
                run = await self._create_continuation_run(
                    source_run,
                    user_goal=reply,
                    assistant_prompt=request.prompt,
                )
                memory_id = await self._memory_service.record_human_correction(
                    run,
                    content=reply,
                )
                run = _with_memory_refs(run, [memory_id])
                run = await self._checkpoint(run, "clarification_recorded")
                return await self._execute_run(run.run_id)

            if request is not None and request.kind == "write_authorization":
                if approve is None:
                    raise GeneralAgentRuntimeError("提交写入决定时必须明确批准或拒绝。")
                if (
                    approve
                    and request.second_confirmation_required
                    and not second_confirmation
                ):
                    raise GeneralAgentRuntimeError("该高风险写入需要二次确认。")
                return await self._continue_write_authorization(
                    source_run,
                    request,
                    approve=approve,
                    second_confirmation=second_confirmation,
                )

            if source_run.status in {
                GeneralAgentRunStatus.FAILED,
                GeneralAgentRunStatus.TIMEOUT,
            }:
                return await self._execute_run(
                    source_run.run_id,
                    resume_from_graph=True,
                )

            raise GeneralAgentRuntimeError("当前任务不处于可接续状态。")

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
            grouped.setdefault(run.conversation_id, []).append(run)

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
                    request_count=len(ordered),
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
        runs = [
            run
            for run in await self._all_runs()
            if run.conversation_id == conversation_id
        ]
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
        await self._memory_service.delete_conversation_memories(conversation_id)
        return deleted_count

    async def delete(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            raise GeneralAgentRuntimeError("运行中的任务不能删除，请先取消。")
        deleted = await self._repository.delete(run_id)
        if deleted:
            if self._effect_repository is not None:
                await self._effect_repository.delete_run(run_id)
            await self._graph_checkpointer.adelete_thread(run_id)
            await self._event_center.delete_snapshot(run_id)
        return deleted

    async def list_effects(self, run_id: str) -> builtins.list[EffectRecord]:
        await self._require_run(run_id)
        if self._effect_repository is None:
            return []
        return await self._effect_repository.list_effects(run_id)

    async def recovery_snapshot(
        self,
        run_id: str,
    ) -> GeneralAgentRecoverySnapshot:
        await self._require_run(run_id)
        summary_reader = getattr(self._graph_checkpointer, "inspect_thread", None)
        checkpoint = CheckpointIntegritySummary()
        if callable(summary_reader):
            summary = summary_reader(run_id)
            checkpoint = CheckpointIntegritySummary(
                current_revision=summary.current_revision,
                available_revisions=summary.available_revisions,
                integrity_status=summary.integrity_status,
                recovered_from_revision=summary.recovered_from_revision,
                damage_warnings=summary.damage_warnings,
                legacy_migrated=summary.legacy_migrated,
            )
        events = await self.list_effects(run_id)
        latest: dict[str, EffectRecord] = {}
        for event in events:
            latest[event.effect_id] = event
        effects = [
            EffectSummary(
                effect_id=event.effect_id,
                node_id=event.node_id,
                tool_name=event.tool_name,
                status=event.status,
                resource_scopes=event.resource_scopes,
                authorization_bound=event.authorization_reference is not None,
                reason=event.reason,
                updated_at=event.created_at,
            )
            for event in latest.values()
        ]
        effects.sort(key=lambda item: (item.updated_at, item.effect_id))
        return GeneralAgentRecoverySnapshot(
            run_id=run_id,
            checkpoint=checkpoint,
            effects=effects,
        )

    async def _messages_for_new_turn(
        self,
        conversation_id: str,
        *,
        goal: str,
        created_at: str,
        existing_conversation: bool,
    ) -> tuple[builtins.list[GeneralAgentMessage], str | None, int]:
        if not existing_conversation:
            return (
                [
                    GeneralAgentMessage(
                        role="user",
                        content=goal,
                        created_at=created_at,
                    )
                ],
                None,
                1,
            )

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
        return messages, latest.run_id, latest.request_index + 1

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
            self._start_background(run.run_id, resume_from_graph=True)
            recovered += 1
        return recovered

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _create_continuation_run(
        self,
        source_run: GeneralAgentRun,
        *,
        user_goal: str,
        assistant_prompt: str = "",
    ) -> GeneralAgentRun:
        created_at = now_iso()
        timestamp = datetime.now(UTC)
        run_id = f"general_run_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        messages = list(source_run.messages)
        if assistant_prompt.strip() and not (
            messages
            and messages[-1].role == "assistant"
            and messages[-1].content == assistant_prompt.strip()
        ):
            messages.append(
                GeneralAgentMessage(
                    role="assistant",
                    content=assistant_prompt.strip(),
                    created_at=source_run.updated_at,
                )
            )
        messages.append(
            GeneralAgentMessage(
                role="user",
                content=user_goal,
                created_at=created_at,
            )
        )
        run = GeneralAgentRun(
            run_id=run_id,
            task_id=source_run.conversation_id,
            conversation_id=source_run.conversation_id,
            request_index=source_run.request_index + 1,
            parent_run_id=source_run.run_id,
            user_goal=user_goal,
            scope=source_run.scope,
            author_constraints=source_run.author_constraints,
            external_access_allowed=source_run.external_access_allowed,
            limits=source_run.limits,
            messages=messages,
            lifecycle_events=[
                GeneralAgentLifecycleEvent(
                    status=GeneralAgentRunStatus.INIT,
                    reason="收到新的作者请求，本轮执行已创建。",
                    created_at=created_at,
                )
            ],
            created_at=created_at,
            updated_at=created_at,
            started_at=created_at,
        )
        return await self._checkpoint(run, "continuation_run_created")

    async def _continue_write_authorization(
        self,
        source_run: GeneralAgentRun,
        request: GeneralAgentHumanRequest,
        *,
        approve: bool,
        second_confirmation: bool,
    ) -> GeneralAgentRun:
        if request.node_id is None or request.tool_name is None:
            raise GeneralAgentRuntimeError("写入授权请求缺少目标节点。")
        source_node = _find_current_node(source_run, request.node_id)
        decision = "授权继续上一轮的写入操作。" if approve else "拒绝上一轮的写入操作。"
        run = await self._create_continuation_run(
            source_run,
            user_goal=decision,
            assistant_prompt=request.prompt,
        )
        if not approve:
            final_answer = "已按你的决定拒绝写入，本次没有修改正文。"
            plan = GeneralAgentExecutionPlan(
                rationale="作者拒绝了上一轮待确认的持久化操作，本轮不执行写入节点。",
                direct_response=final_answer,
                nodes=[],
            )
            run = run.model_copy(
                update={
                    "plan": plan,
                    "plan_revision": 1,
                    "final_answer": final_answer,
                    "finished_at": now_iso(),
                    "resumable": False,
                }
            )
            run = _transition(
                run,
                GeneralAgentRunStatus.COMPLETED,
                "作者拒绝写入，本轮执行已结束。",
            )
            return await self._checkpoint(run, "write_rejected")

        input_payload = dict(request.input_summary or source_node.resolved_input)
        grant = await self._policy_service.issue_author_write(
            task_id=run.task_id,
            tool_name=request.tool_name,
            input_payload=input_payload,
            resource_scopes=tuple(request.resource_scopes),
            second_confirmation=second_confirmation,
        )
        plan_node = GeneralAgentPlanNode(
            node_id=source_node.node_id,
            kind=source_node.kind,
            capability_name=source_node.capability_name,
            objective=source_node.objective,
            input_data=input_payload,
            dependencies=[],
            input_bindings=[],
        )
        plan = GeneralAgentExecutionPlan(
            rationale="作者已批准上一轮待确认的确定输入，本轮只执行该授权节点。",
            nodes=[plan_node],
            final_response_guidance=(
                source_run.plan.final_response_guidance if source_run.plan else ""
            ),
        )
        node_run = GeneralAgentNodeRun(
            node_id=source_node.node_id,
            plan_revision=1,
            kind=source_node.kind,
            capability_name=source_node.capability_name,
            objective=source_node.objective,
            dependencies=[],
            status=GeneralAgentNodeStatus.PENDING,
            resolved_input=input_payload,
            authorization_grant_id=grant.grant_id,
            authorization_approved=True,
            authorization_second_confirmation=second_confirmation,
            authorization_resource_scopes=request.resource_scopes,
        )
        run = run.model_copy(
            update={
                "plan": plan,
                "plan_revision": 1,
                "node_runs": [node_run],
            }
        )
        run = _transition(
            run,
            GeneralAgentRunStatus.EXECUTING,
            "作者已授权上一轮的确定输入，开始本轮写入执行。",
        )
        run = await self._checkpoint(run, "write_authorization_recorded")
        return await self._execute_run(run.run_id)

    def _start_background(
        self,
        run_id: str,
        *,
        resume_from_graph: bool = False,
    ) -> None:
        current = self._tasks.get(run_id)
        if current is not None and not current.done():
            raise GeneralAgentRuntimeError("该任务已经在运行。")
        task = asyncio.create_task(
            self._execute_run(run_id, resume_from_graph=resume_from_graph)
        )
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

    async def _execute_run(
        self,
        run_id: str,
        *,
        resume_from_graph: bool = False,
    ) -> GeneralAgentRun:
        lock = self._locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            run = await self._require_run(run_id)
            try:
                async with asyncio.timeout(run.limits.max_runtime_seconds):
                    config = {
                        "recursion_limit": 20,
                        "configurable": {"thread_id": run_id},
                    }
                    graph_input: _RuntimeGraphState | None = {
                        "run": run.model_dump(mode="json")
                    }
                    result: dict[str, Any] | None = None
                    if resume_from_graph:
                        graph_state = await self._graph.aget_state(config)
                        if graph_state.next:
                            graph_input = None
                        elif graph_state.values:
                            result = dict(graph_state.values)
                    if result is None:
                        result = await self._graph.ainvoke(
                            graph_input,
                            config=config,
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
            except InjectedProcessTermination:
                raise
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
        return graph.compile(checkpointer=self._graph_checkpointer)

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
        phase: ContextPhase = "replan" if state.get("replan_guidance", "") else "plan"
        assembly = await self._context_assembler.assemble(
            run,
            phase=phase,
            replan_guidance=state.get("replan_guidance", ""),
        )
        run = _with_context_snapshot(run, assembly)
        run = await self._checkpoint(run, "context_assembled")
        plan = await self._orchestrator.plan(
            run,
            context=assembly.snapshot.envelope,
            replan_guidance=state.get("replan_guidance", ""),
        )
        memory_ids = await self._memory_service.record_plan(run, plan)
        run = _with_memory_refs(run, memory_ids)
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
        memory_ids = await self._memory_service.record_node_results(
            run,
            [
                node
                for node in run.node_runs
                if node.plan_revision == run.plan_revision
                and node.status is GeneralAgentNodeStatus.SUCCESS
            ],
        )
        if memory_ids:
            run = _with_memory_refs(run, memory_ids)
            run = await self._checkpoint(run, "node_memories_recorded")
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
        execution_issues = _execution_failure_issues(blocking_failures)
        source_quality_issues = _chapter_source_quality_issues(run)
        recovery_issues = [*execution_issues, *source_quality_issues]
        if recovery_issues and run.replan_count < run.limits.max_replans:
            run = run.model_copy(
                update={
                    "replan_count": run.replan_count + 1,
                    "verification_issues": recovery_issues,
                    "final_answer": "",
                }
            )
            run = _transition(
                run,
                GeneralAgentRunStatus.REPLANNING,
                "执行结果缺少必要来源或步骤失败，进入有限自动修复。",
            )
            run = await self._checkpoint(run, "execution_recovery_requested")
            return {
                "run": run.model_dump(mode="json"),
                "replan_guidance": _execution_replan_guidance(recovery_issues),
            }
        assembly = await self._context_assembler.assemble(run, phase="verify")
        run = _with_context_snapshot(run, assembly)
        run = await self._checkpoint(run, "verification_context_assembled")
        verification = await self._orchestrator.verify(
            run,
            context=assembly.snapshot.envelope,
        )
        memory_ids = await self._memory_service.record_verification(
            run,
            verification,
        )
        run = _with_memory_refs(run, memory_ids)
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
        unresolved_issues = list(
            dict.fromkeys([*source_quality_issues, *verification.issues])
        )
        final_status = (
            GeneralAgentRunStatus.FAILED
            if blocking_failures
            or source_quality_issues
            or verification.outcome == "failed"
            else GeneralAgentRunStatus.COMPLETED
        )
        run = run.model_copy(
            update={
                "verification_issues": unresolved_issues,
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


def _chapter_source_quality_issues(run: GeneralAgentRun) -> list[str]:
    """明确章节内容请求必须取得 Markdown 正文来源，空检索不能伪装成功。"""

    if not is_explicit_chapter_content_request(run.user_goal):
        return []
    current_nodes = [
        node
        for node in run.node_runs
        if node.plan_revision == run.plan_revision
        and node.status is GeneralAgentNodeStatus.SUCCESS
    ]
    source_refs = {
        source_ref for node in current_nodes for source_ref in node.source_refs
    }
    if any(source_ref.startswith("manuscript:") for source_ref in source_refs):
        return []
    orders = explicit_chapter_orders(run.user_goal)
    return [
        "当前请求明确指定章节顺序"
        f"{orders}，但执行结果没有取得 manuscript: 正文来源引用；"
        "必须改用 read_manuscript 按章节顺序直接读取，不能把空搜索视为完成。"
    ]


def _execution_replan_guidance(issues: list[str]) -> str:
    return (
        "上一版计划已在真实运行时校验或能力执行中失败。"
        "请根据失败位置和真实能力输入输出 Schema 重新规划；"
        "不要假定失败节点已经成功，也不要重复原错误交接地址。失败详情："
        + "；".join(issues)
    )


def _with_memory_refs(
    run: GeneralAgentRun,
    memory_ids: list[str],
) -> GeneralAgentRun:
    return run.model_copy(
        update={"memory_refs": _deduplicate([*run.memory_refs, *memory_ids])}
    )


def _with_context_snapshot(
    run: GeneralAgentRun,
    assembly: ContextAssemblyResult,
) -> GeneralAgentRun:
    envelope = assembly.snapshot.envelope
    stats = {item.category: item for item in envelope.category_stats}
    memory_ids = [reference.memory_id for reference in assembly.snapshot.memory_refs]
    compression = GeneralAgentCompressionStats(
        compressed=envelope.compressed,
        fallback_used=envelope.fallback_used,
        input_char_count=envelope.total_char_count,
        output_char_count=(
            len(json.dumps(envelope.digest.model_dump(mode="json"), ensure_ascii=False))
            if envelope.digest is not None
            else envelope.total_char_count
        ),
        estimated_token_count=envelope.estimated_token_count,
        omitted_message_count=stats.get(
            "process_history",
            GeneralAgentContextCategoryStat(category="process_history"),
        ).omitted_count,
        omitted_node_count=stats.get(
            "working_memory",
            GeneralAgentContextCategoryStat(category="working_memory"),
        ).omitted_count,
        selected_memory_count=len(memory_ids),
    )
    return run.model_copy(
        update={
            "memory_refs": _deduplicate([*run.memory_refs, *memory_ids]),
            "context_snapshot_id": assembly.snapshot.snapshot_id,
            "context_snapshot": assembly.snapshot,
            "compression_stats": compression,
            "context_resume_differences": _deduplicate(
                [
                    *run.context_resume_differences,
                    *assembly.resume_differences,
                ]
            ),
        }
    )


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class GeneralAgentRuntimeError(RuntimeError):
    """通用 Runtime 请求无法按当前状态执行。"""


class GeneralAgentRunNotFoundError(GeneralAgentRuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"通用写作助手任务“{run_id}”不存在。")


class GeneralAgentConversationNotFoundError(GeneralAgentRuntimeError):
    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"通用写作助手对话“{conversation_id}”不存在。")
