import type {
  GeneralAgentRunRequest,
  GeneralAgentRunStatus,
} from "@/lib/types/general-agent";

export type GeneralAgentAssessmentMode =
  | "deterministic"
  | "deterministic_with_human_review";

export type GeneralAgentEvaluationCase = {
  case_id: string;
  label: string;
  category:
    | "fact_qa"
    | "writing_advice"
    | "character_analysis"
    | "story_planning"
    | "drafting"
    | "revision"
    | "consistency_review"
    | "authorization_boundary";
  user_goal: string;
  scope_type: "none" | "selection" | "chapter" | "range" | "novel";
  run_input: Omit<GeneralAgentRunRequest, "user_goal">;
  assessment_mode: GeneralAgentAssessmentMode;
  expected: {
    acceptable_statuses: GeneralAgentRunStatus[];
    required_capabilities: string[];
    required_capability_groups: string[][];
    allowed_capabilities: string[];
    forbidden_capabilities: string[];
    min_node_count: number;
    max_node_count: number;
    requires_source_refs: boolean;
    expected_human_kind?: "clarification" | "write_authorization" | null;
    external_access_allowed: boolean;
    max_replans: number;
    answer_claims: Array<{ description: string; any_of: string[] }>;
    forbidden_answer_terms: string[];
  };
  reference_answer: string;
  notes: string;
};

export type GeneralAgentEvaluationDataset = {
  dataset_id: string;
  label: string;
  lifecycle: "confirmed";
  agent_name: "general_writing_assistant";
  description: string;
  updated_at: string;
  cases: GeneralAgentEvaluationCase[];
  checksum: string;
};

export type GeneralAgentEvaluationCheck = {
  check_id: string;
  label: string;
  passed: boolean;
  detail: string;
  critical: boolean;
};

export type GeneralAgentEvaluationDimension = {
  dimension:
    | "task_completion"
    | "routing_quality"
    | "safety_boundary"
    | "execution_health"
    | "answer_quality";
  label: string;
  score: number;
  weight: number;
  passed: boolean;
  checks: GeneralAgentEvaluationCheck[];
};

export type GeneralAgentEvaluationRecord = {
  evaluation_id: string;
  lifecycle: "confirmed";
  status: "completed" | "completed_with_warnings";
  dataset_id: string;
  dataset_checksum: string;
  case_id: string;
  case_label: string;
  run_id: string;
  run_status: GeneralAgentRunStatus;
  user_goal: string;
  reference_answer: string;
  actual_answer: string;
  plan_revision: number;
  evaluated_capabilities: string[];
  overall_score: number;
  passed: boolean;
  semantic_review_required: boolean;
  dimensions: GeneralAgentEvaluationDimension[];
  issues: string[];
  created_at: string;
};

export type GeneralAgentEvaluationDatasetListResponse = {
  datasets: GeneralAgentEvaluationDataset[];
};

export type GeneralAgentEvaluationListResponse = {
  evaluations: GeneralAgentEvaluationRecord[];
  page: number;
  page_size: number;
  total: number;
};

export type GeneralAgentEvaluationResponse = {
  evaluation: GeneralAgentEvaluationRecord;
};
