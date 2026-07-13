export type EvaluationStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_warnings"
  | "failed";

export type EvaluationPhase =
  | "queued"
  | "deterministic"
  | "judging"
  | "aggregating"
  | "finished";

export type EvaluationLifecycle = "draft" | "confirmed" | "rejected";

export type EvaluationMode =
  | "deterministic_and_judge"
  | "deterministic_only";

export type EvaluationEligibilityLevel =
  | "full"
  | "diagnostic"
  | "ineligible";

export type EvaluationIndependenceLevel =
  | "same_model"
  | "same_provider_family"
  | "different_model"
  | "unknown";

export type EvaluationQualityState =
  | "stable"
  | "usable"
  | "needs_review"
  | "high_risk"
  | "not_comparable";

export type EvaluationIssueType =
  | "missing_candidate"
  | "extra_candidate"
  | "ambiguous_match"
  | "field_difference"
  | "semantic_issue"
  | "evidence_issue"
  | "judge_disagreement";

export type EvaluationKnowledgeType =
  | "character"
  | "realm"
  | "technique"
  | "location"
  | "faction"
  | "item"
  | "rule"
  | "event";

export type EvaluationModelIdentity = {
  provider: string | null;
  model_id: string | null;
  family: string | null;
  endpoint_kind: string | null;
  fingerprint: string | null;
  known: boolean;
  unknown_reason: string | null;
};

export type EvaluationDatasetSummary = {
  dataset_id: string;
  label?: string;
  name?: string;
  display_name?: string;
  description?: string | null;
  lifecycle: EvaluationLifecycle | "confirmed";
  checksum: string | null;
  case_count?: number;
  valid?: boolean;
  knowledge_types?: EvaluationKnowledgeType[];
  updated_at?: string | null;
};

export type EvaluationDatasetListResponse = {
  datasets: EvaluationDatasetSummary[];
};

export type EvaluationDatasetDetailResponse = {
  dataset: EvaluationDatasetSummary;
};

export type EvaluationLatestRunResult = {
  evaluation_id: string;
  status: EvaluationStatus;
  lifecycle: EvaluationLifecycle;
  overall_quality_score: number | null;
  final_quality_state?: EvaluationQualityState | null;
};

export type EligibleEvaluationRun = {
  run_id: string;
  case_id: string | null;
  display_title: string;
  model_display_name: string;
  status?: string;
  scope_type: string;
  chapter_id?: string | null;
  chapter_title?: string | null;
  chapter_ids?: string[];
  chapter_titles?: string[];
  total_chapter_count?: number;
  started_at: string;
  requested_model_name?: string | null;
  model_name?: string | null;
  generation_model_identity: EvaluationModelIdentity;
  prompt_version: string;
  schema_version: string;
  eligibility_level: EvaluationEligibilityLevel;
  reason: string | null;
  suggested_card_available?: boolean;
  latest_evaluation?: EvaluationLatestRunResult | null;
};

export type EligibleEvaluationRunListResponse = {
  runs: EligibleEvaluationRun[];
  page: number;
  page_size: number;
  total: number;
};

export type CreateKnowledgeEvaluationRequest = {
  dataset_id: string;
  run_ids: string[];
  judge_enabled: boolean;
  metric_profile_id: string;
};

export type EvaluationPreviewRun = {
  run_id: string;
  case_id: string | null;
  display_title: string;
  model_display_name: string;
  eligibility_level: EvaluationEligibilityLevel;
  reason: string | null;
  generation_model_identity: EvaluationModelIdentity;
  independence_level: EvaluationIndependenceLevel | null;
  expected_card_count: number;
  estimated_matched_card_count: number;
  estimated_judge_card_count: number;
};

export type KnowledgeEvaluationPreview = {
  can_create: boolean;
  evaluation_mode: EvaluationMode;
  has_diagnostic_runs: boolean;
  dataset: {
    dataset_id: string;
    checksum: string;
  };
  runs: EvaluationPreviewRun[];
  judge: {
    requested: boolean;
    available: boolean | null;
    model_identity: EvaluationModelIdentity | null;
    unavailable_reason: string | null;
  };
  estimate: {
    run_count: number;
    expected_card_count: number;
    matched_card_count: number;
    judge_card_count: number;
    judge_batch_count: number;
  };
  warnings: string[];
  blocking_errors: string[];
};

export type EvaluationProgress = {
  run_total: number;
  run_completed: number;
  judge_card_total: number;
  judge_card_completed: number;
};

export type EvaluationJudgeSummary = {
  enabled?: boolean;
  model_identity: EvaluationModelIdentity | null;
  self_judge: boolean | null;
  independence_by_run: Record<string, EvaluationIndependenceLevel>;
};

export type EvaluationMetrics = {
  overall_quality_score?: number | null;
  candidate_precision_micro?: number | null;
  candidate_recall_micro?: number | null;
  candidate_f1_micro?: number | null;
  candidate_f1_macro?: number | null;
  structured_field_score?: number | null;
  semantic_score?: number | null;
  semantic_correctness?: number | null;
  evidence_score?: number | null;
  evidence_grounded_precision?: number | null;
  expected_evidence_recall?: number | null;
  negative_suppression_score?: number | null;
  judge_coverage?: number | null;
  execution_coverage?: number | null;
  schema_compliance_rate?: number | null;
  critical_risk_count?: number;
  critical_flag_count?: number;
  ambiguous_count?: number;
  contradiction_count?: number;
  unsupported_claim_count?: number;
  missing_critical_claim_count?: number;
  judge_disagreement_count?: number;
  reference_issue_count?: number;
  final_quality_state?: EvaluationQualityState | null;
  [key: string]: number | string | null | undefined;
};

export type EvaluationRunResultSummary = {
  run_id: string;
  case_id?: string | null;
  display_title?: string;
  chapter_title?: string | null;
  scope_type?: string;
  eligibility_level?: EvaluationEligibilityLevel;
  metrics?: EvaluationMetrics;
  semantic_score?: number | null;
  judge_coverage?: number | null;
  overall_quality_score?: number | null;
  final_quality_state?: EvaluationQualityState | null;
  warnings?: EvaluationNotice[];
};

export type EvaluationNotice = {
  code: string;
  message: string;
  run_id?: string | null;
};

export type KnowledgeEvaluation = {
  evaluation_id: string;
  parent_evaluation_id: string | null;
  request_fingerprint?: string;
  snapshot_root_hash?: string;
  evaluation_mode: EvaluationMode;
  lifecycle: EvaluationLifecycle;
  status: EvaluationStatus;
  phase: EvaluationPhase;
  dataset: {
    dataset_id: string;
    name?: string;
    display_name?: string;
    checksum: string;
  };
  metric_profile_id: string;
  subject_title?: string;
  judge: EvaluationJudgeSummary;
  progress: EvaluationProgress;
  run_results: EvaluationRunResultSummary[];
  aggregate_metrics: EvaluationMetrics;
  warnings: Array<string | EvaluationNotice>;
  errors: Array<string | EvaluationNotice>;
  error_code: string | null;
  error_message?: string | null;
  created_at: string;
  started_at: string | null;
  updated_at: string;
  heartbeat_at: string | null;
  finished_at: string | null;
  poll_url?: string;
};

export type KnowledgeEvaluationListResponse = {
  evaluations: KnowledgeEvaluation[];
  page: number;
  page_size: number;
  total: number;
};

export type KnowledgeEvaluationDetailResponse = {
  evaluation: KnowledgeEvaluation;
};

export type EvaluationFieldDiff = {
  field: string;
  label?: string | null;
  issue?: string | null;
  expected: unknown;
  actual: unknown;
};

export type EvaluationEvidenceDiff = {
  quote_id?: string | null;
  chapter_id?: string | null;
  chapter_title?: string | null;
  expected_quote?: string | null;
  actual_quote?: string | null;
  located?: boolean | null;
  reason?: string | null;
};

export type EvaluationJudgeFinding = {
  finding_id?: string;
  kind?: string;
  severity?: string;
  field?: string | null;
  claim_id?: string | null;
  message?: string;
  reason?: string;
  quote_ids?: string[];
};

export type KnowledgeEvaluationComparison = {
  comparison_id: string;
  run_id: string;
  case_id?: string | null;
  task_title?: string;
  expected_card_id?: string | null;
  actual_review_item_id?: string | null;
  knowledge_type: EvaluationKnowledgeType;
  issue_type: EvaluationIssueType;
  display_title: string;
  match_basis?: string | null;
  expected_card?: Record<string, unknown> | null;
  actual_card?: Record<string, unknown> | null;
  field_diffs?: EvaluationFieldDiff[];
  evidence_diffs?: EvaluationEvidenceDiff[];
  missing_critical_claims?: string[];
  unsupported_claims?: string[];
  contradictions?: string[];
  judge_reason?: string | null;
  judge_confidence?: number | null;
  judge_status?: string | null;
  judge_findings?: EvaluationJudgeFinding[];
  judge_call_ids?: string[];
};

export type KnowledgeEvaluationComparisonListResponse = {
  comparisons: KnowledgeEvaluationComparison[];
  page: number;
  page_size: number;
  total: number;
};
