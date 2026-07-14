"""十二个专业子 Agent 的独立输入和结构化草稿输出。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class SubagentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KnowledgeIdentityRequest(SubagentModel):
    knowledge_type: StructuredKnowledgeType
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=50)


class AgentSourceRequest(SubagentModel):
    """专业 Agent 可明确请求的小说事实来源，不包含创作工作区。"""

    auto_collect: bool = True
    include_structure: bool = False
    chapter_ids: list[str] = Field(default_factory=list, max_length=100)
    manuscript_query: str = Field(default="", max_length=2_000)
    knowledge_query: str = Field(default="", max_length=2_000)
    knowledge_identities: list[KnowledgeIdentityRequest] = Field(
        default_factory=list,
        max_length=20,
    )
    catalog_types: set[StructuredKnowledgeType] = Field(default_factory=set)
    knowledge_card_ids: list[str] = Field(default_factory=list, max_length=100)
    upstream_artifact_refs: list[str] = Field(default_factory=list, max_length=50)
    direct_context: str = Field(default="", max_length=100_000)


class CanonEvidenceInput(SubagentModel):
    question: str = Field(min_length=1, max_length=20_000)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class ExternalResearchInput(SubagentModel):
    research_question: str = Field(min_length=1, max_length=20_000)
    source_preferences: list[str] = Field(default_factory=list, max_length=20)
    date_range: str | None = Field(default=None, max_length=100)
    max_sources: int = Field(default=5, ge=1, le=10)
    external_access_grant_id: str = Field(min_length=1, max_length=128)


class NarrativeSummaryInput(SubagentModel):
    summary_goal: str = Field(min_length=1, max_length=20_000)
    target_chars: int = Field(default=2_000, ge=100, le=20_000)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class WorldbuildingInput(SubagentModel):
    design_goal: str = Field(min_length=1, max_length=20_000)
    hard_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class CharacterInput(SubagentModel):
    character_goal: str = Field(min_length=1, max_length=20_000)
    character_names: list[str] = Field(default_factory=list, max_length=50)
    hard_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class StoryArchitectureInput(SubagentModel):
    architecture_goal: str = Field(min_length=1, max_length=20_000)
    target_range: str = Field(default="", max_length=500)
    hard_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class ScenePlanningInput(SubagentModel):
    scene_goal: str = Field(min_length=1, max_length=20_000)
    chapter_id: str | None = Field(default=None, max_length=128)
    hard_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class DraftingInput(SubagentModel):
    writing_goal: str = Field(min_length=1, max_length=20_000)
    target_chars: int = Field(default=3_000, ge=100, le=100_000)
    style_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class RevisionInput(SubagentModel):
    text: str = Field(min_length=1, max_length=150_000)
    revision_goal: str = Field(min_length=1, max_length=20_000)
    preserve_constraints: list[str] = Field(default_factory=list, max_length=100)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class ConsistencyReviewInput(SubagentModel):
    text: str = Field(min_length=1, max_length=150_000)
    review_goal: str = Field(default="检查全部一致性维度", max_length=20_000)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class NarrativeReviewInput(SubagentModel):
    text: str = Field(min_length=1, max_length=150_000)
    review_goal: str = Field(default="检查叙事质量", max_length=20_000)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class StyleReviewInput(SubagentModel):
    text: str = Field(min_length=1, max_length=150_000)
    style_target: str = Field(default="保持当前小说文风", max_length=20_000)
    source_request: AgentSourceRequest = Field(default_factory=AgentSourceRequest)


class EvidenceItem(SubagentModel):
    claim: str
    source_ref: str
    excerpt: str = ""


class CanonEvidenceOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["canon_evidence_report"] = "canon_evidence_report"
    answer: str
    confidence: Literal["high", "medium", "low", "unknown"]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchSource(SubagentModel):
    title: str
    url: str
    claim: str = ""
    reliability_note: str = ""


class ExternalResearchOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["external_research_report"] = "external_research_report"
    conclusion: str
    sources: list[ResearchSource] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    timeliness_notes: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "unknown"]
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NarrativeSummaryOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["narrative_summary"] = "narrative_summary"
    summary: str
    key_events: list[str] = Field(default_factory=list)
    character_changes: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KnowledgeProposal(SubagentModel):
    knowledge_type: StructuredKnowledgeType
    name: str
    summary: str
    rationale: str
    source_refs: list[str] = Field(default_factory=list)


class WorldbuildingOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["worldbuilding_proposal"] = "worldbuilding_proposal"
    proposal: str
    rules: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    conflict_risks: list[str] = Field(default_factory=list)
    knowledge_proposals: list[KnowledgeProposal] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CharacterOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["character_proposal"] = "character_proposal"
    analysis: str
    proposals: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    behavior_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    knowledge_proposals: list[KnowledgeProposal] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StoryArchitectureOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["story_architecture"] = "story_architecture"
    overview: str
    stage_goals: list[str] = Field(default_factory=list)
    plotlines: list[str] = Field(default_factory=list)
    escalation: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SceneBeat(SubagentModel):
    order: int = Field(ge=1)
    goal: str
    action: str
    information_release: str = ""
    transition: str = ""


class ScenePlanningOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["scene_plan"] = "scene_plan"
    overview: str
    viewpoint: str
    beats: list[SceneBeat] = Field(default_factory=list)
    continuity_requirements: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DraftingOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["manuscript_candidate"] = "manuscript_candidate"
    text: str
    constraints_applied: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RevisionOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["revision_candidate"] = "revision_candidate"
    text: str
    change_summary: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReviewIssue(SubagentModel):
    dimension: str
    severity: Literal["critical", "major", "minor", "suggestion"]
    problem: str
    evidence: str
    source_ref: str = ""
    suggestion: str


class ConsistencyReviewOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["consistency_review"] = "consistency_review"
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    checked_dimensions: list[
        Literal[
            "world_rules",
            "character",
            "timeline",
            "causality",
            "state_continuity",
            "foreshadowing",
        ]
    ] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NarrativeReviewOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["narrative_review"] = "narrative_review"
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StyleReviewOutput(SubagentModel):
    lifecycle: Literal["draft"] = "draft"
    artifact_type: Literal["style_review"] = "style_review"
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    style_observations: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
