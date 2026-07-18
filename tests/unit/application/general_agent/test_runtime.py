"""通用写作助手高层规划、真实能力 DAG 与恢复测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from decimal import Decimal
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.models import (
    GeneralAgentNodeStatus,
    GeneralAgentRunLimits,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.orchestrator import OrchestratorAgent
from taichu.application.general_agent.service import GeneralAgentRuntimeService
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.services.outline_service import OutlineService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.subagents.canon_evidence import agent as canon_evidence_agent
from taichu.application.subagents.narrative_summary import (
    agent as narrative_summary_agent,
)
from taichu.application.subagents.contract import SubagentPlugin
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools import (
    apply_manuscript_patch,
    get_novel_structure,
    list_knowledge_catalog,
    preview_manuscript_patch,
    read_knowledge_cards,
    read_manuscript,
    resolve_knowledge_identity,
    search_manuscript,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.knowledge_retrieval import tool as retrieve_knowledge
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from taichu.infrastructure.general_agent_runs import JsonGeneralAgentRunRepository
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from tests.fakes import InMemoryKnowledgeRepository


def _async_test(
    test: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


class _TraceRepository:
    def __init__(self) -> None:
        self.records: list[Any] = []

    async def append(self, record: object) -> None:
        self.records.append(record)


class _ScriptedGateway:
    def __init__(
        self,
        *,
        plans: list[dict[str, Any]],
        verification: dict[str, Any] | list[dict[str, Any]],
        subagent_outputs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._plans = list(plans)
        self._verifications = (
            list(verification) if isinstance(verification, list) else [verification]
        )
        self._subagent_outputs = subagent_outputs or {}
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if request.task_name in {
            "general_writing_orchestrator.plan",
            "general_writing_orchestrator.replan",
        }:
            payload = self._plans.pop(0)
        elif request.task_name == "general_writing_orchestrator.verify":
            payload = self._verifications.pop(0)
        else:
            payload = self._subagent_outputs[request.task_name]
        return LLMResponse(
            text=json.dumps(payload, ensure_ascii=False),
            model_id=request.model_id,
            upstream_model=request.model_id,
            usage=LLMUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            cost=LLMCost(amount=Decimal("0.01"), kind="estimated"),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        del request
        if False:
            yield LLMStreamEvent(event_type="completed")

    def list_models(self) -> list[LLMModelProfile]:
        return []


@_async_test
async def test_runtime_plans_and_executes_real_subagent_with_real_retrieval_tool(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    knowledge_repository = InMemoryKnowledgeRepository()
    knowledge_service = KnowledgeService(knowledge_repository)
    await knowledge_service.create_confirmed_from_data(
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        data={
            "name": "秦阳",
            "aliases": ["秦师兄"],
            "summary": "太初教弟子，曾进入绝仙毒谷。",
            "source_origin": "manual",
            "source_note": "作者确认。",
            "role_type": "protagonist",
        },
    )
    retrieval_service = RetrievalService(
        MongoLexicalRetrievalBackend(knowledge_repository),
        JsonlRetrievalTraceRepository(tmp_path),
    )
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "outline_service": outline_service,
            "knowledge_service": knowledge_service,
            "retrieval_service": retrieval_service,
            "invocation_policy_service": policy,
        }
    )
    tool_registry = ToolRegistry(tool_context, traces)
    _register_tools(tool_registry, _read_tool_modules())
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "需要先从小说事实源取证，再回答人物经历问题。",
                "nodes": [
                    {
                        "node_id": "canon_answer",
                        "kind": "subagent",
                        "capability_name": "canon_evidence",
                        "objective": "回答秦阳曾经做过什么。",
                        "input_data": {
                            "question": "秦阳曾经去过哪里？",
                            "source_request": {
                                "auto_collect": True,
                                "knowledge_query": "秦阳 曾经 去过",
                            },
                        },
                    }
                ],
                "final_response_guidance": "给出结论并说明证据边界。",
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "秦阳曾进入绝仙毒谷；该结论来自作者确认的角色知识卡。",
            "issues": [],
            "should_replan": False,
        },
        subagent_outputs={
            "canon_evidence": {
                "answer": "秦阳曾进入绝仙毒谷。",
                "confidence": "high",
                "evidence": [],
                "conflicting_evidence": [],
                "unknowns": [],
                "source_refs": [],
                "warnings": [],
            }
        },
    )
    artifacts = JsonIntermediateArtifactRepository(tmp_path)
    subagent_context = CapabilityContext(
        capabilities={
            **tool_context.capabilities,
            "llm": gateway,
            "model_role_router": ModelRoleRouter(
                "default-model",
                {"orchestrator": "planning-model", "canon_evidence": "fact-model"},
            ),
            "tool_registry": tool_registry,
            "artifact_repository": artifacts,
            "invocation_trace_repository": traces,
        }
    )
    subagent_registry = SubagentRegistry(subagent_context, traces)
    subagent_registry.register(
        SubagentPlugin(
            manifest=canon_evidence_agent.manifest,
            run=canon_evidence_agent.run,
        )
    )
    runtime = _runtime(
        tmp_path,
        gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    run = await runtime.run(user_goal="秦阳曾经去过哪里？")

    assert run.status is GeneralAgentRunStatus.COMPLETED
    assert run.plan is not None
    assert run.plan.nodes[0].capability_name == "canon_evidence"
    assert run.node_runs[-1].status is GeneralAgentNodeStatus.SUCCESS
    assert "绝仙毒谷" in run.final_answer
    assert run.checkpoint_revision >= 8
    assert {record.capability_type for record in traces.records} >= {
        "tool",
        "subagent",
        "llm",
    }
    assert {request.model_id for request in gateway.requests} >= {
        "planning-model",
        "fact-model",
    }


@_async_test
async def test_runtime_recovers_invalid_data_handoff_after_runtime_failure(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "紫气东来",
    )
    chapter_id = outline.current_chapter_id
    assert chapter_id is not None
    chapter_content = "张狂测出无上紫种，各堂主震惊并争相收徒。"
    await chapter_service.save_chapter(chapter_id, chapter_content)

    invalid_plan: dict[str, Any] = {
        "rationale": "先读取正文，再交给叙事摘要助手。",
        "nodes": [
            {
                "node_id": "read_chapter",
                "kind": "tool",
                "capability_name": "read_manuscript",
                "objective": "读取目标章节。",
                "input_data": {"chapter_ids": [chapter_id]},
            },
            {
                "node_id": "summarize_chapter",
                "kind": "subagent",
                "capability_name": "narrative_summary",
                "objective": "概括目标章节。",
                "input_data": {
                    "summary_goal": "概括本章主要情节。",
                    "target_chars": 300,
                    "source_request": {"auto_collect": False},
                },
                "dependencies": ["read_chapter"],
                "input_bindings": [
                    {
                        "source_node_id": "read_chapter",
                        "source_path": "result.content",
                        "target_path": "text",
                    }
                ],
            },
        ],
    }
    repaired_plan: dict[str, Any] = {
        **invalid_plan,
        "rationale": "按真实输入输出结构修正正文交接地址。",
        "nodes": [
            invalid_plan["nodes"][0],
            {
                **invalid_plan["nodes"][1],
                "input_bindings": [
                    {
                        "source_node_id": "read_chapter",
                        "source_path": "chunks.0.content",
                        "target_path": "source_request.direct_context",
                    }
                ],
            },
        ],
    }
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "outline_service": outline_service,
            "invocation_policy_service": policy,
        }
    )
    tool_registry = ToolRegistry(tool_context, traces)
    _register_tools(tool_registry, [read_manuscript])
    gateway = _ScriptedGateway(
        plans=[invalid_plan, repaired_plan],
        verification={
            "outcome": "satisfied",
            "final_answer": "本章写张狂测出无上紫种，引发各堂主争抢。",
            "issues": [],
            "should_replan": False,
        },
        subagent_outputs={
            "narrative_summary": {
                "summary": "张狂测出无上紫种，各堂主争相收徒。",
                "key_events": ["张狂测出无上紫种"],
                "character_changes": [],
                "unresolved_items": ["张狂最终拜入哪一堂尚未确定"],
                "source_refs": [],
                "warnings": [],
            }
        },
    )
    subagent_context = CapabilityContext(
        capabilities={
            **tool_context.capabilities,
            "llm": gateway,
            "model_role_router": ModelRoleRouter("default-model"),
            "tool_registry": tool_registry,
            "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
            "invocation_trace_repository": traces,
        }
    )
    subagent_registry = SubagentRegistry(subagent_context, traces)
    subagent_registry.register(
        SubagentPlugin(
            manifest=narrative_summary_agent.manifest.model_copy(
                update={"allowed_tools": frozenset({"read_manuscript"})}
            ),
            run=narrative_summary_agent.run,
        )
    )
    runtime = _runtime(
        tmp_path,
        gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    run = await runtime.run(user_goal="这一章讲了什么？")

    assert run.status is GeneralAgentRunStatus.COMPLETED
    assert run.replan_count == 1
    assert run.plan_revision == 2
    assert run.plan is not None
    assert run.plan.nodes[1].input_bindings[0].source_path == "chunks.0.content"
    failed_summary_node = next(
        node
        for node in run.node_runs
        if node.node_id == "summarize_chapter" and node.plan_revision == 1
    )
    assert failed_summary_node.status is GeneralAgentNodeStatus.FAILED
    assert failed_summary_node.error_type == "DynamicDagExecutionError"
    assert "result.content" in (failed_summary_node.error_message or "")
    summary_node = next(
        node
        for node in run.node_runs
        if node.node_id == "summarize_chapter"
        and node.plan_revision == run.plan_revision
    )
    assert summary_node.status is GeneralAgentNodeStatus.SUCCESS
    assert (
        summary_node.resolved_input["source_request"]["direct_context"]
        == chapter_content
    )
    planning_requests = [
        request
        for request in gateway.requests
        if request.task_name
        in {
            "general_writing_orchestrator.plan",
            "general_writing_orchestrator.replan",
        }
    ]
    assert len(planning_requests) == 2
    assert '"output_schema"' in planning_requests[0].messages[-1].content
    assert "result.content" in planning_requests[1].messages[-1].content
    assert "text" in planning_requests[1].messages[-1].content
    assert [request.task_name for request in planning_requests] == [
        "general_writing_orchestrator.plan",
        "general_writing_orchestrator.replan",
    ]
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 1

    exhausted_gateway = _ScriptedGateway(
        plans=[invalid_plan],
        verification={
            "outcome": "partial",
            "final_answer": "只读取到了正文，章节概括没有完成。",
            "issues": ["章节概括步骤失败。"],
            "should_replan": False,
        },
    )
    exhausted_runtime = _runtime(
        tmp_path,
        exhausted_gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    exhausted = await exhausted_runtime.run(
        user_goal="这一章讲了什么？",
        limits=GeneralAgentRunLimits(max_replans=0),
    )

    assert exhausted.status is GeneralAgentRunStatus.FAILED
    assert exhausted.replan_count == 0
    assert exhausted.final_answer == "只读取到了正文，章节概括没有完成。"


@_async_test
async def test_runtime_pauses_for_bound_write_and_resumes_from_checkpoint(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    outline = await outline_service.create_chapter(
        outline.volumes[0].volume_id,
        "开端",
    )
    chapter_id = outline.current_chapter_id
    assert chapter_id is not None
    original = "旧内容。秦阳走入山门。"
    await chapter_service.save_chapter(chapter_id, original)
    base_hash = sha256_text(original)
    operations = [
        {
            "operation": "replace_span",
            "start_char": 0,
            "end_char": 3,
            "text": "新内容",
        }
    ]
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "invocation_policy_service": policy,
        }
    )
    tool_registry = ToolRegistry(tool_context, traces)
    _register_tools(
        tool_registry,
        [preview_manuscript_patch, apply_manuscript_patch],
    )
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "先生成确定性差异，再请求作者授权并应用同一补丁。",
                "nodes": [
                    {
                        "node_id": "preview_patch",
                        "kind": "tool",
                        "capability_name": "preview_manuscript_patch",
                        "objective": "预览正文修改。",
                        "input_data": {
                            "chapter_id": chapter_id,
                            "base_content_sha256": base_hash,
                            "operations": operations,
                        },
                    },
                    {
                        "node_id": "apply_patch",
                        "kind": "tool",
                        "capability_name": "apply_manuscript_patch",
                        "objective": "作者授权后写入正文。",
                        "dependencies": ["preview_patch"],
                        "input_data": {
                            "chapter_id": chapter_id,
                            "base_content_sha256": base_hash,
                            "operations": operations,
                        },
                        "input_bindings": [
                            {
                                "source_node_id": "preview_patch",
                                "source_path": "patch_id",
                                "target_path": "patch_id",
                            },
                            {
                                "source_node_id": "preview_patch",
                                "source_path": "expected_content_sha256",
                                "target_path": "expected_content_sha256",
                            },
                            {
                                "source_node_id": "preview_patch",
                                "source_path": "normalized_operations",
                                "target_path": "operations",
                            },
                        ],
                    },
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "正文修改已经按预览结果写入。",
            "issues": [],
            "should_replan": False,
        },
    )
    subagent_context = CapabilityContext(
        capabilities={
            **tool_context.capabilities,
            "llm": gateway,
            "model_role_router": ModelRoleRouter("default-model"),
            "tool_registry": tool_registry,
            "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
        }
    )
    subagent_registry = SubagentRegistry(subagent_context, traces)
    runtime = _runtime(
        tmp_path,
        gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    waiting = await runtime.run(user_goal="把本章开头的旧内容改成新内容。")

    assert waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert waiting.pending_human_request is not None
    assert waiting.pending_human_request.kind == "write_authorization"
    assert waiting.pending_human_request.tool_name == "apply_manuscript_patch"
    assert (await chapter_service.read_chapter(chapter_id)).markdown == original
    preview_node = next(
        item for item in waiting.node_runs if item.node_id == "preview_patch"
    )
    assert preview_node.status is GeneralAgentNodeStatus.SUCCESS

    completed = await runtime.resume(waiting.run_id, approve=True)

    assert completed.status is GeneralAgentRunStatus.COMPLETED
    assert (await chapter_service.read_chapter(chapter_id)).markdown.startswith(
        "新内容"
    )
    apply_node = next(
        item
        for item in completed.node_runs
        if item.node_id == "apply_patch"
        and item.plan_revision == completed.plan_revision
    )
    assert apply_node.status is GeneralAgentNodeStatus.SUCCESS
    assert apply_node.authorization_grant_id is not None
    assert apply_node.resolved_input["patch_id"] == preview_node.output["patch_id"]


@_async_test
async def test_runtime_clarifies_and_performs_one_bounded_replan(
    tmp_path: Path,
) -> None:
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    tool_registry = ToolRegistry(
        CapabilityContext(capabilities={"invocation_policy_service": policy}),
        traces,
    )
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "缺少要调整的叙事视角。",
                "requires_clarification": True,
                "clarification_question": "你希望改成第一人称还是第三人称？",
                "nodes": [],
            },
            {
                "rationale": "作者已明确第三人称，可以直接给出调整原则。",
                "direct_response": "先统一视角锚点，再逐段清理越界心理描写。",
                "nodes": [],
            },
            {
                "rationale": "根据校验意见补充可执行检查步骤。",
                "direct_response": "采用第三人称限知，并逐段检查视角越界。",
                "nodes": [],
            },
        ],
        verification=[
            {
                "outcome": "partial",
                "final_answer": "先统一第三人称视角。",
                "issues": ["缺少逐段检查方法。"],
                "should_replan": True,
                "replan_guidance": "补充可执行的视角越界检查步骤。",
            },
            {
                "outcome": "satisfied",
                "final_answer": "采用第三人称限知，并逐段检查非视点人物的心理描写。",
                "issues": [],
                "should_replan": False,
            },
        ],
    )
    context = CapabilityContext(
        capabilities={
            "llm": gateway,
            "model_role_router": ModelRoleRouter("default-model"),
            "tool_registry": tool_registry,
            "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
        }
    )
    subagent_registry = SubagentRegistry(context, traces)
    runtime = _runtime(
        tmp_path,
        gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    waiting = await runtime.run(user_goal="帮我统一这一段的叙事视角。")
    assert waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert waiting.pending_human_request is not None
    assert waiting.pending_human_request.kind == "clarification"

    completed = await runtime.resume(waiting.run_id, answer="第三人称限知。")

    assert completed.status is GeneralAgentRunStatus.COMPLETED
    assert completed.replan_count == 1
    assert completed.plan_revision == 2
    assert completed.messages[-1].content == "第三人称限知。"
    assert "非视点人物" in completed.final_answer
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 2


def _runtime(
    root: Path,
    gateway: _ScriptedGateway,
    tool_registry: ToolRegistry,
    subagent_registry: SubagentRegistry,
    policy: InvocationPolicyService,
    traces: _TraceRepository,
) -> GeneralAgentRuntimeService:
    router = ModelRoleRouter(
        "default-model",
        {"orchestrator": "planning-model", "canon_evidence": "fact-model"},
    )
    return GeneralAgentRuntimeService(
        repository=JsonGeneralAgentRunRepository(root),
        event_center=GeneralAgentEventCenter(),
        orchestrator=OrchestratorAgent(
            llm=gateway,
            model_router=router,
            tool_registry=tool_registry,
            subagent_registry=subagent_registry,
            trace_repository=traces,
        ),
        executor=DynamicDagExecutor(
            tool_registry=tool_registry,
            subagent_registry=subagent_registry,
            policy_service=policy,
        ),
        policy_service=policy,
    )


def _register_tools(registry: ToolRegistry, modules: list[ModuleType]) -> None:
    for module in modules:
        registry.register(ToolPlugin(manifest=module.manifest, run=module.run))


def _read_tool_modules() -> list[ModuleType]:
    return [
        get_novel_structure,
        read_manuscript,
        search_manuscript,
        retrieve_knowledge,
        resolve_knowledge_identity,
        list_knowledge_catalog,
        read_knowledge_cards,
    ]
