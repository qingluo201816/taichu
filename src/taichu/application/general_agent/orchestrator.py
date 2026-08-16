"""负责理解、规划、校验和收敛的高层编排 Agent。"""

from __future__ import annotations

import ast
import json
import re
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
    GeneralAgentContextEnvelope,
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentNodeStatus,
    GeneralAgentPlanDraft,
    GeneralAgentRun,
    GeneralAgentVerification,
)
from taichu.application.general_agent.request_analysis import (
    explicit_chapter_orders,
    is_explicit_chapter_content_request,
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

_PLAN_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent，负责一次形成可执行的最小充分 DAG。
你的职责是理解目标、从完整能力契约目录选择最小充分路径、维护依赖和全局收敛；你不是设定、写作或审校专家。

硬性规则：
1. 只能使用能力目录中真实存在的 Tool 和专业子 Agent，不得创造能力名称。
2. 小问题不得强行扩展成长链路；无需项目事实或专业执行时可直接回答。
3. 涉及小说事实时必须安排取证能力，不能靠自身猜测。
4. Tool 是确定性原子能力；需要专业判断、写作、规划或审校时选择子 Agent。
5. 节点依赖必须形成无环图；可并行的节点不要制造虚假依赖。
6. 必须依据完整能力契约，在选择能力的同一次输出中填写当前已能确定的 input_data。
7. 已知明确章节序号且用户要求读取、概括或总结正文时，必须选择 read_manuscript 直接读取；search_manuscript 只用于原文位置未知的关键词搜索。
8. 参数依赖上游节点结果时必须使用 input_bindings 声明；source_path 以上游 output 为根，target_path 以当前能力输入对象为根。
9. 未经用户明确允许，不得安排外部研究能力。
10. 写 Tool 可以出现在计划中，但 Runtime 会在执行前暂停并请求作者授权。
11. 信息缺口会实质改变结果时才澄清；不要询问可以从小说正文或知识库取得的事实。
12. 所有面向作者的内容使用中文。
13. 运行记忆不是小说事实；fact_reference 只能提示你安排正文或统一召回重新取证。
14. 你不能直接写入、确认或删除运行记忆。
15. 完整能力契约目录中的所有能力都是真实注册能力；不得编造契约中不存在的输入、输出字段或能力。
16. 问题需要连接多个正文片段、知识卡或发现未在问题中明说的桥接实体时，优先安排 retrieve_story_graph；单一知识事实仍使用 retrieve_knowledge，明确章节读取仍使用 read_manuscript。
17. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
"""

_VERIFY_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent，当前负责结果校验与最终收敛。
请对照用户目标、约束、执行计划和真实节点结果判断任务是否满足。

硬性规则：
1. 不得把失败节点描述为成功，也不得补造节点没有提供的小说事实或来源。
2. satisfied 表示目标已满足；partial 表示可以交付但存在明确缺口；failed 表示没有可用结果。
3. 只有存在可由已注册能力修复的实质缺口时才请求重规划。
4. 最终回答直接面向作者，使用中文，清楚区分事实、建议、草稿与不确定项。
5. 运行记忆不是小说事实；没有重新取证的事实引用不能写成确定事实。
6. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
"""


_PLAN_SYSTEM_PROMPT += """
18. input_bindings 的数组下标统一使用点号，例如 chunks.0.content；方括号形式会被规范化，但不得使用其他路径语法。
19. 重规划时不得重复执行已经成功且仍可满足目标的节点；需要把成功结果带入新修订版时，使用 reuse_from_node_id 明确引用上一修订版节点。
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
        capability_catalog_char_budget: int = 80_000,
    ) -> None:
        self._llm = llm
        self._model_router = model_router
        self._tool_registry = tool_registry
        self._subagent_registry = subagent_registry
        self._trace_repository = trace_repository
        self._capability_catalog_char_budget = max(
            10_000,
            capability_catalog_char_budget,
        )

    async def plan(
        self,
        run: GeneralAgentRun,
        *,
        context: GeneralAgentContextEnvelope,
        replan_guidance: str = "",
    ) -> GeneralAgentExecutionPlan:
        """一次选择能力、填写已知参数并声明结果依赖。"""
        phase = "replan" if replan_guidance else "plan"
        capability_catalog = self._capability_catalog()
        chapter_orders = explicit_chapter_orders(context.current_goal)
        plan_output_schema = GeneralAgentPlanDraft.model_json_schema()
        nodes_schema = plan_output_schema.get("properties", {}).get("nodes")
        if isinstance(nodes_schema, dict):
            nodes_schema["maxItems"] = run.limits.max_plan_nodes
        plan_error = ""
        plan: GeneralAgentExecutionPlan | None = None
        for plan_attempt in range(2):
            payload = {
                "允许外部研究": run.external_access_allowed,
                "最大计划节点数": run.limits.max_plan_nodes,
                "当前重规划次数": run.replan_count,
                "已解析的明确章节顺序": chapter_orders,
            }
            if plan_error:
                payload["上一版计划错误"] = plan_error
                payload["修复要求"] = "修复能力、参数或依赖，不要重复上一版错误。"
            candidate = await self._complete_json(
                run=run,
                phase=phase,
                system_prompt=_PLAN_SYSTEM_PROMPT,
                context=context,
                stable_payload={
                    "完整能力契约目录": capability_catalog,
                    "输出Schema": plan_output_schema,
                },
                working_payload=payload,
                output_schema=GeneralAgentPlanDraft,
            )
            try:
                self._validate_capabilities(candidate, run, context=context)
            except OrchestratorPlanError as error:
                if plan_attempt:
                    raise
                plan_error = str(error)
                continue
            plan = GeneralAgentExecutionPlan.model_validate(
                candidate.model_dump(mode="json")
            )
            break
        if plan is None:
            raise OrchestratorPlanError("执行计划未通过完整能力契约校验。")
        return plan

    async def verify(
        self,
        run: GeneralAgentRun,
        *,
        context: GeneralAgentContextEnvelope,
    ) -> GeneralAgentVerification:
        """检查真实执行结果并生成最终回答或有限重规划决定。"""
        working_payload = {
            "计划修订号": run.plan_revision,
            "剩余重规划次数": max(0, run.limits.max_replans - run.replan_count),
        }
        decision = await self._complete_json(
            run=run,
            phase="verify",
            system_prompt=_VERIFY_SYSTEM_PROMPT,
            context=context,
            stable_payload={
                "输出Schema": GeneralAgentVerification.model_json_schema(),
            },
            working_payload=working_payload,
            output_schema=GeneralAgentVerification,
        )
        if run.replan_count >= run.limits.max_replans and decision.should_replan:
            decision = decision.model_copy(update={"should_replan": False})
        return decision

    def _capability_catalog(
        self,
    ) -> dict[str, Any]:
        index, tool_contracts, subagent_contracts = self._capability_definitions()
        return _complete_capability_contracts(
            index=index,
            tool_contracts=tool_contracts,
            subagent_contracts=subagent_contracts,
            char_budget=self._capability_catalog_char_budget,
        )

    def _capability_definitions(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        tool_contracts: dict[str, dict[str, Any]] = {}
        index: list[dict[str, Any]] = []
        for tool_manifest in self._tool_registry.list_manifests():
            tool_summary: dict[str, Any] = {
                "name": tool_manifest.name,
                "type": "tool",
                "description": tool_manifest.description,
                "side_effect": tool_manifest.side_effect.value,
                "requires_external_access": tool_manifest.requires_external_access,
                "authorization_policy": tool_manifest.authorization_policy.value,
            }
            index.append(tool_summary)
            tool_contracts[tool_manifest.name] = {
                **tool_summary,
                "input_schema": _planning_schema(
                    tool_manifest.input_schema.model_json_schema()
                ),
                "output_schema": _planning_schema(
                    tool_manifest.output_schema.model_json_schema()
                ),
            }
        subagent_contracts: dict[str, dict[str, Any]] = {}
        for subagent_manifest in self._subagent_registry.list_manifests():
            subagent_summary: dict[str, Any] = {
                "name": subagent_manifest.name,
                "type": "subagent",
                "label": subagent_manifest.label,
                "description": subagent_manifest.description,
                "non_responsibilities": list(
                    subagent_manifest.non_responsibilities
                ),
                "allowed_tools": sorted(subagent_manifest.allowed_tools),
                "accepted_artifact_types": sorted(
                    subagent_manifest.accepted_artifact_types
                ),
                "produced_artifact_types": sorted(
                    subagent_manifest.artifact_types
                ),
            }
            index.append(subagent_summary)
            subagent_contracts[subagent_manifest.name] = {
                **subagent_summary,
                "input_schema": _planning_schema(
                    subagent_manifest.input_schema.model_json_schema()
                ),
                "output_schema": _planning_schema(
                    subagent_manifest.output_schema.model_json_schema()
                ),
            }
        return index, tool_contracts, subagent_contracts

    def _validate_capabilities(
        self,
        plan: GeneralAgentExecutionPlan,
        run: GeneralAgentRun,
        *,
        context: GeneralAgentContextEnvelope,
    ) -> None:
        tools = {item.name: item for item in self._tool_registry.list_manifests()}
        subagents = {
            item.name: item for item in self._subagent_registry.list_manifests()
        }
        if len(plan.nodes) > run.limits.max_plan_nodes:
            raise OrchestratorPlanError("编排计划超过本次任务允许的节点数量。")
        for node in plan.nodes:
            invalid_artifact_refs = _invalid_literal_artifact_refs(node.input_data)
            if invalid_artifact_refs:
                raise OrchestratorPlanError(
                    f"节点“{node.node_id}”提供了无效的中间产物 ID："
                    + "、".join(invalid_artifact_refs)
                    + "。节点间产物必须通过 dependencies 或 input_bindings 传递。"
                )
            if node.reuse_from_node_id is not None:
                reusable = [
                    item
                    for item in run.node_runs
                    if item.node_id == node.reuse_from_node_id
                    and item.status is GeneralAgentNodeStatus.SUCCESS
                ]
                if not reusable:
                    raise OrchestratorPlanError(
                        f"计划要求复用的成功节点“{node.reuse_from_node_id}”不存在。"
                    )
                source = max(reusable, key=lambda item: item.plan_revision)
                if (
                    source.kind is not node.kind
                    or source.capability_name != node.capability_name
                ):
                    raise OrchestratorPlanError(
                        f"节点“{node.node_id}”与复用来源"
                        f"“{node.reuse_from_node_id}”的能力契约不一致。"
                    )
            if node.kind is GeneralAgentNodeKind.TOOL:
                manifest = tools.get(node.capability_name)
                if manifest is None:
                    raise OrchestratorPlanError(
                        f"编排计划引用了未知工具“{node.capability_name}”。"
                    )
                if manifest.requires_external_access and not run.external_access_allowed:
                    raise OrchestratorPlanError(
                        "用户未允许外部研究，计划却安排了外部工具。"
                    )
                continue
            if node.capability_name not in subagents:
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

        if not is_explicit_chapter_content_request(context.current_goal):
            return
        if "read_manuscript" not in tools:
            return
        if not plan.nodes:
            raise OrchestratorPlanError(
                "明确章节内容请求不能直接回答，必须先用 read_manuscript 读取正文。"
            )
        selected_names = {node.capability_name for node in plan.nodes}
        if "read_manuscript" not in selected_names:
            orders = explicit_chapter_orders(context.current_goal)
            raise OrchestratorPlanError(
                "请求已明确指定章节顺序"
                f"{orders}，必须选择 read_manuscript 直接读取正文，"
                "不得降级为 search_manuscript 或只调用事实证据子智能体。"
            )

    async def _complete_json(
        self,
        *,
        run: GeneralAgentRun,
        phase: str,
        system_prompt: str,
        context: GeneralAgentContextEnvelope,
        stable_payload: dict[str, Any],
        working_payload: dict[str, Any],
        output_schema: type[_OutputModel],
    ) -> _OutputModel:
        model_id = self._model_router.model_for("orchestrator")
        stable_prompt = _json_message(
            {
                "稳定记忆": context.stable_memory,
                "阶段稳定契约": stable_payload,
            }
        )

        dynamic_prompt = _json_message(
            {
                "工作记忆": context.working_memory.model_dump(mode="json"),
                "本阶段运行参数": working_payload,
                "当前请求附加上下文": {
                    "用户约束": context.current_request.user_constraints,
                    "作用范围": context.current_request.scope,
                },
                "长期记忆": [
                    item.model_dump(mode="json")
                    for item in context.long_term_memory
                ],
                "历史记忆摘要": context.history_memory.summary,
            }
        )
        last_text = ""
        last_error: Exception | None = None
        for attempt in range(2):
            developer_messages = [
                LLMMessage(role="developer", content=stable_prompt),
                LLMMessage(role="developer", content=dynamic_prompt),
            ]
            if attempt:
                developer_messages.append(
                    LLMMessage(
                        role="developer",
                        content=(
                            "上次输出未通过结构校验，请只修复 JSON 结构。"
                            f"\n错误：{str(last_error)[:2_000]}"
                            f"\n上次输出：{last_text[:10_000]}"
                        ),
                    )
                )
            messages = [
                LLMMessage(role="system", content=system_prompt),
                *developer_messages,
                *[
                    LLMMessage(
                        role="user" if message.role == "user" else "assistant",
                        content=message.content,
                    )
                    for message in context.history_memory.messages
                    if message.role in {"user", "assistant"}
                ],
                LLMMessage(role="user", content=context.current_request.content),
            ]
            request = LLMRequest(
                model_id=model_id,
                messages=tuple(messages),
                task_type="general_agent_orchestration",
                task_name=f"general_writing_orchestrator.{phase}",
                run_id=run.run_id,
                context_snapshot_id=run.context_snapshot_id,
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


def _complete_capability_contracts(
    *,
    index: list[dict[str, Any]],
    tool_contracts: dict[str, dict[str, Any]],
    subagent_contracts: dict[str, dict[str, Any]],
    char_budget: int,
) -> dict[str, Any]:
    catalog = {
        "能力总数": len(index),
        "Tool契约": [
            tool_contracts[name] for name in sorted(tool_contracts)
        ],
        "子Agent契约": [
            subagent_contracts[name] for name in sorted(subagent_contracts)
        ],
        "目录字符预算": char_budget,
    }
    actual_chars = _json_char_count(catalog)
    if actual_chars > char_budget:
        raise OrchestratorPlanError(
            "完整能力契约目录超过字符预算；系统不会静默省略已注册能力。"
        )
    catalog["实际字符数"] = actual_chars
    return catalog


def _json_char_count(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


_RUNTIME_INJECTED_INPUT_FIELDS = {
    "author_grant_id",
    "external_access_grant_id",
    "idempotency_key",
}

_ARTIFACT_ID = re.compile(r"^artifact_[a-f0-9]{32}$")


def _invalid_literal_artifact_refs(input_data: dict[str, Any]) -> tuple[str, ...]:
    source_request = input_data.get("source_request")
    if not isinstance(source_request, dict):
        return ()
    refs = source_request.get("upstream_artifact_refs")
    if not isinstance(refs, list):
        return ()
    return tuple(
        str(ref)
        for ref in refs
        if not isinstance(ref, str) or _ARTIFACT_ID.fullmatch(ref) is None
    )


def _planning_schema(value: Any) -> Any:
    """保留参数生成所需的 JSON Schema 语义，去除展示型冗余。"""
    if isinstance(value, list):
        return [_planning_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    ignored = {"title", "default", "examples", "deprecated", "readOnly", "writeOnly"}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in ignored:
            continue
        if key == "properties" and isinstance(item, dict):
            result[key] = {
                field: _planning_schema(schema)
                for field, schema in item.items()
                if field not in _RUNTIME_INJECTED_INPUT_FIELDS
            }
            continue
        if key == "required" and isinstance(item, list):
            result[key] = [
                field
                for field in item
                if field not in _RUNTIME_INJECTED_INPUT_FIELDS
            ]
            continue
        result[key] = _planning_schema(item)
    return result


def _json_message(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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
    candidate = stripped[start : end + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as json_error:
        try:
            payload = ast.literal_eval(candidate)
        except (SyntaxError, ValueError) as literal_error:
            raise json_error from literal_error
    if not isinstance(payload, dict):
        raise ValueError("模型输出必须是 JSON 对象。")
    return payload


class OrchestratorPlanError(ValueError):
    """高层计划引用了无效能力或违反任务权限。"""


class OrchestratorOutputError(ValueError):
    """高层编排 Agent 未能产出有效结构化结果。"""
