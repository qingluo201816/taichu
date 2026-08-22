export type RAGGoldenCategory =
  | "single_fact"
  | "cross_source"
  | "graph_multi_hop"
  | "hard_negative";

export interface RAGExpectedRelation {
  subject: string;
  predicate: string;
  object: string;
  relation_id: string;
  text: string;
}

export interface RAGGoldenCase {
  case_id: string;
  query: string;
  category: RAGGoldenCategory;
  graph_required: boolean;
  smoke: boolean;
  expected_source_ids: string[];
  expected_relations: RAGExpectedRelation[];
  expected_path: string[];
  expected_claims: string[];
  reference_answer: string;
}

export interface RAGGoldenSuite {
  suite_id: string;
  cases: RAGGoldenCase[];
}

export interface RAGEvaluationResultSummary {
  run_id: string;
  mode: string;
  created_at: string;
  status: string;
  passed: boolean | null;
  case_count: number | null;
  graph_case_count: number | null;
  error_message: string | null;
}

export interface RAGCaseScore {
  case_id: string;
  recall_at_k: number | null;
  mrr_at_k: number | null;
  authority_verified: boolean;
  relation_recall_at_k: number | null;
  complete_path_recall: number | null;
  graph_expansion_noise_rate: number | null;
  retrieved_source_ids: string[];
  retrieved_relation_ids: string[];
}

export interface RAGAblationScore {
  case_id: string;
  graph_on: RAGCaseScore;
  graph_off: RAGCaseScore;
  recall_delta: number | null;
  mrr_delta: number | null;
  relation_recall_delta: number;
  complete_path_delta: number;
}

export interface RAGEvaluationReportDetail {
  suite_id: string;
  mode: string;
  created_at: string;
  top_k: number;
  case_scores: RAGCaseScore[];
  ablation_scores: RAGAblationScore[];
  summary: {
    case_count: number;
    graph_case_count: number;
    mean_recall_at_k: number;
    mean_mrr_at_k: number;
    authority_pass_rate: number;
    mean_relation_recall_at_k: number | null;
    complete_path_pass_rate: number | null;
    mean_ablation_recall_delta: number | null;
    mean_ablation_complete_path_delta: number | null;
  };
}

export interface RAGSemanticMetric {
  metric: string;
  score: number;
  threshold: number;
  passed: boolean;
  reason: string | null;
}

export interface RAGSemanticCaseScore {
  case_id: string;
  actual_answer: string;
  source_refs: string[];
  metrics: RAGSemanticMetric[];
}

export interface RAGRunReport {
  deterministic: RAGEvaluationReportDetail;
  semantic_scores: RAGSemanticCaseScore[];
  runtime_identity: Record<string, string>;
  gate: { passed: boolean; failures: string[] };
}

export interface RAGInfrastructureFailureReport {
  status: "infrastructure_failed";
  mode: string;
  created_at: string;
  error_type: string;
  error_message: string;
}

export type RAGEvaluationResultDetail =
  | RAGRunReport
  | RAGInfrastructureFailureReport;

export interface RAGEvaluationConfiguration {
  pipeline: Array<{
    key: string;
    order: number;
    name: string;
    description: string;
  }>;
  parameters: Array<{
    key: string;
    name: string;
    value: string;
    description: string;
  }>;
  ci_policies: Array<{
    name: string;
    trigger: string;
    scope: string;
  }>;
}
