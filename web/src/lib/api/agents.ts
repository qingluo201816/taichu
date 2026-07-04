import { apiRequest } from "@/lib/api-client";
import type { AgentListResponse } from "@/lib/types/agents";

export async function listAgents(): Promise<AgentListResponse> {
  return apiRequest<AgentListResponse>("/api/agents");
}
