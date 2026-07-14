export type GeneralAgentRunStatus =
  | "init"
  | "clarifying"
  | "planning"
  | "executing"
  | "waiting_human"
  | "verifying"
  | "replanning"
  | "completed"
  | "failed"
  | "cancelled"
  | "timeout";

export type GeneralAgentNodeStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "skipped"
  | "waiting_human";

export type GeneralAgentNodeKind = "tool" | "subagent";

export type GeneralAgentScopeType =
  | "none"
  | "selection"
  | "chapter"
  | "range"
  | "novel";

export type GeneralAgentScope = {
  scope_type: GeneralAgentScopeType;
  current_chapter_id?: string | null;
  chapter_ids: string[];
  selection_text: string;
  direct_context: string;
};

export type GeneralAgentInputBinding = {
  source_node_id: string;
  source_path: string;
  target_path: string;
};

export type GeneralAgentPlanNode = {
  node_id: string;
  kind: GeneralAgentNodeKind;
  capability_name: string;
  objective: string;
  input_data: Record<string, unknown>;
  dependencies: string[];
  input_bindings: GeneralAgentInputBinding[];
  continue_on_failure: boolean;
};

export type GeneralAgentExecutionPlan = {
  rationale: string;
  requires_clarification: boolean;
  clarification_question: string;
  direct_response: string;
  nodes: GeneralAgentPlanNode[];
  final_response_guidance: string;
};

export type GeneralAgentNodeRun = {
  node_id: string;
  plan_revision: number;
  kind: GeneralAgentNodeKind;
  capability_name: string;
  objective: string;
  dependencies: string[];
  status: GeneralAgentNodeStatus;
  resolved_input: Record<string, unknown>;
  output: Record<string, unknown>;
  source_refs: string[];
  artifact_refs: string[];
  trace_id?: string | null;
  authorization_grant_id?: string | null;
  authorization_approved: boolean;
  authorization_second_confirmation: boolean;
  authorization_resource_scopes: string[];
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  error_type?: string | null;
  error_message?: string | null;
};

export type GeneralAgentHumanRequest = {
  request_id: string;
  kind: "clarification" | "write_authorization";
  prompt: string;
  node_id?: string | null;
  tool_name?: string | null;
  input_sha256?: string | null;
  input_summary: Record<string, unknown>;
  resource_scopes: string[];
  second_confirmation_required: boolean;
  created_at: string;
};

export type GeneralAgentRun = {
  run_id: string;
  task_id: string;
  agent_name: "general_writing_assistant";
  user_goal: string;
  scope: GeneralAgentScope;
  author_constraints: string[];
  external_access_allowed: boolean;
  limits: {
    max_plan_nodes: number;
    max_replans: number;
    max_concurrency: number;
    max_total_tool_calls: number;
    max_runtime_seconds: number;
  };
  status: GeneralAgentRunStatus;
  messages: Array<{
    role: "user" | "assistant" | "system";
    content: string;
    created_at: string;
  }>;
  plan?: GeneralAgentExecutionPlan | null;
  plan_revision: number;
  replan_count: number;
  node_runs: GeneralAgentNodeRun[];
  pending_human_request?: GeneralAgentHumanRequest | null;
  final_answer: string;
  verification_issues: string[];
  checkpoint_revision: number;
  resumable: boolean;
  created_at: string;
  updated_at: string;
  started_at: string;
  finished_at?: string | null;
  errors: string[];
};

export type GeneralAgentRunSummary = {
  run_id: string;
  agent_name: string;
  user_goal: string;
  status: GeneralAgentRunStatus;
  scope_type: string;
  plan_revision: number;
  replan_count: number;
  completed_node_count: number;
  failed_node_count: number;
  total_node_count: number;
  waiting_human_kind?: string | null;
  final_answer_preview: string;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
};

export type GeneralAgentRunRequest = {
  user_goal: string;
  scope: GeneralAgentScope;
  author_constraints: string[];
  external_access_allowed: boolean;
};

export type GeneralAgentResumeRequest = {
  answer?: string;
  approve?: boolean;
  second_confirmation?: boolean;
};

export type GeneralAgentRunResponse = { run: GeneralAgentRun };

export type GeneralAgentRunListResponse = {
  runs: GeneralAgentRunSummary[];
  page: number;
  page_size: number;
  total: number;
};
