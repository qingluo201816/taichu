"""自动运行记忆与五层上下文预算测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import json
from pathlib import Path
from typing import Any, Never, TypeVar

import pytest

from taichu.application.agent_memory.models import (
    AgentMemoryDependency,
    AgentMemoryDependencyRelation,
    AgentMemoryEntry,
    AgentMemoryEvidenceAnchor,
    AgentMemoryKind,
    AgentMemoryQuery,
    AgentMemoryValidity,
    MemoryWriteCandidate,
)
from taichu.application.general_agent.context import (
    ContextAssembler,
    ContextAssemblyError,
    ContextCompactor,
    GeneralAgentContextPolicy,
)
from taichu.application.general_agent.models import (
    GeneralAgentMessage,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentScope,
)
from taichu.application.general_agent.request_analysis import (
    explicit_chapter_orders,
    is_explicit_chapter_content_request,
)
from taichu.application.general_agent.service import _chapter_source_quality_issues
from taichu.application.services.agent_memory_service import (
    AgentMemoryService,
    _summarize_output,
)
from tests.fakes.agent_memory import in_memory_agent_memory_repository
from taichu.infrastructure.long_term_memory import MarkdownLongTermMemoryRetriever

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def test_node_output_memory_summary_is_human_readable() -> None:
    summary = _summarize_output(
        {
            "lifecycle": "draft",
            "artifact_type": "narrative_summary",
            "summary": "秦浩轩完成引气。",
            "key_events": ["进入太初教", "首次引气成功"],
            "source_refs": ["internal-ref"],
        }
    )
    assert summary == "摘要：秦浩轩完成引气。；关键事件：进入太初教；首次引气成功"
    assert "{" not in summary
    assert "draft" not in summary
    assert "narrative_summary" not in summary


def test_memory_is_automatic_isolated_relevant_and_request_expiring(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        instruction = await _write(
            service,
            conversation_id="conversation_a",
            kind=AgentMemoryKind.USER_INSTRUCTION,
            content="叙事视角使用第三人称限知。",
            request_index=1,
        )
        resource = await _write(
            service,
            conversation_id="conversation_a",
            kind=AgentMemoryKind.RESOURCE_SUMMARY,
            content="第六章摘要：秦阳发现新的冲突线索。",
            request_index=1,
            expires_after_request_index=3,
        )
        await _write(
            service,
            conversation_id="conversation_b",
            kind=AgentMemoryKind.USER_INSTRUCTION,
            content="另一会话使用第一人称。",
            request_index=1,
        )

        query = AgentMemoryQuery(
            conversation_id="conversation_a",
            current_request_index=2,
            query_text="第六章冲突采用什么叙事视角",
            top_k=10,
            char_budget=2_000,
        )
        first = await service.retrieve(query)
        second = await service.retrieve(query)
        assert first.selected_memory_ids == second.selected_memory_ids
        assert instruction.memory_id in first.selected_memory_ids
        assert resource.memory_id in first.selected_memory_ids
        assert all(item.conversation_id == "conversation_a" for item in first.entries)
        assert all("lifecycle" not in item.model_dump() for item in first.entries)

        expired = await service.retrieve(
            query.model_copy(update={"current_request_index": 4})
        )
        assert resource.memory_id not in expired.selected_memory_ids
        assert instruction.memory_id in expired.selected_memory_ids

    _run(scenario())


def test_task_summary_is_not_repeated_in_working_and_history_memory(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        await _write(
            service,
            conversation_id="conversation_long",
            kind=AgentMemoryKind.TASK_SUMMARY,
            content="请求：上一轮问题\n结果：上一轮模型回答",
            request_index=1,
        )
        result = await ContextAssembler(memory_service=service).assemble(
            _long_run(round_count=2),
            phase="plan",
        )

        envelope = result.snapshot.envelope
        assert envelope.history_memory.messages
        assert all(
            memory.kind != AgentMemoryKind.TASK_SUMMARY.value
            for memory in envelope.working_memory.memories
        )

    _run(scenario())


def test_context_assembler_retrieves_markdown_long_term_memory_each_phase(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        path = tmp_path / "long_term_memory.md"
        path.write_text(
            "## 战斗偏好\n关键词：战斗\n\n战斗场景使用短句。\n",
            encoding="utf-8",
        )
        assembler = ContextAssembler(
            memory_service=_memory_service(tmp_path),
            long_term_memory_retriever=MarkdownLongTermMemoryRetriever(path),
        )
        run = _long_run(round_count=1).model_copy(
            update={"user_goal": "写一段战斗场景"}
        )

        first = await assembler.assemble(run, phase="plan")
        assert [item.content for item in first.snapshot.envelope.long_term_memory] == [
            "战斗偏好\n战斗场景使用短句。"
        ]

        path.write_text(
            "## 战斗偏好\n关键词：战斗\n\n战斗场景使用短句，减少解释。\n",
            encoding="utf-8",
        )
        repeated = await assembler.assemble(
            run.model_copy(update={"context_snapshot": first.snapshot}),
            phase="plan",
        )
        assert repeated.reused_snapshot is False
        assert repeated.resume_differences == ("按当前请求召回的长期记忆已经变化。",)

    _run(scenario())


def test_rejected_memory_is_retained_but_removed_from_current_context(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        draft = await _write(
            service,
            conversation_id="conversation_validity",
            kind=AgentMemoryKind.RESOURCE_SUMMARY,
            content="候选正文第一版。",
            request_index=1,
        )
        review = await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.WORK_NOTE,
                content="审查发现人物状态冲突。",
                run_ids=["run_review"],
                conversation_id="conversation_validity",
                created_request_index=1,
                dependencies=[
                    AgentMemoryDependency(
                        memory_id=draft.memory_id,
                        relation=AgentMemoryDependencyRelation.REVIEW_TARGET,
                    )
                ],
            )
        )
        await service.invalidate(
            draft.memory_id,
            validity=AgentMemoryValidity.REJECTED,
            reason="审查发现阻断性问题。",
            invalidated_by_memory_id=review.memory_id,
            exclude_memory_ids={review.memory_id},
        )

        active = await service.list_active(
            "conversation_validity",
            current_request_index=1,
        )
        invalidated = await service.list_invalidated(
            "conversation_validity",
            current_request_index=1,
        )
        draft_after = await service.get(draft.memory_id)
        review_after = await service.get(review.memory_id)

        assert draft_after is not None
        assert draft_after.validity is AgentMemoryValidity.REJECTED
        assert review_after is not None
        assert review_after.validity is AgentMemoryValidity.ACTIVE
        assert draft.memory_id not in {entry.memory_id for entry in active}
        assert draft.memory_id in {entry.memory_id for entry in invalidated}

        context = await ContextAssembler(memory_service=service).assemble(
            _long_run(round_count=2).model_copy(
                update={
                    "conversation_id": "conversation_validity",
                    "task_id": "conversation_validity",
                }
            ),
            phase="plan",
        )
        working = context.snapshot.envelope.working_memory
        assert draft.memory_id not in {memory.memory_id for memory in working.memories}
        assert draft.memory_id in {
            memory.memory_id for memory in working.invalidated_memories
        }

    _run(scenario())


def test_revision_supersedes_rejected_draft_without_invalidating_revision(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        run = _long_run(round_count=2).model_copy(
            update={
                "conversation_id": "conversation_revision",
                "task_id": "conversation_revision",
                "node_runs": [],
            }
        )
        draft = GeneralAgentNodeRun(
            node_id="draft",
            plan_revision=1,
            kind=GeneralAgentNodeKind.SUBAGENT,
            capability_name="drafting",
            objective="生成候选正文。",
            status=GeneralAgentNodeStatus.SUCCESS,
            output={
                "artifact_type": "manuscript_candidate",
                "text": "候选正文第一版。",
            },
            artifact_refs=["artifact_draft"],
        )
        review = GeneralAgentNodeRun(
            node_id="review",
            plan_revision=1,
            kind=GeneralAgentNodeKind.SUBAGENT,
            capability_name="consistency_reviewer",
            objective="审查候选正文。",
            dependencies=["draft"],
            status=GeneralAgentNodeStatus.SUCCESS,
            output={
                "artifact_type": "consistency_review",
                "verdict": "未通过",
                "issues": [
                    {
                        "severity": "major",
                        "problem": "人物状态冲突。",
                    }
                ],
            },
            artifact_refs=["artifact_review"],
        )
        revision = GeneralAgentNodeRun(
            node_id="revision",
            plan_revision=1,
            kind=GeneralAgentNodeKind.SUBAGENT,
            capability_name="revision",
            objective="根据审查意见修订正文。",
            dependencies=["draft", "review"],
            status=GeneralAgentNodeStatus.SUCCESS,
            output={
                "artifact_type": "revision_candidate",
                "text": "候选正文第二版。",
            },
            artifact_refs=["artifact_revision"],
        )

        memory_ids = await service.record_node_results(
            run,
            [draft, review, revision],
        )
        entries = [
            entry
            for memory_id in memory_ids
            if (entry := await service.get(memory_id)) is not None
        ]
        by_result_type = {entry.result_type: entry for entry in entries}

        assert (
            by_result_type["manuscript_candidate"].validity
            is AgentMemoryValidity.SUPERSEDED
        )
        assert (
            by_result_type["consistency_review"].validity is AgentMemoryValidity.STALE
        )
        assert (
            by_result_type["revision_candidate"].validity is AgentMemoryValidity.ACTIVE
        )
        assert (
            by_result_type["revision_candidate"].supersedes_memory_id
            == by_result_type["manuscript_candidate"].memory_id
        )
        context = await ContextAssembler(memory_service=service).assemble(
            run.model_copy(update={"node_runs": [draft, review, revision]}),
            phase="verify",
        )
        assert [
            item["node_id"]
            for item in context.snapshot.envelope.working_memory.node_summaries
        ] == ["revision"]

        repeated_ids = await service.record_node_results(
            run,
            [draft, review, revision],
        )
        repeated_entries = [
            entry
            for memory_id in repeated_ids
            if (entry := await service.get(memory_id)) is not None
        ]
        assert repeated_ids == memory_ids
        assert {entry.result_type: entry.validity for entry in repeated_entries} == {
            "manuscript_candidate": AgentMemoryValidity.SUPERSEDED,
            "consistency_review": AgentMemoryValidity.STALE,
            "revision_candidate": AgentMemoryValidity.ACTIVE,
        }

    _run(scenario())


def test_changed_evidence_marks_memory_and_basis_dependents_stale(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        resolver = _MutableEvidenceResolver()
        service = AgentMemoryService(
            repository=in_memory_agent_memory_repository(tmp_path),
            evidence_resolver=resolver,
        )
        source = await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.RESOURCE_SUMMARY,
                content="第十一章正文取证结果。",
                source_refs=["manuscript:chapter_011:0-100"],
                run_ids=["run_evidence"],
                conversation_id="conversation_evidence",
                created_request_index=1,
                evidence_anchors=[
                    AgentMemoryEvidenceAnchor(
                        reference="manuscript:chapter_011:0-100",
                        content_sha256="a" * 64,
                    )
                ],
            )
        )
        conclusion = await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.WORK_NOTE,
                content="基于第十一章得出的阶段结论。",
                run_ids=["run_evidence"],
                conversation_id="conversation_evidence",
                created_request_index=1,
                dependencies=[
                    AgentMemoryDependency(
                        memory_id=source.memory_id,
                        relation=AgentMemoryDependencyRelation.BASIS,
                    )
                ],
            )
        )
        resolver.fingerprints["manuscript:chapter_011:0-100"] = "b" * 64

        await service.refresh_evidence_validity("conversation_evidence")
        source_after = await service.get(source.memory_id)
        conclusion_after = await service.get(conclusion.memory_id)

        assert source_after is not None
        assert source_after.validity is AgentMemoryValidity.STALE
        assert conclusion_after is not None
        assert conclusion_after.validity is AgentMemoryValidity.STALE

    _run(scenario())


def test_five_layers_trim_in_fixed_order_and_keep_current_request_complete(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        for index in range(12):
            await _write(
                service,
                conversation_id="conversation_long",
                kind=AgentMemoryKind.RESOURCE_SUMMARY,
                content=f"资源 {index} 摘要：" + "章节线索" * 80,
                request_index=1,
                expires_after_request_index=8,
            )
        run = _long_run(round_count=30)
        policy = GeneralAgentContextPolicy(
            total_char_budget=18_000,
            working_memory_retrieval_top_k=12,
            working_memory_char_budget=8_000,
            long_term_memory_char_budget=8_000,
            history_memory_limit=10,
            history_memory_char_budget=5_000,
            node_summary_char_budget=4_000,
            plan_summary_char_budget=3_000,
            message_compaction_threshold=8,
            node_output_compaction_threshold=1_000,
        )
        result = await ContextAssembler(
            memory_service=service,
            policy=policy,
        ).assemble(run, phase="verify")
        envelope = result.snapshot.envelope

        assert envelope.total_char_count <= policy.total_char_budget
        assert envelope.current_request.content == run.user_goal
        assert (
            envelope.current_request.scope["direct_context"] == run.scope.direct_context
        )
        assert envelope.current_request.user_constraints == run.author_constraints
        assert envelope.stable_memory
        assert envelope.long_term_memory == []
        assert all(
            item.role in {"user", "assistant"}
            for item in envelope.history_memory.messages
        )
        assert all(
            item.content != run.user_goal for item in envelope.history_memory.messages
        )
        assert envelope.history_memory.omitted_message_count > 0
        assert envelope.history_memory.summary
        assert envelope.digest is not None
        assert [item.category for item in envelope.category_stats] == [
            "stable_memory",
            "working_memory",
            "long_term_memory",
            "history_memory",
            "current_request",
        ]
        assert envelope.category_stats[-1].omitted_count == 0

        checkpointed = run.model_copy(
            update={
                "context_snapshot_id": result.snapshot.snapshot_id,
                "context_snapshot": result.snapshot,
            }
        )
        repeated = await ContextAssembler(
            memory_service=service,
            policy=policy,
        ).assemble(checkpointed, phase="verify")
        assert repeated.reused_snapshot is True

    _run(scenario())


def test_current_request_is_rejected_instead_of_truncated(tmp_path: Path) -> None:
    run = _long_run(round_count=2).model_copy(
        update={
            "scope": GeneralAgentScope(
                scope_type="selection",
                selection_text="完整选区" * 2_000,
            )
        }
    )
    assembler = ContextAssembler(
        memory_service=_memory_service(tmp_path),
        policy=GeneralAgentContextPolicy(total_char_budget=2_000),
    )
    with pytest.raises(ContextAssemblyError, match="不会截断这两层"):
        _run(assembler.assemble(run, phase="plan"))


def test_current_request_keeps_original_whitespace(tmp_path: Path) -> None:
    run = _long_run(round_count=2).model_copy(
        update={"user_goal": "  保留首尾空格和换行\n"}
    )
    result = _run(
        ContextAssembler(memory_service=_memory_service(tmp_path)).assemble(
            run,
            phase="plan",
        )
    )
    assert result.snapshot.envelope.current_request.content == run.user_goal


def test_node_output_within_budget_is_not_arbitrarily_truncated(
    tmp_path: Path,
) -> None:
    volumes = [
        {
            "volume_id": f"volume_{volume_order}",
            "title": f"第{volume_order}卷",
            "order": volume_order,
            "chapters": [
                {
                    "chapter_id": f"chapter_{volume_order}_{chapter_order}",
                    "title": f"第{chapter_order}章",
                    "order": chapter_order,
                    "word_count": 4_000,
                    "status": "active",
                    "markdown_path": (
                        f"manuscripts/volume_{volume_order}/chapter_{chapter_order}.md"
                    ),
                }
                for chapter_order in range(1, 26)
            ],
        }
        for volume_order in range(1, 5)
    ]
    output = {
        "current_volume_id": "volume_4",
        "current_chapter_id": "chapter_4_25",
        "total_chapters": 100,
        "returned_chapters": 100,
        "volumes": volumes,
    }
    run = _long_run(round_count=2).model_copy(
        update={
            "user_goal": "查看整部小说的卷章结构",
            "node_runs": [
                GeneralAgentNodeRun(
                    node_id="fetch_structure",
                    plan_revision=1,
                    kind=GeneralAgentNodeKind.TOOL,
                    capability_name="get_novel_structure",
                    objective="获取整部小说的卷章结构。",
                    status=GeneralAgentNodeStatus.SUCCESS,
                    output=output,
                    source_refs=["manuscript:manifest", "manuscript:outline"],
                )
            ],
        }
    )
    result = _run(
        ContextAssembler(
            memory_service=_memory_service(tmp_path),
            policy=GeneralAgentContextPolicy(node_summary_char_budget=32_000),
        ).assemble(run, phase="verify")
    )

    summary = result.snapshot.envelope.working_memory.node_summaries[0]
    assert summary["output_summary"] == output
    assert len(summary["output_summary"]["volumes"]) == 4
    assert summary["output_summary"]["volumes"][-1]["title"] == "第4卷"


def test_oversized_node_output_uses_valid_structural_projection(
    tmp_path: Path,
) -> None:
    output = {
        "total_chapters": 100,
        "volumes": [
            {
                "title": f"第{volume_order}卷",
                "order": volume_order,
                "chapters": [
                    {"title": f"第{chapter_order}章", "content": "正文" * 500}
                    for chapter_order in range(1, 26)
                ],
            }
            for volume_order in range(1, 5)
        ],
    }
    run = _long_run(round_count=2).model_copy(
        update={
            "node_runs": [
                GeneralAgentNodeRun(
                    node_id="fetch_structure",
                    plan_revision=1,
                    kind=GeneralAgentNodeKind.TOOL,
                    capability_name="get_novel_structure",
                    objective="获取整部小说的卷章结构。",
                    status=GeneralAgentNodeStatus.SUCCESS,
                    output=output,
                )
            ]
        }
    )
    result = _run(
        ContextAssembler(
            memory_service=_memory_service(tmp_path),
            policy=GeneralAgentContextPolicy(node_summary_char_budget=4_000),
        ).assemble(run, phase="verify")
    )

    projection = result.snapshot.envelope.working_memory.node_summaries[0][
        "output_summary"
    ]
    assert projection["_projection_status"] == "compressed"
    assert projection["fields"]["volumes"]["item_count"] == 4
    assert projection["fields"]["volumes"]["items"][-1]["title"] == "第4卷"
    assert "正文正文正文" not in json.dumps(projection, ensure_ascii=False)


def test_compaction_failure_uses_safe_nonempty_digest(tmp_path: Path) -> None:
    assembler = ContextAssembler(
        memory_service=_memory_service(tmp_path),
        policy=GeneralAgentContextPolicy(
            total_char_budget=20_000,
            message_compaction_threshold=1,
        ),
        compactor=_FailingCompactor(),
    )
    result = _run(assembler.assemble(_long_run(round_count=10), phase="plan"))
    assert result.snapshot.envelope.fallback_used is True
    assert result.snapshot.envelope.digest is not None
    assert result.snapshot.envelope.digest.omitted_counts


def test_legacy_run_groups_by_task_id_and_derives_request_index() -> None:
    run = _long_run(round_count=5)
    payload = run.model_dump(mode="json")
    payload.pop("conversation_id")
    payload.pop("request_index")
    migrated = GeneralAgentRun.model_validate(payload)
    assert migrated.conversation_id == migrated.task_id
    assert migrated.request_index == 3


def test_explicit_chapter_reference_supports_arabic_chinese_and_ranges() -> None:
    assert explicit_chapter_orders("正文第8章讲的什么") == [8]
    assert explicit_chapter_orders("总结第八章") == [8]
    assert explicit_chapter_orders("概括第8到10章") == [8, 9, 10]
    assert is_explicit_chapter_content_request("正文第8章讲的什么") is True
    assert is_explicit_chapter_content_request("设计第8章的新冲突") is False


def test_explicit_chapter_content_requires_manuscript_source() -> None:
    run = _long_run(round_count=2).model_copy(
        update={
            "user_goal": "正文第8章讲的什么",
            "plan_revision": 1,
            "node_runs": [
                GeneralAgentNodeRun(
                    node_id="canon_chapter",
                    plan_revision=1,
                    kind=GeneralAgentNodeKind.SUBAGENT,
                    capability_name="canon_evidence",
                    objective="概括第8章",
                    status=GeneralAgentNodeStatus.SUCCESS,
                    source_refs=[],
                )
            ],
        }
    )
    assert _chapter_source_quality_issues(run)

    sourced = run.model_copy(
        update={
            "node_runs": [
                run.node_runs[0].model_copy(
                    update={"source_refs": ["manuscript:chapter_008:0-1200"]}
                )
            ]
        }
    )
    assert _chapter_source_quality_issues(sourced) == []


def _memory_service(root: Path) -> AgentMemoryService:
    return AgentMemoryService(
        repository=in_memory_agent_memory_repository(root),
    )


class _FailingCompactor(ContextCompactor):
    def compact(self, *args: Any, **kwargs: Any) -> Never:
        del args, kwargs
        raise RuntimeError("模拟压缩器失败")


class _MutableEvidenceResolver:
    def __init__(self) -> None:
        self.fingerprints = {
            "manuscript:chapter_011:0-100": "a" * 64,
        }

    async def fingerprint(self, reference: str) -> str | None:
        return self.fingerprints.get(reference)


async def _write(
    service: AgentMemoryService,
    *,
    conversation_id: str,
    kind: AgentMemoryKind,
    content: str,
    request_index: int,
    expires_after_request_index: int | None = None,
) -> AgentMemoryEntry:
    return await service.write(
        MemoryWriteCandidate(
            kind=kind,
            content=content,
            source_refs=["run:source:auto"],
            run_ids=["run_source"],
            conversation_id=conversation_id,
            created_request_index=request_index,
            expires_after_request_index=expires_after_request_index,
            retention_priority=80,
        )
    )


def _long_run(*, round_count: int = 30) -> GeneralAgentRun:
    timestamp = "2026-07-19T01:01:01Z"
    messages = [
        GeneralAgentMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"第 {index + 1} 次内容：" + "叙事上下文" * 30,
            created_at=f"2026-07-19T01:{index:02d}:01Z",
        )
        for index in range(round_count)
    ]
    nodes = [
        GeneralAgentNodeRun(
            node_id=f"node_{index}",
            plan_revision=1,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective=f"读取并检查第 {index + 1} 个范围。",
            status=GeneralAgentNodeStatus.SUCCESS,
            output={"content": "节点完整输出" * 150},
            source_refs=[f"chapter:chapter_{index + 1}"],
        )
        for index in range(20)
    ]
    return GeneralAgentRun(
        run_id="general_run_20260719_010101_abcdef",
        task_id="conversation_long",
        conversation_id="conversation_long",
        request_index=max(1, (round_count + 1) // 2),
        user_goal="把当前章节统一成第三人称限知视角。",
        author_constraints=["不得改变秦阳的姓名"],
        scope=GeneralAgentScope(
            scope_type="chapter",
            current_chapter_id="chapter_001",
            chapter_ids=["chapter_001"],
            direct_context="正文直接上下文" * 500,
        ),
        messages=messages,
        plan_revision=1,
        node_runs=nodes,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )
