export type RetrievalEvaluationCategory =
  | "exact_name_alias"
  | "semantic_paraphrase"
  | "state_relation_event_rule"
  | "multi_entity_disambiguation"
  | "no_answer_adversarial";

export type RetrievalAtKMetric = {
  k: 1 | 3 | 5 | 10;
  recall: number;
  precision: number;
  ndcg: number;
};

export type RetrievalEvaluationCase = {
  case_id: string;
  label: string;
  category: RetrievalEvaluationCategory;
  query_text: string;
  context_text: string;
  knowledge_types: string[];
  relevant_card_ids: string[];
  must_not_return_card_ids: string[];
  should_be_empty: boolean;
  expected_top_k: 1 | 3 | 5 | 10;
};

export type RetrievalEvaluationDataset = {
  dataset_id: string;
  evaluation_type: "retrieval";
  label: string;
  description: string;
  lifecycle: "confirmed";
  updated_at: string;
  cases: RetrievalEvaluationCase[];
  checksum: string;
};

export type RetrievalEvaluationSummary = {
  case_count: number;
  relevance_case_count: number;
  at_k: RetrievalAtKMetric[];
  mrr: number;
  empty_result_accuracy: number;
  forbidden_hit_rate: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  average_candidate_count: number;
  truncation_rate: number;
  content_budget_hit_rate: number;
};

export type RetrievalEvaluationGroup = {
  category: RetrievalEvaluationCategory;
  summary: RetrievalEvaluationSummary;
};

export type RetrievalEvaluationCaseResult = {
  case_id: string;
  category: RetrievalEvaluationCategory;
  retrieval_id: string;
  returned_card_ids: string[];
  forbidden_hit_ids: string[];
  at_k: RetrievalAtKMetric[];
  reciprocal_rank: number;
  empty_result_correct: boolean | null;
  latency_ms: number;
  candidate_count: number;
  hit_count: number;
  truncated: boolean;
  budget_limited: boolean;
  content_chars_used: number;
};

export type RetrievalEvaluationFailure = {
  case_id: string;
  reasons: string[];
  returned_card_ids: string[];
};

export type RetrievalEvaluationRecord = {
  evaluation_id: string;
  lifecycle: "confirmed";
  status: "completed";
  dataset_id: string;
  dataset_checksum: string;
  requested_strategy: string;
  effective_strategies: string[];
  index_snapshot_id: string;
  confirmed_card_count: number;
  policy_snapshots: Array<Record<string, string | number | boolean | null>>;
  summary: RetrievalEvaluationSummary;
  groups: RetrievalEvaluationGroup[];
  cases: RetrievalEvaluationCaseResult[];
  failures: RetrievalEvaluationFailure[];
  environment: Record<string, string>;
  started_at: string;
  finished_at: string;
};

export type RetrievalEvaluationListItem = Omit<
  RetrievalEvaluationRecord,
  "policy_snapshots" | "groups" | "cases" | "failures" | "environment"
> & {
  failure_count: number;
};

export type RetrievalEvaluationDatasetResponse = {
  dataset: RetrievalEvaluationDataset;
};

export type RetrievalEvaluationListResponse = {
  evaluations: RetrievalEvaluationListItem[];
};

export type RetrievalEvaluationResponse = {
  evaluation: RetrievalEvaluationRecord;
};
