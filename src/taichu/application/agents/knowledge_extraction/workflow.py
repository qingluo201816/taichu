"""LangGraph workflow for current-chapter knowledge extraction."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from time import perf_counter
from typing import Any, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from taichu.application.agents.knowledge_extraction.prompts import (
    CHARACTER_EXPERT_PROMPT,
    CHARACTER_EXPERT_PROMPT_VERSION,
    ENTITY_EXPERT_PROMPT,
    ENTITY_EXPERT_PROMPT_VERSION,
    GENERAL_EXTRACTION_PROMPT,
    GENERAL_EXTRACTION_PROMPT_VERSION,
    KNOWLEDGE_EXTRACTION_PROMPT_VERSION,
)
from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.llm import LLMContract
from taichu.application.services.chapter_service import ChapterService
from taichu.domain.models.agent_run import (
    AgentLLMCall,
    AgentMetrics,
    AgentReviewCandidateAction,
    AgentReviewCandidateStatus,
    AgentReviewItem,
    AgentRun,
    AgentRunNode,
    AgentRunNodeStatus,
    AgentRunScope,
    AgentRunStatus,
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
    knowledge_type_schema,
    type_specific_field_keys,
)
from taichu.infrastructure.agent_runs.json_store import JsonAgentRunStore

ALLOWED_KNOWLEDGE_TYPES = frozenset(
    {
        StructuredKnowledgeType.CHARACTER,
        StructuredKnowledgeType.LOCATION,
        StructuredKnowledgeType.FACTION,
        StructuredKnowledgeType.ITEM,
    }
)
_GENERAL_TYPE_KEYS = {
    "characters": "character",
    "locations": "location",
    "factions": "faction",
    "items": "item",
}
_AGENT_FORBIDDEN_FIELDS = FORBIDDEN_KNOWLEDGE_FIELD_KEYS | {
    "current_goal",
    "secret",
    "known_secrets",
}


class KnowledgeExtractionState(TypedDict, total=False):
    """Mutable state shared by LangGraph nodes."""

    run_id: str
    chapter_id: str
    model_name: str
    force: bool
    started_at: str
    finished_at: str | None
    chapter_title: str
    markdown_text: str
    content_hash: str
    word_count: int
    segments: list[str]
    raw_candidates: list[dict[str, Any]]
    merged_candidates: list[dict[str, Any]]
    character_candidates: list[dict[str, Any]]
    entity_candidates: list[dict[str, Any]]
    typed_candidates: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    errors: list[str]
    failed: bool
    run: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeExtractionDependencies:
    """Runtime dependencies captured by workflow nodes."""

    chapter_service: ChapterService
    llm: LLMContract
    knowledge_repository: StructuredKnowledgeRepository
    run_store: JsonAgentRunStore


def build_knowledge_extraction_graph(
    dependencies: KnowledgeExtractionDependencies,
) -> CompiledStateGraph:
    """Build the first-version current-chapter extraction graph."""
    graph = StateGraph(KnowledgeExtractionState)
    graph.add_node(
        "LoadChapterNode",
        cast(Any, _node("LoadChapterNode", _load_chapter(dependencies))),
    )
    graph.add_node(
        "SegmentChapterNode",
        cast(Any, _node("SegmentChapterNode", _segment_chapter())),
    )
    graph.add_node(
        "GeneralExtractionNode",
        cast(Any, _node("GeneralExtractionNode", _general_extraction(dependencies))),
    )
    graph.add_node(
        "MergeChapterCandidatesNode",
        cast(Any, _node("MergeChapterCandidatesNode", _merge_candidates())),
    )
    graph.add_node(
        "TypeDispatchNode",
        cast(Any, _node("TypeDispatchNode", _dispatch_candidates())),
    )
    graph.add_node(
        "CharacterExpertNode",
        cast(Any, _node("CharacterExpertNode", _character_expert(dependencies))),
    )
    graph.add_node(
        "EntityExpertNode",
        cast(Any, _node("EntityExpertNode", _entity_expert(dependencies))),
    )
    graph.add_node(
        "NormalizeAndValidateNode",
        cast(Any, _node("NormalizeAndValidateNode", _normalize_and_validate())),
    )
    graph.add_node(
        "RunInternalConflictCheckNode",
        cast(Any, _node("RunInternalConflictCheckNode", _internal_conflict_check())),
    )
    graph.add_node(
        "MatchExistingKnowledgeNode",
        cast(Any, _node("MatchExistingKnowledgeNode", _match_existing(dependencies))),
    )
    graph.add_node(
        "BuildReviewItemsNode",
        cast(Any, _node("BuildReviewItemsNode", _build_review_items())),
    )
    graph.add_node(
        "WriteIntermediateJsonNode",
        cast(
            Any,
            _node("WriteIntermediateJsonNode", _write_intermediate_json(dependencies)),
        ),
    )

    graph.add_edge(START, "LoadChapterNode")
    graph.add_edge("LoadChapterNode", "SegmentChapterNode")
    graph.add_edge("SegmentChapterNode", "GeneralExtractionNode")
    graph.add_edge("GeneralExtractionNode", "MergeChapterCandidatesNode")
    graph.add_edge("MergeChapterCandidatesNode", "TypeDispatchNode")
    graph.add_edge("TypeDispatchNode", "CharacterExpertNode")
    graph.add_edge("CharacterExpertNode", "EntityExpertNode")
    graph.add_edge("EntityExpertNode", "NormalizeAndValidateNode")
    graph.add_edge("NormalizeAndValidateNode", "RunInternalConflictCheckNode")
    graph.add_edge("RunInternalConflictCheckNode", "MatchExistingKnowledgeNode")
    graph.add_edge("MatchExistingKnowledgeNode", "BuildReviewItemsNode")
    graph.add_edge("BuildReviewItemsNode", "WriteIntermediateJsonNode")
    graph.add_edge("WriteIntermediateJsonNode", END)
    return graph.compile()


def initial_knowledge_extraction_state(
    *,
    chapter_id: str,
    model_name: str | None = None,
    force: bool = False,
) -> KnowledgeExtractionState:
    """Create the initial graph state for one current-chapter run."""
    now = _now_iso()
    return {
        "run_id": _new_run_id(now),
        "chapter_id": chapter_id,
        "model_name": model_name or "",
        "force": force,
        "started_at": now,
        "finished_at": None,
        "chapter_title": "",
        "markdown_text": "",
        "content_hash": "",
        "word_count": 0,
        "segments": [],
        "raw_candidates": [],
        "merged_candidates": [],
        "character_candidates": [],
        "entity_candidates": [],
        "typed_candidates": [],
        "review_items": [],
        "nodes": [],
        "llm_calls": [],
        "errors": [],
        "failed": False,
    }


def run_from_state(state: KnowledgeExtractionState) -> AgentRun:
    """Convert graph state into a persisted AgentRun model."""
    status = AgentRunStatus.FAILED if state.get("failed") else AgentRunStatus.COMPLETED
    finished_at = state.get("finished_at") or _now_iso()
    nodes = [
        AgentRunNode.model_validate(node)
        for node in state.get("nodes", [])
    ]
    llm_calls = [
        AgentLLMCall.model_validate(call)
        for call in state.get("llm_calls", [])
    ]
    review_items = [
        AgentReviewItem.model_validate(item)
        for item in state.get("review_items", [])
    ]
    metrics = _metrics(
        review_items=review_items,
        nodes=nodes,
        llm_calls=llm_calls,
        started_at=state["started_at"],
        finished_at=finished_at,
    )
    return AgentRun(
        run_id=state["run_id"],
        model_name=state.get("model_name", ""),
        status=status,
        scope=AgentRunScope(
            chapter_id=state["chapter_id"],
            chapter_title=state.get("chapter_title", ""),
            content_hash=state.get("content_hash", ""),
        ),
        started_at=state["started_at"],
        finished_at=finished_at,
        nodes=nodes,
        llm_calls=llm_calls,
        raw_candidates=state.get("raw_candidates", []),
        typed_candidates=state.get("typed_candidates", []),
        review_items=review_items,
        metrics=metrics,
        errors=state.get("errors", []),
        prompt_version=KNOWLEDGE_EXTRACTION_PROMPT_VERSION,
    )


def _node(
    node_name: str,
    handler: Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]],
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        if state.get("failed") and node_name != "WriteIntermediateJsonNode":
            return _record_node(
                state,
                node_name=node_name,
                status=AgentRunNodeStatus.SKIPPED,
                started_at=_now_iso(),
                output_summary="前序节点失败，已跳过。",
            )
        started = _now_iso()
        timer = perf_counter()
        try:
            next_state = await handler(cast(KnowledgeExtractionState, dict(state)))
        except Exception as caught:  # noqa: BLE001
            next_state = cast(KnowledgeExtractionState, dict(state))
            next_state["failed"] = True
            next_state.setdefault("errors", []).append(str(caught))
            return _record_node(
                next_state,
                node_name=node_name,
                status=AgentRunNodeStatus.FAILED,
                started_at=started,
                duration_ms=_elapsed_ms(timer),
                error=str(caught),
            )
        status = (
            AgentRunNodeStatus.FAILED
            if next_state.get("failed") and node_name != "WriteIntermediateJsonNode"
            else AgentRunNodeStatus.SUCCESS
        )
        node_error = (
            next_state.get("errors", [])[-1]
            if status is AgentRunNodeStatus.FAILED
            else None
        )
        return _record_node(
            next_state,
            node_name=node_name,
            status=status,
            started_at=started,
            duration_ms=_elapsed_ms(timer),
            input_summary=_node_input_summary(node_name, state),
            output_summary=_node_output_summary(node_name, next_state),
            error=node_error,
        )

    return run


def _load_chapter(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        chapter = await dependencies.chapter_service.read_chapter(state["chapter_id"])
        markdown = chapter.markdown
        if not markdown.strip():
            state["failed"] = True
            state.setdefault("errors", []).append("当前章节正文为空，无法抽取。")
            return state
        state["chapter_title"] = chapter.chapter.title
        state["markdown_text"] = markdown
        state["content_hash"] = hashlib.sha256(
            markdown.encode("utf-8")
        ).hexdigest()
        state["word_count"] = len(re.findall(r"\S", markdown))
        return state

    return run


def _segment_chapter() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        markdown = state.get("markdown_text", "")
        if len(markdown) <= 6000:
            state["segments"] = [markdown]
            return state
        paragraphs = [part for part in re.split(r"\n{2,}", markdown) if part.strip()]
        segments: list[str] = []
        current = ""
        for paragraph in paragraphs:
            next_text = f"{current}\n\n{paragraph}" if current else paragraph
            if len(next_text) > 5000 and current:
                segments.append(current)
                current = paragraph
            else:
                current = next_text
        if current:
            segments.append(current)
        state["segments"] = segments or [markdown]
        return state

    return run


def _general_extraction(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        raw_candidates: list[dict[str, Any]] = []
        for index, segment in enumerate(state.get("segments", []), start=1):
            prompt = _render_prompt(
                GENERAL_EXTRACTION_PROMPT,
                chapter_id=state["chapter_id"],
                chapter_title=_segment_title(state, index),
                chapter_text=segment,
                allowed_types="character, location, faction, item",
            )
            parsed = await _complete_json(
                state,
                dependencies,
                node_name="GeneralExtractionNode",
                prompt_version=GENERAL_EXTRACTION_PROMPT_VERSION,
                prompt=prompt,
            )
            if parsed is None:
                state["failed"] = True
                return state
            raw_candidates.extend(_raw_candidates_from_general_output(parsed))
        state["raw_candidates"] = raw_candidates
        return state

    return run


def _merge_candidates() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        type_by_name: dict[str, str] = {}
        for candidate in state.get("raw_candidates", []):
            name = _name(candidate)
            candidate_type = str(candidate.get("knowledge_type") or "")
            normalized_name = _normalize_identity(name)
            if normalized_name in type_by_name and type_by_name[normalized_name] != candidate_type:
                candidate.setdefault("internal_conflicts", []).append(
                    "同名候选出现在不同知识类型中。"
                )
            type_by_name.setdefault(normalized_name, candidate_type)
            key = (candidate_type, normalized_name)
            if key not in merged:
                merged[key] = candidate
                continue
            existing = merged[key]
            existing["aliases"] = sorted(
                {
                    *_list_strings(existing.get("aliases")),
                    *_list_strings(candidate.get("aliases")),
                }
            )
            existing["source_excerpt"] = _first_non_empty(
                existing.get("source_excerpt"),
                candidate.get("source_excerpt"),
            )
        state["merged_candidates"] = list(merged.values())
        return state

    return run


def _dispatch_candidates() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        merged = state.get("merged_candidates", [])
        state["character_candidates"] = [
            item for item in merged if item.get("knowledge_type") == "character"
        ]
        state["entity_candidates"] = [
            item
            for item in merged
            if item.get("knowledge_type") in {"location", "faction", "item"}
        ]
        return state

    return run


def _character_expert(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        candidates = state.get("character_candidates", [])
        if not candidates:
            return state
        prompt = _render_prompt(
            CHARACTER_EXPERT_PROMPT,
            character_schema=_json_dump(
                knowledge_type_schema(StructuredKnowledgeType.CHARACTER).model_dump(
                    mode="json"
                )
            ),
            chapter_id=state["chapter_id"],
            chapter_title=state.get("chapter_title", ""),
            character_candidates=_json_dump(candidates),
        )
        parsed = await _complete_json(
            state,
            dependencies,
            node_name="CharacterExpertNode",
            prompt_version=CHARACTER_EXPERT_PROMPT_VERSION,
            prompt=prompt,
        )
        if parsed is None:
            state["failed"] = True
            return state
        cards = parsed.get("cards") if isinstance(parsed, dict) else []
        if isinstance(cards, list):
            state.setdefault("typed_candidates", []).extend(
                _cards_with_type(cards, "character")
            )
        return state

    return run


def _entity_expert(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        candidates = state.get("entity_candidates", [])
        if not candidates:
            return state
        active_index = [
            {
                "id": card.id,
                "type": card.type.value,
                "name": card.name,
                "aliases": card.aliases,
                "summary": card.summary,
            }
            for card in await dependencies.knowledge_repository.list_active_cards()
        ]
        entity_schemas = [
            knowledge_type_schema(knowledge_type).model_dump(mode="json")
            for knowledge_type in (
                StructuredKnowledgeType.LOCATION,
                StructuredKnowledgeType.FACTION,
                StructuredKnowledgeType.ITEM,
            )
        ]
        prompt = _render_prompt(
            ENTITY_EXPERT_PROMPT,
            entity_schemas=_json_dump(entity_schemas),
            active_knowledge_index=_json_dump(active_index),
            chapter_id=state["chapter_id"],
            chapter_title=state.get("chapter_title", ""),
            entity_candidates=_json_dump(candidates),
        )
        parsed = await _complete_json(
            state,
            dependencies,
            node_name="EntityExpertNode",
            prompt_version=ENTITY_EXPERT_PROMPT_VERSION,
            prompt=prompt,
        )
        if parsed is None:
            state["failed"] = True
            return state
        for key, knowledge_type in (
            ("locations", "location"),
            ("factions", "faction"),
            ("items", "item"),
        ):
            cards = parsed.get(key) if isinstance(parsed, dict) else []
            if isinstance(cards, list):
                state.setdefault("typed_candidates", []).extend(
                    _cards_with_type(cards, knowledge_type)
                )
        return state

    return run


def _normalize_and_validate() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        normalized: list[dict[str, Any]] = []
        for candidate in state.get("typed_candidates", []):
            card = dict(candidate)
            validation_errors = _candidate_validation_errors(card)
            card["schema_validation"] = {
                "passed": not validation_errors,
                "errors": validation_errors,
            }
            card.setdefault("status", "active")
            card.setdefault("source_origin", "agent_extract")
            normalized.append(card)
        state["typed_candidates"] = normalized
        return state

    return run


def _internal_conflict_check() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        seen: dict[tuple[str, str], int] = {}
        for index, candidate in enumerate(state.get("typed_candidates", [])):
            key = (
                str(candidate.get("type") or ""),
                _normalize_identity(candidate.get("name")),
            )
            if key[1] and key in seen:
                candidate.setdefault("internal_conflicts", []).append(
                    "本轮运行中存在同名同类型重复候选。"
                )
                state["typed_candidates"][seen[key]].setdefault(
                    "internal_conflicts",
                    [],
                ).append("本轮运行中存在同名同类型重复候选。")
            else:
                seen[key] = index
        return state

    return run


def _match_existing(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        for candidate in state.get("typed_candidates", []):
            knowledge_type = str(candidate.get("type") or "")
            matches = await dependencies.knowledge_repository.search_active_identity(
                knowledge_type,
                str(candidate.get("name") or ""),
                _list_strings(candidate.get("aliases")),
            )
            if not matches:
                continue
            match = matches[0]
            candidate["target_card_id"] = match.id
            candidate["matched_card_name"] = match.name
            candidate["match_reason"] = "命中已有有效知识卡的名称或别名。"
            conflicts = _external_conflicts(candidate, match)
            if conflicts:
                candidate["external_conflicts"] = conflicts
        return state

    return run


def _build_review_items() -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        now = _now_iso()
        review_items: list[dict[str, Any]] = []
        for index, candidate in enumerate(state.get("typed_candidates", []), start=1):
            validation = candidate.get("schema_validation") or {
                "passed": False,
                "errors": ["候选缺少 schema 校验结果。"],
            }
            action = _candidate_action(candidate, validation)
            review_items.append(
                {
                    "review_item_id": f"review_item_{index:03d}",
                    "run_id": state["run_id"],
                    "candidate_action": action.value,
                    "knowledge_type": str(candidate.get("type") or ""),
                    "candidate_status": "pending",
                    "display_title": str(candidate.get("name") or "未命名候选"),
                    "suggested_card": _strip_internal_candidate_fields(candidate),
                    "target_card_id": candidate.get("target_card_id"),
                    "matched_card_name": candidate.get("matched_card_name"),
                    "match_reason": str(candidate.get("match_reason") or ""),
                    "source_excerpt": str(
                        candidate.get("evidence_excerpt")
                        or candidate.get("source_excerpt")
                        or ""
                    ),
                    "schema_validation": validation,
                    "internal_conflicts": _list_strings(
                        candidate.get("internal_conflicts")
                    ),
                    "external_conflicts": _list_strings(
                        candidate.get("external_conflicts")
                    ),
                    "suggested_action_label": _action_label(action),
                    "author_action": None,
                    "created_knowledge_card_id": None,
                    "updated_knowledge_card_id": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        state["review_items"] = review_items
        return state

    return run


def _write_intermediate_json(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        state["finished_at"] = _now_iso()
        run_model = run_from_state(state)
        await dependencies.run_store.write_run(run_model)
        state["run"] = run_model.model_dump(mode="json")
        return state

    return run


async def _complete_json(
    state: KnowledgeExtractionState,
    dependencies: KnowledgeExtractionDependencies,
    *,
    node_name: str,
    prompt_version: str,
    prompt: str,
) -> dict[str, Any] | None:
    started_at = _now_iso()
    timer = perf_counter()
    raw_response = ""
    parsed: dict[str, Any] = {}
    error: str | None = None
    try:
        raw_response = await dependencies.llm.complete(prompt)
        parsed_value = json.loads(raw_response)
        if not isinstance(parsed_value, dict):
            raise ValueError("LLM 响应 JSON 顶层必须是对象。")
        parsed = parsed_value
    except Exception as caught:  # noqa: BLE001
        error = f"{node_name} 的 LLM 响应不是有效 JSON：{caught}"
        state.setdefault("errors", []).append(error)
    state.setdefault("llm_calls", []).append(
        {
            "call_id": f"llm_call_{len(state.get('llm_calls', [])) + 1:03d}",
            "node_name": node_name,
            "model_name": state.get("model_name") or "默认模型",
            "prompt_version": prompt_version,
            "input_prompt": prompt,
            "raw_response": raw_response,
            "parsed_output": parsed,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "duration_ms": _elapsed_ms(timer),
            "error": error,
        }
    )
    return None if error else parsed


def _raw_candidates_from_general_output(output: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key, knowledge_type in _GENERAL_TYPE_KEYS.items():
        values = output.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            candidate["knowledge_type"] = knowledge_type
            candidate.setdefault("name", _first_non_empty(item.get("name"), item.get("title")))
            candidate.setdefault("aliases", [])
            candidate.setdefault(
                "source_excerpt",
                _first_non_empty(
                    item.get("source_excerpt"),
                    item.get("evidence_excerpt"),
                    item.get("excerpt"),
                ),
            )
            candidates.append(candidate)
    return candidates


def _cards_with_type(cards: list[Any], knowledge_type: str) -> list[dict[str, Any]]:
    typed: list[dict[str, Any]] = []
    for card in cards:
        if isinstance(card, dict):
            payload = dict(card)
            payload["type"] = knowledge_type
            payload.setdefault("status", "active")
            payload.setdefault("source_origin", "agent_extract")
            typed.append(payload)
    return typed


def _candidate_validation_errors(card: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    forbidden = _AGENT_FORBIDDEN_FIELDS & set(card)
    if forbidden:
        errors.append(f"包含第一版禁止字段：{', '.join(sorted(forbidden))}")
    try:
        knowledge_type = StructuredKnowledgeType(str(card.get("type") or ""))
    except ValueError:
        errors.append("知识类型不属于第一版范围。")
        return errors
    if knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
        errors.append("第一版只允许角色、地点、势力、物品。")
    for field_key in ("name", "summary", "source_note", "evidence_excerpt"):
        if not str(card.get(field_key) or "").strip():
            errors.append(f"缺少必填字段：{field_key}")
    if card.get("source_origin") != StructuredKnowledgeSourceOrigin.AGENT_EXTRACT.value:
        errors.append("source_origin 必须是 agent_extract。")
    evidence_excerpt = str(card.get("evidence_excerpt") or "")
    if len(evidence_excerpt) > 300:
        errors.append("原文摘录不能超过 300 字。")
    allowed_keys = {
        "type",
        "name",
        "aliases",
        "summary",
        "importance",
        "status",
        "source_origin",
        "source_note",
        "evidence_excerpt",
        *type_specific_field_keys(knowledge_type),
        "schema_validation",
        "internal_conflicts",
        "external_conflicts",
        "target_card_id",
        "matched_card_name",
        "match_reason",
    }
    unknown = set(card) - allowed_keys
    if unknown:
        errors.append(f"包含未知字段：{', '.join(sorted(unknown))}")
    return errors


def _external_conflicts(
    candidate: dict[str, Any],
    existing: StructuredKnowledgeCard,
) -> list[str]:
    conflicts: list[str] = []
    for key, value in candidate.items():
        if key in {
            "source_note",
            "evidence_excerpt",
            "status",
            "source_origin",
            "last_seen_chapter_id",
        }:
            continue
        if key not in knowledge_type_schema(existing.type).model_fields and not hasattr(
            existing,
            key,
        ):
            continue
        current_value = getattr(existing, key, None)
        if _is_non_empty(current_value) and _is_non_empty(value) and current_value != value:
            conflicts.append(f"字段“{key}”与已有有效知识卡不一致。")
    return conflicts


def _candidate_action(
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> AgentReviewCandidateAction:
    if not validation.get("passed"):
        return AgentReviewCandidateAction.IGNORE
    if candidate.get("external_conflicts") or candidate.get("internal_conflicts"):
        return AgentReviewCandidateAction.CONFLICT
    if candidate.get("target_card_id"):
        return AgentReviewCandidateAction.UPDATE_CARD
    return AgentReviewCandidateAction.CREATE_CARD


def _strip_internal_candidate_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "schema_validation",
        "internal_conflicts",
        "external_conflicts",
        "target_card_id",
        "matched_card_name",
        "match_reason",
        "source_excerpt",
    }
    return {key: value for key, value in candidate.items() if key not in excluded}


def _metrics(
    *,
    review_items: list[AgentReviewItem],
    nodes: list[AgentRunNode],
    llm_calls: list[AgentLLMCall],
    started_at: str,
    finished_at: str,
) -> AgentMetrics:
    return AgentMetrics(
        candidate_total=len(review_items),
        character_candidate_count=_count_items(review_items, "character"),
        location_candidate_count=_count_items(review_items, "location"),
        faction_candidate_count=_count_items(review_items, "faction"),
        item_candidate_count=_count_items(review_items, "item"),
        create_card_count=_count_actions(review_items, AgentReviewCandidateAction.CREATE_CARD),
        update_card_count=_count_actions(review_items, AgentReviewCandidateAction.UPDATE_CARD),
        conflict_count=_count_actions(review_items, AgentReviewCandidateAction.CONFLICT),
        schema_passed_count=sum(1 for item in review_items if item.schema_validation.passed),
        schema_failed_count=sum(1 for item in review_items if not item.schema_validation.passed),
        confirmed_count=_count_status(review_items, AgentReviewCandidateStatus.CONFIRMED),
        rejected_count=_count_status(review_items, AgentReviewCandidateStatus.REJECTED),
        pending_count=_count_status(review_items, AgentReviewCandidateStatus.PENDING),
        deferred_count=_count_status(review_items, AgentReviewCandidateStatus.DEFERRED),
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


def _count_status(
    items: list[AgentReviewItem],
    status: AgentReviewCandidateStatus,
) -> int:
    return sum(1 for item in items if item.candidate_status is status)


def _record_node(
    state: KnowledgeExtractionState,
    *,
    node_name: str,
    status: AgentRunNodeStatus,
    started_at: str,
    duration_ms: int = 0,
    input_summary: str = "",
    output_summary: str = "",
    error: str | None = None,
) -> KnowledgeExtractionState:
    state.setdefault("nodes", []).append(
        {
            "node_name": node_name,
            "status": status.value,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "duration_ms": duration_ms,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "error": error,
        }
    )
    return state


def _node_input_summary(node_name: str, state: KnowledgeExtractionState) -> str:
    if node_name == "GeneralExtractionNode":
        return f"{len(state.get('segments', []))} 个章节片段。"
    if node_name in {"CharacterExpertNode", "EntityExpertNode"}:
        return f"{len(state.get('merged_candidates', []))} 个章内候选。"
    return ""


def _node_output_summary(node_name: str, state: KnowledgeExtractionState) -> str:
    if node_name == "LoadChapterNode":
        return f"读取章节“{state.get('chapter_title', '')}”，约 {state.get('word_count', 0)} 字。"
    if node_name == "SegmentChapterNode":
        return f"生成 {len(state.get('segments', []))} 个处理片段。"
    if node_name == "GeneralExtractionNode":
        return f"生成 {len(state.get('raw_candidates', []))} 个原始候选。"
    if node_name == "MergeChapterCandidatesNode":
        return f"合并为 {len(state.get('merged_candidates', []))} 个候选。"
    if node_name == "BuildReviewItemsNode":
        return f"生成 {len(state.get('review_items', []))} 个审核项。"
    return ""


def _render_prompt(template: str, **values: str) -> str:
    prompt = template
    for key, value in values.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)
    return prompt


def _segment_title(state: KnowledgeExtractionState, index: int) -> str:
    if len(state.get("segments", [])) <= 1:
        return state.get("chapter_title", "")
    return f"{state.get('chapter_title', '')}（片段 {index}）"


def _new_run_id(now: str) -> str:
    compact = (
        now.replace("-", "")
        .replace(":", "")
        .replace("+00:00", "")
        .replace("Z", "")
    )
    date_part = compact[:8]
    time_part = compact[9:15] if "T" in compact else compact[8:14]
    return f"extract_run_{date_part}_{time_part}_{uuid4().hex[:6]}"


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _name(candidate: dict[str, Any]) -> str:
    return str(candidate.get("name") or candidate.get("title") or "").strip()


def _normalize_identity(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.split()).casefold()


def _first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_non_empty(value: object) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _iso_duration_ms(started_at: str, finished_at: str) -> int:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((finished - started).total_seconds() * 1000))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _action_label(action: AgentReviewCandidateAction) -> str:
    return {
        AgentReviewCandidateAction.CREATE_CARD: "建议创建新知识卡",
        AgentReviewCandidateAction.UPDATE_CARD: "建议补充已有知识卡",
        AgentReviewCandidateAction.CONFLICT: "存在冲突，建议编辑后确认",
        AgentReviewCandidateAction.IGNORE: "建议忽略",
    }[action]
