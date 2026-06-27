import type { SourceRefInfo } from "@/lib/types/ai-cards";
import type { PendingFactInfo } from "@/lib/types/inbox";

export type KnowledgeCardInfo = {
  id: string;
  type: string;
  name: string;
  aliases: string[];
  summary: string;
  fields: Record<string, unknown>;
  source_refs: SourceRefInfo[];
  status: "confirmed" | "archived";
  created_at: string;
  updated_at: string;
};

export type KnowledgeListResponse = {
  cards: KnowledgeCardInfo[];
};

export type ConfirmEditedPendingFactRequest = {
  name?: string | null;
  summary?: string | null;
  aliases?: string[] | null;
  fields?: Record<string, unknown> | null;
};

export type PendingFactConfirmationResponse = {
  pending_fact: PendingFactInfo;
  knowledge_card: KnowledgeCardInfo;
  created: boolean;
};

export type PendingFactRejectionResponse = {
  pending_fact: PendingFactInfo;
};
