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
    GeneralAgentContextEnvelope,
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentPlanDraft,
    GeneralAgentPlanSelection,
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

_PLAN_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent，当前只负责选择能力和形成依赖骨架。
你的职责是理解目标、从完整轻量能力目录选择最小充分路径、维护依赖和全局收敛；你不是设定、写作或审校专家。

硬性规则：
1. 只能使用能力目录中真实存在的 Tool 和专业子 Agent，不得创造能力名称。
2. 小问题不得强行扩展成长链路；无需项目事实或专业执行时可直接回答。
3. 涉及小说事实时必须安排取证能力，不能靠自身猜测。
4. Tool 是确定性原子能力；需要专业判断、写作、规划或审校时选择子 Agent。
5. 节点依赖必须形成无环图；可并行的节点不要制造虚假依赖。
6. 本阶段不得填写能力的精确 input_data 或 input_bindings；应用层会在选定能力后加载精确 Schema 并进入参数物化阶段。
7. 已知明确章节序号且用户要求读取、概括或总结正文时，必须选择 read_manuscript 直接读取；search_manuscript 只用于原文位置未知的关键词搜索。
8. 专业子 Agent 可消费兼容的上游中间产物；此阶段只声明依赖，不猜测字段路径。
9. 未经用户明确允许，不得安排外部研究能力。
10. 写 Tool 可以出现在计划中，但 Runtime 会在执行前暂停并请求作者授权。
11. 信息缺口会实质改变结果时才澄清；不要询问可以从小说正文或知识库取得的事实。
12. 所有面向作者的内容使用中文。
13. 运行记忆不是小说事实；fact_reference 只能提示你安排正文或统一召回重新取证。
14. 你不能直接写入、确认或删除运行记忆。
15. 完整轻量能力目录中的所有能力都是真实注册能力；不得声称目录中存在但“候选契约未加载”。
16. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
"""

_MATERIALIZE_SYSTEM_PROMPT = """你是太初通用写作助手的高层编排 Agent，当前负责把已确认的计划骨架物化为可执行 DAG。

硬性规则：
1. 节点 ID、能力类型、能力名称、目标、依赖和 continue_on_failure 必须与计划骨架完全一致，不得增加、删除、替换或重排能力。
2. 只能依据“已选能力精确契约”填写 input_data 和 input_bindings。
3. source_path 已经以上游能力的 output 对象为根，不得添加 result 或节点 ID 前缀；数组下标使用点号数字，例如 chunks.0.content。
4. target_path 已经以当前能力输入对象为根，必须来自当前能力 input_schema，例如 source_request.direct_context。
5. 专业子 Agent 可通过 source_request.upstream_artifact_refs 消费依赖节点中兼容的中间产物；Runtime 会自动补充这些引用。
6. 明确章节序号必须转换为 read_manuscript 的 start_order/end_order 或稳定 chapter_ids，不得降级为关键词搜索。
7. 不得编造精确契约中不存在的输入或输出字段。
8. 只输出符合给定 Schema 的 JSON 对象，不要输出 Markdown。
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
        """先从完整轻量目录选择能力，再按需加载精确契约物化 DAG。"""
        phase = "replan" if replan_guidance else "plan"
        capability_catalog = self._capability_catalog()
        chapter_orders = explicit_chapter_orders(context.current_goal)
        selection_error = ""
        selection: GeneralAgentPlanSelection | None = None
        for selection_attempt in range(2):
            payload = {
                "固定预算上下文": context.model_dump(mode="json"),
                "允许外部研究": run.external_access_allowed,
                "最大计划节点数": run.limits.max_plan_nodes,
                "当前重规划次数": run.replan_count,
                "完整轻量能力目录": capability_catalog,
                "已解析的明确章节顺序": chapter_orders,
                "输出Schema": GeneralAgentPlanSelection.model_json_schema(),
            }
            if selection_error:
                payload["上一版能力选择错误"] = selection_error
                payload["修复要求"] = "重新选择能力骨架，不要重复上一版错误。"
            candidate = await self._complete_json(
                run=run,
                phase=phase,
                system_prompt=_PLAN_SYSTEM_PROMPT,
                payload=payload,
                output_schema=GeneralAgentPlanSelection,
            )
            try:
                self._validate_selection(candidate, run, context=context)
            except OrchestratorPlanError as error:
                if selection_attempt:
                    raise
                selection_error = str(error)
                continue
            selection = candidate
            break
        if selection is None:
            raise OrchestratorPlanError("能力选择未通过完整目录校验。")
        if not selection.nodes:
            return GeneralAgentExecutionPlan.model_validate(
                selection.model_dump(mode="json")
            )

        selected_names = {node.capability_name for node in selection.nodes}
        exact_contracts = self._capability_contracts(selected_names)
        materialized = await self._complete_json(
            run=run,
            phase=f"{phase}.materialize",
            system_prompt=_MATERIALIZE_SYSTEM_PROMPT,
            payload={
                "固定预算上下文": context.model_dump(mode="json"),
                "已解析的明确章节顺序": chapter_orders,
                "计划骨架": selection.model_dump(mode="json"),
                "已选能力精确契约": exact_contracts,
                "输出Schema": GeneralAgentPlanDraft.model_json_schema(),
            },
            output_schema=GeneralAgentPlanDraft,
        )
        plan = GeneralAgentExecutionPlan.model_validate(
            materialized.model_dump(mode="json")
        )
        _validate_materialized_plan(selection, plan)
        self._validate_capabilities(plan, run)
        return plan

    async def verify(
        self,
        run: GeneralAgentRun,
        *,
        context: GeneralAgentContextEnvelope,
    ) -> GeneralAgentVerification:
        """检查真实执行结果并生成最终回答或有限重规划决定。"""
        payload = {
            "固定预算上下文": context.model_dump(mode="json"),
            "计划修订号": run.plan_revision,
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

    def _capability_catalog(
        self,
    ) -> dict[str, Any]:
        index, _, _ = self._capability_definitions()
        return _complete_capability_index(
            index=index,
            char_budget=self._capability_catalog_char_budget,
        )

    def _capability_contracts(
        self,
        selected_names: set[str],
    ) -> dict[str, Any]:
        index, tool_contracts, subagent_contracts = self._capability_definitions()
        return _selected_capability_contracts(
            selected_names=selected_names,
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
            summary = {
                "name": tool_manifest.name,
                "type": "tool",
                "description": tool_manifest.description,
                "side_effect": tool_manifest.side_effect.value,
                "requires_external_access": tool_manifest.requires_external_access,
                "authorization_policy": tool_manifest.authorization_policy.value,
            }
            index.append(summary)
            tool_contracts[tool_manifest.name] = {
                **summary,
                "input_schema": tool_manifest.input_schema.model_json_schema(),
                "output_schema": tool_manifest.output_schema.model_json_schema(),
            }
        subagent_contracts: dict[str, dict[str, Any]] = {}
        for subagent_manifest in self._subagent_registry.list_manifests():
            summary = {
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
            index.append(summary)
            subagent_contracts[subagent_manifest.name] = {
                **summary,
                "input_schema": subagent_manifest.input_schema.model_json_schema(),
                "output_schema": subagent_manifest.output_schema.model_json_schema(),
            }
        return index, tool_contracts, subagent_contracts

    def _validate_selection(
        self,
        selection: GeneralAgentPlanSelection,
        run: GeneralAgentRun,
        *,
        context: GeneralAgentContextEnvelope,
    ) -> None:
        tools = {item.name: item for item in self._tool_registry.list_manifests()}
        subagents = {
            item.name: item for item in self._subagent_registry.list_manifests()
        }
        if len(selection.nodes) > run.limits.max_plan_nodes:
            raise OrchestratorPlanError("编排计划超过本次任务允许的节点数量。")
        for node in selection.nodes:
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
        if not selection.nodes:
            raise OrchestratorPlanError(
                "明确章节内容请求不能直接回答，必须先用 read_manuscript 读取正文。"
            )
        selected_names = {node.capability_name for node in selection.nodes}
        if "read_manuscript" not in selected_names:
            orders = explicit_chapter_orders(context.current_goal)
            raise OrchestratorPlanError(
                "请求已明确指定章节顺序"
                f"{orders}，必须选择 read_manuscript 直接读取正文，"
                "不得降级为 search_manuscript 或只调用事实证据子智能体。"
            )

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


def _complete_capability_index(
    *,
    index: list[dict[str, Any]],
    char_budget: int,
) -> dict[str, Any]:
    catalog = {
        "能力总数": len(index),
        "能力索引": sorted(index, key=lambda item: str(item["name"])),
        "目录字符预算": char_budget,
    }
    actual_chars = _json_char_count(catalog)
    if actual_chars > char_budget:
        raise OrchestratorPlanError(
            "完整轻量能力目录超过字符预算；系统不会静默省略已注册能力。"
        )
    catalog["实际字符数"] = actual_chars
    return catalog


def _selected_capability_contracts(
    *,
    selected_names: set[str],
    index: list[dict[str, Any]],
    tool_contracts: dict[str, dict[str, Any]],
    subagent_contracts: dict[str, dict[str, Any]],
    char_budget: int,
) -> dict[str, Any]:
    known_names = {str(item["name"]) for item in index}
    unknown_names = selected_names - known_names
    if unknown_names:
        raise OrchestratorPlanError(
            "计划选择了未注册能力：" + "、".join(sorted(unknown_names))
        )
    payload = {
        "已选Tool精确契约": [
            tool_contracts[name]
            for name in sorted(selected_names & tool_contracts.keys())
        ],
        "已选子Agent精确契约": [
            subagent_contracts[name]
            for name in sorted(selected_names & subagent_contracts.keys())
        ],
        "精确契约字符预算": char_budget,
    }
    actual_chars = _json_char_count(payload)
    if actual_chars > char_budget:
        raise OrchestratorPlanError(
            "已选能力的精确契约超过字符预算；系统不会删除节点或省略 Schema。"
        )
    payload["实际字符数"] = actual_chars
    return payload


def _validate_materialized_plan(
    selection: GeneralAgentPlanSelection,
    plan: GeneralAgentExecutionPlan,
) -> None:
    expected = [
        (
            node.node_id,
            node.kind,
            node.capability_name,
            node.objective,
            tuple(node.dependencies),
            node.continue_on_failure,
        )
        for node in selection.nodes
    ]
    actual = [
        (
            node.node_id,
            node.kind,
            node.capability_name,
            node.objective,
            tuple(node.dependencies),
            node.continue_on_failure,
        )
        for node in plan.nodes
    ]
    if actual != expected:
        raise OrchestratorPlanError(
            "精确契约阶段只能填写参数和字段绑定，不得改变能力选择或依赖骨架。"
        )


def _json_char_count(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


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
