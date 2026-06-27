import type { AIResultCard, SourceRefInfo } from "@/lib/types/ai-cards";

export type AgentInfo = {
  name: string;
  label: string;
  description: string;
  required_capabilities: string[];
  exposures: string[];
  supports_streaming: boolean;
};

export type AgentListResponse = {
  agents: AgentInfo[];
};

export type AgentChatRequest = {
  message: string;
  chapter_id?: string | null;
  include_current_chapter: boolean;
  include_confirmed_facts: boolean;
};

export type AgentConversationInfo = {
  id: string;
  agent_name: string;
  message: string;
  chapter_id?: string | null;
  used_current_chapter: boolean;
  used_confirmed_facts: boolean;
  source_refs: SourceRefInfo[];
  card_id: string;
  created_at: string;
};

export type AgentChatResponse = {
  conversation: AgentConversationInfo;
  card: AIResultCard;
};
