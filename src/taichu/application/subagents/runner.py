"""专业子 Agent 的真实 Tool 取证、模型调用和结构化校验。"""

from __future__ import annotations

import json
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.intermediate_artifact import (
    IntermediateArtifactRepository,
)
from taichu.application.contracts.invocation_trace import InvocationTraceRepository
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    response_text,
)
from taichu.application.invocations.models import (
    InvocationContext,
    InvocationStatus,
    InvocationTraceRecord,
    now_iso,
)
from taichu.application.services.invocation_policy_service import (
    canonical_input_hash,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import AgentSourceRequest
from taichu.application.tools.registry import ToolRegistry


async def run_structured_subagent(
    *,
    manifest: SubagentManifest,
    system_prompt: str,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    """收集授权来源，调用独立模型角色并有限修复结构化输出。"""
    llm_value = context.capabilities.get("llm")
    if not isinstance(llm_value, LLMGatewayContract):
        raise TypeError("专业子 Agent 缺少有效模型网关。")
    llm = llm_value
    router = context.require("model_role_router", ModelRoleRouter)
    source_context, source_refs = await _collect_sources(
        manifest,
        input_data,
        invocation,
        context,
    )
    input_json = input_data.model_dump_json(indent=2)
    schema_json = json.dumps(
        manifest.output_schema.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    user_prompt = (
        "请完成下面的专业任务。只能输出一个符合 Schema 的 JSON 对象，不要使用 Markdown 代码块。\n\n"
        f"任务输入：\n{input_json}\n\n"
        f"已授权来源：\n{source_context or '本次没有额外来源；不得虚构事实。'}\n\n"
        f"输出 Schema：\n{schema_json}"
    )
    model_id = router.model_for(manifest.model_role)
    last_text = ""
    last_error: Exception | None = None
    for attempt in range(manifest.repair_attempts + 1):
        prompt = user_prompt
        if attempt:
            prompt += (
                "\n\n上一次输出未通过 Schema 校验。请修复结构，不要改变任务事实边界。"
                f"\n校验错误：{str(last_error)[:2_000]}"
                f"\n上次输出：{last_text[:8_000]}"
            )
        request = LLMRequest(
            model_id=model_id,
            messages=(
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=prompt),
            ),
            task_type="general_writing_subagent",
            task_name=manifest.name,
            run_id=invocation.run_id,
            chapter_ids=tuple(_chapter_ids(input_data)),
            response_mode="json",
            temperature=_temperature(manifest.name),
            max_output_tokens=min(
                manifest.limits.max_output_tokens,
                invocation.budget.max_output_tokens,
            ),
            feature="general_writing_assistant",
        )
        llm_context = invocation.child(
            caller_type="subagent",
            caller_name=manifest.name,
            phase=f"{manifest.name}:llm",
        )
        started_at = now_iso()
        timer = perf_counter()
        try:
            response = await llm.complete(request)
        except Exception as error:
            await _append_llm_failure_trace(
                context,
                request,
                llm_context,
                started_at,
                timer,
                manifest.model_role,
                attempt,
                error,
            )
            raise
        last_text = response_text(response)
        await _append_llm_trace(
            context,
            request,
            response,
            llm_context,
            started_at,
            timer,
            manifest.model_role,
            attempt,
        )
        try:
            payload = _extract_json(last_text)
            output = manifest.output_schema.model_validate(payload)
            if hasattr(output, "source_refs"):
                output = output.model_copy(
                    update={"source_refs": list(dict.fromkeys(source_refs))}
                )
            if len(output.model_dump_json()) > manifest.limits.max_output_chars:
                raise ValueError("专业子 Agent 输出超过 Manifest 字符预算。")
            return output
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            last_error = error
    raise SubagentOutputValidationError(
        f"专业子 Agent“{manifest.name}”输出未通过结构校验：{last_error}"
    )


async def _collect_sources(
    manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> tuple[str, list[str]]:
    registry = context.require("tool_registry", ToolRegistry)
    if manifest.name == "external_research":
        return await _collect_external_sources(
            manifest, input_data, invocation, registry
        )
    request = getattr(input_data, "source_request", AgentSourceRequest())
    if not isinstance(request, AgentSourceRequest):
        return "", []
    calls: list[tuple[str, dict[str, object]]] = []
    goal = _primary_goal(input_data)
    review_text = (
        str(getattr(input_data, "text", ""))
        if manifest.name == "consistency_reviewer"
        else ""
    )
    if request.include_structure:
        calls.append(("get_novel_structure", {}))
    if request.chapter_ids:
        calls.append(
            (
                "read_manuscript",
                {
                    "chapter_ids": request.chapter_ids,
                    "max_content_chars": 40_000,
                },
            )
        )
    manuscript_query = request.manuscript_query or (
        goal
        if request.auto_collect and manifest.name != "consistency_reviewer"
        else ""
    )
    if manuscript_query:
        calls.append(
            (
                "search_manuscript",
                {"query": manuscript_query[:2_000], "max_hits": 12},
            )
        )
    knowledge_query = request.knowledge_query or (goal if request.auto_collect else "")
    if knowledge_query:
        retrieval_payload: dict[str, object] = {
            "query_text": knowledge_query[:20_000],
            "top_k": 12,
            "max_content_chars": 12_000,
        }
        if manifest.name == "consistency_reviewer":
            retrieval_payload.update(
                {
                    "context_text": review_text[:100_000],
                    "top_k": 20,
                    "max_content_chars": 20_000,
                }
            )
        calls.append(
            (
                "retrieve_knowledge",
                retrieval_payload,
            )
        )
    for identity in request.knowledge_identities:
        calls.append(
            (
                "resolve_knowledge_identity",
                identity.model_dump(mode="json"),
            )
        )
    if request.catalog_types:
        calls.append(
            (
                "list_knowledge_catalog",
                {
                    "knowledge_types": [item.value for item in request.catalog_types],
                    "limit": 100,
                },
            )
        )
    if request.knowledge_card_ids:
        calls.append(
            (
                "read_knowledge_cards",
                {"card_ids": request.knowledge_card_ids},
            )
        )
    chunks = [request.direct_context] if request.direct_context else []
    refs: list[str] = []
    if request.upstream_artifact_refs:
        artifact_repository = _artifact_repository(context)
        for artifact_id in request.upstream_artifact_refs:
            artifact = await artifact_repository.get(artifact_id)
            if artifact is None:
                raise ValueError(f"中间产物“{artifact_id}”不存在。")
            if artifact.artifact_type not in manifest.accepted_artifact_types:
                raise ValueError(
                    f"专业子 Agent“{manifest.name}”不接受中间产物类型"
                    f"“{artifact.artifact_type}”。"
                )
            chunks.append(
                f"[upstream_artifact:{artifact.artifact_type}]\n"
                f"{json.dumps(artifact.payload, ensure_ascii=False)}"
            )
            refs.append(artifact_id)
            refs.extend(artifact.source_refs)
    for index, (tool_name, payload) in enumerate(calls):
        if index >= manifest.limits.max_tool_calls:
            break
        if tool_name not in manifest.allowed_tools:
            continue
        child = invocation.child(
            caller_type="subagent",
            caller_name=manifest.name,
            phase=f"{manifest.name}:source_collection",
        )
        envelope = await registry.invoke(tool_name, payload, child)
        chunks.append(f"[{tool_name}]\n{envelope.output.model_dump_json(indent=2)}")
        refs.extend(envelope.source_refs)
    text = "\n\n".join(chunks)
    return text[:100_000], list(dict.fromkeys(refs))


async def _collect_external_sources(
    manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    registry: ToolRegistry,
) -> tuple[str, list[str]]:
    payload = input_data.model_dump(mode="json")
    grant_id = str(payload["external_access_grant_id"])
    external_invocation = invocation.model_copy(
        update={"external_access_grant_id": grant_id}
    )
    search = await registry.invoke(
        "search_external_sources",
        {
            "query": payload["research_question"],
            "source_preferences": payload.get("source_preferences", []),
            "date_range": payload.get("date_range"),
            "max_results": payload.get("max_sources", 5),
        },
        external_invocation.child(
            caller_type="subagent",
            caller_name=manifest.name,
            phase="external_research:search",
        ),
    )
    chunks = [f"[search_external_sources]\n{search.output.model_dump_json(indent=2)}"]
    refs = list(search.source_refs)
    items = getattr(search.output, "items", [])
    read_limit = min(3, manifest.limits.max_tool_calls - 1)
    for item in items[:read_limit]:
        result = await registry.invoke(
            "read_external_source",
            {"url": item.url, "max_content_chars": 15_000},
            external_invocation.child(
                caller_type="subagent",
                caller_name=manifest.name,
                phase="external_research:read",
            ),
        )
        chunks.append(
            f"[read_external_source]\n{result.output.model_dump_json(indent=2)}"
        )
        refs.extend(result.source_refs)
    return "\n\n".join(chunks)[:100_000], list(dict.fromkeys(refs))


async def _append_llm_trace(
    context: CapabilityContext,
    request: LLMRequest,
    response: LLMResponse | str,
    invocation: InvocationContext,
    started_at: str,
    timer: float,
    model_role: str,
    retry_count: int,
) -> None:
    repository_value = context.capabilities.get("invocation_trace_repository")
    if not isinstance(repository_value, InvocationTraceRepository):
        raise TypeError("专业子 Agent 缺少调用记录仓储。")
    repository = repository_value
    usage = response.usage if isinstance(response, LLMResponse) else None
    model_id = (
        response.model_id if isinstance(response, LLMResponse) else request.model_id
    )
    finished_at = now_iso()
    record = InvocationTraceRecord(
        trace_id=f"trace_{uuid4().hex}",
        capability_type="llm",
        capability_name=request.task_name,
        task_id=invocation.task_id,
        run_id=invocation.run_id,
        call_id=invocation.call_id,
        parent_call_id=invocation.parent_call_id,
        caller_type=invocation.caller_type,
        caller_name=invocation.caller_name,
        status=InvocationStatus.COMPLETED,
        input_sha256=canonical_input_hash(
            {"messages": [message.content for message in request.messages]}
        ),
        input_char_count=sum(len(message.content) for message in request.messages),
        output_char_count=len(response_text(response)),
        model_role=model_role,
        model_id=model_id,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        retry_count=retry_count,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=max(0, round((perf_counter() - timer) * 1000)),
    )
    try:
        await repository.append(record)
    except Exception:  # noqa: BLE001
        return


async def _append_llm_failure_trace(
    context: CapabilityContext,
    request: LLMRequest,
    invocation: InvocationContext,
    started_at: str,
    timer: float,
    model_role: str,
    retry_count: int,
    error: Exception,
) -> None:
    repository_value = context.capabilities.get("invocation_trace_repository")
    if not isinstance(repository_value, InvocationTraceRepository):
        return
    record = InvocationTraceRecord(
        trace_id=f"trace_{uuid4().hex}",
        capability_type="llm",
        capability_name=request.task_name,
        task_id=invocation.task_id,
        run_id=invocation.run_id,
        call_id=invocation.call_id,
        parent_call_id=invocation.parent_call_id,
        caller_type=invocation.caller_type,
        caller_name=invocation.caller_name,
        status=InvocationStatus.FAILED,
        input_sha256=canonical_input_hash(
            {"messages": [message.content for message in request.messages]}
        ),
        input_char_count=sum(len(message.content) for message in request.messages),
        model_role=model_role,
        model_id=request.model_id,
        retry_count=retry_count,
        started_at=started_at,
        finished_at=now_iso(),
        duration_ms=max(0, round((perf_counter() - timer) * 1000)),
        error_type=type(error).__name__,
        error_message=str(error)[:500],
    )
    try:
        await repository_value.append(record)
    except Exception:  # noqa: BLE001
        return


def _extract_json(text: str) -> dict[str, object]:
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


def _primary_goal(input_data: BaseModel) -> str:
    payload = input_data.model_dump(mode="json")
    for key in (
        "question",
        "summary_goal",
        "design_goal",
        "character_goal",
        "architecture_goal",
        "scene_goal",
        "writing_goal",
        "revision_goal",
        "review_goal",
        "style_target",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _chapter_ids(input_data: BaseModel) -> list[str]:
    payload = input_data.model_dump(mode="json")
    result: list[str] = []
    chapter_id = payload.get("chapter_id")
    if isinstance(chapter_id, str) and chapter_id:
        result.append(chapter_id)
    source_request = payload.get("source_request")
    if isinstance(source_request, dict):
        values = source_request.get("chapter_ids", [])
        if isinstance(values, list):
            result.extend(value for value in values if isinstance(value, str))
    return list(dict.fromkeys(result))


def _temperature(agent_name: str) -> float:
    if agent_name == "drafting":
        return 0.8
    if agent_name in {"worldbuilding", "character", "story_architecture"}:
        return 0.6
    if agent_name in {"scene_planning", "revision"}:
        return 0.4
    return 0.2


class SubagentOutputValidationError(ValueError):
    """模型输出在有限修复后仍不满足专业 Agent Schema。"""


def _artifact_repository(
    context: CapabilityContext,
) -> IntermediateArtifactRepository:
    value = context.capabilities.get("artifact_repository")
    if not isinstance(value, IntermediateArtifactRepository):
        raise TypeError("专业子 Agent 缺少中间产物仓储。")
    return value
