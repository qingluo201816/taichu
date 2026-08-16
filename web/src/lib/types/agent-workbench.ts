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

export type EditConfirmMergeMode = "merge" | "overwrite";

export type KnowledgeType =
  | "character"
  | "realm"
  | "technique"
  | "location"
  | "faction"
  | "item"
  | "rule"
  | "event";

export type AgentRunSummary = {
  run_id: string;
  agent_name: string;
  status: AgentRunStatus;
  scope_type: string;
  chapter_id: string;
  chapter_title: string;
  chapter_ids: string[];
  chapter_titles: string[];
  candidate_count: number;
  pending_count: number;
  confirmed_count: number;
  rejected_count: number;
  total_chapter_count: number;
  completed_chapter_count: number;
  failed_chapter_count: number;
  started_at: string;
  finished_at?: string | null;
};

export type AgentRunScope = {
  scope_type: string;
  chapter_id: string;
  chapter_title: string;
  content_hash: string;
  chapter_ids: string[];
  chapter_titles: string[];
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

export type AgentRunGraphNode = {
  node_name: string;
  label: string;
  lane: string;
};

export type AgentRunGraphEdge = {
  source: string;
  target: string;
};

export type AgentBatchChapterProgress = {
  chapter_id: string;
  chapter_title: string;
  status: AgentNodeStatus;
  started_at?: string | null;
  finished_at?: string | null;
  candidate_count: number;
  nodes?: AgentRunNode[];
  error?: string | null;
};

export type AgentLLMCall = {
  call_id: string;
  node_name: string;
  model_name: string;
  model_id: string;
  model_display_name: string;
  upstream_model: string;
  wire_protocol: string;
  prompt_version: string;
  input_prompt: string;
  raw_response: string;
  parsed_output: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  input_tokens?: number | null;
  cached_input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  total_tokens?: number | null;
  cost_amount?: string | number | null;
  cost_currency: string;
  cost_kind: string;
  provider_request_id?: string | null;
  finish_reason?: string | null;
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
  realm_candidate_count: number;
  technique_candidate_count: number;
  location_candidate_count: number;
  faction_candidate_count: number;
  item_candidate_count: number;
  rule_candidate_count: number;
  event_candidate_count: number;
  candidate_count_by_type: Partial<Record<KnowledgeType, number>>;
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
  model_id: string;
  model_display_name: string;
  upstream_model: string;
  wire_protocol: string;
  status: AgentRunStatus;
  scope: AgentRunScope;
  started_at: string;
  finished_at?: string | null;
  nodes: AgentRunNode[];
  graph_nodes: AgentRunGraphNode[];
  graph_edges: AgentRunGraphEdge[];
  batch_chapter_progress: AgentBatchChapterProgress[];
  max_concurrency: number;
  current_concurrency: number;
  total_chapter_count: number;
  completed_chapter_count: number;
  failed_chapter_count: number;
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
  model_id?: string | null;
  force?: boolean;
};

export type CreateBatchKnowledgeExtractionRunRequest = {
  chapter_ids: string[];
  model_id?: string | null;
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

export type KnowledgeSedimentationProgress = {
  last_accepted_chapter_id?: string | null;
  updated_at?: string | null;
};

export type KnowledgeExtractionStreamEventType =
  | "run_started"
  | "node_started"
  | "node_finished"
  | "llm_call_finished"
  | "run_completed"
  | "run_failed"
  | "task_started"
  | "chapter_branch_started"
  | "chapter_branch_node_started"
  | "chapter_branch_node_finished"
  | "chapter_branch_finished"
  | "task_completed"
  | "task_failed"
  | "task_deleted";

export type KnowledgeExtractionStreamEvent = {
  type?: KnowledgeExtractionStreamEventType;
  event_type: KnowledgeExtractionStreamEventType;
  run_id: string;
  message: string;
  run?: AgentRun;
  node?: AgentRunNode;
  llm_call?: AgentLLMCall;
  chapter_progress?: AgentBatchChapterProgress;
};
