"""LangGraph workflow for current-chapter knowledge extraction."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from time import perf_counter
from typing import Annotated, Any, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from taichu.application.agents.knowledge_extraction.prompts import (
    CHARACTER_EXPERT_PROMPT,
    CHARACTER_EXPERT_PROMPT_VERSION,
    ENTITY_EXPERT_PROMPT,
    ENTITY_EXPERT_PROMPT_VERSION,
    EVENT_RULE_EXPERT_PROMPT,
    EVENT_RULE_EXPERT_PROMPT_VERSION,
    GENERAL_EXTRACTION_PROMPT,
    GENERAL_EXTRACTION_PROMPT_VERSION,
    KNOWLEDGE_EXTRACTION_PROMPT_VERSION,
    SUMMARY_SYNTHESIS_PROMPT,
    SUMMARY_SYNTHESIS_PROMPT_VERSION,
)
from taichu.application.contracts.agent_run_repository import AgentRunRepository
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMModelIdentity,
    LLMRequest,
    LLMResponse,
    response_text,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.agents.models.agent_run import (
    AgentBatchChapterProgress,
    AgentEntityGroup,
    AgentIgnoredExtraction,
    AgentLLMCall,
    AgentMetrics,
    AgentRawMention,
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
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeCard,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
    knowledge_type_schema,
    type_specific_field_keys,
)

ALLOWED_KNOWLEDGE_TYPES = frozenset(
    {
        StructuredKnowledgeType.CHARACTER,
        StructuredKnowledgeType.REALM,
        StructuredKnowledgeType.TECHNIQUE,
        StructuredKnowledgeType.LOCATION,
        StructuredKnowledgeType.FACTION,
        StructuredKnowledgeType.ITEM,
        StructuredKnowledgeType.RULE,
        StructuredKnowledgeType.EVENT,
    }
)
_GENERAL_TYPE_KEYS = {
    "characters": "character",
    "realms": "realm",
    "techniques": "technique",
    "locations": "location",
    "factions": "faction",
    "items": "item",
    "rules": "rule",
    "events": "event",
}
_ALLOWED_TYPE_LABEL = (
    "character, location, faction, item, realm, technique, event, rule"
)
_ENTITY_EXPERT_TYPES = {"location", "faction", "item", "realm", "technique"}
_EVENT_RULE_EXPERT_TYPES = {"event", "rule"}
_MAX_MENTION_EVIDENCE_COUNT = 5
_MAX_GROUP_EVIDENCE_COUNT = 12
_JSON_REPAIR_MAX_RETRIES = 2
_KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS = 100_000
_REJECT_CHARACTER_NAMES = frozenset(
    {
        "另一生面孔",
        "小山羊胡子",
        "穿青衫的人",
        "一个少年",
        "另一人",
        "其中一个",
        "那人",
        "他们",
        "众人",
        "少年们",
        "村民",
        "大人们",
        "徒弟们",
        "镇上的人",
        "猎户",
    }
)
_REJECT_LOCATION_NAMES = frozenset(
    {
        "酒家",
        "药铺门口",
        "小店铺",
        "内院",
        "小镇广场",
        "山里",
        "镇上",
        "北街",
        "家中",
        "小山谷",
        "普通树林",
        "路边",
        "广场",
    }
)
_REJECT_ITEM_NAMES = frozenset(
    {
        "银两",
        "衣物",
        "器具",
        "普通银两",
        "普通衣物",
        "普通器具",
    }
)
_LOCATION_NAME_MARKERS = (
    "镇",
    "岭",
    "山",
    "门",
    "铺",
    "谷",
    "洞",
    "峰",
    "城",
    "街",
    "院",
)
_FACTION_NAME_MARKERS = (
    "教",
    "宗",
    "门",
    "派",
    "族",
    "家",
    "会",
    "盟",
    "国",
    "朝",
    "院",
)
_SPECIAL_ITEM_MARKERS = (
    "令",
    "牌",
    "丹",
    "药",
    "剑",
    "符",
    "珠",
    "黄精",
    "法宝",
)
_REALM_NAME_MARKERS = (
    "境",
    "阶",
    "层",
    "炼气",
    "筑基",
    "金丹",
    "元婴",
    "化神",
)
_TECHNIQUE_NAME_MARKERS = (
    "功",
    "法",
    "诀",
    "术",
    "神通",
    "禁术",
    "剑诀",
    "阵",
    "丹",
)
_ITEM_FUNCTION_MARKERS = (
    "用于",
    "能够",
    "可以",
    "洞悉",
    "检验",
    "检测",
    "药效",
    "炼制",
    "材料",
    "飞行",
    "行驶",
    "全封闭",
    "通体",
    "生于",
    "每一",
    "最多",
)
_TECHNIQUE_FUNCTION_MARKERS = (
    "功法",
    "绝学",
    "攻击法",
    "修炼",
    "施展",
    "传承",
    "预知",
    "制敌",
    "法诀",
    "神通",
    "境界",
)
_AGENT_FORBIDDEN_FIELDS = FORBIDDEN_KNOWLEDGE_FIELD_KEYS | {
    "current_goal",
    "secret",
    "known_secrets",
}


KnowledgeExtractionEventSink = Callable[[dict[str, Any]], Awaitable[None]]


def _append_state_list(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [*left, *right]


def _append_state_strings(left: list[str], right: list[str]) -> list[str]:
    return [*left, *right]


def _or_state_bool(left: bool, right: bool) -> bool:
    return bool(left) or bool(right)


class KnowledgeExtractionState(TypedDict, total=False):
    """Mutable state shared by LangGraph nodes."""

    run_id: str
    chapter_id: str
    scope_type: str
    chapter_ids: list[str]
    chapter_titles: list[str]
    chapter_content_hashes: dict[str, str]
    model_name: str
    requested_model_name: str | None
    model_id: str
    model_display_name: str
    upstream_model: str
    wire_protocol: str
    generation_model_identity: dict[str, Any]
    force: bool
    started_at: str
    finished_at: str | None
    chapter_title: str
    markdown_text: str
    content_hash: str
    word_count: int
    segments: list[str]
    raw_mentions: list[dict[str, Any]]
    entity_groups: list[dict[str, Any]]
    ignored: list[dict[str, Any]]
    raw_candidates: list[dict[str, Any]]
    character_entity_groups: list[dict[str, Any]]
    entity_entity_groups: list[dict[str, Any]]
    event_rule_entity_groups: list[dict[str, Any]]
    character_typed_candidates: list[dict[str, Any]]
    entity_typed_candidates: list[dict[str, Any]]
    event_rule_typed_candidates: list[dict[str, Any]]
    typed_candidates: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    graph_nodes: list[dict[str, str]]
    graph_edges: list[dict[str, str]]
    batch_chapter_progress: list[dict[str, Any]]
    max_concurrency: int
    current_concurrency: int
    total_chapter_count: int
    completed_chapter_count: int
    failed_chapter_count: int
    nodes: Annotated[list[dict[str, Any]], _append_state_list]
    llm_calls: Annotated[list[dict[str, Any]], _append_state_list]
    errors: Annotated[list[str], _append_state_strings]
    failed: Annotated[bool, _or_state_bool]
    run: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeExtractionDependencies:
    """Runtime dependencies captured by workflow nodes."""

    chapter_service: ChapterService
    llm: LLMGatewayContract
    retrieval_service: RetrievalService
    run_store: AgentRunRepository
    event_sink: KnowledgeExtractionEventSink | None = None


KNOWLEDGE_EXTRACTION_GRAPH_NODES: list[dict[str, str]] = [
    {"node_name": "LoadChapterNode", "label": "读取章节", "lane": "预处理"},
    {"node_name": "SegmentChapterNode", "label": "切分正文", "lane": "预处理"},
    {"node_name": "GeneralExtractionNode", "label": "通用抽取", "lane": "抽取"},
    {"node_name": "MentionNormalizeNode", "label": "提及清洗", "lane": "抽取"},
    {"node_name": "EntityAggregationNode", "label": "实体聚合", "lane": "抽取"},
    {"node_name": "CandidateQualityGateNode", "label": "质量闸门", "lane": "抽取"},
    {"node_name": "TypeDispatchNode", "label": "类型分发", "lane": "分发"},
    {"node_name": "CharacterExpertNode", "label": "角色专家", "lane": "并行专家"},
    {"node_name": "EntityExpertNode", "label": "实体专家", "lane": "并行专家"},
    {"node_name": "EventRuleExpertNode", "label": "事件规则专家", "lane": "并行专家"},
    {"node_name": "MergeExpertCandidatesNode", "label": "合并候选", "lane": "汇合"},
    {"node_name": "NormalizeAndValidateNode", "label": "规范校验", "lane": "后处理"},
    {
        "node_name": "RunInternalConflictCheckNode",
        "label": "本轮冲突检查",
        "lane": "后处理",
    },
    {
        "node_name": "MatchExistingKnowledgeNode",
        "label": "匹配有效知识",
        "lane": "后处理",
    },
    {
        "node_name": "SynthesizeCandidateSummariesNode",
        "label": "综合候选摘要",
        "lane": "后处理",
    },
    {"node_name": "BuildReviewItemsNode", "label": "生成审核项", "lane": "后处理"},
    {"node_name": "WriteIntermediateJsonNode", "label": "写入中间态", "lane": "写入"},
]

KNOWLEDGE_EXTRACTION_GRAPH_EDGES: list[dict[str, str]] = [
    {"source": "LoadChapterNode", "target": "SegmentChapterNode"},
    {"source": "SegmentChapterNode", "target": "GeneralExtractionNode"},
    {"source": "GeneralExtractionNode", "target": "MentionNormalizeNode"},
    {"source": "MentionNormalizeNode", "target": "EntityAggregationNode"},
    {"source": "EntityAggregationNode", "target": "CandidateQualityGateNode"},
    {"source": "CandidateQualityGateNode", "target": "TypeDispatchNode"},
    {"source": "TypeDispatchNode", "target": "CharacterExpertNode"},
    {"source": "TypeDispatchNode", "target": "EntityExpertNode"},
    {"source": "TypeDispatchNode", "target": "EventRuleExpertNode"},
    {"source": "CharacterExpertNode", "target": "MergeExpertCandidatesNode"},
    {"source": "EntityExpertNode", "target": "MergeExpertCandidatesNode"},
    {"source": "EventRuleExpertNode", "target": "MergeExpertCandidatesNode"},
    {"source": "MergeExpertCandidatesNode", "target": "NormalizeAndValidateNode"},
    {
        "source": "NormalizeAndValidateNode",
        "target": "RunInternalConflictCheckNode",
    },
    {
        "source": "RunInternalConflictCheckNode",
        "target": "MatchExistingKnowledgeNode",
    },
    {
        "source": "MatchExistingKnowledgeNode",
        "target": "SynthesizeCandidateSummariesNode",
    },
    {
        "source": "SynthesizeCandidateSummariesNode",
        "target": "BuildReviewItemsNode",
    },
    {"source": "BuildReviewItemsNode", "target": "WriteIntermediateJsonNode"},
]

BATCH_KNOWLEDGE_EXTRACTION_GRAPH_NODES: list[dict[str, str]] = [
    {
        "node_name": "BatchChapterPoolNode",
        "label": "章节并行抽取池",
        "lane": "并行抽取",
    },
    {
        "node_name": "BatchCardAggregationNode",
        "label": "多章卡片聚合",
        "lane": "统一后处理",
    },
    {
        "node_name": "BatchConflictCheckNode",
        "label": "批量冲突检查",
        "lane": "统一后处理",
    },
    {
        "node_name": "BatchMatchExistingKnowledgeNode",
        "label": "匹配有效知识",
        "lane": "统一后处理",
    },
    {
        "node_name": "BatchSynthesizeCandidateSummariesNode",
        "label": "综合候选摘要",
        "lane": "统一后处理",
    },
    {
        "node_name": "BatchBuildReviewItemsNode",
        "label": "生成审核项",
        "lane": "统一后处理",
    },
    {"node_name": "BatchWriteRunNode", "label": "写入批量运行", "lane": "写入"},
]

BATCH_KNOWLEDGE_EXTRACTION_GRAPH_EDGES: list[dict[str, str]] = [
    {"source": "BatchChapterPoolNode", "target": "BatchCardAggregationNode"},
    {"source": "BatchCardAggregationNode", "target": "BatchConflictCheckNode"},
    {"source": "BatchConflictCheckNode", "target": "BatchMatchExistingKnowledgeNode"},
    {
        "source": "BatchMatchExistingKnowledgeNode",
        "target": "BatchSynthesizeCandidateSummariesNode",
    },
    {
        "source": "BatchSynthesizeCandidateSummariesNode",
        "target": "BatchBuildReviewItemsNode",
    },
    {"source": "BatchBuildReviewItemsNode", "target": "BatchWriteRunNode"},
]


def build_knowledge_extraction_graph(
    dependencies: KnowledgeExtractionDependencies,
) -> CompiledStateGraph:
    """Build the first-version current-chapter extraction graph."""
    graph = StateGraph(KnowledgeExtractionState)
    graph.add_node(
        "LoadChapterNode",
        cast(Any, _node("LoadChapterNode", _load_chapter(dependencies), dependencies)),
    )
    graph.add_node(
        "SegmentChapterNode",
        cast(Any, _node("SegmentChapterNode", _segment_chapter(), dependencies)),
    )
    graph.add_node(
        "GeneralExtractionNode",
        cast(
            Any,
            _node(
                "GeneralExtractionNode", _general_extraction(dependencies), dependencies
            ),
        ),
    )
    graph.add_node(
        "MentionNormalizeNode",
        cast(Any, _node("MentionNormalizeNode", _normalize_mentions(), dependencies)),
    )
    graph.add_node(
        "EntityAggregationNode",
        cast(Any, _node("EntityAggregationNode", _aggregate_entities(), dependencies)),
    )
    graph.add_node(
        "CandidateQualityGateNode",
        cast(
            Any,
            _node(
                "CandidateQualityGateNode",
                _candidate_quality_gate(dependencies),
                dependencies,
            ),
        ),
    )
    graph.add_node(
        "TypeDispatchNode",
        cast(Any, _node("TypeDispatchNode", _dispatch_entity_groups(), dependencies)),
    )
    graph.add_node(
        "CharacterExpertNode",
        cast(
            Any,
            _node("CharacterExpertNode", _character_expert(dependencies), dependencies),
        ),
    )
    graph.add_node(
        "EntityExpertNode",
        cast(
            Any, _node("EntityExpertNode", _entity_expert(dependencies), dependencies)
        ),
    )
    graph.add_node(
        "EventRuleExpertNode",
        cast(
            Any,
            _node(
                "EventRuleExpertNode", _event_rule_expert(dependencies), dependencies
            ),
        ),
    )
    graph.add_node(
        "MergeExpertCandidatesNode",
        cast(
            Any,
            _node(
                "MergeExpertCandidatesNode", _merge_expert_candidates(), dependencies
            ),
        ),
    )
    graph.add_node(
        "NormalizeAndValidateNode",
        cast(
            Any,
            _node("NormalizeAndValidateNode", _normalize_and_validate(), dependencies),
        ),
    )
    graph.add_node(
        "RunInternalConflictCheckNode",
        cast(
            Any,
            _node(
                "RunInternalConflictCheckNode",
                _internal_conflict_check(),
                dependencies,
            ),
        ),
    )
    graph.add_node(
        "MatchExistingKnowledgeNode",
        cast(
            Any,
            _node(
                "MatchExistingKnowledgeNode",
                _match_existing(dependencies),
                dependencies,
            ),
        ),
    )
    graph.add_node(
        "SynthesizeCandidateSummariesNode",
        cast(
            Any,
            _node(
                "SynthesizeCandidateSummariesNode",
                _synthesize_candidate_summaries(dependencies),
                dependencies,
            ),
        ),
    )
    graph.add_node(
        "BuildReviewItemsNode",
        cast(Any, _node("BuildReviewItemsNode", _build_review_items(), dependencies)),
    )
    graph.add_node(
        "WriteIntermediateJsonNode",
        cast(
            Any,
            _node(
                "WriteIntermediateJsonNode",
                _write_intermediate_json(dependencies),
                dependencies,
            ),
        ),
    )

    graph.add_edge(START, "LoadChapterNode")
    graph.add_edge("LoadChapterNode", "SegmentChapterNode")
    graph.add_edge("SegmentChapterNode", "GeneralExtractionNode")
    graph.add_edge("GeneralExtractionNode", "MentionNormalizeNode")
    graph.add_edge("MentionNormalizeNode", "EntityAggregationNode")
    graph.add_edge("EntityAggregationNode", "CandidateQualityGateNode")
    graph.add_edge("CandidateQualityGateNode", "TypeDispatchNode")
    graph.add_edge("TypeDispatchNode", "CharacterExpertNode")
    graph.add_edge("TypeDispatchNode", "EntityExpertNode")
    graph.add_edge("TypeDispatchNode", "EventRuleExpertNode")
    graph.add_edge("CharacterExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("EntityExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("EventRuleExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("MergeExpertCandidatesNode", "NormalizeAndValidateNode")
    graph.add_edge("NormalizeAndValidateNode", "RunInternalConflictCheckNode")
    graph.add_edge("RunInternalConflictCheckNode", "MatchExistingKnowledgeNode")
    graph.add_edge("MatchExistingKnowledgeNode", "SynthesizeCandidateSummariesNode")
    graph.add_edge("SynthesizeCandidateSummariesNode", "BuildReviewItemsNode")
    graph.add_edge("BuildReviewItemsNode", "WriteIntermediateJsonNode")
    graph.add_edge("WriteIntermediateJsonNode", END)
    return graph.compile()


def build_knowledge_extraction_branch_graph(
    dependencies: KnowledgeExtractionDependencies,
) -> CompiledStateGraph:
    """Build one branch graph for batch extraction before final review generation."""
    graph = StateGraph(KnowledgeExtractionState)
    graph.add_node(
        "LoadChapterNode",
        cast(Any, _node("LoadChapterNode", _load_chapter(dependencies), dependencies)),
    )
    graph.add_node(
        "SegmentChapterNode",
        cast(Any, _node("SegmentChapterNode", _segment_chapter(), dependencies)),
    )
    graph.add_node(
        "GeneralExtractionNode",
        cast(
            Any,
            _node(
                "GeneralExtractionNode", _general_extraction(dependencies), dependencies
            ),
        ),
    )
    graph.add_node(
        "MentionNormalizeNode",
        cast(Any, _node("MentionNormalizeNode", _normalize_mentions(), dependencies)),
    )
    graph.add_node(
        "EntityAggregationNode",
        cast(Any, _node("EntityAggregationNode", _aggregate_entities(), dependencies)),
    )
    graph.add_node(
        "CandidateQualityGateNode",
        cast(
            Any,
            _node(
                "CandidateQualityGateNode",
                _candidate_quality_gate(dependencies),
                dependencies,
            ),
        ),
    )
    graph.add_node(
        "TypeDispatchNode",
        cast(Any, _node("TypeDispatchNode", _dispatch_entity_groups(), dependencies)),
    )
    graph.add_node(
        "CharacterExpertNode",
        cast(
            Any,
            _node("CharacterExpertNode", _character_expert(dependencies), dependencies),
        ),
    )
    graph.add_node(
        "EntityExpertNode",
        cast(
            Any, _node("EntityExpertNode", _entity_expert(dependencies), dependencies)
        ),
    )
    graph.add_node(
        "EventRuleExpertNode",
        cast(
            Any,
            _node(
                "EventRuleExpertNode", _event_rule_expert(dependencies), dependencies
            ),
        ),
    )
    graph.add_node(
        "MergeExpertCandidatesNode",
        cast(
            Any,
            _node(
                "MergeExpertCandidatesNode", _merge_expert_candidates(), dependencies
            ),
        ),
    )

    graph.add_edge(START, "LoadChapterNode")
    graph.add_edge("LoadChapterNode", "SegmentChapterNode")
    graph.add_edge("SegmentChapterNode", "GeneralExtractionNode")
    graph.add_edge("GeneralExtractionNode", "MentionNormalizeNode")
    graph.add_edge("MentionNormalizeNode", "EntityAggregationNode")
    graph.add_edge("EntityAggregationNode", "CandidateQualityGateNode")
    graph.add_edge("CandidateQualityGateNode", "TypeDispatchNode")
    graph.add_edge("TypeDispatchNode", "CharacterExpertNode")
    graph.add_edge("TypeDispatchNode", "EntityExpertNode")
    graph.add_edge("TypeDispatchNode", "EventRuleExpertNode")
    graph.add_edge("CharacterExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("EntityExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("EventRuleExpertNode", "MergeExpertCandidatesNode")
    graph.add_edge("MergeExpertCandidatesNode", END)
    return graph.compile()


def initial_knowledge_extraction_state(
    *,
    chapter_id: str,
    chapter_title: str = "",
    model_name: str | None = None,
    requested_model_name: str | None = None,
    model_id: str | None = None,
    model_display_name: str | None = None,
    upstream_model: str | None = None,
    wire_protocol: str | None = None,
    generation_model_identity: LLMModelIdentity | None = None,
    force: bool = False,
) -> KnowledgeExtractionState:
    """Create the initial graph state for one current-chapter run."""
    now = _now_iso()
    return {
        "run_id": _new_run_id(now),
        "chapter_id": chapter_id,
        "model_name": model_name or "",
        "requested_model_name": requested_model_name,
        "model_id": model_id or model_name or "",
        "model_display_name": model_display_name or model_name or "",
        "upstream_model": upstream_model or model_name or "",
        "wire_protocol": wire_protocol or "openai_responses",
        "generation_model_identity": (
            generation_model_identity
            or LLMModelIdentity.unknown("运行未提供真实模型身份。")
        ).model_dump(mode="json"),
        "force": force,
        "started_at": now,
        "finished_at": None,
        "chapter_title": chapter_title,
        "markdown_text": "",
        "content_hash": "",
        "word_count": 0,
        "segments": [],
        "raw_mentions": [],
        "entity_groups": [],
        "ignored": [],
        "raw_candidates": [],
        "character_entity_groups": [],
        "entity_entity_groups": [],
        "event_rule_entity_groups": [],
        "character_typed_candidates": [],
        "entity_typed_candidates": [],
        "event_rule_typed_candidates": [],
        "typed_candidates": [],
        "review_items": [],
        "nodes": [],
        "llm_calls": [],
        "errors": [],
        "failed": False,
    }


def run_from_state(state: KnowledgeExtractionState) -> AgentRun:
    """Convert graph state into a persisted AgentRun model."""
    return run_snapshot_from_state(
        state,
        status=AgentRunStatus.FAILED
        if state.get("failed")
        else AgentRunStatus.COMPLETED,
        finished_at=state.get("finished_at") or _now_iso(),
    )


def run_snapshot_from_state(
    state: KnowledgeExtractionState,
    *,
    status: AgentRunStatus,
    finished_at: str | None = None,
) -> AgentRun:
    """Convert current graph state into a run snapshot for storage or streaming."""
    metrics_finished_at = finished_at or _now_iso()
    nodes = [AgentRunNode.model_validate(node) for node in state.get("nodes", [])]
    llm_calls = [
        AgentLLMCall.model_validate(call) for call in state.get("llm_calls", [])
    ]
    review_items = [
        AgentReviewItem.model_validate(item) for item in state.get("review_items", [])
    ]
    graph_nodes = [
        AgentRunGraphNode.model_validate(item)
        for item in state.get("graph_nodes", KNOWLEDGE_EXTRACTION_GRAPH_NODES)
    ]
    graph_edges = [
        AgentRunGraphEdge.model_validate(item)
        for item in state.get("graph_edges", KNOWLEDGE_EXTRACTION_GRAPH_EDGES)
    ]
    batch_chapter_progress = [
        AgentBatchChapterProgress.model_validate(item)
        for item in state.get("batch_chapter_progress", [])
    ]
    raw_mentions = [
        AgentRawMention.model_validate(item) for item in state.get("raw_mentions", [])
    ]
    entity_groups = [
        AgentEntityGroup.model_validate(item) for item in state.get("entity_groups", [])
    ]
    ignored = [
        AgentIgnoredExtraction.model_validate(item) for item in state.get("ignored", [])
    ]
    metrics = _metrics(
        review_items=review_items,
        nodes=nodes,
        llm_calls=llm_calls,
        started_at=state["started_at"],
        finished_at=metrics_finished_at,
    )
    return AgentRun(
        run_id=state["run_id"],
        model_name=state.get("model_name", ""),
        requested_model_name=state.get("requested_model_name"),
        model_id=state.get("model_id", ""),
        model_display_name=state.get("model_display_name", ""),
        upstream_model=state.get("upstream_model", ""),
        wire_protocol=state.get("wire_protocol", ""),
        generation_model_identity=LLMModelIdentity.model_validate(
            state.get(
                "generation_model_identity",
                LLMModelIdentity.unknown("运行未提供真实模型身份。").model_dump(
                    mode="json"
                ),
            )
        ),
        status=status,
        scope=AgentRunScope(
            scope_type=state.get("scope_type", "chapter"),
            chapter_id=state.get("chapter_id", ""),
            chapter_title=state.get("chapter_title", ""),
            content_hash=state.get("content_hash", ""),
            chapter_ids=state.get("chapter_ids", []),
            chapter_titles=state.get("chapter_titles", []),
            chapter_content_hashes=(
                {state.get("chapter_id", ""): state.get("content_hash", "")}
                if state.get("chapter_id") and state.get("content_hash")
                else {}
            ),
        ),
        started_at=state["started_at"],
        finished_at=finished_at,
        nodes=nodes,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        batch_chapter_progress=batch_chapter_progress,
        max_concurrency=int(state.get("max_concurrency") or 1),
        current_concurrency=int(state.get("current_concurrency") or 0),
        total_chapter_count=int(state.get("total_chapter_count") or 0),
        completed_chapter_count=int(state.get("completed_chapter_count") or 0),
        failed_chapter_count=int(state.get("failed_chapter_count") or 0),
        llm_calls=llm_calls,
        raw_mentions=raw_mentions,
        entity_groups=entity_groups,
        raw_candidates=state.get("raw_candidates", []),
        typed_candidates=state.get("typed_candidates", []),
        review_items=review_items,
        ignored=ignored,
        metrics=metrics,
        errors=state.get("errors", []),
        prompt_version=KNOWLEDGE_EXTRACTION_PROMPT_VERSION,
    )


def _node(
    node_name: str,
    handler: Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]],
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        if state.get("failed") and node_name != "WriteIntermediateJsonNode":
            record = _node_record(
                node_name=node_name,
                status=AgentRunNodeStatus.SKIPPED,
                started_at=_now_iso(),
                output_summary="前序节点失败，已跳过。",
            )
            await _emit_node_finished(dependencies, state, record)
            return cast(KnowledgeExtractionState, {"nodes": [record]})
        started = _now_iso()
        timer = perf_counter()
        baselines = _additive_baselines(state)
        await _emit_node_started(dependencies, state, node_name, started)
        try:
            next_state = await handler(_state_working_copy(state))
        except Exception as caught:  # noqa: BLE001
            next_state = _state_working_copy(state)
            next_state["failed"] = True
            next_state.setdefault("errors", []).append(str(caught))
            record = _node_record(
                node_name=node_name,
                status=AgentRunNodeStatus.FAILED,
                started_at=started,
                duration_ms=_elapsed_ms(timer),
                error=str(caught),
            )
            next_state.setdefault("nodes", []).append(record)
            await _emit_node_finished(dependencies, next_state, record)
            return _state_delta(state, next_state, baselines)
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
        if node_name == "WriteIntermediateJsonNode":
            records = next_state.get("nodes", [])
            record = (
                records[-1]
                if records
                else _node_record(
                    node_name=node_name,
                    status=status,
                    started_at=started,
                    duration_ms=_elapsed_ms(timer),
                    input_summary=_node_input_summary(node_name, state),
                    output_summary=_node_output_summary(node_name, next_state),
                    error=node_error,
                )
            )
        else:
            record = _node_record(
                node_name=node_name,
                status=status,
                started_at=started,
                duration_ms=_elapsed_ms(timer),
                input_summary=_node_input_summary(node_name, state),
                output_summary=_node_output_summary(node_name, next_state),
                error=node_error,
            )
            next_state.setdefault("nodes", []).append(record)
        await _emit_node_finished(dependencies, next_state, record)
        return _state_delta(state, next_state, baselines)

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
        state["content_hash"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        state["word_count"] = len(re.findall(r"\S", markdown))
        return state

    return run


def _segment_chapter() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
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
        raw_mentions: list[dict[str, Any]] = []
        raw_candidates: list[dict[str, Any]] = []
        ignored: list[dict[str, Any]] = []
        for index, segment in enumerate(state.get("segments", []), start=1):
            prompt = _render_prompt(
                GENERAL_EXTRACTION_PROMPT,
                chapter_id=state["chapter_id"],
                chapter_title=_segment_title(state, index),
                chapter_text=segment,
                allowed_types=_ALLOWED_TYPE_LABEL,
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
            raw_mentions.extend(_raw_mentions_from_general_output(parsed, index))
            raw_candidates.extend(_raw_candidates_from_general_output(parsed))
            ignored.extend(_ignored_from_general_output(parsed, index))
        state["raw_mentions"] = raw_mentions
        state["raw_candidates"] = raw_candidates
        state["ignored"] = ignored
        return state

    return run


def _normalize_mentions() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        normalized: list[dict[str, Any]] = []
        ignored = list(state.get("ignored", []))
        markdown = state.get("markdown_text", "")
        for mention in state.get("raw_mentions", []):
            knowledge_type = str(mention.get("knowledge_type") or "")
            name = _first_non_empty(mention.get("name"))
            if knowledge_type not in _GENERAL_TYPE_KEYS.values() or not name:
                ignored.append(
                    {
                        "text": name,
                        "reason": "mention 缺少名称或类型不属于第一版范围。",
                        "segment_index": mention.get("segment_index"),
                    }
                )
                continue
            requested_evidence = [
                excerpt[:300]
                for excerpt in _list_strings(mention.get("evidence_excerpts"))
            ][:_MAX_MENTION_EVIDENCE_COUNT]
            evidence_excerpts = _grounded_evidence_excerpts(
                requested_evidence,
                markdown,
            )
            if not evidence_excerpts:
                ignored.append(
                    {
                        "text": name,
                        "reason": "mention 缺少可在正文精确定位的原文证据。",
                        "segment_index": mention.get("segment_index"),
                    }
                )
                continue
            normalized.append(
                {
                    "mention_id": _first_non_empty(
                        mention.get("mention_id"),
                        f"mention_{len(normalized) + 1:03d}",
                    ),
                    "name": name[:80],
                    "knowledge_type": knowledge_type,
                    "description": _first_non_empty(mention.get("description")),
                    "evidence_excerpts": evidence_excerpts,
                    "reason": _first_non_empty(mention.get("reason")),
                    "segment_index": int(mention.get("segment_index") or 1),
                }
            )
        state["raw_mentions"] = normalized
        state["ignored"] = ignored
        return state

    return run


def _aggregate_entities() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for mention in state.get("raw_mentions", []):
            knowledge_type = str(mention.get("knowledge_type") or "")
            canonical_name = _first_non_empty(mention.get("name"))
            normalized_name = _normalize_identity(canonical_name)
            if not normalized_name:
                continue
            key = (knowledge_type, normalized_name)
            if key not in groups:
                groups[key] = {
                    "entity_group_id": f"entity_group_{len(order) + 1:03d}",
                    "canonical_name": canonical_name,
                    "knowledge_type": knowledge_type,
                    "raw_names": [],
                    "mention_count": 0,
                    "evidence_excerpts": [],
                    "quality_decision": "pending",
                    "quality_reason": "",
                }
                order.append(key)
            group = groups[key]
            raw_names = group.setdefault("raw_names", [])
            if canonical_name not in raw_names:
                raw_names.append(canonical_name)
            group["mention_count"] = int(group.get("mention_count") or 0) + 1
            group["evidence_excerpts"] = _append_unique_strings(
                _list_strings(group.get("evidence_excerpts")),
                _list_strings(mention.get("evidence_excerpts")),
            )[:_MAX_GROUP_EVIDENCE_COUNT]
        state["entity_groups"] = [groups[key] for key in order]
        return state

    return run


def _candidate_quality_gate(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        gated: list[dict[str, Any]] = []
        for group in state.get("entity_groups", []):
            decision, reason = await _quality_decision(
                group,
                dependencies,
                run_id=state.get("run_id"),
            )
            gated_group = {
                **group,
                "quality_decision": decision,
                "quality_reason": reason,
            }
            gated.append(gated_group)
        state["entity_groups"] = gated
        state["raw_candidates"] = [
            _candidate_from_entity_group(group)
            for group in gated
            if group.get("quality_decision") == "accepted"
        ]
        return state

    return run


def _dispatch_entity_groups() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        accepted = [
            group
            for group in state.get("entity_groups", [])
            if group.get("quality_decision") == "accepted"
        ]
        state["character_entity_groups"] = [
            group for group in accepted if group.get("knowledge_type") == "character"
        ]
        state["entity_entity_groups"] = [
            group
            for group in accepted
            if group.get("knowledge_type") in _ENTITY_EXPERT_TYPES
        ]
        state["event_rule_entity_groups"] = [
            group
            for group in accepted
            if group.get("knowledge_type") in _EVENT_RULE_EXPERT_TYPES
        ]
        return state

    return run


def _character_expert(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        entity_groups = state.get("character_entity_groups", [])
        if not entity_groups:
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
            character_entity_groups=_json_dump(entity_groups),
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
            state["character_typed_candidates"] = _cards_with_type(cards, "character")
        return state

    return run


def _entity_expert(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        entity_groups = state.get("entity_entity_groups", [])
        if not entity_groups:
            return state
        retrieval = await dependencies.retrieval_service.retrieve(
            RetrievalRequest(
                mode=RetrievalMode.CATALOG,
                top_k=200,
                consumer=RetrievalConsumerContext(
                    consumer_type="knowledge_workflow",
                    run_id=state.get("run_id"),
                    stage="EntityExpertNode",
                ),
            )
        )
        active_index = [
            {
                "id": card.id,
                "type": card.type.value,
                "name": card.name,
                "aliases": card.aliases,
                "summary": card.summary,
            }
            for card in (item.knowledge_card for item in retrieval.items)
        ]
        entity_schemas = [
            knowledge_type_schema(knowledge_type).model_dump(mode="json")
            for knowledge_type in (
                StructuredKnowledgeType.LOCATION,
                StructuredKnowledgeType.FACTION,
                StructuredKnowledgeType.ITEM,
                StructuredKnowledgeType.REALM,
                StructuredKnowledgeType.TECHNIQUE,
            )
        ]
        prompt = _render_prompt(
            ENTITY_EXPERT_PROMPT,
            entity_schemas=_json_dump(entity_schemas),
            active_knowledge_index=_json_dump(active_index),
            chapter_id=state["chapter_id"],
            chapter_title=state.get("chapter_title", ""),
            entity_groups=_json_dump(entity_groups),
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
            ("realms", "realm"),
            ("techniques", "technique"),
            ("locations", "location"),
            ("factions", "faction"),
            ("items", "item"),
        ):
            cards = parsed.get(key) if isinstance(parsed, dict) else []
            if isinstance(cards, list):
                state.setdefault("entity_typed_candidates", []).extend(
                    _cards_with_type(cards, knowledge_type)
                )
        return state

    return run


def _event_rule_expert(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        entity_groups = state.get("event_rule_entity_groups", [])
        if not entity_groups:
            return state
        retrieval = await dependencies.retrieval_service.retrieve(
            RetrievalRequest(
                mode=RetrievalMode.CATALOG,
                top_k=200,
                consumer=RetrievalConsumerContext(
                    consumer_type="knowledge_workflow",
                    run_id=state.get("run_id"),
                    stage="EventRuleExpertNode",
                ),
            )
        )
        active_rule_index = [
            {
                "id": card.id,
                "name": card.name,
                "aliases": card.aliases,
                "summary": card.summary,
            }
            for card in (item.knowledge_card for item in retrieval.items)
            if card.type == StructuredKnowledgeType.RULE
        ]
        event_rule_schemas = [
            knowledge_type_schema(knowledge_type).model_dump(mode="json")
            for knowledge_type in (
                StructuredKnowledgeType.EVENT,
                StructuredKnowledgeType.RULE,
            )
        ]
        prompt = _render_prompt(
            EVENT_RULE_EXPERT_PROMPT,
            event_rule_schemas=_json_dump(event_rule_schemas),
            active_rule_index=_json_dump(active_rule_index),
            chapter_id=state["chapter_id"],
            chapter_title=state.get("chapter_title", ""),
            event_rule_entity_groups=_json_dump(entity_groups),
        )
        parsed = await _complete_json(
            state,
            dependencies,
            node_name="EventRuleExpertNode",
            prompt_version=EVENT_RULE_EXPERT_PROMPT_VERSION,
            prompt=prompt,
        )
        if parsed is None:
            state["failed"] = True
            return state
        for key, knowledge_type in (
            ("events", "event"),
            ("rules", "rule"),
        ):
            cards = parsed.get(key) if isinstance(parsed, dict) else []
            if isinstance(cards, list):
                state.setdefault("event_rule_typed_candidates", []).extend(
                    _cards_with_type(cards, knowledge_type)
                )
        return state

    return run


def _merge_expert_candidates() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        candidates = [
            *state.get("character_typed_candidates", []),
            *state.get("entity_typed_candidates", []),
            *state.get("event_rule_typed_candidates", []),
        ]
        state["typed_candidates"] = mark_cross_type_projection_conflicts(
            merge_overlapping_event_candidates(
                _ground_candidates_from_entity_groups(
                    state,
                    candidates,
                )
            )
        )
        return state

    return run


def _normalize_and_validate() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        normalized: list[dict[str, Any]] = []
        for candidate in state.get("typed_candidates", []):
            card = dict(candidate)
            validation_errors = _candidate_validation_errors(card)
            card["schema_validation"] = {
                "passed": not validation_errors,
                "errors": validation_errors,
            }
            card.setdefault("lifecycle", "confirmed")
            card.setdefault("source_origin", "agent_extract")
            normalized.append(card)
        state["typed_candidates"] = normalized
        return state

    return run


def _internal_conflict_check() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
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
        catalog = await dependencies.retrieval_service.retrieve(
            RetrievalRequest(
                mode=RetrievalMode.CATALOG,
                top_k=200,
                max_content_chars=50_000,
                consumer=RetrievalConsumerContext(
                    consumer_type="knowledge_workflow",
                    run_id=state.get("run_id"),
                    stage="MatchExistingKnowledgeCatalogNode",
                ),
            )
        )
        catalog_cards = [item.knowledge_card for item in catalog.items]
        catalog_identity_index = _build_card_identity_index(catalog_cards)
        for candidate in state.get("typed_candidates", []):
            try:
                knowledge_type = StructuredKnowledgeType(
                    str(candidate.get("type") or "")
                )
            except ValueError:
                continue
            candidate_name = str(candidate.get("name") or "").strip()
            if not candidate_name:
                continue
            retrieval = await dependencies.retrieval_service.retrieve(
                RetrievalRequest(
                    mode=RetrievalMode.IDENTITY,
                    identity=RetrievalIdentityQuery(
                        knowledge_type=knowledge_type,
                        name=candidate_name,
                        aliases=_list_strings(candidate.get("aliases")),
                    ),
                    consumer=RetrievalConsumerContext(
                        consumer_type="knowledge_workflow",
                        run_id=state.get("run_id"),
                        stage="MatchExistingKnowledgeNode",
                    ),
                )
            )
            matches = [item.knowledge_card for item in retrieval.items]
            if matches:
                _bind_candidate_to_existing_card(
                    candidate,
                    matches[0],
                    align_type=False,
                )
                continue

            cross_type_matches = _catalog_identity_matches(
                candidate,
                catalog_identity_index,
            )
            if len(cross_type_matches) == 1:
                _bind_candidate_to_existing_card(
                    candidate,
                    cross_type_matches[0],
                    align_type=cross_type_matches[0].type is not knowledge_type,
                )
                continue
            if len(cross_type_matches) > 1:
                candidate["internal_conflicts"] = _append_unique_strings(
                    _list_strings(candidate.get("internal_conflicts")),
                    ["候选名称或别名命中多张已有知识卡，无法自动确定归属。"],
                )
        state["typed_candidates"] = dedupe_candidates_by_target(
            state.get("typed_candidates", [])
        )
        return state

    return run


def _synthesize_candidate_summaries(
    dependencies: KnowledgeExtractionDependencies,
) -> Callable[[KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]]:
    async def run(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
        state["typed_candidates"] = await synthesize_candidate_summaries(
            state,
            dependencies,
            state.get("typed_candidates", []),
            include_new=False,
            node_name="SynthesizeCandidateSummariesNode",
        )
        return state

    return run


async def synthesize_candidate_summaries(
    state: KnowledgeExtractionState,
    dependencies: KnowledgeExtractionDependencies,
    candidates: list[dict[str, Any]],
    *,
    include_new: bool,
    node_name: str,
) -> list[dict[str, Any]]:
    """Rewrite summaries as fact snapshots and preserve auditable LLM calls."""
    selected = [
        candidate
        for candidate in candidates
        if include_new or str(candidate.get("target_card_id") or "").strip()
    ]
    if not selected:
        return candidates

    indexed = list(enumerate(selected, start=1))
    chunks = [indexed[index : index + 5] for index in range(0, len(indexed), 5)]
    semaphore = asyncio.Semaphore(5)

    async def synthesize_chunk(
        chunk: list[tuple[int, dict[str, Any]]],
    ) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
        chunk_state = cast(KnowledgeExtractionState, dict(state))
        chunk_state["llm_calls"] = []
        chunk_state["errors"] = []
        prompt_candidates: list[dict[str, Any]] = []
        for candidate_index, candidate in chunk:
            existing = candidate.get("_existing_card")
            existing_card = existing if isinstance(existing, dict) else {}
            prompt_candidates.append(
                {
                    "candidate_id": f"summary_candidate_{candidate_index:03d}",
                    "knowledge_type": str(candidate.get("type") or ""),
                    "name": str(candidate.get("name") or ""),
                    "old_summary": str(existing_card.get("summary") or ""),
                    "current_candidate_summary": str(candidate.get("summary") or ""),
                    "new_evidence": _list_strings(candidate.get("evidence_excerpts")),
                    "source_chapters": _list_strings(candidate.get("chapter_titles"))
                    or _list_strings(candidate.get("chapter_ids")),
                    "source_note": str(candidate.get("source_note") or ""),
                }
            )
        prompt = _render_prompt(
            SUMMARY_SYNTHESIS_PROMPT,
            candidates_json=_json_dump(prompt_candidates),
        )
        async with semaphore:
            payload = await _complete_json(
                chunk_state,
                dependencies,
                node_name=node_name,
                prompt_version=SUMMARY_SYNTHESIS_PROMPT_VERSION,
                prompt=prompt,
            )
        summaries: dict[str, str] = {}
        raw_summaries = (
            payload.get("summaries")
            if isinstance(payload, dict) and set(payload) == {"summaries"}
            else None
        )
        if isinstance(raw_summaries, list):
            for item in raw_summaries:
                if not isinstance(item, dict) or not {
                    "candidate_id",
                    "summary",
                }.issubset(item):
                    continue
                candidate_id = str(item.get("candidate_id") or "").strip()
                summary = _normalize_synthesized_summary(item.get("summary"))
                if candidate_id and summary:
                    summaries[candidate_id] = summary
        return (
            summaries,
            chunk_state.get("llm_calls", []),
            chunk_state.get("errors", []),
        )

    results = await asyncio.gather(*(synthesize_chunk(chunk) for chunk in chunks))
    synthesized: dict[str, str] = {}
    for summaries, llm_calls, errors in results:
        synthesized.update(summaries)
        state.setdefault("llm_calls", []).extend(llm_calls)
        state.setdefault("errors", []).extend(errors)

    for candidate_index, candidate in indexed:
        candidate_id = f"summary_candidate_{candidate_index:03d}"
        existing = candidate.get("_existing_card")
        existing_card = existing if isinstance(existing, dict) else {}
        fallback = str(existing_card.get("summary") or candidate.get("summary") or "")
        summary = synthesized.get(candidate_id)
        if summary:
            candidate["summary"] = summary
            candidate.pop("_summary_synthesis_error", None)
        else:
            candidate["summary"] = fallback
            candidate["_summary_synthesis_error"] = "摘要综合失败，请编辑摘要后再确认。"
        validation_errors = _candidate_validation_errors(candidate)
        candidate["schema_validation"] = {
            "passed": not validation_errors,
            "errors": validation_errors,
        }
    return candidates


def _normalize_synthesized_summary(value: object) -> str:
    summary = " ".join(str(value or "").split()).strip()
    if not summary:
        return ""
    sentences = re.split(r"(?<=[。！？!?])", summary)
    seen: set[str] = set()
    result: list[str] = []
    for sentence in sentences:
        cleaned = sentence.strip()
        normalized = re.sub(r"[\s，。；：、！？!?]", "", cleaned).casefold()
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return "".join(result)


def _build_review_items() -> Callable[
    [KnowledgeExtractionState], Awaitable[KnowledgeExtractionState]
]:
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
                    "suggested_card": _candidate_card_with_occurrence_count(
                        candidate, state.get("chapter_id")
                    ),
                    "appearance_chapter_ids": _list_strings(
                        candidate.get("chapter_ids")
                    )
                    or _list_strings([state.get("chapter_id")]),
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
        finished_at = _now_iso()
        state["finished_at"] = finished_at
        state = _record_node(
            state,
            node_name="WriteIntermediateJsonNode",
            status=AgentRunNodeStatus.SUCCESS,
            started_at=finished_at,
            input_summary=f"{len(state.get('review_items', []))} 个审核项。",
            output_summary="已写入 JSON 中间态。",
        )
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
    current_prompt = prompt
    current_prompt_version = prompt_version
    last_raw_response = ""
    last_parse_error: Exception | None = None

    for attempt_index in range(_JSON_REPAIR_MAX_RETRIES + 1):
        started_at = _now_iso()
        timer = perf_counter()
        raw_response = ""
        parsed: dict[str, Any] = {}
        call_error: str | None = None
        llm_response: LLMResponse | None = None

        try:
            response = await dependencies.llm.complete(
                LLMRequest(
                    model_id=state.get("model_id") or state.get("model_name") or "",
                    messages=(
                        LLMMessage(
                            role="system",
                            content=(
                                "你是太初知识沉淀工作流节点，必须严格返回合法 JSON。"
                            ),
                        ),
                        LLMMessage(role="user", content=current_prompt),
                    ),
                    task_type="knowledge_extraction",
                    task_name=_node_label(node_name),
                    run_id=state.get("run_id"),
                    chapter_ids=tuple(_list_strings(state.get("chapter_ids")))
                    or (state.get("chapter_id", ""),),
                    response_mode="json",
                    max_output_tokens=_KNOWLEDGE_EXTRACTION_MAX_OUTPUT_TOKENS,
                    feature="知识沉淀",
                )
            )
            llm_response = response if isinstance(response, LLMResponse) else None
            raw_response = response_text(response)
            parsed_value = json.loads(raw_response)
            if not isinstance(parsed_value, dict):
                raise ValueError("LLM 响应 JSON 顶层必须是对象。")
            parsed = parsed_value
        except (json.JSONDecodeError, ValueError) as caught:
            last_raw_response = raw_response
            last_parse_error = caught
            call_error = f"{node_name} 的 LLM 响应不是有效 JSON：{caught}"
        except Exception as caught:  # noqa: BLE001
            call_error = f"{node_name} 的 LLM 调用失败：{caught}"
            await _record_llm_completion(
                state,
                dependencies,
                node_name=node_name,
                prompt_version=current_prompt_version,
                prompt=current_prompt,
                raw_response=raw_response,
                parsed=parsed,
                started_at=started_at,
                duration_ms=_elapsed_ms(timer),
                error=call_error,
                response=llm_response,
            )
            state.setdefault("errors", []).append(call_error)
            return None

        await _record_llm_completion(
            state,
            dependencies,
            node_name=node_name,
            prompt_version=current_prompt_version,
            prompt=current_prompt,
            raw_response=raw_response,
            parsed=parsed,
            started_at=started_at,
            duration_ms=_elapsed_ms(timer),
            error=call_error,
            response=llm_response,
        )

        if call_error is None:
            return parsed

        if attempt_index < _JSON_REPAIR_MAX_RETRIES:
            current_prompt = _json_repair_prompt(
                node_name=node_name,
                parse_error=str(last_parse_error),
                raw_response=last_raw_response,
            )
            current_prompt_version = f"{prompt_version}_json_repair_v1"
            continue

        final_error = (
            f"{node_name} 的 LLM 响应不是有效 JSON，"
            f"已重试 {_JSON_REPAIR_MAX_RETRIES} 次：{last_parse_error}"
        )
        state.setdefault("errors", []).append(final_error)
        return None

    return None


async def _record_llm_completion(
    state: KnowledgeExtractionState,
    dependencies: KnowledgeExtractionDependencies,
    *,
    node_name: str,
    prompt_version: str,
    prompt: str,
    raw_response: str,
    parsed: dict[str, Any],
    started_at: str,
    duration_ms: int,
    error: str | None,
    response: LLMResponse | None = None,
) -> None:
    usage = response.usage if response is not None else None
    cost = response.cost if response is not None else None
    call = {
        "call_id": (
            response.call_id
            if response is not None and response.call_id
            else f"llm_call_{node_name}_{uuid4().hex[:8]}"
        ),
        "node_name": node_name,
        "model_name": state.get("model_display_name")
        or state.get("model_name")
        or "默认模型",
        "model_id": state.get("model_id") or state.get("model_name") or "",
        "model_display_name": state.get("model_display_name")
        or state.get("model_name")
        or "",
        "upstream_model": state.get("upstream_model") or state.get("model_name") or "",
        "wire_protocol": state.get("wire_protocol") or "openai_responses",
        "prompt_version": prompt_version,
        "input_prompt": prompt,
        "raw_response": raw_response,
        "parsed_output": parsed,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "duration_ms": duration_ms,
        "input_tokens": usage.input_tokens if usage else None,
        "cached_input_tokens": usage.cached_input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "reasoning_tokens": usage.reasoning_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "cost_amount": cost.amount if cost else None,
        "cost_currency": cost.currency if cost else "CNY",
        "cost_kind": cost.kind if cost else "unavailable",
        "provider_request_id": response.provider_request_id if response else None,
        "error": error,
    }
    state.setdefault("llm_calls", []).append(call)
    await _emit_event(
        dependencies,
        {
            "event_type": "llm_call_finished",
            "run_id": state.get("run_id", ""),
            "message": f"模型调用完成：{_node_label(node_name)}。",
            "llm_call": call,
        },
    )


def _json_repair_prompt(
    *,
    node_name: str,
    parse_error: str,
    raw_response: str,
) -> str:
    return (
        "你是严格的 JSON 修复器。\n"
        f"节点：{node_name}\n"
        f"解析错误：{parse_error}\n\n"
        "任务：只把下面的模型输出修复为合法 JSON。\n"
        "硬规则：\n"
        "1. 不允许改写字段名、字段含义、事实内容、数组顺序或对象结构。\n"
        "2. 只修复 JSON 语法问题，例如中文弯引号、缺失英文双引号、非法换行、尾随逗号。\n"
        "3. 输出必须是 JSON 对象，不要输出解释、Markdown 或代码块。\n\n"
        "待修复输出：\n"
        f"{raw_response}"
    )


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
            candidate.setdefault(
                "name", _first_non_empty(item.get("name"), item.get("title"))
            )
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


def _raw_mentions_from_general_output(
    output: dict[str, Any],
    segment_index: int,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    raw_mentions = output.get("mentions")
    if isinstance(raw_mentions, list):
        for item in raw_mentions:
            if isinstance(item, dict):
                mention = _raw_mention_from_item(
                    item,
                    segment_index=segment_index,
                    index=len(mentions) + 1,
                )
                if mention is not None:
                    mentions.append(mention)
        return mentions

    for key, knowledge_type in _GENERAL_TYPE_KEYS.items():
        values = output.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload["knowledge_type"] = knowledge_type
            mention = _raw_mention_from_item(
                payload,
                segment_index=segment_index,
                index=len(mentions) + 1,
            )
            if mention is not None:
                mentions.append(mention)
    return mentions


def _raw_mention_from_item(
    item: dict[str, Any],
    *,
    segment_index: int,
    index: int,
) -> dict[str, Any] | None:
    knowledge_type = str(item.get("knowledge_type") or item.get("type") or "")
    if knowledge_type not in _GENERAL_TYPE_KEYS.values():
        return None
    name = _first_non_empty(item.get("name"), item.get("title"), item.get("text"))
    if not name:
        return None
    return {
        "mention_id": f"mention_{segment_index:03d}_{index:03d}",
        "name": name,
        "knowledge_type": knowledge_type,
        "description": _first_non_empty(
            item.get("description"),
            item.get("summary"),
            item.get("source_excerpt"),
        ),
        "evidence_excerpts": _evidence_excerpts_from_item(item),
        "reason": _first_non_empty(item.get("reason"), item.get("match_reason")),
        "segment_index": segment_index,
    }


def _ignored_from_general_output(
    output: dict[str, Any],
    segment_index: int,
) -> list[dict[str, Any]]:
    ignored: list[dict[str, Any]] = []
    values = output.get("ignored")
    if not isinstance(values, list):
        return ignored
    for item in values:
        if isinstance(item, str):
            text = item.strip()
            reason = ""
        elif isinstance(item, dict):
            text = _first_non_empty(
                item.get("text"), item.get("name"), item.get("title")
            )
            reason = _first_non_empty(item.get("reason"), item.get("description"))
        else:
            continue
        if text or reason:
            ignored.append(
                {
                    "text": text,
                    "reason": reason,
                    "segment_index": segment_index,
                }
            )
    return ignored


async def _quality_decision(
    group: dict[str, Any],
    dependencies: KnowledgeExtractionDependencies,
    *,
    run_id: str | None,
) -> tuple[str, str]:
    knowledge_type = str(group.get("knowledge_type") or "")
    name = _first_non_empty(group.get("canonical_name"))
    mention_count = int(group.get("mention_count") or 0)
    evidence_excerpts = _list_strings(group.get("evidence_excerpts"))
    if knowledge_type not in _GENERAL_TYPE_KEYS.values():
        return "rejected", "知识类型不属于第一版范围。"
    if not name:
        return "rejected", "缺少稳定名称。"
    if not evidence_excerpts:
        return "rejected", "缺少可回放的原文证据。"
    retrieval = await dependencies.retrieval_service.retrieve(
        RetrievalRequest(
            mode=RetrievalMode.IDENTITY,
            identity=RetrievalIdentityQuery(
                knowledge_type=StructuredKnowledgeType(knowledge_type),
                name=name,
                aliases=_list_strings(group.get("raw_names")),
            ),
            consumer=RetrievalConsumerContext(
                consumer_type="knowledge_workflow",
                run_id=run_id,
                stage="CandidateQualityGateNode",
            ),
        )
    )
    active_matches = [item.knowledge_card for item in retrieval.items]
    if active_matches:
        return "accepted", "命中已有有效知识卡，可作为更新候选。"
    if knowledge_type == "character":
        return _character_quality_decision(name, mention_count, evidence_excerpts)
    if knowledge_type == "location":
        return _location_quality_decision(name)
    if knowledge_type == "faction":
        return _faction_quality_decision(name)
    if knowledge_type == "item":
        return _item_quality_decision(name, evidence_excerpts)
    if knowledge_type == "realm":
        return _realm_quality_decision(name)
    if knowledge_type == "technique":
        return _technique_quality_decision(name, evidence_excerpts)
    if knowledge_type == "event":
        return _event_quality_decision(name, evidence_excerpts)
    if knowledge_type == "rule":
        return _rule_quality_decision(name, evidence_excerpts)
    return "rejected", "知识类型不属于第一版范围。"


def _character_quality_decision(
    name: str,
    mention_count: int,
    evidence_excerpts: list[str],
) -> tuple[str, str]:
    normalized = _normalize_identity(name)
    if normalized in {_normalize_identity(value) for value in _REJECT_CHARACTER_NAMES}:
        return "rejected", "临时称呼、相对指代或普通人群泛称。"
    if name.endswith(("们", "众")):
        return "rejected", "普通人群泛称。"
    if name in {"镇长", "村长", "族长", "掌柜", "师父"}:
        return "accepted", "明确称号或职务，并可进入作者审核。"
    if mention_count >= 2:
        return "accepted", "本章出现多次，可进入作者审核。"
    if 2 <= len(name) <= 5 and not any(
        marker in name for marker in ("一个", "某个", "那")
    ):
        return "accepted", "具备稳定专名特征。"
    if any(name in excerpt for excerpt in evidence_excerpts):
        return "accepted", "具备原文直接命名证据。"
    return "rejected", "缺少稳定专名、明确职务或独立行为链。"


def _location_quality_decision(name: str) -> tuple[str, str]:
    normalized_rejects = {
        _normalize_identity(value) for value in _REJECT_LOCATION_NAMES
    }
    if _normalize_identity(name) in normalized_rejects:
        return "rejected", "普通功能空间、泛称地点或单次环境描写。"
    if any(marker in name for marker in _LOCATION_NAME_MARKERS) and len(name) >= 3:
        return "accepted", "具备可复用地点名称或空间属性。"
    return "rejected", "缺少稳定专有地点名或可复用空间属性。"


def _faction_quality_decision(name: str) -> tuple[str, str]:
    if name.endswith("们") or "神仙们" in name:
        return "rejected", "普通人群泛称或缺少稳定组织名。"
    if any(marker in name for marker in _FACTION_NAME_MARKERS) and len(name) >= 2:
        return "accepted", "具备稳定组织名称或明确组织身份。"
    return "rejected", "缺少稳定组织名称。"


def _item_quality_decision(
    name: str,
    evidence_excerpts: list[str],
) -> tuple[str, str]:
    if _normalize_identity(name) in {
        _normalize_identity(value) for value in _REJECT_ITEM_NAMES
    }:
        return "rejected", "普通消耗品、银两、衣物或器具。"
    if any(marker in name for marker in _SPECIAL_ITEM_MARKERS) and len(name) >= 2:
        return "accepted", "有明确名称且具备设定价值或可追踪属性。"
    if _named_evidence_has_marker(name, evidence_excerpts, _ITEM_FUNCTION_MARKERS):
        return "accepted", "具备原文直接命名及可复用功能或属性证据。"
    return "rejected", "缺少设定价值、稀有性或可追踪归属。"


def _realm_quality_decision(name: str) -> tuple[str, str]:
    if any(marker in name for marker in _REALM_NAME_MARKERS) and len(name) >= 2:
        return "accepted", "具备明确境界、阶段或修炼层次名称。"
    return "rejected", "缺少稳定境界或修炼阶段名称。"


def _technique_quality_decision(
    name: str,
    evidence_excerpts: list[str],
) -> tuple[str, str]:
    if any(marker in name for marker in _TECHNIQUE_NAME_MARKERS) and len(name) >= 2:
        return "accepted", "具备明确功法、术法或神通名称。"
    if _named_evidence_has_marker(
        name,
        evidence_excerpts,
        _TECHNIQUE_FUNCTION_MARKERS,
    ):
        return "accepted", "具备原文直接命名及可复用修炼或施展机制。"
    return "rejected", "缺少稳定功法、术法或可复用设定名称。"


def _named_evidence_has_marker(
    name: str,
    evidence_excerpts: list[str],
    markers: tuple[str, ...],
) -> bool:
    return len(name) >= 2 and any(
        name in excerpt and any(marker in excerpt for marker in markers)
        for excerpt in evidence_excerpts
    )


def _event_quality_decision(
    name: str,
    evidence_excerpts: list[str],
) -> tuple[str, str]:
    if len(name) >= 4 and evidence_excerpts:
        return "accepted", "具备明确剧情事件或状态变化证据。"
    return "rejected", "缺少明确事件名称或可回放事件证据。"


def _rule_quality_decision(
    name: str,
    evidence_excerpts: list[str],
) -> tuple[str, str]:
    if len(name) >= 4 and evidence_excerpts:
        return "accepted", "具备明确规则、禁制、约束或因果条件证据。"
    return "rejected", "缺少稳定规则名称或明确规则证据。"


def _candidate_from_entity_group(group: dict[str, Any]) -> dict[str, Any]:
    evidence_excerpts = _list_strings(group.get("evidence_excerpts"))
    return {
        "entity_group_id": group.get("entity_group_id"),
        "name": _first_non_empty(group.get("canonical_name")),
        "aliases": [
            name
            for name in _list_strings(group.get("raw_names"))
            if name != group.get("canonical_name")
        ],
        "knowledge_type": str(group.get("knowledge_type") or ""),
        "source_excerpt": evidence_excerpts[0] if evidence_excerpts else "",
        "evidence_excerpts": evidence_excerpts,
        "quality_decision": group.get("quality_decision"),
        "quality_reason": group.get("quality_reason"),
    }


def _cards_with_type(cards: list[Any], knowledge_type: str) -> list[dict[str, Any]]:
    typed: list[dict[str, Any]] = []
    for card in cards:
        if isinstance(card, dict):
            payload = dict(card)
            payload["type"] = knowledge_type
            payload.setdefault("lifecycle", "confirmed")
            payload.setdefault("source_origin", "agent_extract")
            typed.append(payload)
    return typed


def _ground_candidates_from_entity_groups(
    state: KnowledgeExtractionState,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace model-written evidence with exact quotes from accepted groups."""
    markdown = state.get("markdown_text", "")
    evidence_by_group = {
        str(group.get("entity_group_id") or ""): _grounded_evidence_excerpts(
            _list_strings(group.get("evidence_excerpts")),
            markdown,
        )
        for group in state.get("entity_groups", [])
        if str(group.get("entity_group_id") or "").strip()
    }
    grounded: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = dict(candidate)
        group_id = str(payload.get("entity_group_id") or "")
        evidence = evidence_by_group.get(group_id)
        if evidence is None:
            evidence = _grounded_evidence_excerpts(
                _list_strings(payload.get("evidence_excerpts")),
                markdown,
            )
        payload["evidence_excerpts"] = evidence
        payload["evidence_excerpt"] = evidence[0][:300] if evidence else ""
        if evidence:
            chapter_title = str(
                state.get("chapter_title") or state.get("chapter_id") or "当前章节"
            )
            quoted = "；".join(f"“{excerpt}”" for excerpt in evidence[:3])
            payload["source_note"] = f"{chapter_title}\n关键原文：{quoted}"
        grounded.append(payload)
    return grounded


def _grounded_evidence_excerpts(values: list[str], markdown: str) -> list[str]:
    if not markdown:
        return []
    return _append_unique_strings(
        [],
        [
            value.strip()
            for value in values
            if value.strip() and value.strip() in markdown
        ],
    )


def merge_overlapping_event_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge high-confidence duplicate event candidates from the same chapter."""
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = dict(candidate)
        if str(payload.get("type") or "") != StructuredKnowledgeType.EVENT.value:
            merged.append(payload)
            continue

        duplicate_index = next(
            (
                index
                for index, current in enumerate(merged)
                if str(current.get("type") or "") == StructuredKnowledgeType.EVENT.value
                and _event_candidates_overlap(current, payload)
            ),
            None,
        )
        if duplicate_index is None:
            merged.append(payload)
            continue

        current = merged[duplicate_index]
        if _event_candidate_richness(payload) > _event_candidate_richness(current):
            primary, secondary = payload, current
        else:
            primary, secondary = current, payload
        merged[duplicate_index] = _merge_event_candidate_pair(primary, secondary)
    return merged


def _event_candidates_overlap(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    left_chapters = _candidate_chapter_ids(left)
    right_chapters = _candidate_chapter_ids(right)
    if left_chapters and right_chapters and left_chapters.isdisjoint(right_chapters):
        return False

    left_name = _normalize_comparison_text(left.get("name"))
    right_name = _normalize_comparison_text(right.get("name"))
    if not left_name or not right_name:
        return False
    if _longest_common_substring_length(left_name, right_name) < 3:
        return False

    left_evidence = _normalized_evidence(left)
    right_evidence = _normalized_evidence(right)
    if not left_evidence or not right_evidence:
        return False
    return _evidence_set_is_contained(left_evidence, right_evidence) or (
        _evidence_set_is_contained(right_evidence, left_evidence)
    )


def _candidate_chapter_ids(candidate: dict[str, Any]) -> set[str]:
    chapter_ids = set(_list_strings(candidate.get("chapter_ids")))
    chapter_id = str(candidate.get("chapter_id") or "").strip()
    if chapter_id:
        chapter_ids.add(chapter_id)
    return chapter_ids


def _normalized_evidence(candidate: dict[str, Any]) -> list[str]:
    return [
        normalized
        for value in _list_strings(candidate.get("evidence_excerpts"))
        if len(normalized := _normalize_comparison_text(value)) >= 10
    ]


def _evidence_set_is_contained(
    needles: list[str],
    haystacks: list[str],
) -> bool:
    return bool(needles) and all(
        any(needle in haystack for haystack in haystacks) for needle in needles
    )


def _event_candidate_richness(candidate: dict[str, Any]) -> tuple[int, int, int]:
    evidence = _list_strings(candidate.get("evidence_excerpts"))
    narrative_length = len(str(candidate.get("summary") or "")) + len(
        str(candidate.get("description") or "")
    )
    return len(evidence), sum(len(value) for value in evidence), narrative_length


def _merge_event_candidate_pair(
    primary: dict[str, Any],
    secondary: dict[str, Any],
) -> dict[str, Any]:
    result = dict(primary)
    primary_name = str(result.get("name") or "").strip()
    secondary_name = str(secondary.get("name") or "").strip()
    aliases = _append_unique_strings(
        _list_strings(result.get("aliases")),
        [secondary_name, *_list_strings(secondary.get("aliases"))],
    )
    result["aliases"] = [
        alias
        for alias in aliases
        if _normalize_identity(alias) != _normalize_identity(primary_name)
    ]
    evidence = _append_unique_strings(
        _list_strings(result.get("evidence_excerpts")),
        _list_strings(secondary.get("evidence_excerpts")),
    )
    result["evidence_excerpts"] = evidence[:20]
    if evidence:
        result["evidence_excerpt"] = evidence[0][:300]
    result["source_note"] = _dedupe_text_blocks(
        [
            str(result.get("source_note") or ""),
            str(secondary.get("source_note") or ""),
        ]
    )
    for key in ("summary", "description"):
        if len(str(secondary.get(key) or "")) > len(str(result.get(key) or "")):
            result[key] = secondary.get(key)
    for key in ("chapter_ids", "chapter_titles", "internal_conflicts"):
        combined = _append_unique_strings(
            _list_strings(result.get(key)),
            _list_strings(secondary.get(key)),
        )
        if combined:
            result[key] = combined
    counts = [
        value
        for value in (
            result.get("appearance_chapter_count"),
            secondary.get("appearance_chapter_count"),
        )
        if isinstance(value, int)
    ]
    if counts:
        result["appearance_chapter_count"] = max(counts)
    if not str(result.get("chapter_id") or "").strip():
        result["chapter_id"] = secondary.get("chapter_id")
    return result


def _normalize_comparison_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_character in left:
        current = [0]
        for index, right_character in enumerate(right, start=1):
            length = previous[index - 1] + 1 if left_character == right_character else 0
            current.append(length)
            longest = max(longest, length)
        previous = current
    return longest


def _build_card_identity_index(
    cards: list[StructuredKnowledgeCard],
) -> dict[str, list[StructuredKnowledgeCard]]:
    index: dict[str, list[StructuredKnowledgeCard]] = {}
    for card in cards:
        terms = [card.name, *card.aliases]
        for term in terms:
            normalized = _normalize_identity(term)
            if not normalized:
                continue
            indexed_cards = index.setdefault(normalized, [])
            if all(existing.id != card.id for existing in indexed_cards):
                indexed_cards.append(card)
    return index


def _catalog_identity_matches(
    candidate: dict[str, Any],
    identity_index: dict[str, list[StructuredKnowledgeCard]],
) -> list[StructuredKnowledgeCard]:
    matches: dict[str, StructuredKnowledgeCard] = {}
    for term in [
        str(candidate.get("name") or ""),
        *_list_strings(candidate.get("aliases")),
    ]:
        normalized = _normalize_identity(term)
        for card in identity_index.get(normalized, []):
            matches[card.id] = card
    return list(matches.values())


def _bind_candidate_to_existing_card(
    candidate: dict[str, Any],
    match: StructuredKnowledgeCard,
    *,
    align_type: bool,
) -> None:
    original_name = str(candidate.get("name") or "").strip()
    try:
        original_type = StructuredKnowledgeType(str(candidate.get("type") or ""))
    except ValueError:
        original_type = None

    if align_type and original_type is not None:
        stale_fields = type_specific_field_keys(
            original_type
        ) - type_specific_field_keys(match.type)
        for field_key in stale_fields:
            candidate.pop(field_key, None)
        candidate["type"] = match.type.value
        candidate["name"] = match.name
        candidate["aliases"] = [
            alias
            for alias in _append_unique_strings(
                _list_strings(candidate.get("aliases")),
                [original_name],
            )
            if _normalize_identity(alias) != _normalize_identity(match.name)
        ]

    candidate["target_card_id"] = match.id
    candidate["matched_card_name"] = match.name
    candidate["match_reason"] = (
        "候选名称或别名唯一命中已有知识卡，已按已有卡类型对齐。"
        if align_type
        else "命中已有有效知识卡的名称或别名。"
    )
    candidate["_existing_card"] = match.model_dump(mode="json")
    conflicts = _external_conflicts(candidate, match)
    if conflicts:
        candidate["external_conflicts"] = conflicts
    else:
        candidate.pop("external_conflicts", None)
    validation_errors = _candidate_validation_errors(candidate)
    candidate["schema_validation"] = {
        "passed": not validation_errors,
        "errors": validation_errors,
    }


def dedupe_candidates_by_target(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge candidates that resolve to one card or share an in-batch identity."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    passthrough: list[tuple[int, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        target_id = str(candidate.get("target_card_id") or "").strip()
        if not target_id:
            passthrough.append((index, candidate))
            continue
        if target_id not in groups:
            groups[target_id] = []
            order.append(target_id)
        groups[target_id].append(candidate)

    merged_positions: list[tuple[int, dict[str, Any]]] = list(passthrough)
    for target_id in order:
        group = groups[target_id]
        matched_name = str(group[0].get("matched_card_name") or "")
        primary = max(
            group,
            key=lambda item: int(
                bool(matched_name)
                and _normalize_identity(item.get("name"))
                == _normalize_identity(matched_name)
            ),
        )
        merged = dict(primary)
        aliases = _list_strings(merged.get("aliases"))
        chapter_ids = _list_strings(merged.get("chapter_ids"))
        chapter_titles = _list_strings(merged.get("chapter_titles"))
        evidence = _list_strings(merged.get("evidence_excerpts"))
        conflicts = _list_strings(merged.get("internal_conflicts"))
        source_notes = [str(merged.get("source_note") or "").strip()]
        for candidate in group:
            if candidate is primary:
                continue
            candidate_name = str(candidate.get("name") or "").strip()
            aliases = _append_unique_strings(
                aliases,
                [candidate_name, *_list_strings(candidate.get("aliases"))],
            )
            chapter_ids = _append_unique_strings(
                chapter_ids,
                _list_strings(candidate.get("chapter_ids")),
            )
            chapter_titles = _append_unique_strings(
                chapter_titles,
                _list_strings(candidate.get("chapter_titles")),
            )
            evidence = _append_unique_strings(
                evidence,
                _list_strings(candidate.get("evidence_excerpts")),
            )
            conflicts = _append_unique_strings(
                conflicts,
                _list_strings(candidate.get("internal_conflicts")),
            )
            source_notes.append(str(candidate.get("source_note") or "").strip())
        primary_name = str(merged.get("name") or "").strip()
        merged["aliases"] = [
            alias for alias in aliases if alias and alias != primary_name
        ]
        merged["chapter_ids"] = chapter_ids
        merged["chapter_titles"] = chapter_titles
        merged["evidence_excerpts"] = evidence[:20]
        if evidence:
            merged["evidence_excerpt"] = evidence[0][:300]
        merged["source_note"] = _dedupe_text_blocks(source_notes)
        if conflicts:
            merged["internal_conflicts"] = conflicts
        first_index = min(candidates.index(candidate) for candidate in group)
        merged_positions.append((first_index, merged))
    return _dedupe_unmatched_candidates_by_identity(
        [item for _, item in sorted(merged_positions, key=lambda pair: pair[0])]
    )


def _dedupe_unmatched_candidates_by_identity(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge same-type new candidates when a name is another candidate's alias."""
    grouped: list[tuple[set[str], list[dict[str, Any]]]] = []
    for candidate in candidates:
        if str(candidate.get("target_card_id") or "").strip():
            grouped.append((set(), [candidate]))
            continue
        identities = _candidate_identity_keys(candidate)
        if not identities:
            grouped.append((set(), [candidate]))
            continue
        knowledge_type = str(candidate.get("type") or "")
        matching_indexes = [
            index
            for index, (group_identities, group) in enumerate(grouped)
            if group_identities
            and str(group[0].get("type") or "") == knowledge_type
            and group_identities.intersection(identities)
        ]
        if not matching_indexes:
            grouped.append((set(identities), [candidate]))
            continue
        first_index = matching_indexes[0]
        group_identities, group = grouped[first_index]
        group_identities.update(identities)
        group.append(candidate)
        for index in reversed(matching_indexes[1:]):
            joined_identities, joined_group = grouped.pop(index)
            group_identities.update(joined_identities)
            group.extend(joined_group)

    merged: list[dict[str, Any]] = []
    for _, group in grouped:
        if len(group) == 1:
            merged.append(group[0])
            continue
        primary = max(
            group,
            key=lambda candidate: (
                len(_candidate_identity_keys(candidate)),
                len(_list_strings(candidate.get("evidence_excerpts"))),
            ),
        )
        combined = dict(primary)
        aliases = _list_strings(combined.get("aliases"))
        chapter_ids = _list_strings(combined.get("chapter_ids"))
        chapter_titles = _list_strings(combined.get("chapter_titles"))
        evidence = _list_strings(combined.get("evidence_excerpts"))
        conflicts = _list_strings(combined.get("internal_conflicts"))
        source_notes = [str(combined.get("source_note") or "").strip()]
        for candidate in group:
            if candidate is primary:
                continue
            aliases = _append_unique_strings(
                aliases,
                [
                    str(candidate.get("name") or "").strip(),
                    *_list_strings(candidate.get("aliases")),
                ],
            )
            chapter_ids = _append_unique_strings(
                chapter_ids,
                _list_strings(candidate.get("chapter_ids")),
            )
            chapter_titles = _append_unique_strings(
                chapter_titles,
                _list_strings(candidate.get("chapter_titles")),
            )
            evidence = _append_unique_strings(
                evidence,
                _list_strings(candidate.get("evidence_excerpts")),
            )
            conflicts = _append_unique_strings(
                conflicts,
                _list_strings(candidate.get("internal_conflicts")),
            )
            source_notes.append(str(candidate.get("source_note") or "").strip())
        primary_name = str(combined.get("name") or "").strip()
        combined["aliases"] = [
            alias for alias in aliases if alias and alias != primary_name
        ]
        combined["chapter_ids"] = chapter_ids
        combined["chapter_titles"] = chapter_titles
        combined["evidence_excerpts"] = evidence[:20]
        if evidence:
            combined["evidence_excerpt"] = evidence[0][:300]
        combined["source_note"] = _dedupe_text_blocks(source_notes)
        if conflicts:
            combined["internal_conflicts"] = conflicts
        merged.append(combined)
    return merged


def _candidate_identity_keys(candidate: dict[str, Any]) -> set[str]:
    return {
        identity
        for value in [candidate.get("name"), *_list_strings(candidate.get("aliases"))]
        if (identity := _normalize_identity(value))
    }


def mark_cross_type_projection_conflicts(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Require review when named objects are projected again as events or rules."""
    concrete_types = {"item", "technique"}
    projection_types = {"event", "rule"}
    for concrete in candidates:
        if str(concrete.get("type") or "") not in concrete_types:
            continue
        concrete_evidence = set(_list_strings(concrete.get("evidence_excerpts")))
        if not concrete_evidence:
            continue
        for projected in candidates:
            if str(projected.get("type") or "") not in projection_types:
                continue
            projected_evidence = set(_list_strings(projected.get("evidence_excerpts")))
            if not concrete_evidence.intersection(projected_evidence):
                continue
            concrete_name = _normalize_identity(concrete.get("name"))
            projected_name = _normalize_identity(projected.get("name"))
            if concrete_name and concrete_name not in projected_name:
                continue
            projected.setdefault("internal_conflicts", [])
            projected["internal_conflicts"] = _append_unique_strings(
                _list_strings(projected.get("internal_conflicts")),
                ["候选与具名物品或功法共享核心证据，请确认是否属于重复类型投影。"],
            )
    return candidates


def _dedupe_text_blocks(values: list[str]) -> str:
    blocks: list[str] = []
    seen: set[str] = set()
    for value in values:
        for block in re.split(r"(?:\r?\n)\s*(?:\r?\n)+", value.strip()):
            cleaned = block.strip()
            normalized = " ".join(cleaned.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            blocks.append(cleaned)
    return "\n\n".join(blocks)


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
        errors.append(
            "正文知识沉淀只允许角色、境界、功法、地点、势力、物品、规则、事件。"
        )
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
        "appearance_chapter_count",
        "lifecycle",
        "source_origin",
        "source_note",
        "entity_group_id",
        "evidence_excerpt",
        "evidence_excerpts",
        *type_specific_field_keys(knowledge_type),
        "schema_validation",
        "internal_conflicts",
        "external_conflicts",
        "target_card_id",
        "matched_card_name",
        "match_reason",
        "chapter_ids",
        "chapter_titles",
        "_existing_card",
        "_summary_synthesis_error",
    }
    unknown = set(card) - allowed_keys
    if unknown:
        errors.append(f"包含未知字段：{', '.join(sorted(unknown))}")
    synthesis_error = str(card.get("_summary_synthesis_error") or "").strip()
    if synthesis_error:
        errors.append(synthesis_error)
    return errors


def _external_conflicts(
    candidate: dict[str, Any],
    existing: StructuredKnowledgeCard,
) -> list[str]:
    conflicts: list[str] = []
    for key in _strict_conflict_fields(existing.type):
        value = candidate.get(key)
        current_value = getattr(existing, key, None)
        if (
            _is_non_empty(current_value)
            and _is_non_empty(value)
            and current_value != value
        ):
            conflicts.append(f"字段“{key}”与已有有效知识卡存在互斥事实。")
    return conflicts


def _strict_conflict_fields(knowledge_type: StructuredKnowledgeType) -> set[str]:
    if knowledge_type is StructuredKnowledgeType.CHARACTER:
        return {"death_chapter_id"}
    if knowledge_type is StructuredKnowledgeType.LOCATION:
        return {"controlling_faction_id"}
    if knowledge_type is StructuredKnowledgeType.ITEM:
        return {"current_holder_id"}
    return set()


def _candidate_action(
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> AgentReviewCandidateAction:
    if not validation.get("passed"):
        if candidate.get("_summary_synthesis_error"):
            return AgentReviewCandidateAction.CONFLICT
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
        "chapter_ids",
        "chapter_titles",
        "_existing_card",
        "_summary_synthesis_error",
    }
    return {key: value for key, value in candidate.items() if key not in excluded}


def _candidate_card_with_occurrence_count(
    candidate: dict[str, Any], chapter_id: object
) -> dict[str, Any]:
    card = _strip_internal_candidate_fields(candidate)
    if card.get("appearance_chapter_count") is None and str(chapter_id or "").strip():
        card["appearance_chapter_count"] = 1
    return card


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
            review_items, AgentReviewCandidateAction.CREATE_CARD
        ),
        update_card_count=_count_actions(
            review_items, AgentReviewCandidateAction.UPDATE_CARD
        ),
        conflict_count=_count_actions(
            review_items, AgentReviewCandidateAction.CONFLICT
        ),
        schema_passed_count=sum(
            1 for item in review_items if item.schema_validation.passed
        ),
        schema_failed_count=sum(
            1 for item in review_items if not item.schema_validation.passed
        ),
        confirmed_count=_count_status(
            review_items, AgentReviewCandidateStatus.CONFIRMED
        ),
        rejected_count=_count_status(review_items, AgentReviewCandidateStatus.REJECTED),
        pending_count=_count_status(review_items, AgentReviewCandidateStatus.PENDING),
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


_ADDITIVE_STATE_KEYS = {"nodes", "llm_calls", "errors"}


def _state_working_copy(state: KnowledgeExtractionState) -> KnowledgeExtractionState:
    copied: dict[str, Any] = {}
    for key, value in state.items():
        if isinstance(value, list):
            copied[key] = [
                dict(item) if isinstance(item, dict) else item for item in value
            ]
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return cast(KnowledgeExtractionState, copied)


def _additive_baselines(state: KnowledgeExtractionState) -> dict[str, int]:
    return {
        key: len(cast(list[Any], state.get(key, []))) for key in _ADDITIVE_STATE_KEYS
    }


def _state_delta(
    before: KnowledgeExtractionState,
    after: KnowledgeExtractionState,
    baselines: dict[str, int],
) -> KnowledgeExtractionState:
    delta: dict[str, Any] = {}
    for key, value in after.items():
        if key in _ADDITIVE_STATE_KEYS:
            appended = cast(list[Any], value)[baselines.get(key, 0) :]
            if appended:
                delta[key] = appended
            continue
        if before.get(key) != value:
            delta[key] = value
    return cast(KnowledgeExtractionState, delta)


async def _emit_node_started(
    dependencies: KnowledgeExtractionDependencies,
    state: KnowledgeExtractionState,
    node_name: str,
    started_at: str,
) -> None:
    await _emit_event(
        dependencies,
        {
            "event_type": "node_started",
            "run_id": state.get("run_id", ""),
            "message": f"开始执行：{_node_label(node_name)}。",
            "node": _node_record(
                node_name=node_name,
                status=AgentRunNodeStatus.RUNNING,
                started_at=started_at,
                input_summary=_node_input_summary(node_name, state),
            ),
        },
    )


async def _emit_node_finished(
    dependencies: KnowledgeExtractionDependencies,
    state: KnowledgeExtractionState,
    record: dict[str, Any],
) -> None:
    status = str(record.get("status") or "")
    label = _node_label(str(record.get("node_name") or ""))
    message = f"节点完成：{label}。" if status == "success" else f"节点状态：{label}。"
    await _emit_event(
        dependencies,
        {
            "event_type": "node_finished",
            "run_id": state.get("run_id", ""),
            "message": message,
            "node": record,
        },
    )


async def _emit_event(
    dependencies: KnowledgeExtractionDependencies,
    event: dict[str, Any],
) -> None:
    if dependencies.event_sink is None:
        return
    if "type" not in event and "event_type" in event:
        event = {"type": event["event_type"], **event}
    await dependencies.event_sink(event)


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
        _node_record(
            node_name=node_name,
            status=status,
            started_at=started_at,
            duration_ms=duration_ms,
            input_summary=input_summary,
            output_summary=output_summary,
            error=error,
        )
    )
    return state


def _node_record(
    *,
    node_name: str,
    status: AgentRunNodeStatus,
    started_at: str,
    duration_ms: int = 0,
    input_summary: str = "",
    output_summary: str = "",
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "status": status.value,
        "started_at": started_at,
        "finished_at": None if status is AgentRunNodeStatus.RUNNING else _now_iso(),
        "duration_ms": duration_ms,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "error": error,
    }


def _node_label(node_name: str) -> str:
    for node in KNOWLEDGE_EXTRACTION_GRAPH_NODES:
        if node["node_name"] == node_name:
            return node["label"]
    return node_name


def _node_input_summary(node_name: str, state: KnowledgeExtractionState) -> str:
    if node_name == "GeneralExtractionNode":
        return f"{len(state.get('segments', []))} 个章节片段。"
    if node_name == "MentionNormalizeNode":
        return f"{len(state.get('raw_mentions', []))} 个原始 mention。"
    if node_name == "EntityAggregationNode":
        return f"{len(state.get('raw_mentions', []))} 个规范 mention。"
    if node_name == "CandidateQualityGateNode":
        return f"{len(state.get('entity_groups', []))} 个实体聚合组。"
    if node_name == "TypeDispatchNode":
        return f"{len(_accepted_entity_groups(state))} 个通过质量闸门的实体组。"
    if node_name == "CharacterExpertNode":
        return f"{len(state.get('character_entity_groups', []))} 个角色实体组。"
    if node_name == "EntityExpertNode":
        return f"{len(state.get('entity_entity_groups', []))} 个实体设定组。"
    if node_name == "EventRuleExpertNode":
        return f"{len(state.get('event_rule_entity_groups', []))} 个事件规则组。"
    if node_name == "MergeExpertCandidatesNode":
        return (
            f"角色 {len(state.get('character_typed_candidates', []))} 个，"
            f"实体 {len(state.get('entity_typed_candidates', []))} 个，"
            f"事件规则 {len(state.get('event_rule_typed_candidates', []))} 个。"
        )
    return ""


def _node_output_summary(node_name: str, state: KnowledgeExtractionState) -> str:
    if node_name == "LoadChapterNode":
        return f"读取章节“{state.get('chapter_title', '')}”，约 {state.get('word_count', 0)} 字。"
    if node_name == "SegmentChapterNode":
        return f"生成 {len(state.get('segments', []))} 个处理片段。"
    if node_name == "GeneralExtractionNode":
        return f"生成 {len(state.get('raw_mentions', []))} 个 raw mentions。"
    if node_name == "MentionNormalizeNode":
        return f"保留 {len(state.get('raw_mentions', []))} 个有效 mention。"
    if node_name == "EntityAggregationNode":
        return f"聚合为 {len(state.get('entity_groups', []))} 个 entity_groups。"
    if node_name == "CandidateQualityGateNode":
        accepted_count = len(_accepted_entity_groups(state))
        return f"通过 {accepted_count} 个实体组，过滤 {len(state.get('entity_groups', [])) - accepted_count} 个。"
    if node_name == "TypeDispatchNode":
        return (
            f"角色组 {len(state.get('character_entity_groups', []))} 个，"
            f"实体组 {len(state.get('entity_entity_groups', []))} 个，"
            f"事件规则组 {len(state.get('event_rule_entity_groups', []))} 个。"
        )
    if node_name == "CharacterExpertNode":
        return f"生成 {len(state.get('character_typed_candidates', []))} 个角色候选。"
    if node_name == "EntityExpertNode":
        return f"生成 {len(state.get('entity_typed_candidates', []))} 个实体候选。"
    if node_name == "EventRuleExpertNode":
        return (
            f"生成 {len(state.get('event_rule_typed_candidates', []))} 个事件规则候选。"
        )
    if node_name == "MergeExpertCandidatesNode":
        return f"合并为 {len(state.get('typed_candidates', []))} 个候选草稿。"
    if node_name == "NormalizeAndValidateNode":
        return f"完成 {len(state.get('typed_candidates', []))} 个候选结构校验。"
    if node_name == "SynthesizeCandidateSummariesNode":
        count = sum(
            1
            for candidate in state.get("typed_candidates", [])
            if candidate.get("target_card_id")
        )
        return f"完成 {count} 个已有知识更新候选的摘要综合。"
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
        now.replace("-", "").replace(":", "").replace("+00:00", "").replace("Z", "")
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


def _append_unique_strings(current: list[str], incoming: list[str]) -> list[str]:
    merged = list(current)
    for value in incoming:
        if value not in merged:
            merged.append(value)
    return merged


def _accepted_entity_groups(state: KnowledgeExtractionState) -> list[dict[str, Any]]:
    return [
        group
        for group in state.get("entity_groups", [])
        if group.get("quality_decision") == "accepted"
    ]


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


def _evidence_excerpts_from_item(item: dict[str, Any]) -> list[str]:
    evidence = item.get("evidence_excerpts")
    if isinstance(evidence, list):
        return [
            value.strip()[:300]
            for value in evidence
            if isinstance(value, str) and value.strip()
        ][:_MAX_MENTION_EVIDENCE_COUNT]
    excerpt = _first_non_empty(
        item.get("evidence_excerpt"),
        item.get("source_excerpt"),
        item.get("excerpt"),
    )
    return [excerpt] if excerpt else []


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
