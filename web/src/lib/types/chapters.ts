import type { AIResultCard, SourceRefInfo } from "@/lib/types/ai-cards";

export type ChapterInfo = {
  id: string;
  volume_id: string | null;
  title: string;
  order: number;
  markdown_path: string;
  status: string;
  word_count: number;
  created_at: string;
  updated_at: string;
};

export type ChapterListResponse = {
  chapters: ChapterInfo[];
};

export type ChapterReadResponse = {
  chapter: ChapterInfo;
  markdown: string;
};

export type PendingFactInfo = {
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

export type ChapterSummaryInfo = {
  id: string;
  chapter_id: string;
  status: "draft" | "confirmed" | "ignored";
  summary: string;
  key_events: string[];
  character_changes: Record<string, unknown>[];
  new_setting_candidates: PendingFactInfo[];
  foreshadow_candidates: Record<string, unknown>[];
  next_chapter_hooks: string[];
  source_refs: SourceRefInfo[];
  created_at: string;
  updated_at: string;
};

export type ChapterSummaryRunResponse = {
  summary: ChapterSummaryInfo;
  card: AIResultCard;
};

export type ChapterSummaryListResponse = {
  summaries: ChapterSummaryInfo[];
};

export type ChapterSummaryResponse = {
  summary: ChapterSummaryInfo;
};

export type PendingFactResponse = {
  pending_fact: PendingFactInfo;
};

export type ChapterSummaryActionRequest = {
  action: "confirm" | "ignore";
  edits?: {
    summary?: string | null;
    key_events?: string[] | null;
    character_changes?: Record<string, unknown>[] | null;
    foreshadow_candidates?: Record<string, unknown>[] | null;
    next_chapter_hooks?: string[] | null;
  } | null;
};
