export type AgentRunStatus = "pending" | "running" | "completed" | "failed";

export type AgentNodeStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "skipped";

export type ReviewCandidateAction =
  | "create_card"
  | "update_card"
  | "conflict"
  | "ignore";

export type ReviewCandidateStatus =
  | "pending"
  | "confirmed"
  | "rejected";

export type EditConfirmMergeMode = "append" | "overwrite";

export type KnowledgeType = "character" | "location" | "faction" | "item";

export type AgentRunSummary = {
  run_id: string;
  agent_name: string;
  status: AgentRunStatus;
  chapter_id: string;
  chapter_title: string;
  candidate_count: number;
  pending_count: number;
  confirmed_count: number;
  rejected_count: number;
  started_at: string;
  finished_at?: string | null;
};

export type AgentRunScope = {
  scope_type: string;
  chapter_id: string;
  chapter_title: string;
  content_hash: string;
};

export type AgentRunNode = {
  node_name: string;
  status: AgentNodeStatus;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
  error?: string | null;
};

export type AgentLLMCall = {
  call_id: string;
  node_name: string;
  model_name: string;
  prompt_version: string;
  input_prompt: string;
  raw_response: string;
  parsed_output: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  error?: string | null;
};

export type AgentRawMention = {
  mention_id: string;
  name: string;
  knowledge_type: KnowledgeType;
  description: string;
  evidence_excerpts: string[];
  reason: string;
  segment_index: number;
};

export type AgentEntityGroup = {
  entity_group_id: string;
  canonical_name: string;
  knowledge_type: KnowledgeType;
  raw_names: string[];
  mention_count: number;
  evidence_excerpts: string[];
  quality_decision: string;
  quality_reason: string;
};

export type AgentIgnoredExtraction = {
  text: string;
  reason: string;
  segment_index?: number | null;
};

export type AgentSchemaValidation = {
  passed: boolean;
  errors: string[];
};

export type AgentReviewItem = {
  review_item_id: string;
  run_id: string;
  candidate_action: ReviewCandidateAction;
  knowledge_type: KnowledgeType;
  candidate_status: ReviewCandidateStatus;
  display_title: string;
  suggested_card: Record<string, unknown>;
  target_card_id?: string | null;
  matched_card_name?: string | null;
  match_reason: string;
  source_excerpt: string;
  schema_validation: AgentSchemaValidation;
  internal_conflicts: string[];
  external_conflicts: string[];
  suggested_action_label: string;
  author_action?: string | null;
  created_knowledge_card_id?: string | null;
  updated_knowledge_card_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentMetrics = {
  candidate_total: number;
  character_candidate_count: number;
  location_candidate_count: number;
  faction_candidate_count: number;
  item_candidate_count: number;
  create_card_count: number;
  update_card_count: number;
  conflict_count: number;
  schema_passed_count: number;
  schema_failed_count: number;
  confirmed_count: number;
  rejected_count: number;
  pending_count: number;
  total_duration_ms: number;
  llm_call_count: number;
  node_duration_ms: Record<string, number>;
};

export type AgentRun = {
  run_id: string;
  agent_name: string;
  agent_version: string;
  schema_version: string;
  prompt_version: string;
  model_name: string;
  status: AgentRunStatus;
  scope: AgentRunScope;
  started_at: string;
  finished_at?: string | null;
  nodes: AgentRunNode[];
  llm_calls: AgentLLMCall[];
  raw_mentions: AgentRawMention[];
  entity_groups: AgentEntityGroup[];
  raw_candidates: Record<string, unknown>[];
  typed_candidates: Record<string, unknown>[];
  review_items: AgentReviewItem[];
  ignored: AgentIgnoredExtraction[];
  metrics: AgentMetrics;
  errors: string[];
};

export type CreateKnowledgeExtractionRunRequest = {
  chapter_id: string;
  model_name?: string | null;
  force?: boolean;
};

export type KnowledgeExtractionRunCreateResponse = {
  run: AgentRunSummary;
};

export type KnowledgeExtractionRunListResponse = {
  runs: AgentRunSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type KnowledgeExtractionRunDetailResponse = {
  run: AgentRun;
};

export type KnowledgeExtractionCandidateListResponse = {
  candidates: AgentReviewItem[];
};

export type EditConfirmCandidateRequest = {
  card_updates: Record<string, unknown>;
  target_card_id?: string | null;
  merge_mode?: EditConfirmMergeMode;
};

export type KnowledgeExtractionCandidateActionResponse = {
  run: AgentRun;
};
