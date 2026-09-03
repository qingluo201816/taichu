export enum TrackKind {
  SYNTHETIC = "synthetic",
  LIVE_PROVIDER = "live_provider",
}

export enum SuiteRunLifecycle {
  QUEUED = "queued",
  RUNNING = "running",
  CANCELLING = "cancelling",
  FINALIZING = "finalizing",
  COMPLETED = "completed",
  UNFINISHED = "unfinished",
  CANCELLED = "cancelled",
}

export enum SuiteConclusion {
  PASSED = "passed",
  FAILED = "failed",
  INVALID = "invalid",
  NOT_EVALUATED = "not_evaluated",
}

export enum ProviderExecutionState {
  NOT_APPLICABLE = "not_applicable",
  PENDING = "pending",
  RUNNING = "running",
  BLOCKED = "blocked",
  ERROR = "error",
  COMPLETED = "completed",
}

export enum CaseExecutionState {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETED = "completed",
  BLOCKED = "blocked",
  ERROR = "error",
  CANCELLED = "cancelled",
  UNFINISHED = "unfinished",
}

export enum CaseConclusion {
  PASSED = "passed",
  FAILED = "failed",
  INVALID = "invalid",
  UNFINISHED = "unfinished",
  CANCELLED = "cancelled",
}

export enum ComparabilityStatus {
  COMPARABLE = "comparable",
  INCOMPARABLE = "incomparable",
  INVALID = "invalid",
}

export enum AdmissionStatus {
  ADMITTED = "admitted",
  BLOCKED = "blocked",
}

export enum FirstLiveIterationState {
  AWAITING_SYNTHETIC = "awaiting_synthetic",
  READY_FOR_DEEPSEEK = "ready_for_deepseek",
  DEEPSEEK_RUNNING = "deepseek_running",
  CLASSIFYING = "classifying",
  CLOSING_SYSTEM_DEFECTS = "closing_system_defects",
  READY_FOR_COMPARISON = "ready_for_comparison",
  BLOCKED = "blocked",
  INVALID = "invalid",
}

export interface BenchmarkPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  index_revision: number;
  total_snapshot: string;
}

export interface BenchmarkSuiteSummary {
  suite_id: string;
  name: string;
  content_hash: string;
  case_count: number;
  case_order: string[];
  track_case_counts: Record<TrackKind, number>;
  cases: BenchmarkCaseSummary[];
}

export interface BenchmarkCaseSummary {
  ordinal: number;
  case_id: string;
  name: string;
  summary: string;
  tracks: TrackKind[];
}

export interface BenchmarkExpectedTerminal {
  run_status:
    | "completed"
    | "preview_only"
    | "write_rejected"
    | "waiting_human"
    | "safe_failure";
  resumable: boolean;
  pending_human_kind: string | null;
  recovery_action:
    | "none"
    | "resume"
    | "reuse_checkpoint"
    | "reconcile_effect"
    | "stop";
  reason_code: string;
}

export interface BenchmarkBudgetLimits {
  max_node_executions: number;
  max_replans: number;
  max_capability_calls: number;
  max_model_calls: number;
  max_total_tokens: number;
  max_runtime_ms: number;
}

export interface BenchmarkCaseExpectation extends BenchmarkCaseSummary {
  user_request: string;
  objective: string;
  target_final_artifact: string;
  behavior_expectations: string[];
  expected_terminal: BenchmarkExpectedTerminal;
  budget_limits: BenchmarkBudgetLimits;
  capability_domain_id: string;
}

export interface BenchmarkCapabilityDomain {
  domain_id: string;
  name: string;
  purpose: string;
  case_ids: string[];
}

export type BenchmarkEntryId = "multi_step" | "recovery";

export type BenchmarkObservabilityStatus =
  | "available"
  | "disabled"
  | "unavailable";

export interface BenchmarkObservabilityScore {
  name: string;
  value: number;
}

export interface BenchmarkObservabilityEntry {
  entry_id: BenchmarkEntryId;
  dataset_name: string;
  dataset_id: string;
  dataset_url: string;
  dataset_version: string;
  dataset_item_count: number;
  experiment_id: string;
  experiment_name: string;
  experiment_url: string;
  traces_url: string;
  experiment_status: string;
  created_at: string;
  case_count: number;
  passed_count: number;
  trace_count: number;
  duration_p50_ms: number | null;
  duration_p90_ms: number | null;
  total_estimated_cost: number | null;
  scores: BenchmarkObservabilityScore[];
}

export interface BenchmarkObservabilitySnapshot {
  provider: "opik";
  status: BenchmarkObservabilityStatus;
  project_name: string;
  project_url: string | null;
  suite_content_hash: string;
  refreshed_at: string;
  message: string;
  entries: BenchmarkObservabilityEntry[];
}

export interface BenchmarkScenarioCategory {
  category_id: string;
  name: string;
  purpose: string;
  case_ids: string[];
}

export interface BenchmarkPortfolioEntry {
  entry_id: BenchmarkEntryId;
  name: string;
  summary: string;
  opik_dataset_name: string;
  case_count: number;
  case_ids: string[];
  categories: BenchmarkScenarioCategory[];
  invalid_invocation_rules: string[];
}

export interface BenchmarkSuiteDetail
  extends Omit<BenchmarkSuiteSummary, "cases"> {
  benchmark_entries: BenchmarkPortfolioEntry[];
  capability_domains: BenchmarkCapabilityDomain[];
  cases: BenchmarkCaseExpectation[];
}

export interface BenchmarkSuiteRun {
  run_id: string;
  revision: number;
  lifecycle: SuiteRunLifecycle;
  conclusion: SuiteConclusion | null;
  suite_content_hash: string;
  selected_case_ids: string[];
  track: TrackKind;
  provider_state: ProviderExecutionState;
  case_row_refs: string[];
  pending_case_ids: string[];
  terminal_artifact_ref: string | null;
}

export interface BenchmarkCaseResult {
  suite_id: string;
  case_id: string;
  case_execution_id: string;
  attempt_number: number;
  execution_state: CaseExecutionState;
  conclusion: CaseConclusion | null;
  failure_category: string | null;
  failure_categories: string[];
  evidence_bundle_id: string;
  evidence_availability: string;
}

export interface BenchmarkRunSubmission {
  idempotency_key: string;
  run_id: string;
  suite_id: string;
  suite_content_hash: string;
  selected_case_ids: string[];
  track: TrackKind;
}

export interface BenchmarkExperiment {
  experiment_id: string;
  comparability: {
    status: ComparabilityStatus;
    reasons: string[];
  };
  [key: string]: unknown;
}

export interface BenchmarkFirstLiveIteration {
  iteration_id: string;
  revision: number;
  state: FirstLiveIterationState;
  code_hash: string;
  suite_hash: string;
  fixture_hash: string;
  capability_catalog_hash: string;
  selected_case_ids: string[];
  synthetic_qualification_artifact_refs: string[];
  prior_iteration_ids: string[];
  first_live_artifact_ref: string | null;
  pending_intent_refs: string[];
  confirmed_relation_refs: string[];
  comparison_refs: string[];
  latest_comparison_ref: string | null;
  problems: string[];
  [key: string]: unknown;
}

export interface BenchmarkSuiteArtifact {
  artifact_id: string;
  run_id: string;
  conclusion: SuiteConclusion;
  case_rows: BenchmarkCaseResult[];
  evidence_bundles: Array<{
    identity: { bundle_id: string; case_id: string };
    availability: Record<string, string>;
    problems: string[];
    details: {
      gates: Array<{
        gate_kind: string;
        status: string;
        conditions: Array<{
          condition_id: string;
          status: string;
          expected: string;
          observed: string;
        }>;
      }>;
      capability_invocations: Array<{
        kind: "tool" | "subagent";
        capability_name: string;
        call_id: string;
        handler_identity: string;
        outcome: string;
      }>;
      normalization_actions: Array<{
        kind: "human" | "model" | "tool" | "subagent";
        name: string;
        outcome: string;
        step_id: string;
        step_index: number;
        evidence: Record<string, unknown>;
      }>;
      normalization_hash: string;
      runtime_evidence_refs: string[];
      assertions?: Array<{
        assertion_id: string;
        assertion_kind: string;
        expected: string;
        observed: string;
        status: string;
        claim_projection?: {
          normalized_text?: string;
        } | null;
      }>;
      final_answer_text?: string | null;
      track?: TrackKind;
      terminal?: {
        pending_human_kind: string | null;
        resumable: boolean;
        run_status: string;
        stop_reason: string;
      };
      runtime_failure?: {
        run_status: string;
        resumable: boolean;
        plan_present: boolean;
        node_count: number;
        interaction_count: number;
        capability_result_count: number;
        effect_count: number;
        failure_evidence: Array<Record<string, unknown>>;
      } | null;
    } | null;
  }>;
  provider_state: ProviderExecutionState;
  artifact_hash: string;
}

export interface BenchmarkComparison {
  comparison_id: string;
  admitted: boolean;
  first_live_artifact_ref: string | null;
  admission: {
    status: AdmissionStatus;
    blocked_reasons: string[];
  };
  closure_ids: string[];
  blocked_reasons: string[];
  ranking_candidate_ids: string[];
  ranking_basis: string[];
  catalog_model_count: number;
  covered_model_count: number;
  full_suite_model_count: number;
  blocked_model_count: number;
  candidate_results: Array<{
    candidate_id: string;
    display_name: string;
    run_id: string;
    execution_state: "completed" | "blocked" | "error";
    evidence_scope: "full_suite" | "capability_probe";
    qualification: "qualified" | "partial" | "failed" | "blocked";
    eligible_for_ranking: boolean;
    requested_provider_id: string;
    requested_model_id: string;
    actual_provider_id: string | null;
    actual_model_id: string | null;
    fallback_used: boolean;
    request_timeout_seconds: number;
    provider_max_retries: number;
    case_count: number;
    passed_case_count: number;
    pass_rate: number;
    model_call_attempts: number;
    completed_model_calls: number;
    failed_model_calls: number;
    avg_model_call_attempts: number;
    capability_steps: number;
    avg_capability_steps: number;
    tool_steps: number;
    subagent_steps: number;
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
    reasoning_tokens: number;
    total_tokens: number;
    suite_elapsed_ms: number;
    total_duration_ms: number;
    avg_model_call_duration_ms: number;
    p50_model_call_duration_ms: number;
    p95_model_call_duration_ms: number;
    cost_amount: number | null;
    cost_currency: string;
    cost_kind_counts: Record<string, number>;
    unavailable_cost_calls: number;
    provider_error_count: number;
    failed_case_ids: string[];
    failure_category_counts: Record<string, number>;
    gate_pass_counts: Record<string, number>;
    artifact_ref: string;
    artifact_hash: string;
    blocked_reason: string | null;
  }>;
  record_hash: string;
  [key: string]: unknown;
}

export interface BenchmarkIssueCorrelationStatus {
  revision: number;
  total_snapshot: string;
  [key: string]: unknown;
}
