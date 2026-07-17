"""Application service for the knowledge extraction workbench."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from hashlib import sha256
import re
from typing import Any, cast
from uuid import uuid4

from taichu.application.agents.knowledge_extraction.workflow import (
    ALLOWED_KNOWLEDGE_TYPES,
    BATCH_KNOWLEDGE_EXTRACTION_GRAPH_EDGES,
    BATCH_KNOWLEDGE_EXTRACTION_GRAPH_NODES,
    KnowledgeExtractionDependencies,
    build_knowledge_extraction_branch_graph,
    build_knowledge_extraction_graph,
    initial_knowledge_extraction_state,
    run_snapshot_from_state,
    _action_label,
    _candidate_action,
    _candidate_validation_errors,
    _external_conflicts,
    _normalize_identity,
    _strip_internal_candidate_fields,
)
from taichu.application.contracts.knowledge_sedimentation_progress_repository import (
    KnowledgeSedimentationProgress,
    KnowledgeSedimentationProgressRepository,
)
from taichu.application.contracts.agent_run_repository import AgentRunRepository
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMModelIdentity,
    LLMModelProfile,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.services.knowledge_service import (
    AuthorMergeMode,
    KnowledgeCardNotFoundError,
    KnowledgeIdentityConflictError,
    KnowledgeService,
)
from taichu.application.services.agent_task_event_service import AgentTaskEventCenter
from taichu.application.agents.models.agent_run import (
    AgentBatchChapterProgress,
    AgentLLMCall,
    AgentMetrics,
    AgentReviewCandidateAction,
    AgentReviewCandidateStatus,
    AgentReviewItem,
    AgentRun,
    AgentRunGraphEdge,
    AgentRunGraphNode,
    AgentRunNode,
    AgentRunNodeStatus,
    AgentRunScope,
    AgentRunStatus,
    AgentSchemaValidation,
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
    type_specific_field_keys,
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_AGENT_FORBIDDEN_FIELDS = FORBIDDEN_KNOWLEDGE_FIELD_KEYS | {
    "current_goal",
    "secret",
    "known_secrets",
}
_REVIEW_ONLY_FIELDS = {
    "entity_group_id",
    "evidence_excerpt",
    "evidence_excerpts",
}


class _InMemorySedimentationProgressRepository:
    """Test fallback; the assembled application always uses MongoDB persistence."""

    def __init__(self) -> None:
        self._progress = KnowledgeSedimentationProgress()

    async def get_progress(self) -> KnowledgeSedimentationProgress:
        return self._progress

    async def advance_to(self, chapter_id: str) -> KnowledgeSedimentationProgress:
        self._progress = KnowledgeSedimentationProgress(
            last_accepted_chapter_id=chapter_id
        )
        return self._progress


class KnowledgeExtractionService:
    """Run the Agent and process author review actions."""

    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        llm: object,
        retrieval_service: RetrievalService,
        knowledge_service: KnowledgeService,
        run_store: AgentRunRepository,
        sedimentation_progress_repository: KnowledgeSedimentationProgressRepository
        | None = None,
        task_events: AgentTaskEventCenter | None = None,
        default_model_id: str = "deepseek-v4-pro",
    ) -> None:
        self._chapter_service = chapter_service
        self._llm = cast(LLMGatewayContract, llm)
        self._retrieval_service = retrieval_service
        self._knowledge_service = knowledge_service
        self._run_store = run_store
        self._sedimentation_progress_repository = (
            sedimentation_progress_repository
            or _InMemorySedimentationProgressRepository()
        )
        self._task_events = task_events
        self._default_model_id = default_model_id
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._review_locks: dict[str, asyncio.Lock] = {}

    def validate_model_selection(self, model_name: str | None) -> None:
        """Reject request-only model switching before an Agent run is created."""
        self._resolve_model_selection(model_name)

    async def get_sedimentation_progress(self) -> KnowledgeSedimentationProgress:
        """Return the single novel's accepted knowledge frontier."""
        return await self._sedimentation_progress_repository.get_progress()

    async def accept_run(self, run_id: str) -> KnowledgeSedimentationProgress:
        """Advance the frontier after every candidate in a continuous run is reviewed."""
        run = await self.get_run(run_id)
        if run.status is not AgentRunStatus.COMPLETED:
            raise KnowledgeExtractionError("只能采纳已完成的知识沉淀任务。")
        if any(
            item.candidate_status is AgentReviewCandidateStatus.PENDING
            for item in run.review_items
        ):
            raise KnowledgeExtractionError(
                "请先确认或废弃本次沉淀的全部候选，再采纳章节范围。"
            )
        chapter_ids = run.scope.chapter_ids or [run.scope.chapter_id]
        await self._validate_sedimentation_scope(chapter_ids)
        return await self._sedimentation_progress_repository.advance_to(chapter_ids[-1])

    def _resolve_model_selection(
        self,
        model_name: str | None,
    ) -> tuple[LLMModelProfile, str | None]:
        requested_model_name = (
            model_name if model_name is not None and model_name.strip() else None
        )
        selected_id = (
            requested_model_name.strip()
            if requested_model_name is not None
            else self._default_model_id
        )
        if hasattr(self._llm, "list_models"):
            for profile in self._llm.list_models():
                if profile.id != selected_id:
                    continue
                if not profile.enabled:
                    raise KnowledgeExtractionModelSelectionError(
                        f"模型“{profile.display_name}”当前已停用，请选择其他模型。"
                    )
                return profile, requested_model_name
            raise KnowledgeExtractionModelSelectionError(
                "所选模型不存在，请刷新模型列表后重试。"
            )
        identity = getattr(
            self._llm,
            "model_identity",
            LLMModelIdentity.unknown("测试替身未提供模型身份。"),
        )
        actual_model_id = identity.model_id or self._default_model_id
        if requested_model_name is not None and selected_id != actual_model_id:
            raise KnowledgeExtractionModelSelectionError(
                "所选模型不存在，请刷新模型列表后重试。"
            )
        return (
            LLMModelProfile(
                id=actual_model_id,
                display_name=actual_model_id,
                provider="rightcode",
                upstream_model=actual_model_id,
                wire_protocol="openai_responses",
                base_url_key="RIGHTCODE_RESPONSES_BASE_URL",
                enabled=True,
                is_default=True,
                supports_streaming=False,
            ),
            requested_model_name,
        )

    async def create_run(
        self,
        *,
        chapter_id: str,
        model_name: str | None = None,
        force: bool = False,
    ) -> AgentRun:
        """Synchronously run current-chapter extraction and persist JSON state."""
        return await self._run_graph(
            chapter_id=chapter_id,
            model_name=model_name,
            force=force,
            event_sink=self._publish_task_event if self._task_events else None,
        )

    async def stream_run(
        self,
        *,
        chapter_id: str,
        model_name: str | None = None,
        force: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield structured current-chapter extraction lifecycle events."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        last_run_id = ""

        async def event_sink(event: dict[str, Any]) -> None:
            nonlocal last_run_id
            if event.get("run_id"):
                last_run_id = str(event["run_id"])
            await self._publish_task_event(event)
            await queue.put(event)

        async def execute() -> None:
            try:
                await self._run_graph(
                    chapter_id=chapter_id,
                    model_name=model_name,
                    force=force,
                    event_sink=event_sink,
                )
            except Exception as caught:  # noqa: BLE001
                await event_sink(
                    {
                        "type": "run_failed",
                        "event_type": "run_failed",
                        "run_id": last_run_id,
                        "message": str(caught) or "正文知识沉淀运行失败。",
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(execute())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass

    async def stream_batch_run(
        self,
        *,
        chapter_ids: list[str],
        model_name: str | None = None,
        force: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield structured lifecycle events for a multi-chapter extraction run."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        last_run_id = ""

        async def event_sink(event: dict[str, Any]) -> None:
            nonlocal last_run_id
            if event.get("run_id"):
                last_run_id = str(event["run_id"])
            await self._publish_task_event(event)
            await queue.put(event)

        async def execute() -> None:
            try:
                await self._run_batch_graph(
                    chapter_ids=chapter_ids,
                    model_name=model_name,
                    force=force,
                    event_sink=event_sink,
                )
            except Exception as caught:  # noqa: BLE001
                await event_sink(
                    {
                        "type": "task_failed",
                        "event_type": "task_failed",
                        "run_id": last_run_id,
                        "message": str(caught) or "批量正文知识沉淀运行失败。",
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(execute())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass

    async def start_run_task(
        self,
        *,
        chapter_id: str,
        model_name: str | None = None,
        force: bool = False,
    ) -> AgentRun:
        """Start one extraction run in the background and return its first snapshot."""
        first_run = asyncio.get_running_loop().create_future()

        async def event_sink(event: dict[str, Any]) -> None:
            await self._publish_task_event(event)
            if not first_run.done() and isinstance(event.get("run"), dict):
                first_run.set_result(AgentRun.model_validate(event["run"]))

        async def execute() -> None:
            try:
                await self._run_graph(
                    chapter_id=chapter_id,
                    model_name=model_name,
                    force=force,
                    event_sink=event_sink,
                )
            except Exception as caught:  # noqa: BLE001
                if not first_run.done():
                    first_run.set_exception(caught)
                await event_sink(
                    {
                        "type": "run_failed",
                        "event_type": "run_failed",
                        "run_id": "",
                        "message": str(caught) or "正文知识沉淀运行失败。",
                    }
                )

        task = asyncio.create_task(execute())
        self._track_background_task(task)
        return await asyncio.wait_for(first_run, timeout=10)

    async def start_batch_run_task(
        self,
        *,
        chapter_ids: list[str],
        model_name: str | None = None,
        force: bool = False,
    ) -> AgentRun:
        """Start one batch extraction run in the background and return its first snapshot."""
        first_run = asyncio.get_running_loop().create_future()

        async def event_sink(event: dict[str, Any]) -> None:
            await self._publish_task_event(event)
            if not first_run.done() and isinstance(event.get("run"), dict):
                first_run.set_result(AgentRun.model_validate(event["run"]))

        async def execute() -> None:
            try:
                await self._run_batch_graph(
                    chapter_ids=chapter_ids,
                    model_name=model_name,
                    force=force,
                    event_sink=event_sink,
                )
            except Exception as caught:  # noqa: BLE001
                if not first_run.done():
                    first_run.set_exception(caught)
                await event_sink(
                    {
                        "type": "task_failed",
                        "event_type": "task_failed",
                        "run_id": "",
                        "message": str(caught) or "批量正文知识沉淀运行失败。",
                    }
                )

        task = asyncio.create_task(execute())
        self._track_background_task(task)
        return await asyncio.wait_for(first_run, timeout=10)

    async def _publish_task_event(self, event: dict[str, Any]) -> None:
        if self._task_events is None:
            return
        await self._task_events.publish(event)

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(_consume_background_task_exception)

    async def _run_graph(
        self,
        *,
        chapter_id: str,
        model_name: str | None,
        force: bool,
        event_sink,
    ) -> AgentRun:
        chapter_titles = await self._validate_sedimentation_scope([chapter_id])
        profile, requested_model_name = self._resolve_model_selection(model_name)
        initial_state = initial_knowledge_extraction_state(
            chapter_id=chapter_id,
            chapter_title=chapter_titles[chapter_id],
            model_name=profile.display_name,
            requested_model_name=requested_model_name,
            model_id=profile.id,
            model_display_name=profile.display_name,
            upstream_model=profile.upstream_model,
            wire_protocol=profile.wire_protocol,
            generation_model_identity=_identity_for_gateway(self._llm, profile),
            force=force,
        )
        if event_sink is not None:
            await event_sink(
                {
                    "type": "run_started",
                    "event_type": "run_started",
                    "run_id": initial_state["run_id"],
                    "message": "正文知识沉淀运行已启动。",
                    "run": run_snapshot_from_state(
                        initial_state,
                        status=AgentRunStatus.RUNNING,
                    ).model_dump(mode="json"),
                }
            )
        graph = build_knowledge_extraction_graph(
            KnowledgeExtractionDependencies(
                chapter_service=self._chapter_service,
                llm=self._llm,
                retrieval_service=self._retrieval_service,
                run_store=self._run_store,
                event_sink=event_sink,
            )
        )
        final_state = await graph.ainvoke(initial_state)
        run_data = final_state.get("run")
        if not isinstance(run_data, dict):
            raise KnowledgeExtractionError("正文知识沉淀运行未生成中间态。")
        run = AgentRun.model_validate(run_data)
        if event_sink is not None:
            await event_sink(
                {
                    "type": (
                        "run_failed"
                        if run.status is AgentRunStatus.FAILED
                        else "run_completed"
                    ),
                    "event_type": (
                        "run_failed"
                        if run.status is AgentRunStatus.FAILED
                        else "run_completed"
                    ),
                    "run_id": run.run_id,
                    "message": (
                        "正文知识沉淀运行失败。"
                        if run.status is AgentRunStatus.FAILED
                        else "正文知识沉淀运行已完成。"
                    ),
                    "run": run.model_dump(mode="json"),
                }
            )
        return run

    async def _run_batch_graph(
        self,
        *,
        chapter_ids: list[str],
        model_name: str | None,
        force: bool,
        event_sink,
    ) -> AgentRun:
        profile, requested_model_name = self._resolve_model_selection(model_name)
        unique_chapter_ids = _unique_non_empty(chapter_ids)
        if not unique_chapter_ids:
            raise KnowledgeExtractionError("请至少选择一个章节。")
        chapter_titles = await self._validate_sedimentation_scope(unique_chapter_ids)
        started_at = _now_iso()
        run_id = _new_run_id(started_at)
        chapter_content_hashes: dict[str, str] = {}
        progress_items = [
            AgentBatchChapterProgress(
                chapter_id=chapter_id,
                chapter_title=chapter_titles.get(chapter_id, ""),
            )
            for chapter_id in unique_chapter_ids
        ]
        nodes: list[AgentRunNode] = []
        llm_calls: list[AgentLLMCall] = []
        raw_mentions: list[Any] = []
        entity_groups: list[Any] = []
        raw_candidates: list[dict[str, Any]] = []
        ignored: list[Any] = []
        typed_candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        max_concurrency = 5

        def snapshot(
            *,
            status: AgentRunStatus = AgentRunStatus.RUNNING,
            finished_at: str | None = None,
            review_items: list[AgentReviewItem] | None = None,
        ) -> AgentRun:
            items = review_items or []
            return AgentRun(
                run_id=run_id,
                model_name=profile.display_name,
                requested_model_name=requested_model_name,
                model_id=profile.id,
                model_display_name=profile.display_name,
                upstream_model=profile.upstream_model,
                wire_protocol=profile.wire_protocol,
                generation_model_identity=_identity_for_gateway(self._llm, profile),
                status=status,
                scope=AgentRunScope(
                    scope_type="chapter_batch",
                    chapter_id=unique_chapter_ids[0],
                    chapter_title=chapter_titles.get(unique_chapter_ids[0], ""),
                    chapter_ids=unique_chapter_ids,
                    chapter_titles=[
                        chapter_titles.get(chapter_id, "")
                        for chapter_id in unique_chapter_ids
                    ],
                    chapter_content_hashes=dict(chapter_content_hashes),
                ),
                started_at=started_at,
                finished_at=finished_at,
                nodes=nodes,
                graph_nodes=[
                    AgentRunGraphNode.model_validate(node)
                    for node in BATCH_KNOWLEDGE_EXTRACTION_GRAPH_NODES
                ],
                graph_edges=[
                    AgentRunGraphEdge.model_validate(edge)
                    for edge in BATCH_KNOWLEDGE_EXTRACTION_GRAPH_EDGES
                ],
                batch_chapter_progress=progress_items,
                max_concurrency=max_concurrency,
                current_concurrency=sum(
                    1
                    for item in progress_items
                    if item.status is AgentRunNodeStatus.RUNNING
                ),
                total_chapter_count=len(unique_chapter_ids),
                completed_chapter_count=sum(
                    1
                    for item in progress_items
                    if item.status is AgentRunNodeStatus.SUCCESS
                ),
                failed_chapter_count=sum(
                    1
                    for item in progress_items
                    if item.status is AgentRunNodeStatus.FAILED
                ),
                llm_calls=llm_calls,
                raw_mentions=raw_mentions,
                entity_groups=entity_groups,
                raw_candidates=raw_candidates,
                typed_candidates=typed_candidates,
                review_items=items,
                ignored=ignored,
                metrics=_metrics_for_items(
                    review_items=items,
                    nodes=nodes,
                    llm_calls=llm_calls,
                    started_at=started_at,
                    finished_at=finished_at or _now_iso(),
                ),
                errors=errors,
                prompt_version="knowledge_extraction_batch_prompt_v1",
            )

        await event_sink(
            {
                "type": "task_started",
                "event_type": "task_started",
                "run_id": run_id,
                "message": "批量正文知识沉淀任务已启动。",
                "run": snapshot().model_dump(mode="json"),
            }
        )

        pool_node = _make_node(
            "BatchChapterPoolNode",
            AgentRunNodeStatus.RUNNING,
            input_summary=f"已选择 {len(unique_chapter_ids)} 个章节，并发上限 5。",
        )
        nodes = _upsert_node(nodes, pool_node)
        await event_sink(
            {
                "type": "node_started",
                "event_type": "node_started",
                "run_id": run_id,
                "message": "开始执行：章节并行抽取池。",
                "node": pool_node.model_dump(mode="json"),
                "run": snapshot().model_dump(mode="json"),
            }
        )

        branch_states: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_branch(chapter_id: str) -> None:
            nonlocal progress_items
            async with semaphore:
                branch_started_at = _now_iso()
                branch_nodes: list[AgentRunNode] = []
                progress_items = _update_progress(
                    progress_items,
                    AgentBatchChapterProgress(
                        chapter_id=chapter_id,
                        chapter_title=chapter_titles.get(chapter_id, ""),
                        status=AgentRunNodeStatus.RUNNING,
                        started_at=branch_started_at,
                    ),
                )
                await event_sink(
                    {
                        "type": "chapter_branch_started",
                        "event_type": "chapter_branch_started",
                        "run_id": run_id,
                        "message": f"章节开始抽取：{chapter_titles.get(chapter_id, chapter_id)}",
                        "chapter_progress": _progress_for(
                            progress_items,
                            chapter_id,
                        ).model_dump(mode="json"),
                        "run": snapshot().model_dump(mode="json"),
                    }
                )

                async def branch_event_sink(event: dict[str, Any]) -> None:
                    nonlocal progress_items
                    llm_payload = event.get("llm_call")
                    if isinstance(llm_payload, dict):
                        llm_call = AgentLLMCall.model_validate(llm_payload)
                        llm_calls[:] = _upsert_llm_call(llm_calls, llm_call)
                        await event_sink(
                            {
                                "type": "llm_call_finished",
                                "event_type": "llm_call_finished",
                                "run_id": run_id,
                                "message": (
                                    f"{chapter_titles.get(chapter_id, chapter_id)}："
                                    f"模型调用完成："
                                    f"{_agent_node_display_label(llm_call.node_name)}"
                                ),
                                "llm_call": llm_call.model_dump(mode="json"),
                                "chapter_progress": _progress_for(
                                    progress_items,
                                    chapter_id,
                                ).model_dump(mode="json"),
                                "run": snapshot().model_dump(mode="json"),
                            }
                        )
                        return

                    node_payload = event.get("node")
                    if not isinstance(node_payload, dict):
                        return
                    branch_node = AgentRunNode.model_validate(node_payload)
                    branch_nodes[:] = _upsert_node(branch_nodes, branch_node)
                    current_progress = _progress_for(progress_items, chapter_id)
                    progress_status = (
                        AgentRunNodeStatus.FAILED
                        if branch_node.status is AgentRunNodeStatus.FAILED
                        else current_progress.status
                    )
                    if progress_status is not AgentRunNodeStatus.FAILED:
                        progress_status = AgentRunNodeStatus.RUNNING
                    next_progress = current_progress.model_copy(
                        update={
                            "status": progress_status,
                            "started_at": (
                                current_progress.started_at
                                or branch_node.started_at
                                or branch_started_at
                            ),
                            "nodes": _upsert_node(
                                current_progress.nodes,
                                branch_node,
                            ),
                            "error": branch_node.error or current_progress.error,
                        }
                    )
                    progress_items = _update_progress(progress_items, next_progress)
                    source_event_type = str(
                        event.get("event_type") or event.get("type") or ""
                    )
                    branch_event_type = (
                        "chapter_branch_node_finished"
                        if source_event_type == "node_finished"
                        else "chapter_branch_node_started"
                    )
                    await event_sink(
                        {
                            "type": branch_event_type,
                            "event_type": branch_event_type,
                            "run_id": run_id,
                            "message": (
                                f"{chapter_titles.get(chapter_id, chapter_id)}："
                                f"{_agent_node_display_label(branch_node.node_name)}"
                            ),
                            "chapter_progress": next_progress.model_dump(mode="json"),
                            "run": snapshot().model_dump(mode="json"),
                        }
                    )

                try:
                    branch_state = await self._run_branch_candidate_graph(
                        chapter_id=chapter_id,
                        profile=profile,
                        requested_model_name=requested_model_name,
                        force=force,
                        event_sink=branch_event_sink,
                    )
                    branch_states.append(branch_state)
                    content_hash = str(branch_state.get("content_hash") or "")
                    if content_hash:
                        chapter_content_hashes[chapter_id] = content_hash
                    status = (
                        AgentRunNodeStatus.FAILED
                        if branch_state.get("failed")
                        else AgentRunNodeStatus.SUCCESS
                    )
                    error = "; ".join(
                        str(item) for item in branch_state.get("errors", [])
                    )
                    current_progress = _progress_for(progress_items, chapter_id)
                    state_branch_nodes = _coerce_run_nodes(
                        branch_state.get("nodes", [])
                    )
                    final_branch_nodes = (
                        state_branch_nodes or branch_nodes or current_progress.nodes
                    )
                    progress_items = _update_progress(
                        progress_items,
                        AgentBatchChapterProgress(
                            chapter_id=chapter_id,
                            chapter_title=chapter_titles.get(chapter_id, ""),
                            status=status,
                            started_at=current_progress.started_at,
                            finished_at=_now_iso(),
                            candidate_count=len(
                                branch_state.get("typed_candidates", [])
                            ),
                            nodes=final_branch_nodes,
                            error=error or None,
                        ),
                    )
                except Exception as caught:  # noqa: BLE001
                    errors.append(
                        f"{chapter_titles.get(chapter_id, chapter_id)}：{caught}"
                    )
                    current_progress = _progress_for(progress_items, chapter_id)
                    progress_items = _update_progress(
                        progress_items,
                        AgentBatchChapterProgress(
                            chapter_id=chapter_id,
                            chapter_title=chapter_titles.get(chapter_id, ""),
                            status=AgentRunNodeStatus.FAILED,
                            started_at=current_progress.started_at,
                            finished_at=_now_iso(),
                            nodes=_mark_running_nodes_failed(
                                branch_nodes or current_progress.nodes,
                                str(caught),
                            ),
                            error=str(caught),
                        ),
                    )
                await event_sink(
                    {
                        "type": "chapter_branch_finished",
                        "event_type": "chapter_branch_finished",
                        "run_id": run_id,
                        "message": f"章节抽取结束：{chapter_titles.get(chapter_id, chapter_id)}",
                        "chapter_progress": _progress_for(
                            progress_items,
                            chapter_id,
                        ).model_dump(mode="json"),
                        "run": snapshot().model_dump(mode="json"),
                    }
                )

        await asyncio.gather(
            *(run_branch(chapter_id) for chapter_id in unique_chapter_ids)
        )

        branch_states.sort(
            key=lambda state: unique_chapter_ids.index(
                str(state.get("chapter_id") or "")
            )
        )

        for branch_state in branch_states:
            raw_mentions.extend(branch_state.get("raw_mentions", []))
            entity_groups.extend(branch_state.get("entity_groups", []))
            raw_candidates.extend(branch_state.get("raw_candidates", []))
            ignored.extend(branch_state.get("ignored", []))
            for call in branch_state.get("llm_calls", []):
                llm_calls = _upsert_llm_call(
                    llm_calls,
                    AgentLLMCall.model_validate(call),
                )

        pool_status = (
            AgentRunNodeStatus.FAILED
            if any(item.status is AgentRunNodeStatus.FAILED for item in progress_items)
            else AgentRunNodeStatus.SUCCESS
        )
        pool_node = pool_node.model_copy(
            update={
                "status": pool_status,
                "finished_at": _now_iso(),
                "duration_ms": _node_duration(pool_node),
                "output_summary": (
                    f"完成 {sum(1 for item in progress_items if item.status is AgentRunNodeStatus.SUCCESS)} 个章节，"
                    f"失败 {sum(1 for item in progress_items if item.status is AgentRunNodeStatus.FAILED)} 个章节。"
                ),
            }
        )
        nodes = _upsert_node(nodes, pool_node)
        await event_sink(
            {
                "type": "node_finished",
                "event_type": "node_finished",
                "run_id": run_id,
                "message": "章节并行抽取池执行结束。",
                "node": pool_node.model_dump(mode="json"),
                "run": snapshot().model_dump(mode="json"),
            }
        )

        if not branch_states:
            errors.append("没有章节分支成功返回候选。")

        typed_candidates = await self._run_batch_node(
            run_id,
            nodes,
            event_sink,
            "BatchCardAggregationNode",
            "多章卡片聚合",
            snapshot,
            lambda: _aggregate_batch_candidates(branch_states),
        )

        typed_candidates = await self._run_batch_node(
            run_id,
            nodes,
            event_sink,
            "BatchConflictCheckNode",
            "批量冲突检查",
            snapshot,
            lambda: _batch_internal_conflict_check(typed_candidates),
        )

        typed_candidates = await self._run_batch_node(
            run_id,
            nodes,
            event_sink,
            "BatchMatchExistingKnowledgeNode",
            "匹配有效知识",
            snapshot,
            lambda: self._batch_match_existing(typed_candidates),
        )

        review_items = await self._run_batch_node(
            run_id,
            nodes,
            event_sink,
            "BatchBuildReviewItemsNode",
            "生成审核项",
            snapshot,
            lambda: _build_batch_review_items(run_id, typed_candidates),
        )

        finished_at = _now_iso()
        write_node = _make_node(
            "BatchWriteRunNode",
            AgentRunNodeStatus.SUCCESS,
            input_summary=f"{len(review_items)} 个审核项。",
            output_summary="已写入批量运行 JSON。",
        ).model_copy(update={"finished_at": finished_at})
        nodes = _upsert_node(nodes, write_node)
        status = (
            AgentRunStatus.FAILED
            if not review_items and errors
            else AgentRunStatus.COMPLETED
        )
        run = snapshot(
            status=status,
            finished_at=finished_at,
            review_items=review_items,
        )
        await self._run_store.write_run(run)
        await event_sink(
            {
                "type": "task_failed"
                if status is AgentRunStatus.FAILED
                else "task_completed",
                "event_type": (
                    "task_failed"
                    if status is AgentRunStatus.FAILED
                    else "task_completed"
                ),
                "run_id": run_id,
                "message": (
                    "批量正文知识沉淀运行失败。"
                    if status is AgentRunStatus.FAILED
                    else "批量正文知识沉淀运行已完成。"
                ),
                "node": write_node.model_dump(mode="json"),
                "run": run.model_dump(mode="json"),
            }
        )
        return run

    async def _run_branch_candidate_graph(
        self,
        *,
        chapter_id: str,
        profile: LLMModelProfile,
        requested_model_name: str | None,
        force: bool,
        event_sink=None,
    ) -> dict[str, Any]:
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self._chapter_service,
            llm=self._llm,
            retrieval_service=self._retrieval_service,
            run_store=self._run_store,
            event_sink=event_sink,
        )
        graph = build_knowledge_extraction_branch_graph(dependencies)
        state = initial_knowledge_extraction_state(
            chapter_id=chapter_id,
            model_name=profile.display_name,
            requested_model_name=requested_model_name,
            model_id=profile.id,
            model_display_name=profile.display_name,
            upstream_model=profile.upstream_model,
            wire_protocol=profile.wire_protocol,
            generation_model_identity=_identity_for_gateway(self._llm, profile),
            force=force,
        )
        return await graph.ainvoke(state)

    async def _batch_match_existing(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for candidate in candidates:
            try:
                knowledge_type = StructuredKnowledgeType(
                    str(candidate.get("type") or "")
                )
            except ValueError:
                continue
            candidate_name = str(candidate.get("name") or "").strip()
            if not candidate_name:
                continue
            retrieval = await self._retrieval_service.retrieve(
                RetrievalRequest(
                    mode=RetrievalMode.IDENTITY,
                    identity=RetrievalIdentityQuery(
                        knowledge_type=knowledge_type,
                        name=candidate_name,
                        aliases=_list_strings(candidate.get("aliases")),
                    ),
                    consumer=RetrievalConsumerContext(
                        consumer_type="knowledge_workflow",
                        stage="BatchMatchExistingKnowledgeNode",
                    ),
                )
            )
            matches = [item.knowledge_card for item in retrieval.items]
            if not matches:
                continue
            match = matches[0]
            candidate["target_card_id"] = match.id
            candidate["matched_card_name"] = match.name
            candidate["match_reason"] = "命中已有有效知识卡的名称或别名。"
            conflicts = _external_conflicts(candidate, match)
            if conflicts:
                candidate["external_conflicts"] = conflicts
        return candidates

    async def _run_batch_node(
        self,
        run_id: str,
        nodes: list[AgentRunNode],
        event_sink,
        node_name: str,
        label: str,
        snapshot_factory,
        action,
    ):
        started = _now_iso()
        running_node = _make_node(
            node_name,
            AgentRunNodeStatus.RUNNING,
            started_at=started,
        )
        nodes[:] = _upsert_node(nodes, running_node)
        await event_sink(
            {
                "type": "node_started",
                "event_type": "node_started",
                "run_id": run_id,
                "message": f"开始执行：{label}。",
                "node": running_node.model_dump(mode="json"),
                "run": snapshot_factory().model_dump(mode="json"),
            }
        )
        try:
            result = action()
            if asyncio.iscoroutine(result):
                result = await result
            status = AgentRunNodeStatus.SUCCESS
            error = None
        except Exception as caught:  # noqa: BLE001
            result = []
            status = AgentRunNodeStatus.FAILED
            error = str(caught)
        finished = _now_iso()
        finished_node = running_node.model_copy(
            update={
                "status": status,
                "finished_at": finished,
                "duration_ms": _iso_duration_ms(started, finished),
                "output_summary": _batch_node_output(node_name, result),
                "error": error,
            }
        )
        nodes[:] = _upsert_node(nodes, finished_node)
        await event_sink(
            {
                "type": "node_finished",
                "event_type": "node_finished",
                "run_id": run_id,
                "message": f"节点完成：{label}。",
                "node": finished_node.model_dump(mode="json"),
                "run": snapshot_factory().model_dump(mode="json"),
            }
        )
        if error:
            raise KnowledgeExtractionError(error)
        return result

    async def _validate_sedimentation_scope(
        self,
        chapter_ids: list[str],
    ) -> dict[str, str]:
        chapters = await self._chapter_service.list_chapters()
        ordered_ids = [chapter.id for chapter in chapters]
        chapter_titles = {chapter.id: chapter.title for chapter in chapters}
        progress = await self._sedimentation_progress_repository.get_progress()
        start_index = 0
        if progress.last_accepted_chapter_id is not None:
            try:
                start_index = ordered_ids.index(progress.last_accepted_chapter_id) + 1
            except ValueError as error:
                raise KnowledgeExtractionError(
                    "已沉淀章节不在当前章节目录中，请先修复章节目录。"
                ) from error
        expected = ordered_ids[start_index : start_index + len(chapter_ids)]
        if chapter_ids == expected:
            return {
                chapter_id: chapter_titles[chapter_id] for chapter_id in chapter_ids
            }
        expected_title = (
            chapters[start_index].title
            if start_index < len(chapters)
            else "没有后续章节"
        )
        raise KnowledgeExtractionError(
            f"知识沉淀必须从下一未沉淀章节连续开始；当前应从“{expected_title}”开始。"
        )

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[AgentRun], int]:
        """List persisted runs."""
        return await self._run_store.list_runs(
            page=page,
            page_size=page_size,
            status=status,
        )

    async def get_run(self, run_id: str) -> AgentRun:
        """Return one run detail."""
        run = await self._run_store.get_run(run_id)
        if run is None:
            raise KnowledgeExtractionNotFoundError(f"运行记录“{run_id}”不存在。")
        return run

    async def delete_run(self, run_id: str) -> None:
        """Delete one persisted extraction run record."""
        deleted = await self._run_store.delete_run(run_id)
        if not deleted:
            raise KnowledgeExtractionNotFoundError(f"运行记录“{run_id}”不存在。")
        await self._publish_task_event(
            {
                "type": "task_deleted",
                "event_type": "task_deleted",
                "run_id": run_id,
                "message": "正文知识沉淀运行记录已删除。",
            }
        )

    async def list_candidates(
        self,
        run_id: str,
        *,
        status: str = "pending",
        action: str = "all",
    ) -> list[AgentReviewItem]:
        """List review items for one run."""
        run = await self.get_run(run_id)
        candidates = run.review_items
        if status != "all":
            expected_status = AgentReviewCandidateStatus(status)
            candidates = [
                item for item in candidates if item.candidate_status is expected_status
            ]
        if action != "all":
            expected_action = AgentReviewCandidateAction(action)
            candidates = [
                item for item in candidates if item.candidate_action is expected_action
            ]
        return candidates

    async def confirm_candidate(
        self,
        candidate_id: str,
        *,
        run_id: str | None = None,
    ) -> AgentRun:
        """Confirm a create or update candidate."""
        resolved_run_id = await self._resolve_review_run_id(candidate_id, run_id)
        async with self._review_lock(resolved_run_id):
            return await self._confirm_candidate_locked(candidate_id, resolved_run_id)

    async def _confirm_candidate_locked(
        self,
        candidate_id: str,
        run_id: str,
    ) -> AgentRun:
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
        if item.candidate_status is AgentReviewCandidateStatus.CONFIRMED:
            return run
        _assert_review_item_can_be_processed(item)
        if item.candidate_action is AgentReviewCandidateAction.CONFLICT:
            raise KnowledgeExtractionError("候选冲突必须编辑后确认。")
        if item.candidate_action is AgentReviewCandidateAction.IGNORE:
            raise KnowledgeExtractionError("建议忽略的候选不能直接确认入库。")

        if item.candidate_action is AgentReviewCandidateAction.CREATE_CARD:
            card = _card_from_payload(
                item.knowledge_type,
                _with_candidate_card_id(
                    _with_appearance_chapter_count(item.suggested_card, item),
                    run_id=run.run_id,
                    item=item,
                ),
            )
            written = await self._create_or_recover_candidate_card(card)
            updated = _mark_confirmed(
                item,
                author_action="confirm",
                created_card_id=written.id,
            )
        else:
            if item.target_card_id is None:
                raise KnowledgeExtractionError("候选更新缺少目标知识卡。")
            written = await self._knowledge_service.apply_author_confirmed_updates(
                item.target_card_id,
                _patch_updates_from_payload(
                    item.knowledge_type,
                    _with_appearance_chapter_count(item.suggested_card, item),
                ),
                merge_mode="append",
                allow_appearance_count_update=True,
            )
            updated = _mark_confirmed(
                item,
                author_action="confirm",
                updated_card_id=written.id,
            )
        return await self._replace_review_item(run, index, updated)

    async def edit_confirm_candidate(
        self,
        candidate_id: str,
        *,
        card_updates: dict[str, Any],
        target_card_id: str | None = None,
        merge_mode: AuthorMergeMode = "append",
        run_id: str | None = None,
    ) -> AgentRun:
        """Confirm a candidate after explicit author edits."""
        resolved_run_id = await self._resolve_review_run_id(candidate_id, run_id)
        async with self._review_lock(resolved_run_id):
            return await self._edit_confirm_candidate_locked(
                candidate_id,
                card_updates=card_updates,
                target_card_id=target_card_id,
                merge_mode=merge_mode,
                run_id=resolved_run_id,
            )

    async def _edit_confirm_candidate_locked(
        self,
        candidate_id: str,
        *,
        card_updates: dict[str, Any],
        target_card_id: str | None,
        merge_mode: AuthorMergeMode,
        run_id: str,
    ) -> AgentRun:
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
        if item.candidate_status is AgentReviewCandidateStatus.CONFIRMED:
            return run
        _assert_review_item_can_be_processed(item)
        _reject_author_statistic_updates(card_updates)
        merged_payload = _with_appearance_chapter_count(
            {**item.suggested_card, **card_updates}, item
        )
        target_id = target_card_id or item.target_card_id
        if target_id:
            written = await self._knowledge_service.apply_author_confirmed_updates(
                target_id,
                _patch_updates_from_payload(item.knowledge_type, merged_payload),
                merge_mode=merge_mode,
                allow_appearance_count_update=True,
            )
            updated = _mark_confirmed(
                item,
                author_action="edit_confirm",
                updated_card_id=written.id,
            )
        else:
            card = _card_from_payload(
                item.knowledge_type,
                _with_candidate_card_id(
                    merged_payload,
                    run_id=run.run_id,
                    item=item,
                ),
            )
            written = await self._create_or_recover_candidate_card(card)
            updated = _mark_confirmed(
                item,
                author_action="edit_confirm",
                created_card_id=written.id,
            )
        return await self._replace_review_item(run, index, updated)

    async def reject_candidate(
        self,
        candidate_id: str,
        *,
        run_id: str | None = None,
    ) -> AgentRun:
        """Mark one candidate as rejected without deleting it."""
        resolved_run_id = await self._resolve_review_run_id(candidate_id, run_id)
        async with self._review_lock(resolved_run_id):
            return await self._reject_candidate_locked(candidate_id, resolved_run_id)

    async def _reject_candidate_locked(
        self,
        candidate_id: str,
        run_id: str,
    ) -> AgentRun:
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
        if item.candidate_status is AgentReviewCandidateStatus.REJECTED:
            return run
        _assert_review_item_can_be_processed(item)
        return await self._replace_review_item(
            run,
            index,
            item.model_copy(
                update={
                    "candidate_status": AgentReviewCandidateStatus.REJECTED,
                    "author_action": "reject",
                    "updated_at": _now_iso(),
                }
            ),
        )

    async def _resolve_review_run_id(
        self,
        candidate_id: str,
        run_id: str | None,
    ) -> str:
        if run_id is not None:
            return run_id
        run = await self._run_store.find_run_for_candidate(candidate_id)
        if run is None:
            raise KnowledgeExtractionNotFoundError(f"候选记录“{candidate_id}”不存在。")
        return run.run_id

    def _review_lock(self, run_id: str) -> asyncio.Lock:
        lock = self._review_locks.get(run_id)
        if lock is None:
            lock = asyncio.Lock()
            self._review_locks[run_id] = lock
        return lock

    async def _create_or_recover_candidate_card(
        self,
        card: StructuredKnowledgeCard,
    ) -> StructuredKnowledgeCard:
        try:
            return await self._knowledge_service.create_confirmed_card(card)
        except KnowledgeIdentityConflictError as conflict:
            try:
                existing = await self._knowledge_service.get_card(card.id)
            except KnowledgeCardNotFoundError:
                raise conflict
            if (
                existing.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
                and existing.type is card.type
                and _normalize_identity(existing.name) == _normalize_identity(card.name)
            ):
                return existing
            raise conflict

    async def _find_review_item(
        self,
        candidate_id: str,
        *,
        run_id: str | None = None,
    ) -> tuple[AgentRun, int, AgentReviewItem]:
        run = (
            await self.get_run(run_id)
            if run_id is not None
            else await self._run_store.find_run_for_candidate(candidate_id)
        )
        if run is None:
            raise KnowledgeExtractionNotFoundError(f"候选记录“{candidate_id}”不存在。")
        for index, item in enumerate(run.review_items):
            if item.review_item_id == candidate_id:
                return run, index, item
        raise KnowledgeExtractionNotFoundError(f"候选记录“{candidate_id}”不存在。")

    async def _replace_review_item(
        self,
        run: AgentRun,
        index: int,
        item: AgentReviewItem,
    ) -> AgentRun:
        review_items = list(run.review_items)
        review_items[index] = item
        updated = run.model_copy(
            update={
                "review_items": review_items,
                "metrics": _metrics_for_run(run, review_items),
            }
        )
        await self._run_store.write_run(updated)
        return updated


class KnowledgeExtractionError(ValueError):
    """Raised when a knowledge extraction operation is invalid."""


class KnowledgeExtractionModelSelectionError(KnowledgeExtractionError):
    """Raised when a request asks for an unassembled model runtime."""

    code = "AGENT_MODEL_SELECTION_UNSUPPORTED"


class KnowledgeExtractionNotFoundError(KnowledgeExtractionError):
    """Raised when a run or candidate cannot be found."""


def _assert_review_item_can_be_processed(item: AgentReviewItem) -> None:
    if item.candidate_status is AgentReviewCandidateStatus.CONFIRMED:
        raise KnowledgeExtractionError("该候选已经确认。")
    if item.candidate_status is AgentReviewCandidateStatus.REJECTED:
        raise KnowledgeExtractionError("该候选已经废弃。")


def _mark_confirmed(
    item: AgentReviewItem,
    *,
    author_action: str,
    created_card_id: str | None = None,
    updated_card_id: str | None = None,
) -> AgentReviewItem:
    return item.model_copy(
        update={
            "candidate_status": AgentReviewCandidateStatus.CONFIRMED,
            "author_action": author_action,
            "created_knowledge_card_id": created_card_id,
            "updated_knowledge_card_id": updated_card_id,
            "updated_at": _now_iso(),
        }
    )


def _card_from_payload(
    knowledge_type: StructuredKnowledgeType,
    payload: dict[str, Any],
) -> StructuredKnowledgeCard:
    if knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
        raise KnowledgeExtractionError(
            "正文知识沉淀只允许角色、境界、功法、地点、势力、物品、规则、事件入库。"
        )
    _reject_forbidden(payload)
    now = _now_iso()
    allowed = _allowed_card_keys(knowledge_type) | _REVIEW_ONLY_FIELDS
    unknown = set(payload) - allowed
    if unknown:
        raise KnowledgeExtractionError(
            f"候选包含不支持字段：{', '.join(sorted(unknown))}"
        )
    card_payload: dict[str, Any] = {
        key: value
        for key, value in payload.items()
        if key in _allowed_card_keys(knowledge_type)
    }
    card_payload["id"] = _safe_or_new_id(
        str(card_payload.get("id") or ""),
        knowledge_type,
    )
    card_payload["type"] = knowledge_type.value
    card_payload["lifecycle"] = StructuredKnowledgeLifecycle.CONFIRMED.value
    card_payload["source_origin"] = StructuredKnowledgeSourceOrigin.AGENT_EXTRACT.value
    card_payload["created_at"] = str(card_payload.get("created_at") or now)
    card_payload["updated_at"] = now
    return StructuredKnowledgeCard.model_validate(card_payload)


def _patch_updates_from_payload(
    knowledge_type: StructuredKnowledgeType,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
        raise KnowledgeExtractionError(
            "正文知识沉淀只允许角色、境界、功法、地点、势力、物品、规则、事件入库。"
        )
    _reject_forbidden(payload)
    allowed = (
        _editable_card_keys(knowledge_type)
        | {"appearance_chapter_count"}
        | _REVIEW_ONLY_FIELDS
        | {"id", "type"}
    )
    unknown = set(payload) - allowed
    if unknown:
        raise KnowledgeExtractionError(
            f"候选包含不支持字段：{', '.join(sorted(unknown))}"
        )
    return {
        key: value
        for key, value in payload.items()
        if key in _editable_card_keys(knowledge_type) | {"appearance_chapter_count"}
        and key not in {"lifecycle", "source_origin"}
    }


def _with_appearance_chapter_count(
    payload: dict[str, Any], item: AgentReviewItem
) -> dict[str, Any]:
    """Attach the system-calculated occurrence count to a reviewed candidate."""
    next_payload = dict(payload)
    chapter_count = len(_unique_non_empty(item.appearance_chapter_ids))
    next_payload["appearance_chapter_count"] = chapter_count or next_payload.get(
        "appearance_chapter_count"
    )
    return next_payload


def _with_candidate_card_id(
    payload: dict[str, Any],
    *,
    run_id: str,
    item: AgentReviewItem,
) -> dict[str, Any]:
    """Give one create candidate a stable card id for safe request replay."""
    next_payload = dict(payload)
    identity = f"{run_id}:{item.review_item_id}:{item.knowledge_type.value}"
    digest = sha256(identity.encode("utf-8")).hexdigest()[:32]
    next_payload["id"] = f"{item.knowledge_type.value}-{digest}"
    return next_payload


def _allowed_card_keys(knowledge_type: StructuredKnowledgeType) -> set[str]:
    return {
        "id",
        "type",
        "name",
        "aliases",
        "summary",
        "appearance_chapter_count",
        "lifecycle",
        "source_origin",
        "source_note",
        "created_at",
        "updated_at",
        *type_specific_field_keys(knowledge_type),
    }


def _editable_card_keys(knowledge_type: StructuredKnowledgeType) -> set[str]:
    return {
        "name",
        "aliases",
        "summary",
        "lifecycle",
        "source_origin",
        "source_note",
        *type_specific_field_keys(knowledge_type),
    }


def _reject_author_statistic_updates(card_updates: dict[str, Any]) -> None:
    if "appearance_chapter_count" in card_updates:
        raise KnowledgeExtractionError(
            "出现章节数由正文知识沉淀自动累计，不能手动修改。"
        )


def _reject_forbidden(payload: dict[str, Any]) -> None:
    forbidden = _AGENT_FORBIDDEN_FIELDS & set(payload)
    if forbidden:
        raise KnowledgeExtractionError(
            f"正文知识沉淀不支持字段：{', '.join(sorted(forbidden))}"
        )


def _safe_or_new_id(
    value: str,
    knowledge_type: StructuredKnowledgeType,
) -> str:
    if value and _SAFE_ID.fullmatch(value):
        return value
    return f"{knowledge_type.value}-{uuid4().hex}"


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    return unique


def _new_run_id(now: str) -> str:
    try:
        moment = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        moment = datetime.now(UTC)
    return f"extract_run_{moment.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"


def _make_node(
    node_name: str,
    status: AgentRunNodeStatus,
    *,
    started_at: str | None = None,
    input_summary: str = "",
    output_summary: str = "",
    error: str | None = None,
) -> AgentRunNode:
    now = started_at or _now_iso()
    return AgentRunNode(
        node_name=node_name,
        status=status,
        started_at=now,
        finished_at=None if status is AgentRunNodeStatus.RUNNING else now,
        input_summary=input_summary,
        output_summary=output_summary,
        error=error,
    )


def _upsert_node(
    items: list[AgentRunNode],
    item: AgentRunNode,
) -> list[AgentRunNode]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.node_name == item.node_name:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items


def _upsert_llm_call(
    items: list[AgentLLMCall],
    item: AgentLLMCall,
) -> list[AgentLLMCall]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.call_id == item.call_id:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items


def _coerce_run_nodes(items: Any) -> list[AgentRunNode]:
    if not isinstance(items, list):
        return []
    nodes: list[AgentRunNode] = []
    for item in items:
        try:
            nodes.append(AgentRunNode.model_validate(item))
        except Exception:  # noqa: BLE001
            continue
    return nodes


def _mark_running_nodes_failed(
    items: list[AgentRunNode],
    error: str,
) -> list[AgentRunNode]:
    now = _now_iso()
    next_items: list[AgentRunNode] = []
    for item in items:
        if item.status is AgentRunNodeStatus.RUNNING:
            next_items.append(
                item.model_copy(
                    update={
                        "status": AgentRunNodeStatus.FAILED,
                        "finished_at": now,
                        "duration_ms": _iso_duration_ms(
                            item.started_at or now,
                            now,
                        ),
                        "error": error,
                    }
                )
            )
            continue
        next_items.append(item)
    return next_items


def _agent_node_display_label(node_name: str) -> str:
    labels = {
        "LoadChapterNode": "读取章节",
        "SegmentChapterNode": "切分正文",
        "GeneralExtractionNode": "通用抽取",
        "MentionNormalizeNode": "提及清洗",
        "EntityAggregationNode": "实体聚合",
        "CandidateQualityGateNode": "质量闸门",
        "TypeDispatchNode": "类型分发",
        "CharacterExpertNode": "角色专家",
        "EntityExpertNode": "实体专家",
        "EventRuleExpertNode": "事件规则专家",
        "MergeExpertCandidatesNode": "分支候选汇合",
        "BatchCardAggregationNode": "多章卡片聚合",
        "BatchConflictCheckNode": "批量冲突检查",
        "BatchMatchExistingKnowledgeNode": "匹配有效知识",
        "BatchBuildReviewItemsNode": "生成审核项",
        "BatchWriteRunNode": "写入批量运行",
    }
    return labels.get(node_name, node_name)


def _update_progress(
    items: list[AgentBatchChapterProgress],
    item: AgentBatchChapterProgress,
) -> list[AgentBatchChapterProgress]:
    next_items = list(items)
    for index, current in enumerate(next_items):
        if current.chapter_id == item.chapter_id:
            next_items[index] = item
            return next_items
    next_items.append(item)
    return next_items


def _progress_for(
    items: list[AgentBatchChapterProgress],
    chapter_id: str,
) -> AgentBatchChapterProgress:
    for item in items:
        if item.chapter_id == chapter_id:
            return item
    return AgentBatchChapterProgress(chapter_id=chapter_id)


def _node_duration(node: AgentRunNode) -> int:
    if not node.started_at:
        return 0
    return _iso_duration_ms(node.started_at, _now_iso())


def _aggregate_batch_candidates(
    states: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for state in states:
        chapter_id = str(state.get("chapter_id") or "")
        chapter_title = str(state.get("chapter_title") or chapter_id)
        for candidate in state.get("typed_candidates", []):
            if not isinstance(candidate, dict):
                continue
            payload = dict(candidate)
            source_entry = _source_entry(chapter_title, payload)
            knowledge_type = str(payload.get("type") or "")
            identity = _normalize_identity(payload.get("name"))
            if not knowledge_type or not identity:
                continue
            key = (knowledge_type, identity)
            if key not in grouped:
                payload["chapter_ids"] = [chapter_id] if chapter_id else []
                payload["chapter_titles"] = [chapter_title] if chapter_title else []
                payload["source_entries"] = [source_entry] if source_entry else []
                payload["evidence_excerpts"] = _dedupe_strings(
                    _list_strings(payload.get("evidence_excerpts"))
                )[:20]
                grouped[key] = payload
                order.append(key)
                continue
            current = grouped[key]
            current["aliases"] = _dedupe_strings(
                [
                    *_list_strings(current.get("aliases")),
                    *_list_strings(payload.get("aliases")),
                ]
            )
            current["chapter_ids"] = _dedupe_strings(
                [*_list_strings(current.get("chapter_ids")), chapter_id]
            )
            current["chapter_titles"] = _dedupe_strings(
                [*_list_strings(current.get("chapter_titles")), chapter_title]
            )
            current["evidence_excerpts"] = _dedupe_strings(
                [
                    *_list_strings(current.get("evidence_excerpts")),
                    *_list_strings(payload.get("evidence_excerpts")),
                ]
            )[:20]
            current["source_entries"] = _dedupe_strings(
                [
                    *_list_strings(current.get("source_entries")),
                    *([source_entry] if source_entry else []),
                ]
            )
            if not str(current.get("summary") or "").strip():
                current["summary"] = payload.get("summary", "")
            if not str(current.get("source_note") or "").strip():
                current["source_note"] = payload.get("source_note", "")
    aggregated = [grouped[key] for key in order]
    for index, candidate in enumerate(aggregated, start=1):
        candidate["entity_group_id"] = f"batch_entity_group_{index:03d}"
        evidence = _list_strings(candidate.get("evidence_excerpts"))
        if evidence:
            candidate["evidence_excerpt"] = evidence[0][:300]
        source_entries = _list_strings(candidate.get("source_entries"))
        if source_entries:
            candidate["source_note"] = "\n\n".join(source_entries)
        candidate["appearance_chapter_count"] = (
            len(_dedupe_strings(_list_strings(candidate.get("chapter_ids")))) or None
        )
        candidate.pop("chapter_ids", None)
        candidate.pop("chapter_titles", None)
        candidate.pop("source_entries", None)
        candidate["source_origin"] = "agent_extract"
        candidate.setdefault("lifecycle", "confirmed")
        validation_errors = _candidate_validation_errors(candidate)
        candidate["schema_validation"] = {
            "passed": not validation_errors,
            "errors": validation_errors,
        }
    return aggregated


def _source_entry(chapter_title: str, candidate: dict[str, Any]) -> str:
    excerpts = _list_strings(candidate.get("evidence_excerpts"))[:3]
    if not excerpts:
        return str(candidate.get("source_note") or "").strip()
    quoted = "；".join(f"“{excerpt}”" for excerpt in excerpts)
    return f"{chapter_title}\n关键原文：{quoted}"


def _batch_internal_conflict_check(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], int] = {}
    for index, candidate in enumerate(candidates):
        key = (
            str(candidate.get("type") or ""),
            _normalize_identity(candidate.get("name")),
        )
        if not key[1]:
            continue
        if key in seen:
            candidate.setdefault("internal_conflicts", []).append(
                "批量运行中存在同名同类型重复候选。"
            )
            candidates[seen[key]].setdefault("internal_conflicts", []).append(
                "批量运行中存在同名同类型重复候选。"
            )
        else:
            seen[key] = index
    return candidates


def _build_batch_review_items(
    run_id: str,
    candidates: list[dict[str, Any]],
) -> list[AgentReviewItem]:
    now = _now_iso()
    review_items: list[AgentReviewItem] = []
    for index, candidate in enumerate(candidates, start=1):
        validation = candidate.get("schema_validation")
        if not isinstance(validation, dict):
            validation = {
                "passed": False,
                "errors": ["候选缺少 schema 校验结果。"],
            }
        action = _candidate_action(candidate, validation)
        review_items.append(
            AgentReviewItem(
                review_item_id=f"review_item_{index:03d}",
                run_id=run_id,
                candidate_action=action,
                knowledge_type=StructuredKnowledgeType(
                    str(candidate.get("type") or "")
                ),
                candidate_status=AgentReviewCandidateStatus.PENDING,
                display_title=str(candidate.get("name") or "未命名候选"),
                suggested_card=_strip_internal_candidate_fields(candidate),
                target_card_id=candidate.get("target_card_id"),
                matched_card_name=candidate.get("matched_card_name"),
                match_reason=str(candidate.get("match_reason") or ""),
                source_excerpt=str(
                    candidate.get("evidence_excerpt")
                    or candidate.get("source_excerpt")
                    or ""
                ),
                schema_validation=AgentSchemaValidation.model_validate(validation),
                internal_conflicts=_list_strings(candidate.get("internal_conflicts")),
                external_conflicts=_list_strings(candidate.get("external_conflicts")),
                suggested_action_label=_action_label(action),
                created_at=now,
                updated_at=now,
            )
        )
    return review_items


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _batch_node_output(node_name: str, result: object) -> str:
    if isinstance(result, list):
        if node_name == "BatchCardAggregationNode":
            return f"聚合为 {len(result)} 个跨章节候选。"
        if node_name == "BatchBuildReviewItemsNode":
            return f"生成 {len(result)} 个审核项。"
    if node_name == "BatchConflictCheckNode":
        return "批量内部冲突检查完成。"
    if node_name == "BatchMatchExistingKnowledgeNode":
        return "已有知识匹配完成。"
    return "节点执行完成。"


def _metrics_for_items(
    *,
    review_items: list[AgentReviewItem],
    nodes: list[AgentRunNode],
    llm_calls: list[AgentLLMCall],
    started_at: str,
    finished_at: str,
) -> AgentMetrics:
    return AgentMetrics(
        candidate_total=len(review_items),
        candidate_count_by_type={
            knowledge_type.value: _count_items(review_items, knowledge_type.value)
            for knowledge_type in ALLOWED_KNOWLEDGE_TYPES
        },
        character_candidate_count=_count_items(review_items, "character"),
        realm_candidate_count=_count_items(review_items, "realm"),
        technique_candidate_count=_count_items(review_items, "technique"),
        location_candidate_count=_count_items(review_items, "location"),
        faction_candidate_count=_count_items(review_items, "faction"),
        item_candidate_count=_count_items(review_items, "item"),
        rule_candidate_count=_count_items(review_items, "rule"),
        event_candidate_count=_count_items(review_items, "event"),
        create_card_count=_count_actions(
            review_items,
            AgentReviewCandidateAction.CREATE_CARD,
        ),
        update_card_count=_count_actions(
            review_items,
            AgentReviewCandidateAction.UPDATE_CARD,
        ),
        conflict_count=_count_actions(
            review_items,
            AgentReviewCandidateAction.CONFLICT,
        ),
        schema_passed_count=sum(
            1 for item in review_items if item.schema_validation.passed
        ),
        schema_failed_count=sum(
            1 for item in review_items if not item.schema_validation.passed
        ),
        confirmed_count=_count_status(
            review_items,
            AgentReviewCandidateStatus.CONFIRMED,
        ),
        rejected_count=_count_status(
            review_items,
            AgentReviewCandidateStatus.REJECTED,
        ),
        pending_count=_count_status(
            review_items,
            AgentReviewCandidateStatus.PENDING,
        ),
        total_duration_ms=_iso_duration_ms(started_at, finished_at),
        llm_call_count=len(llm_calls),
        node_duration_ms={node.node_name: node.duration_ms for node in nodes},
    )


def _count_items(items: list[AgentReviewItem], knowledge_type: str) -> int:
    return sum(1 for item in items if item.knowledge_type.value == knowledge_type)


def _count_actions(
    items: list[AgentReviewItem],
    action: AgentReviewCandidateAction,
) -> int:
    return sum(1 for item in items if item.candidate_action is action)


def _iso_duration_ms(started_at: str, finished_at: str) -> int:
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((finish - start).total_seconds() * 1000))


def _metrics_for_run(
    run: AgentRun,
    review_items: list[AgentReviewItem],
) -> AgentMetrics:
    return run.metrics.model_copy(
        update={
            "confirmed_count": _count_status(
                review_items,
                AgentReviewCandidateStatus.CONFIRMED,
            ),
            "rejected_count": _count_status(
                review_items,
                AgentReviewCandidateStatus.REJECTED,
            ),
            "pending_count": _count_status(
                review_items,
                AgentReviewCandidateStatus.PENDING,
            ),
        }
    )


def _count_status(
    items: list[AgentReviewItem],
    status: AgentReviewCandidateStatus,
) -> int:
    return sum(1 for item in items if item.candidate_status is status)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _identity_from_profile(profile: LLMModelProfile) -> LLMModelIdentity:
    return LLMModelIdentity(
        provider="rightcode",
        model_id=profile.id,
        family=profile.id.rsplit("-", 1)[0],
        endpoint_kind=profile.wire_protocol,
        known=profile.upstream_verified,
        unknown_reason=(
            None if profile.upstream_verified else "上游模型名尚未完成真实密钥探测。"
        ),
    )


def _identity_for_gateway(
    gateway: LLMGatewayContract, profile: LLMModelProfile
) -> LLMModelIdentity:
    identity = getattr(gateway, "model_identity", None)
    if isinstance(identity, LLMModelIdentity):
        return identity
    return _identity_from_profile(profile)


def _consume_background_task_exception(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        return
