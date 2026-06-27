import { apiRequest } from "@/lib/api-client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentListResponse,
} from "@/lib/types/agents";

export async function listAgents(): Promise<AgentListResponse> {
  return apiRequest<AgentListResponse>("/api/agents");
}

export async function runAgentChat(
  request: AgentChatRequest,
): Promise<AgentChatResponse> {
  return apiRequest<AgentChatResponse>("/api/agents/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
