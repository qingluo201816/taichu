export type WritingAIButtonType =
  | "chat"
  | "continue"
  | "polish"
  | "setting"
  | "suggestion"
  | "evidence"
  | "chapter_summary"
  | "inspiration"
  | "fact";

export type WritingAIReferenceScope =
  | "none"
  | "selection"
  | "chapter"
  | "full_text";

export type WritingAIRunStatus =
  | "queued"
  | "retrieving"
  | "calling_llm"
  | "parsing"
  | "completed"
  | "failed";

export type WritingAIOutputType =
  | "chat_answer"
  | "text_candidate"
  | "polished_text"
  | "setting_suggestion"
  | "writing_suggestion"
  | "evidence_answer"
  | "chapter_summary"
  | "inspiration"
  | "pending_fact_candidates";

export type WritingAISelectionRange = {
  paragraph_start?: number | null;
  paragraph_end?: number | null;
  char_start?: number | null;
  char_end?: number | null;
};

export type WritingAIInput = {
  user_input: string;
  selected_text: string;
  selection_range?: WritingAISelectionRange | null;
  target_words?: number | null;
  draft_chapter_text?: string | null;
};

export type WritingAIPromptSnapshot = {
  prompt_id: string;
  prompt_version: string;
  system_prompt: string;
  user_prompt: string;
  rendered_at: string;
};

export type WritingAIRetrievalEvidenceItem = {
  item_id: string;
  source_type: string;
  source_id: string;
  display_name: string;
  excerpt: string;
  usage: string;
};

export type WritingAIRetrievalContext = {
  used: boolean;
  empty_reason?: string | null;
  items: WritingAIRetrievalEvidenceItem[];
  knowledge_context: string;
  evidence_context: string;
};

export type WritingAIStructuredOutput = {
  output_type: WritingAIOutputType;
  content: Record<string, unknown>;
};

export type WritingAIRun = {
  run_id: string;
  status: WritingAIRunStatus;
  button_type: WritingAIButtonType;
  button_label: string;
  model: string;
  chapter_id: string;
  chapter_title: string;
  reference_scope: WritingAIReferenceScope;
  input: WritingAIInput;
  prompt_snapshot?: WritingAIPromptSnapshot | null;
  retrieval_context?: WritingAIRetrievalContext | null;
  raw_llm_output: string;
  structured_output?: WritingAIStructuredOutput | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateWritingAIRunRequest = {
  button_type: WritingAIButtonType;
  chapter_id: string;
  reference_scope: WritingAIReferenceScope;
  user_input?: string;
  selected_text?: string;
  selection_range?: WritingAISelectionRange | null;
  target_words?: number | null;
  draft_chapter_text?: string | null;
};

export type WritingAIRunListResponse = {
  runs: WritingAIRun[];
  page: number;
  page_size: number;
  total: number;
};
