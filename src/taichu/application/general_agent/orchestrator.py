"""负责理解、规划、校验和收敛的高层编排 Agent。"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from taichu.application.contracts.invocation_trace import InvocationTraceRepository
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    response_text,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentPlanDraft,
    GeneralAgentRun,
    GeneralAgentVerification,
)
from taichu.application.invocations.models import (
    InvocationStatus,
    InvocationTraceRecord,
    now_iso,
)
from taichu.application.services.invocation_policy_service import canonical_input_hash
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools.registry import ToolRegistry

_OutputModel = TypeVar("_OutputModel", bound=BaseModel)

_PLAN_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent。
你的职责是理解目标、选择最小充分执行路径、维护依赖和全局收敛；你不是设定、写作或审校专家。

硬性规则：
1. 只能使用能力目录中真实存在的 Tool 和专业子 Agent，不得创造能力名称。
2. 小问题不得强行扩展成长链路；无需项目事实或专业执行时可直接回答。
3. 涉及小说事实时必须安排取证能力，不能靠自身猜测。
4. Tool 是确定性原子能力；需要专业判断、写作、规划或审校时选择子 Agent。
5. 节点依赖必须形成无环图；可并行的节点不要制造虚假依赖。
6. 下游需要上游输出字段时，使用 input_bindings。source_path 已经以上游能力的 output 对象为根，不得自行添加 result、节点 ID 等包装层；字段必须来自上游 output_schema，数组下标使用点号数字，例如 chunks.0.content。target_path 已经以当前能力的输入对象为根，必须来自当前能力 input_schema，例如 source_request.direct_context。不得编造 text 等不存在的字段。
7. 专业子 Agent 可通过 source_request.upstream_artifact_refs 消费兼容的上游中间产物，Runtime 会根据依赖自动补充引用。
8. 未经用户明确允许，不得安排外部研究能力。
9. 写 Tool 可以出现在计划中，但 Runtime 会在执行前暂停并请求作者授权。
10. 信息缺口会实质改变结果时才澄清；不要询问可以从小说正文或知识库取得的事实。
11. 所有面向作者的内容使用中文。
12. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
"""

_VERIFY_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent，当前负责结果校验与最终收敛。
请对照用户目标、约束、执行计划和真实节点结果判断任务是否满足。

硬性规则：
1. 不得把失败节点描述为成功，也不得补造节点没有提供的小说事实或来源。
2. satisfied 表示目标已满足；partial 表示可以交付但存在明确缺口；failed 表示没有可用结果。
3. 只有存在可由已注册能力修复的实质缺口时才请求重规划。
4. 最终回答直接面向作者，使用中文，清楚区分事实、建议、草稿与不确定项。
5. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
"""


class OrchestratorAgent:
    """在 Runtime 之上保持全局控制的高层智能编排者。"""

    def __init__(
        self,
        *,
        llm: LLMGatewayContract,
        model_router: ModelRoleRouter,
        tool_registry: ToolRegistry,
        subagent_registry: SubagentRegistry,
        trace_repository: InvocationTraceRepository | None = None,
    ) -> None:
        self._llm = llm
        self._model_router = model_router
        self._tool_registry = tool_registry
        self._subagent_registry = subagent_registry
        self._trace_repository = trace_repository

    async def plan(
        self,
        run: GeneralAgentRun,
        *,
        replan_guidance: str = "",
    ) -> GeneralAgentExecutionPlan:
        """根据当前请求和真实能力目录生成一次动态 DAG。"""
        contract_error = ""
        invalid_plan: dict[str, Any] | None = None
        for contract_attempt in range(2):
            payload = {
                "用户目标": run.user_goal,
                "对话": [message.model_dump(mode="json") for message in run.messages],
                "当前范围": run.scope.model_dump(mode="json"),
                "作者约束": run.author_constraints,
                "允许外部研究": run.external_access_allowed,
                "最大计划节点数": run.limits.max_plan_nodes,
                "当前重规划次数": run.replan_count,
                "重规划指导": replan_guidance,
                "上一版计划": (
                    run.plan.model_dump(mode="json") if run.plan is not None else None
                ),
                "上一版执行结果": _node_result_payload(run),
                "能力目录": self._capability_catalog(),
                "输出Schema": GeneralAgentPlanDraft.model_json_schema(),
            }
            if contract_error:
                payload["本次计划契约校验错误"] = contract_error
                payload["需要修复的本次计划"] = invalid_plan
                payload["修复要求"] = (
                    "只修复未知能力、权限或计划规模问题，不要执行这份错误计划。"
                )
            draft = await self._complete_json(
                run=run,
                phase="plan" if not replan_guidance else "replan",
                system_prompt=_PLAN_SYSTEM_PROMPT,
                payload=payload,
                output_schema=GeneralAgentPlanDraft,
            )
            plan = GeneralAgentExecutionPlan.model_validate(
                draft.model_dump(mode="json")
            )
            try:
                self._validate_capabilities(plan, run)
                if len(plan.nodes) > run.limits.max_plan_nodes:
                    raise OrchestratorPlanError("编排计划超过本次任务允许的节点数量。")
            except OrchestratorPlanError as error:
                if contract_attempt:
                    raise
                contract_error = str(error)
                invalid_plan = plan.model_dump(mode="json")
                continue
            return plan
        raise OrchestratorPlanError("编排计划未通过能力契约校验。")

    async def verify(self, run: GeneralAgentRun) -> GeneralAgentVerification:
        """检查真实执行结果并生成最终回答或有限重规划决定。"""
        payload = {
            "用户目标": run.user_goal,
            "作者约束": run.author_constraints,
            "当前范围": run.scope.model_dump(mode="json"),
            "执行计划": run.plan.model_dump(mode="json") if run.plan else None,
            "计划修订号": run.plan_revision,
            "节点结果": _node_result_payload(run),
            "直接回答草稿": run.plan.direct_response if run.plan else "",
            "最终回答指导": run.plan.final_response_guidance if run.plan else "",
            "剩余重规划次数": max(0, run.limits.max_replans - run.replan_count),
            "输出Schema": GeneralAgentVerification.model_json_schema(),
        }
        decision = await self._complete_json(
            run=run,
            phase="verify",
            system_prompt=_VERIFY_SYSTEM_PROMPT,
            payload=payload,
            output_schema=GeneralAgentVerification,
        )
        if run.replan_count >= run.limits.max_replans and decision.should_replan:
            decision = decision.model_copy(update={"should_replan": False})
        return decision

    def _capability_catalog(self) -> dict[str, list[dict[str, Any]]]:
        tools: list[dict[str, Any]] = []
        for tool_manifest in self._tool_registry.list_manifests():
            tools.append(
                {
                    "name": tool_manifest.name,
                    "description": tool_manifest.description,
                    "side_effect": tool_manifest.side_effect.value,
                    "requires_external_access": tool_manifest.requires_external_access,
                    "input_schema": tool_manifest.input_schema.model_json_schema(),
                    "output_schema": tool_manifest.output_schema.model_json_schema(),
                }
            )
        subagents: list[dict[str, Any]] = []
        for subagent_manifest in self._subagent_registry.list_manifests():
            subagents.append(
                {
                    "name": subagent_manifest.name,
                    "label": subagent_manifest.label,
                    "description": subagent_manifest.description,
                    "non_responsibilities": list(
                        subagent_manifest.non_responsibilities
                    ),
                    "accepted_artifact_types": sorted(
                        subagent_manifest.accepted_artifact_types
                    ),
                    "input_schema": subagent_manifest.input_schema.model_json_schema(),
                    "output_schema": (
                        subagent_manifest.output_schema.model_json_schema()
                    ),
                }
            )
        return {"tools": tools, "subagents": subagents}

    def _validate_capabilities(
        self,
        plan: GeneralAgentExecutionPlan,
        run: GeneralAgentRun,
    ) -> None:
        tools = {item.name: item for item in self._tool_registry.list_manifests()}
        subagents = {
            item.name: item for item in self._subagent_registry.list_manifests()
        }
        for node in plan.nodes:
            if node.kind is GeneralAgentNodeKind.TOOL:
                tool_manifest = tools.get(node.capability_name)
                if tool_manifest is None:
                    raise OrchestratorPlanError(
                        f"编排计划引用了未知工具“{node.capability_name}”。"
                    )
                if (
                    tool_manifest.requires_external_access
                    and not run.external_access_allowed
                ):
                    raise OrchestratorPlanError(
                        "用户未允许外部研究，计划却安排了外部工具。"
                    )
            else:
                subagent_manifest = subagents.get(node.capability_name)
                if subagent_manifest is None:
                    raise OrchestratorPlanError(
                        f"编排计划引用了未知专业子智能体“{node.capability_name}”。"
                    )
                if (
                    node.capability_name == "external_research"
                    and not run.external_access_allowed
                ):
                    raise OrchestratorPlanError(
                        "用户未允许外部研究，计划却安排了外部研究。"
                    )

    async def _complete_json(
        self,
        *,
        run: GeneralAgentRun,
        phase: str,
        system_prompt: str,
        payload: dict[str, Any],
        output_schema: type[_OutputModel],
    ) -> _OutputModel:
        model_id = self._model_router.model_for("orchestrator")
        user_prompt = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        last_text = ""
        last_error: Exception | None = None
        for attempt in range(2):
            prompt = user_prompt
            if attempt:
                prompt += (
                    "\n\n上次输出未通过结构校验，请只修复 JSON 结构。"
                    f"\n错误：{str(last_error)[:2_000]}"
                    f"\n上次输出：{last_text[:10_000]}"
                )
            request = LLMRequest(
                model_id=model_id,
                messages=(
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=prompt),
                ),
                task_type="general_agent_orchestration",
                task_name=f"general_writing_orchestrator.{phase}",
                run_id=run.run_id,
                chapter_ids=tuple(run.scope.chapter_ids),
                response_mode="json",
                temperature=0.1,
                max_output_tokens=12_000,
                feature="general_writing_assistant",
            )
            started_at = now_iso()
            timer = perf_counter()
            try:
                response = await self._llm.complete(request)
                last_text = response_text(response)
                output = output_schema.model_validate(_extract_json(last_text))
                await self._append_llm_trace(
                    run,
                    request,
                    response,
                    started_at,
                    timer,
                    attempt,
                )
                return output
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                last_error = error
                await self._append_llm_failure_trace(
                    run,
                    request,
                    started_at,
                    timer,
                    attempt,
                    error,
                )
            except Exception as error:
                await self._append_llm_failure_trace(
                    run,
                    request,
                    started_at,
                    timer,
                    attempt,
                    error,
                )
                raise
        raise OrchestratorOutputError(
            f"高层编排 Agent 输出未通过结构校验：{last_error}"
        )

    async def _append_llm_trace(
        self,
        run: GeneralAgentRun,
        request: LLMRequest,
        response: LLMResponse,
        started_at: str,
        timer: float,
        retry_count: int,
    ) -> None:
        if self._trace_repository is None:
            return
        usage = response.usage
        record = InvocationTraceRecord(
            trace_id=f"trace_{uuid4().hex}",
            capability_type="llm",
            capability_name=request.task_name,
            task_id=run.task_id,
            run_id=run.run_id,
            call_id=f"call_{uuid4().hex}",
            caller_type="orchestrator",
            caller_name="general_writing_orchestrator",
            status=InvocationStatus.COMPLETED,
            input_sha256=canonical_input_hash({"prompt": str(request)}),
            input_char_count=len(str(request)),
            output_char_count=len(response.text),
            model_role="orchestrator",
            model_id=response.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            retry_count=retry_count,
            started_at=started_at,
            finished_at=now_iso(),
            duration_ms=max(0, round((perf_counter() - timer) * 1000)),
        )
        try:
            await self._trace_repository.append(record)
        except Exception:  # noqa: BLE001
            return

    async def _append_llm_failure_trace(
        self,
        run: GeneralAgentRun,
        request: LLMRequest,
        started_at: str,
        timer: float,
        retry_count: int,
        error: Exception,
    ) -> None:
        if self._trace_repository is None:
            return
        record = InvocationTraceRecord(
            trace_id=f"trace_{uuid4().hex}",
            capability_type="llm",
            capability_name=request.task_name,
            task_id=run.task_id,
            run_id=run.run_id,
            call_id=f"call_{uuid4().hex}",
            caller_type="orchestrator",
            caller_name="general_writing_orchestrator",
            status=InvocationStatus.FAILED,
            input_sha256=canonical_input_hash({"prompt": str(request)}),
            input_char_count=len(str(request)),
            model_role="orchestrator",
            model_id=request.model_id,
            retry_count=retry_count,
            started_at=started_at,
            finished_at=now_iso(),
            duration_ms=max(0, round((perf_counter() - timer) * 1000)),
            error_type=type(error).__name__,
            error_message=str(error)[:500],
        )
        try:
            await self._trace_repository.append(record)
        except Exception:  # noqa: BLE001
            return


def _node_result_payload(run: GeneralAgentRun) -> list[dict[str, Any]]:
    return [
        {
            "node_id": item.node_id,
            "plan_revision": item.plan_revision,
            "kind": item.kind.value,
            "capability_name": item.capability_name,
            "status": item.status.value,
            "output": item.output,
            "source_refs": item.source_refs,
            "artifact_refs": item.artifact_refs,
            "error": item.error_message,
        }
        for item in run.node_runs
    ]


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        stripped = stripped[first_newline + 1 :] if first_newline >= 0 else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型输出中没有 JSON 对象。")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("模型输出必须是 JSON 对象。")
    return payload


class OrchestratorPlanError(ValueError):
    """高层计划引用了无效能力或违反任务权限。"""


class OrchestratorOutputError(ValueError):
    """高层编排 Agent 未能产出有效结构化结果。"""
