"""专业子 Agent 的真实模型角色、Tool 权限和结构校验测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from decimal import Decimal
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from taichu.application.capabilities import CapabilityContext
from taichu.application.artifacts.models import IntermediateArtifactRecord
from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)
from taichu.application.invocations.models import InvocationContext
from taichu.application.invocations.models import now_iso
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.application.services.outline_service import OutlineService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.subagents.contract import SubagentPlugin
from taichu.application.subagents.consistency_reviewer import (
    agent as consistency_reviewer_agent,
)
from taichu.application.subagents.drafting import agent as drafting_agent
from taichu.application.subagents.models import ConsistencyReviewInput, DraftingOutput
from taichu.application.subagents.prompts import PROMPTS
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.subagents.runner import _collect_sources
from taichu.application.tools import (
    get_novel_structure,
    list_knowledge_catalog,
    read_knowledge_cards,
    read_manuscript,
    resolve_knowledge_identity,
    search_manuscript,
)
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.knowledge_retrieval import tool as retrieve_knowledge
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.artifacts import JsonIntermediateArtifactRepository
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
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


class _Gateway:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []
        self.responses = [
            "不是 JSON",
            (
                '{"text":"秦阳推开山门，风雪落在肩头。",'
                '"constraints_applied":["保留玄幻语气"],'
                '"source_refs":[],"risks":[],"warnings":[]}'
            ),
        ]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        text = self.responses.pop(0)
        return LLMResponse(
            text=text,
            model_id=request.model_id,
            upstream_model=request.model_id,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
            cost=LLMCost(amount=Decimal("0.01"), kind="estimated"),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        del request
        if False:
            yield LLMStreamEvent(event_type="completed")

    def list_models(self) -> list[LLMModelProfile]:
        return []


@_async_test
async def test_drafting_uses_independent_model_role_and_repairs_schema(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    repository = InMemoryKnowledgeRepository()
    knowledge_service = KnowledgeService(repository)
    retrieval_service = RetrievalService(
        MongoLexicalRetrievalBackend(repository),
        JsonlRetrievalTraceRepository(tmp_path),
    )
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    artifacts = JsonIntermediateArtifactRepository(tmp_path)
    upstream_artifact = IntermediateArtifactRecord(
        artifact_id=f"artifact_{'a' * 32}",
        artifact_type="scene_plan",
        producer="scene_planning",
        task_id="task-drafting",
        run_id="run-drafting",
        call_id="call-scene-plan",
        input_sha256="1" * 64,
        content_sha256="2" * 64,
        payload={"overview": "场景目标是让秦阳回到山门。"},
        source_refs=["manuscript:chapter-1"],
        created_at=now_iso(),
    )
    await artifacts.save(upstream_artifact)
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
    for module in _read_tool_modules():
        tool_registry.register(ToolPlugin(manifest=module.manifest, run=module.run))

    gateway = _Gateway()
    subagent_context = CapabilityContext(
        capabilities={
            **tool_context.capabilities,
            "llm": gateway,
            "model_role_router": ModelRoleRouter(
                "default-model",
                {"drafting": "drafting-quality-model"},
            ),
            "tool_registry": tool_registry,
            "invocation_trace_repository": traces,
            "artifact_repository": artifacts,
        }
    )
    registry = SubagentRegistry(subagent_context, traces)
    registry.register(
        SubagentPlugin(
            manifest=drafting_agent.manifest,
            run=drafting_agent.run,
        )
    )
    invocation = InvocationContext(
        task_id="task-drafting",
        run_id="run-drafting",
        caller_type="orchestrator",
        caller_name="orchestrator",
    )
    result = await registry.invoke(
        "drafting",
        {
            "writing_goal": "写秦阳回到山门的一小段正文",
            "target_chars": 200,
            "style_constraints": ["保持玄幻语气"],
            "source_request": {
                "auto_collect": False,
                "upstream_artifact_refs": [upstream_artifact.artifact_id],
            },
        },
        invocation,
    )

    output = DraftingOutput.model_validate(result.output)
    assert output.lifecycle == "draft"
    assert output.artifact_type == "manuscript_candidate"
    assert "秦阳" in output.text
    assert upstream_artifact.artifact_id in output.source_refs
    assert len(result.artifact_refs) == 1
    saved_artifact = await artifacts.get(result.artifact_refs[0])
    assert saved_artifact is not None
    assert saved_artifact.artifact_type == "manuscript_candidate"
    assert upstream_artifact.artifact_id in saved_artifact.source_refs
    assert len(gateway.requests) == 2
    assert all(
        request.model_id == "drafting-quality-model" for request in gateway.requests
    )
    assert all(request.run_id == invocation.run_id for request in gateway.requests)
    assert "场景目标是让秦阳回到山门" in str(gateway.requests[-1])
    assert drafting_agent.manifest.model_role == "drafting"
    assert not any(
        "apply" in name or "create" in name or "update" in name or "delete" in name
        for name in drafting_agent.manifest.allowed_tools
    )
    assert {record.capability_type for record in traces.records} >= {
        "llm",
        "subagent",
    }


@_async_test
async def test_consistency_review_uses_review_text_for_knowledge_retrieval(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    repository = InMemoryKnowledgeRepository(
        [
            StructuredKnowledgeCard(
                id="item-nine-leaf-lotus",
                type=StructuredKnowledgeType.ITEM,
                name="九叶金莲",
                aliases=["一叶金莲"],
                summary="九叶金莲与一叶金莲是同一种灵药的不同称呼。",
                lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
                source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
                source_note="作者确认。",
                created_at="2026-07-26T00:00:00Z",
                updated_at="2026-07-26T00:00:00Z",
            )
        ]
    )
    tool_context = CapabilityContext(
        capabilities={
            "chapter_service": ChapterService(storage),
            "outline_service": OutlineService(storage),
            "knowledge_service": KnowledgeService(repository),
            "retrieval_service": RetrievalService(
                MongoLexicalRetrievalBackend(repository),
                JsonlRetrievalTraceRepository(tmp_path),
            ),
            "invocation_policy_service": InvocationPolicyService(),
        }
    )
    traces = _TraceRepository()
    tool_registry = ToolRegistry(tool_context, traces)
    for module in _read_tool_modules():
        tool_registry.register(ToolPlugin(manifest=module.manifest, run=module.run))
    context = CapabilityContext(
        capabilities={
            **tool_context.capabilities,
            "tool_registry": tool_registry,
        }
    )
    input_data = ConsistencyReviewInput(
        text="不死巫魔取出九叶金莲，秦浩轩认出这是先前的一叶金莲。",
        review_goal="检查这一章与已确认设定是否冲突",
    )
    invocation = InvocationContext(
        task_id="task-consistency",
        run_id="run-consistency",
        caller_type="orchestrator",
        caller_name="orchestrator",
    )

    source_context, source_refs = await _collect_sources(
        consistency_reviewer_agent.manifest,
        input_data,
        invocation,
        context,
    )

    assert "[retrieve_knowledge]" in source_context
    assert "[search_manuscript]" not in source_context
    assert "九叶金莲" in source_context
    assert len(source_refs) == 1
    assert source_refs[0].startswith("retrieval_")
    assert "没有第二侧证据时不得判为冲突" in PROMPTS["consistency_reviewer"]
    assert "别名差异判为冲突" in PROMPTS["consistency_reviewer"]


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
