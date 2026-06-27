export type SourceRefInfo = {
  source_type: "chapter" | "knowledge" | "summary" | "workspace" | "ai_card" | "author_manual";
  source_id: string;
  path: string;
  chapter_id?: string | null;
  anchor_type: "document" | "heading" | "paragraph" | "paragraph_range" | "knowledge_field" | "card";
  heading_path?: string[] | null;
  paragraph_start?: number | null;
  paragraph_end?: number | null;
  field_path?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  excerpt: string;
  excerpt_hash: string;
  source_hash: string;
  created_at: string;
  stale?: boolean;
};

export type SelectionRangeInfo = {
  from: number;
  to: number;
};

export type SelectionMode = "ask" | "enrich_setting" | "continue_text";

export type AIResultCardType =
  | "text_candidate"
  | "suggestion"
  | "pending_fact"
  | "evidence"
  | "chapter_summary"
  | "inspiration";

export type AIResultCardStatus =
  | "generated"
  | "inserted"
  | "saved_to_inbox"
  | "converted_to_pending_fact"
  | "discarded"
  | "retried";

export type AIResultCard = {
  id: string;
  type: AIResultCardType;
  workflow: string;
  status: AIResultCardStatus;
  chapter_id?: string | null;
  input_context: {
    mode?: SelectionMode;
    selected_text?: string;
    surrounding_text?: string;
    selection_range?: SelectionRangeInfo;
    selection_ref?: SourceRefInfo;
    user_prompt?: string | null;
    target_words?: number | null;
    [key: string]: unknown;
  };
  content: Record<string, unknown> | string;
  source_refs: SourceRefInfo[];
  parent_card_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type SelectionAIRequest = {
  mode: SelectionMode;
  chapter_id: string;
  selected_text: string;
  surrounding_text: string;
  selection_range: SelectionRangeInfo;
  source_ref: SourceRefInfo;
  user_prompt?: string | null;
  target_words?: number | null;
  parent_card_id?: string | null;
};

export type AICardListResponse = {
  cards: AIResultCard[];
};

export type AICardResponse = {
  card: AIResultCard;
};

export type AICardAction = "inserted" | "discard" | "save_to_idea";
