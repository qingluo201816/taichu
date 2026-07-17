"""通用写作助手评测集、检查项与结果模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.application.general_agent.models import (
    GeneralAgentRunStatus,
    GeneralAgentScope,
)


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneralAgentAssessmentMode(StrEnum):
    DETERMINISTIC = "deterministic"
    DETERMINISTIC_WITH_HUMAN_REVIEW = "deterministic_with_human_review"


class GeneralAgentExpectedClaim(EvaluationModel):
    description: str = Field(min_length=1, max_length=500)
    any_of: list[str] = Field(min_length=1, max_length=20)


class GeneralAgentEvaluationExpected(EvaluationModel):
    acceptable_statuses: list[GeneralAgentRunStatus] = Field(min_length=1)
    required_capabilities: list[str] = Field(default_factory=list)
    required_capability_groups: list[list[str]] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    min_node_count: int = Field(default=0, ge=0, le=40)
    max_node_count: int = Field(default=12, ge=0, le=40)
    requires_source_refs: bool = False
    expected_human_kind: Literal["clarification", "write_authorization"] | None = None
    external_access_allowed: bool = False
    max_replans: int = Field(default=1, ge=0, le=3)
    answer_claims: list[GeneralAgentExpectedClaim] = Field(default_factory=list)
    forbidden_answer_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_node_range(self) -> GeneralAgentEvaluationExpected:
        if self.max_node_count < self.min_node_count:
            raise ValueError("最大节点数不能小于最小节点数。")
        return self


class GeneralAgentEvaluationRunInput(EvaluationModel):
    """冻结一次评测运行所需、但不属于用户问题正文的输入。"""

    scope: GeneralAgentScope = Field(default_factory=GeneralAgentScope)
    author_constraints: list[str] = Field(default_factory=list, max_length=100)
    external_access_allowed: bool = False


class GeneralAgentEvaluationCase(EvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    label: str = Field(min_length=1, max_length=200)
    category: Literal[
        "fact_qa",
        "writing_advice",
        "character_analysis",
        "story_planning",
        "drafting",
        "revision",
        "consistency_review",
        "authorization_boundary",
    ]
    user_goal: str = Field(min_length=1, max_length=100_000)
    scope_type: Literal["none", "selection", "chapter", "range", "novel"]
    run_input: GeneralAgentEvaluationRunInput
    assessment_mode: GeneralAgentAssessmentMode = (
        GeneralAgentAssessmentMode.DETERMINISTIC
    )
    expected: GeneralAgentEvaluationExpected
    reference_answer: str = Field(min_length=1, max_length=100_000)
    notes: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def validate_run_input(self) -> GeneralAgentEvaluationCase:
        if self.run_input.scope.scope_type != self.scope_type:
            raise ValueError("评测运行输入的正文范围必须与样例范围一致。")
        if (
            self.run_input.external_access_allowed
            != self.expected.external_access_allowed
        ):
            raise ValueError("评测运行输入的外部访问许可必须与预期一致。")
        return self


class GeneralAgentEvaluationDataset(EvaluationModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    label: str = Field(min_length=1, max_length=200)
    lifecycle: Literal["confirmed"] = "confirmed"
    agent_name: Literal["general_writing_assistant"] = "general_writing_assistant"
    description: str = Field(default="", max_length=10_000)
    updated_at: str = Field(min_length=1)
    cases: list[GeneralAgentEvaluationCase] = Field(min_length=1, max_length=200)
    checksum: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_case_ids(self) -> GeneralAgentEvaluationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("评测样例标识必须唯一。")
        return self


class GeneralAgentEvaluationCheck(EvaluationModel):
    check_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    passed: bool
    detail: str = Field(min_length=1, max_length=2_000)
    critical: bool = False


class GeneralAgentEvaluationDimension(EvaluationModel):
    dimension: Literal[
        "task_completion",
        "routing_quality",
        "safety_boundary",
        "execution_health",
        "answer_quality",
    ]
    label: str
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    passed: bool
    checks: list[GeneralAgentEvaluationCheck] = Field(default_factory=list)


class GeneralAgentEvaluationStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"


class GeneralAgentEvaluationRecord(EvaluationModel):
    evaluation_id: str = Field(
        pattern=r"^general_eval_\d{8}_\d{6}_[a-z0-9]{6}$"
    )
    lifecycle: Literal["confirmed"] = "confirmed"
    status: GeneralAgentEvaluationStatus
    dataset_id: str
    dataset_checksum: str
    case_id: str
    case_label: str
    run_id: str
    run_status: GeneralAgentRunStatus
    user_goal: str
    reference_answer: str
    actual_answer: str
    plan_revision: int = Field(ge=0)
    evaluated_capabilities: list[str] = Field(default_factory=list)
    overall_score: float = Field(ge=0, le=100)
    passed: bool
    semantic_review_required: bool = False
    dimensions: list[GeneralAgentEvaluationDimension] = Field(min_length=5, max_length=5)
    issues: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
