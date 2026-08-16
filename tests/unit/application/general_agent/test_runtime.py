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

import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.agent_memory.models import AgentMemoryKind, memory_now_iso
from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultOwner,
    ResultIdentityPayload,
    build_capability_result_record,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPoint,
    FaultPressureAdapter,
    FaultStep,
    JsonFaultTriggerStore,
)
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.context import ContextAssembler
from taichu.application.general_agent.executor import DynamicDagExecutor
from taichu.application.general_agent.executor import InjectedProcessTermination
from taichu.application.general_agent.faults import GeneralAgentFaultHook
from taichu.application.general_agent.models import (
    GeneralAgentNodeStatus,
    GeneralAgentRunLimits,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.orchestrator import (
    OrchestratorAgent,
    _extract_json,
)
from taichu.application.general_agent.service import (
    GeneralAgentRuntimeError,
    GeneralAgentRuntimeService,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.agent_memory_service import AgentMemoryService
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
from taichu.infrastructure.agent_memory import (
    JsonAgentMemoryLexicalIndex,
    JsonAgentMemoryRepository,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentCapabilityResultRepository,
    JsonGeneralAgentContextSnapshotRepository,
    JsonGeneralAgentEffectRepository,
    JsonGeneralAgentRunRepository,
    JsonLangGraphCheckpointSaver,
)
from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository
from taichu.infrastructure.evaluations.general_agent_benchmark.recovery_harness import (
    GeneralAgentRecoveryHarness,
)
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


class _InjectedProcessCrash(InjectedProcessTermination):
    """模拟验证节点执行期间进程被强制终止。"""


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


class _CrashOnceDuringVerificationGateway(_ScriptedGateway):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.crash_verification = True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if (
            request.task_name == "general_writing_orchestrator.verify"
            and self.crash_verification
        ):
            self.requests.append(request)
            self.crash_verification = False
            raise _InjectedProcessCrash()
        return await super().complete(request)


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
    assert run.final_answer_basis_sha256 is not None
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
async def test_explicit_chapter_summary_selects_and_fills_parameters_in_one_call(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    outline = await outline_service.create_volume("第一卷")
    chapter_id = ""
    for order in range(1, 9):
        outline = await outline_service.create_chapter(
            outline.volumes[0].volume_id,
            f"第{order}章测试标题",
        )
        chapter_id = outline.current_chapter_id or ""
        await chapter_service.save_chapter(chapter_id, f"第{order}章正文内容。")
    assert chapter_id

    missing_direct_read = {
        "rationale": "先让摘要助手自行搜索第8章。",
        "nodes": [
            {
                "node_id": "summarize_chapter",
                "kind": "subagent",
                "capability_name": "narrative_summary",
                "objective": "概括第8章。",
                "input_data": {
                    "summary_goal": "概括第8章。",
                    "source_request": {"auto_collect": True},
                },
            }
        ],
    }
    direct_read_plan = {
        "rationale": "明确章节顺序应先直接读取正文，再交给摘要助手。",
        "nodes": [
            {
                "node_id": "read_chapter",
                "kind": "tool",
                "capability_name": "read_manuscript",
                "objective": "直接读取第8章正文。",
                "input_data": {"start_order": 8, "end_order": 8},
            },
            {
                "node_id": "summarize_chapter",
                "kind": "subagent",
                "capability_name": "narrative_summary",
                "objective": "忠实概括第8章。",
                "dependencies": ["read_chapter"],
                "input_data": {
                    "summary_goal": "概括第8章主要内容。",
                    "source_request": {"auto_collect": False},
                },
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
        plans=[missing_direct_read, direct_read_plan],
        verification={
            "outcome": "satisfied",
            "final_answer": "第8章主要写第8章正文内容。",
            "issues": [],
            "should_replan": False,
        },
        subagent_outputs={
            "narrative_summary": {
                "summary": "第8章正文内容。",
                "key_events": ["第8章正文内容"],
                "character_changes": [],
                "unresolved_items": [],
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

    run = await runtime.run(user_goal="正文第8章讲的什么")

    assert run.status is GeneralAgentRunStatus.COMPLETED
    assert run.plan is not None
    assert [node.capability_name for node in run.plan.nodes] == [
        "read_manuscript",
        "narrative_summary",
    ]
    assert run.plan.nodes[0].input_data == {"start_order": 8, "end_order": 8}
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 2
    assert all(".materialize" not in request.task_name for request in gateway.requests)
    assert any(
        source_ref.startswith("manuscript:")
        for node in run.node_runs
        for source_ref in node.source_refs
    )


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
            {
                **invalid_plan["nodes"][0],
                "reuse_from_node_id": "read_chapter",
            },
            {
                **invalid_plan["nodes"][1],
                "input_bindings": [
                    {
                        "source_node_id": "read_chapter",
                        "source_path": "chunks[0].content",
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
    reused_read = next(
        node
        for node in run.node_runs
        if node.node_id == "read_chapter" and node.plan_revision == 2
    )
    assert reused_read.status is GeneralAgentNodeStatus.SUCCESS
    assert "未重复调用能力" in (reused_read.reconciliation_reason or "")
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
    assert planning_requests[0].messages[-1].role == "user"
    assert planning_requests[0].messages[-1].content == "这一章讲了什么？"
    assert '"input_schema"' in planning_requests[0].messages[1].content
    assert '"output_schema"' in planning_requests[0].messages[1].content
    assert '"maxItems":24' in planning_requests[0].messages[1].content
    assert planning_requests[1].messages[-1].content == "这一章讲了什么？"
    assert any(
        message.role == "developer" and "result.content" in message.content
        for message in planning_requests[1].messages
    )
    assert any(
        message.role == "developer" and "direct_context" in message.content
        for message in planning_requests[1].messages
    )
    assert all(".materialize" not in request.task_name for request in gateway.requests)
    assert [request.task_name for request in planning_requests] == [
        "general_writing_orchestrator.plan",
        "general_writing_orchestrator.replan",
    ]
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 1
    assert (
        len(
            [
                record
                for record in traces.records
                if getattr(record, "capability_name", "") == "read_manuscript"
            ]
        )
        == 1
    )

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


def test_orchestrator_repairs_common_json_syntax_locally() -> None:
    assert _extract_json(
        """```json
        {'rationale': '本地修复', 'nodes': [], 'direct_response': '完成',}
        ```"""
    ) == {
        "rationale": "本地修复",
        "nodes": [],
        "direct_response": "完成",
    }


@_async_test
async def test_replan_invalidates_intermediate_answer_and_memory(
    tmp_path: Path,
) -> None:
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": ChapterService(storage),
            "outline_service": OutlineService(storage),
            "invocation_policy_service": policy,
        }
    )
    tools = ToolRegistry(tool_context, traces)
    _register_tools(tools, [get_novel_structure])
    subagents = SubagentRegistry(
        CapabilityContext(capabilities={}),
        traces,
    )
    plan = {
        "rationale": "读取结构后回答。",
        "nodes": [
            {
                "node_id": "read_structure",
                "kind": "tool",
                "capability_name": "get_novel_structure",
                "objective": "读取小说结构。",
                "input_data": {},
            }
        ],
    }
    repaired_plan = {
        **plan,
        "rationale": "根据校验意见重新读取并形成最终结论。",
        "nodes": [
            {
                **plan["nodes"][0],
                "node_id": "read_structure_again",
            }
        ],
    }
    gateway = _ScriptedGateway(
        plans=[plan, repaired_plan],
        verification=[
            {
                "outcome": "partial",
                "final_answer": "这是第一版、已经失效的回答。",
                "issues": ["需要重新执行。"],
                "should_replan": True,
                "replan_guidance": "重新读取结构后回答。",
            },
            {
                "outcome": "satisfied",
                "final_answer": "这是第二版有效回答。",
                "issues": [],
                "should_replan": False,
            },
        ],
    )
    runtime = _runtime(tmp_path, gateway, tools, subagents, policy, traces)

    run = await runtime.run(user_goal="读取结构并回答")

    assert run.status is GeneralAgentRunStatus.COMPLETED
    assert run.plan_revision == 2
    assert run.final_answer == "这是第二版有效回答。"
    assert run.final_answer_basis_sha256 is not None
    memories = await JsonAgentMemoryRepository(tmp_path).query(
        conversation_id=run.conversation_id,
        kinds=(AgentMemoryKind.TASK_SUMMARY,),
        include_deleted=False,
    )
    assert len(memories) == 1
    assert "第二版有效回答" in memories[0].content
    assert "第一版、已经失效" not in memories[0].content
    assert f"result-basis:{run.final_answer_basis_sha256}" in memories[0].source_refs


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
    write_plan = {
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
    gateway = _ScriptedGateway(
        plans=[write_plan, write_plan],
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

    waiting = await runtime.run(
        user_goal="把本章开头的旧内容改成新内容。",
        author_constraints=["不得修改章节中的秦阳姓名。"],
    )

    assert waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert waiting.pending_human_request is not None
    assert waiting.pending_human_request.kind == "write_authorization"
    assert waiting.pending_human_request.tool_name == "apply_manuscript_patch"
    assert (await chapter_service.read_chapter(chapter_id)).markdown == original
    preview_node = next(
        item for item in waiting.node_runs if item.node_id == "preview_patch"
    )
    assert preview_node.status is GeneralAgentNodeStatus.SUCCESS

    memory_repository = JsonAgentMemoryRepository(tmp_path)
    automatic_memories = await memory_repository.query(
        conversation_id=waiting.conversation_id
    )
    author_memory = next(
        memory
        for memory in automatic_memories
        if memory.kind is AgentMemoryKind.USER_INSTRUCTION
    )
    await memory_repository.delete(author_memory.memory_id, deleted_at=memory_now_iso())

    completed = await runtime.resume(waiting.run_id, approve=True)

    preserved_waiting = await runtime.get(waiting.run_id)
    assert completed.run_id != waiting.run_id
    assert completed.parent_run_id == waiting.run_id
    assert completed.conversation_id == waiting.conversation_id
    assert completed.request_index == waiting.request_index + 1
    assert preserved_waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert preserved_waiting.pending_human_request == waiting.pending_human_request
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
    assert author_memory.memory_id not in {
        reference.memory_id for reference in completed.context_snapshot.memory_refs
    }

    await chapter_service.save_chapter(chapter_id, original)
    rejected_waiting = await runtime.run(
        user_goal="再次预览同一修改，但这次不要写入。",
    )
    assert rejected_waiting.status is GeneralAgentRunStatus.WAITING_HUMAN

    rejected = await runtime.resume(rejected_waiting.run_id, approve=False)

    preserved_rejected_waiting = await runtime.get(rejected_waiting.run_id)
    assert rejected.run_id != rejected_waiting.run_id
    assert rejected.parent_run_id == rejected_waiting.run_id
    assert rejected.request_index == rejected_waiting.request_index + 1
    assert rejected.status is GeneralAgentRunStatus.COMPLETED
    assert rejected.node_runs == []
    assert "拒绝写入" in rejected.final_answer
    assert preserved_rejected_waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert (await chapter_service.read_chapter(chapter_id)).markdown == original


@_async_test
async def test_runtime_clarifies_then_completes_direct_response_without_verification(
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
        ],
        verification=[],
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

    preserved_waiting = await runtime.get(waiting.run_id)
    assert completed.run_id != waiting.run_id
    assert completed.parent_run_id == waiting.run_id
    assert completed.conversation_id == waiting.conversation_id
    assert completed.request_index == waiting.request_index + 1
    assert preserved_waiting.status is GeneralAgentRunStatus.WAITING_HUMAN
    assert preserved_waiting.pending_human_request == waiting.pending_human_request
    assert completed.status is GeneralAgentRunStatus.COMPLETED
    assert completed.replan_count == 0
    assert completed.plan_revision == 1
    assert completed.messages[-1].content == "第三人称限知。"
    assert completed.final_answer == "先统一视角锚点，再逐段清理越界心理描写。"
    assert completed.node_runs == []
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.verify"
    ) == 0
    snapshots = await runtime.list_context_snapshots(completed.run_id)
    assert [snapshot.phase for snapshot in snapshots] == ["plan"]


@_async_test
async def test_recovery_case_22_reuses_durable_plan_before_first_node(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "先读取结构，再给出建议。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取当前结构。",
                        "input_data": {},
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "结构读取完成，已给出建议。",
            "issues": [],
            "should_replan": False,
        },
    )

    def build_runtime(
        hook: GeneralAgentFaultHook,
    ) -> GeneralAgentRuntimeService:
        policy = InvocationPolicyService()
        tools = ToolRegistry(
            CapabilityContext(
                capabilities={
                    "chapter_service": chapter_service,
                    "outline_service": outline_service,
                    "invocation_policy_service": policy,
                }
            ),
            traces,
        )
        _register_tools(tools, [get_novel_structure])
        subagents = SubagentRegistry(CapabilityContext(capabilities={}), traces)
        return _runtime(
            tmp_path,
            gateway,
            tools,
            subagents,
            policy,
            traces,
            fault_hook=hook,
        )

    result = await GeneralAgentRecoveryHarness(
        runtime_builder=build_runtime,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="读取结构后给我一条建议。",
        plan_id="fault_after_plan",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.PLAN_CREATED,
                once=True,
            ),
        ),
    )

    assert result.triggered_ordinals == (1,)
    assert result.interrupted_run.status is GeneralAgentRunStatus.EXECUTING
    assert result.interrupted_run.node_runs == []
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    assert sum(
        record.capability_type == "tool"
        and record.capability_name == "get_novel_structure"
        and record.status.value == "completed"
        for record in traces.records
    ) == 1
    current_nodes = [
        node
        for node in result.recovered_run.node_runs
        if node.plan_revision == result.recovered_run.plan_revision
    ]
    assert len(current_nodes) == 1
    assert current_nodes[0].status is GeneralAgentNodeStatus.SUCCESS
    assert await JsonGeneralAgentEffectRepository(tmp_path).list_effects(
        result.recovered_run.run_id
    ) == []


@_async_test
async def test_recovery_case_23_rehydrates_durable_result_for_consumer(
    tmp_path: Path,
) -> None:
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    gateway = _ScriptedGateway(
        plans=[
            {
                "rationale": "读取结构结果后形成最终判断。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取当前结构。",
                        "input_data": {},
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "已消费恢复后的同一结构结果。",
            "issues": [],
            "should_replan": False,
        },
    )

    def build_runtime(
        hook: GeneralAgentFaultHook,
    ) -> GeneralAgentRuntimeService:
        policy = InvocationPolicyService()
        tools = ToolRegistry(
            CapabilityContext(
                capabilities={
                    "chapter_service": chapter_service,
                    "outline_service": outline_service,
                    "invocation_policy_service": policy,
                }
            ),
            traces,
        )
        _register_tools(tools, [get_novel_structure])
        subagents = SubagentRegistry(CapabilityContext(capabilities={}), traces)
        return _runtime(
            tmp_path,
            gateway,
            tools,
            subagents,
            policy,
            traces,
            fault_hook=hook,
        )

    result = await GeneralAgentRecoveryHarness(
        runtime_builder=build_runtime,
        fault_adapter=FaultPressureAdapter(
            JsonFaultTriggerStore(tmp_path / "fault_pressure")
        ),
    ).execute(
        user_goal="读取结构并形成判断。",
        plan_id="fault_after_tool_result",
        steps=(
            FaultStep(
                ordinal=1,
                point=FaultPoint.CAPABILITY_RESULT_COMMITTED,
                once=True,
            ),
        ),
    )

    owner = CapabilityResultOwner(
        conversation_id=result.recovered_run.conversation_id,
        run_id=result.recovered_run.run_id,
    )
    records = await JsonGeneralAgentCapabilityResultRepository(
        tmp_path / "general_agent_capability_results"
    ).list_for_run(owner)
    assert len(records) == 1
    record = records[0]
    index_path = (
        tmp_path
        / "general_agent_capability_results"
        / owner.conversation_id
        / owner.run_id
        / "index"
        / f"{record.result_id}.json"
    )
    assert index_path.is_file()
    assert result.triggered_ordinals == (1,)
    assert result.recovered_run.status is GeneralAgentRunStatus.COMPLETED
    assert result.plan_before_sha256 == result.plan_after_sha256
    assert sum(
        trace.capability_type == "tool"
        and trace.capability_name == "get_novel_structure"
        and trace.status.value == "completed"
        for trace in traces.records
    ) == 1
    current = [
        node
        for node in result.recovered_run.node_runs
        if node.plan_revision == result.recovered_run.plan_revision
    ]
    assert len(current) == 1
    assert current[0].output == record.output
    assert record.result_id in current[0].reconciliation_reason
    assert record.content_sha256 in current[0].reconciliation_reason
    assert "复用" in current[0].reconciliation_reason


@_async_test
async def test_runtime_startup_resumes_same_langgraph_run_after_process_crash(
    tmp_path: Path,
) -> None:
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    tool_registry = ToolRegistry(
        CapabilityContext(
            capabilities={
                "chapter_service": chapter_service,
                "outline_service": outline_service,
                "invocation_policy_service": policy,
            }
        ),
        traces,
    )
    _register_tools(tool_registry, [get_novel_structure])
    gateway = _CrashOnceDuringVerificationGateway(
        plans=[
            {
                "rationale": "先读取当前小说结构，再给出章节收尾建议。",
                "nodes": [
                    {
                        "node_id": "read_structure",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取当前小说结构。",
                        "input_data": {},
                    }
                ],
            }
        ],
        verification={
            "outcome": "satisfied",
            "final_answer": "已从原 LangGraph 检查点恢复并完成。",
            "issues": [],
            "should_replan": False,
        },
    )
    subagent_registry = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": gateway,
                "model_role_router": ModelRoleRouter("default-model"),
                "tool_registry": tool_registry,
                "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
            }
        ),
        traces,
    )
    first_runtime = _runtime(
        tmp_path,
        gateway,
        tool_registry,
        subagent_registry,
        policy,
        traces,
    )

    with pytest.raises(_InjectedProcessCrash):
        await first_runtime.run(user_goal="给我一条章节收尾建议。")

    runs, _ = await JsonGeneralAgentRunRepository(tmp_path).list_runs(
        page=1,
        page_size=10,
        status="all",
    )
    interrupted = runs[0]
    assert interrupted.status is GeneralAgentRunStatus.VERIFYING
    interrupted_snapshots = await first_runtime.list_context_snapshots(
        interrupted.run_id
    )
    assert [snapshot.phase for snapshot in interrupted_snapshots] == ["plan", "verify"]

    restarted_policy = InvocationPolicyService()
    restarted_tools = ToolRegistry(
        CapabilityContext(
            capabilities={
                "chapter_service": chapter_service,
                "outline_service": outline_service,
                "invocation_policy_service": restarted_policy,
            }
        ),
        traces,
    )
    _register_tools(restarted_tools, [get_novel_structure])
    restarted_subagents = SubagentRegistry(
        CapabilityContext(
            capabilities={
                "llm": gateway,
                "model_role_router": ModelRoleRouter("default-model"),
                "tool_registry": restarted_tools,
                "artifact_repository": JsonIntermediateArtifactRepository(tmp_path),
            }
        ),
        traces,
    )
    restarted_runtime = _runtime(
        tmp_path,
        gateway,
        restarted_tools,
        restarted_subagents,
        restarted_policy,
        traces,
    )

    assert await restarted_runtime.recover_interrupted() == 1
    completed = interrupted
    for _ in range(100):
        await asyncio.sleep(0.01)
        completed = await restarted_runtime.get(interrupted.run_id)
        if completed.status is GeneralAgentRunStatus.COMPLETED:
            break

    assert completed.run_id == interrupted.run_id
    assert completed.status is GeneralAgentRunStatus.COMPLETED
    assert completed.final_answer == "已从原 LangGraph 检查点恢复并完成。"
    assert [request.task_name for request in gateway.requests].count(
        "general_writing_orchestrator.plan"
    ) == 1
    snapshots = await restarted_runtime.list_context_snapshots(interrupted.run_id)
    assert [snapshot.phase for snapshot in snapshots] == ["plan", "verify", "verify"]
    assert len({snapshot.snapshot_id for snapshot in snapshots}) == 3
    await restarted_runtime.shutdown()


@_async_test
async def test_parent_lifecycle_deletes_capability_results_for_each_run(
    tmp_path: Path,
) -> None:
    policy = InvocationPolicyService()
    tool_registry = ToolRegistry(
        CapabilityContext(capabilities={"invocation_policy_service": policy})
    )
    runtime = _runtime(
        tmp_path,
        _ScriptedGateway(plans=[], verification=[]),
        tool_registry,
        SubagentRegistry(CapabilityContext(capabilities={})),
        policy,
        _TraceRepository(),
    )
    first = await runtime.create_run(user_goal="第一轮。")
    first = first.model_copy(
        update={
            "status": GeneralAgentRunStatus.COMPLETED,
            "finished_at": first.updated_at,
        }
    )
    await runtime._repository.save(first)
    second = await runtime.create_run(
        user_goal="第二轮。",
        conversation_id=first.conversation_id,
        start_new_conversation=False,
    )
    repository = runtime._capability_result_repository
    owners = tuple(
        CapabilityResultOwner(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
        )
        for run in (first, second)
    )
    for index, owner in enumerate(owners, start=1):
        identity = ResultIdentityPayload(
            owner=owner,
            plan_revision=1,
            node_id=f"read_{index}",
            attempt_id=f"attempt_{index:032d}",
            capability_kind="tool",
            capability_name="read_manuscript",
            input_sha256=str(index) * 64,
            handler_identity_sha256="3" * 64,
            input_schema_sha256="4" * 64,
            output_schema_sha256="5" * 64,
        )
        record = build_capability_result_record(
            identity=identity,
            output={"answer": f"结果{index}"},
            source_refs=(f"chapter_{index:03d}",),
            committed_at=f"2026-07-31T00:00:0{index}Z",
        )
        await repository.commit_completed(owner, record)

    deleted = await runtime.delete_conversation(first.conversation_id)

    assert deleted == 2
    for owner in owners:
        assert await repository.list_for_run(owner) == ()
        assert await runtime._repository.get(owner.run_id) is None
    await runtime.shutdown()


@_async_test
async def test_capability_result_cleanup_failure_keeps_parent_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = InvocationPolicyService()
    runtime = _runtime(
        tmp_path,
        _ScriptedGateway(plans=[], verification=[]),
        ToolRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy})
        ),
        SubagentRegistry(CapabilityContext(capabilities={})),
        policy,
        _TraceRepository(),
    )
    run = await runtime.create_run(user_goal="验证清理失败。")
    repository = runtime._capability_result_repository

    async def fail_cleanup(_owner: CapabilityResultOwner) -> object:
        raise RuntimeError("模拟能力结果仓储不可用")

    monkeypatch.setattr(repository, "delete_run", fail_cleanup)

    with pytest.raises(GeneralAgentRuntimeError, match="能力结果"):
        await runtime.delete(run.run_id)

    assert await runtime._repository.get(run.run_id) == run
    await runtime.shutdown()


@_async_test
async def test_capability_result_cleanup_residual_keeps_parent_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = InvocationPolicyService()
    runtime = _runtime(
        tmp_path,
        _ScriptedGateway(plans=[], verification=[]),
        ToolRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy})
        ),
        SubagentRegistry(CapabilityContext(capabilities={})),
        policy,
        _TraceRepository(),
    )
    run = await runtime.create_run(user_goal="验证能力结果残留。")
    repository = runtime._capability_result_repository

    async def keep_residual(_owner: CapabilityResultOwner) -> tuple[object, ...]:
        return (object(),)

    monkeypatch.setattr(repository, "list_for_run", keep_residual)

    with pytest.raises(GeneralAgentRuntimeError, match="仍存在运行结果"):
        await runtime.delete(run.run_id)

    assert await runtime._repository.get(run.run_id) == run
    await runtime.shutdown()


def _runtime(
    root: Path,
    gateway: _ScriptedGateway,
    tool_registry: ToolRegistry,
    subagent_registry: SubagentRegistry,
    policy: InvocationPolicyService,
    traces: _TraceRepository,
    *,
    fault_hook: GeneralAgentFaultHook | None = None,
) -> GeneralAgentRuntimeService:
    router = ModelRoleRouter(
        "default-model",
        {"orchestrator": "planning-model", "canon_evidence": "fact-model"},
    )
    memory_service = AgentMemoryService(
        repository=JsonAgentMemoryRepository(root),
        lexical_index=JsonAgentMemoryLexicalIndex(root),
    )
    graph_checkpointer = JsonLangGraphCheckpointSaver(root)
    effect_repository = JsonGeneralAgentEffectRepository(root)
    capability_result_repository = (
        JsonGeneralAgentCapabilityResultRepository(
            root / "general_agent_capability_results"
        )
    )
    handler_identities = {
        **{
            ("tool", manifest.name): f"test:tool:{manifest.name}"
            for manifest in tool_registry.list_manifests()
        },
        **{
            ("subagent", manifest.name): f"test:subagent:{manifest.name}"
            for manifest in subagent_registry.list_manifests()
        },
    }
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
            capability_result_repository=capability_result_repository,
            capability_handler_identities=handler_identities,
            graph_checkpointer=graph_checkpointer,
            effect_repository=effect_repository,
            fault_hook=fault_hook,
        ),
        policy_service=policy,
        memory_service=memory_service,
        context_assembler=ContextAssembler(memory_service=memory_service),
        capability_result_repository=capability_result_repository,
        graph_checkpointer=graph_checkpointer,
        effect_repository=effect_repository,
        context_snapshot_repository=JsonGeneralAgentContextSnapshotRepository(root),
        llm_replay_repository=JsonLLMCallReplayRepository(root),
        fault_hook=fault_hook,
    )


def _register_tools(registry: ToolRegistry, modules: list[ModuleType]) -> None:
    for module in modules:
        registry.register(
            ToolPlugin(
                manifest=module.manifest,
                run=module.run,
                reconcile=getattr(module, "reconcile", None),
            )
        )


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
