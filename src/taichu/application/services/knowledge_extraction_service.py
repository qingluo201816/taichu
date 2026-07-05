"""Application service for the knowledge extraction workbench."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any
from uuid import uuid4

from taichu.application.agents.knowledge_extraction.workflow import (
    ALLOWED_KNOWLEDGE_TYPES,
    KnowledgeExtractionDependencies,
    build_knowledge_extraction_graph,
    initial_knowledge_extraction_state,
)
from taichu.application.contracts.knowledge_repository import (
    AuthorMergeMode,
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.llm import LLMContract
from taichu.application.services.chapter_service import ChapterService
from taichu.domain.models.agent_run import (
    AgentMetrics,
    AgentReviewCandidateAction,
    AgentReviewCandidateStatus,
    AgentReviewItem,
    AgentRun,
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
    type_specific_field_keys,
)
from taichu.infrastructure.agent_runs.json_store import JsonAgentRunStore

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


class KnowledgeExtractionService:
    """Run the Agent and process author review actions."""

    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        llm: LLMContract,
        knowledge_repository: StructuredKnowledgeRepository,
        run_store: JsonAgentRunStore,
        default_model_name: str = "",
    ) -> None:
        self._chapter_service = chapter_service
        self._llm = llm
        self._knowledge_repository = knowledge_repository
        self._run_store = run_store
        self._default_model_name = default_model_name

    async def create_run(
        self,
        *,
        chapter_id: str,
        model_name: str | None = None,
        force: bool = False,
    ) -> AgentRun:
        """Synchronously run current-chapter extraction and persist JSON state."""
        graph = build_knowledge_extraction_graph(
            KnowledgeExtractionDependencies(
                chapter_service=self._chapter_service,
                llm=self._llm,
                knowledge_repository=self._knowledge_repository,
                run_store=self._run_store,
            )
        )
        final_state = await graph.ainvoke(
            initial_knowledge_extraction_state(
                chapter_id=chapter_id,
                model_name=model_name or self._default_model_name,
                force=force,
            )
        )
        run_data = final_state.get("run")
        if not isinstance(run_data, dict):
            raise KnowledgeExtractionError("正文知识沉淀运行未生成中间态。")
        return AgentRun.model_validate(run_data)

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
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
        _assert_review_item_can_be_processed(item)
        if item.candidate_action is AgentReviewCandidateAction.CONFLICT:
            raise KnowledgeExtractionError("候选冲突必须编辑后确认。")
        if item.candidate_action is AgentReviewCandidateAction.IGNORE:
            raise KnowledgeExtractionError("建议忽略的候选不能直接确认入库。")

        if item.candidate_action is AgentReviewCandidateAction.CREATE_CARD:
            card = _card_from_payload(item.knowledge_type, item.suggested_card)
            written = await self._knowledge_repository.create_active_card(card)
            updated = _mark_confirmed(
                item,
                author_action="confirm",
                created_card_id=written.id,
            )
        else:
            if item.target_card_id is None:
                raise KnowledgeExtractionError("候选更新缺少目标知识卡。")
            written = await self._knowledge_repository.apply_author_confirmed_updates(
                item.target_card_id,
                _patch_updates_from_payload(item.knowledge_type, item.suggested_card),
                merge_mode="append",
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
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
        _assert_review_item_can_be_processed(item)
        merged_payload = {**item.suggested_card, **card_updates}
        target_id = target_card_id or item.target_card_id
        if target_id:
            written = await self._knowledge_repository.apply_author_confirmed_updates(
                target_id,
                _patch_updates_from_payload(item.knowledge_type, merged_payload),
                merge_mode=merge_mode,
            )
            updated = _mark_confirmed(
                item,
                author_action="edit_confirm",
                updated_card_id=written.id,
            )
        else:
            card = _card_from_payload(item.knowledge_type, merged_payload)
            written = await self._knowledge_repository.create_active_card(card)
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
        run, index, item = await self._find_review_item(candidate_id, run_id=run_id)
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
            raise KnowledgeExtractionNotFoundError(
                f"候选记录“{candidate_id}”不存在。"
            )
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
        raise KnowledgeExtractionError("第一版只允许角色、地点、势力、物品入库。")
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
    card_payload["status"] = StructuredKnowledgeStatus.ACTIVE.value
    card_payload["source_origin"] = StructuredKnowledgeSourceOrigin.AGENT_EXTRACT.value
    card_payload["created_at"] = str(card_payload.get("created_at") or now)
    card_payload["updated_at"] = now
    return StructuredKnowledgeCard.model_validate(card_payload)


def _patch_updates_from_payload(
    knowledge_type: StructuredKnowledgeType,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
        raise KnowledgeExtractionError("第一版只允许角色、地点、势力、物品入库。")
    _reject_forbidden(payload)
    allowed = _editable_card_keys(knowledge_type) | _REVIEW_ONLY_FIELDS | {"id", "type"}
    unknown = set(payload) - allowed
    if unknown:
        raise KnowledgeExtractionError(
            f"候选包含不支持字段：{', '.join(sorted(unknown))}"
        )
    return {
        key: value
        for key, value in payload.items()
        if key in _editable_card_keys(knowledge_type)
        and key not in {"status", "source_origin"}
    }


def _allowed_card_keys(knowledge_type: StructuredKnowledgeType) -> set[str]:
    return {
        "id",
        "type",
        "name",
        "aliases",
        "summary",
        "importance",
        "status",
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
        "importance",
        "status",
        "source_origin",
        "source_note",
        *type_specific_field_keys(knowledge_type),
    }


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
