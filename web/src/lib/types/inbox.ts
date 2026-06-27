import type { AIResultCard, SourceRefInfo } from "@/lib/types/ai-cards";

export type InboxMeta = {
  scope: "workspace_scope";
  fact_status: "non_fact";
  source_href?: string | null;
};

export type IdeaCardInfo = InboxMeta & {
  id: string;
  content: string;
  source: string;
  linked_chapter_id?: string | null;
  status: string;
  source_card_id?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type PendingFactInfo = InboxMeta & {
  id: string;
  fact_type: string;
  title: string;
  content: Record<string, unknown> | string;
  proposed_by: string;
  source_refs: SourceRefInfo[];
  status: string;
  target_knowledge_id?: string | null;
  created_at: string;
  confirmed_at?: string | null;
};

export type SavedAICardInfo = AIResultCard & InboxMeta;

export type ChapterIssueInfo = InboxMeta & {
  id: string;
  title: string;
  description: string;
  chapter_id?: string | null;
  status: string;
  source: string;
  source_card_id?: string | null;
  source_refs: SourceRefInfo[];
  created_at: string;
  updated_at: string;
};

export type InboxResponse = {
  ideas: IdeaCardInfo[];
  pending_facts: PendingFactInfo[];
  saved_ai_cards: SavedAICardInfo[];
  chapter_issues: ChapterIssueInfo[];
};

export type SaveIdeaResponse = {
  idea: IdeaCardInfo;
  card: SavedAICardInfo;
};

export type ConvertPendingFactResponse = {
  pending_fact: PendingFactInfo;
  card: SavedAICardInfo;
};

export type PendingFactActionResponse = {
  pending_fact: PendingFactInfo;
};
