import { apiRequest } from "@/lib/api-client";
import type {
  AgentMemoryDeleteResponse,
  AgentMemoryListResponse,
  GeneralAgentConversationDeleteResponse,
  GeneralAgentConversationListResponse,
  GeneralAgentConversationResponse,
  GeneralAgentResumeRequest,
  GeneralAgentRecoveryResponse,
  GeneralAgentRunListResponse,
  GeneralAgentRunRequest,
  GeneralAgentRunResponse,
  GeneralAgentTraceListResponse,
} from "@/lib/types/general-agent";

const PREFIX = "/api/agent-workbench/general-assistant";

export async function startGeneralAgentRun(
  request: GeneralAgentRunRequest,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(`${PREFIX}/runs/start`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listGeneralAgentRuns(options?: {
  page?: number;
  pageSize?: number;
  status?: string;
}): Promise<GeneralAgentRunListResponse> {
  const params = new URLSearchParams({
    page: String(options?.page ?? 1),
    page_size: String(options?.pageSize ?? 30),
    status: options?.status ?? "all",
  });
  return apiRequest<GeneralAgentRunListResponse>(
    `${PREFIX}/runs?${params.toString()}`,
  );
}

export async function listGeneralAgentConversations(options?: {
  page?: number;
  pageSize?: number;
}): Promise<GeneralAgentConversationListResponse> {
  const params = new URLSearchParams({
    page: String(options?.page ?? 1),
    page_size: String(options?.pageSize ?? 30),
  });
  return apiRequest<GeneralAgentConversationListResponse>(
    `${PREFIX}/conversations?${params.toString()}`,
  );
}

export async function getGeneralAgentConversation(
  conversationId: string,
): Promise<GeneralAgentConversationResponse> {
  return apiRequest<GeneralAgentConversationResponse>(
    `${PREFIX}/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export async function listGeneralAgentMemories(
  conversationId: string,
  options?: { includeDeleted?: boolean },
): Promise<AgentMemoryListResponse> {
  const params = new URLSearchParams({
    include_deleted: String(options?.includeDeleted ?? false),
  });
  return apiRequest<AgentMemoryListResponse>(
    `${PREFIX}/conversations/${encodeURIComponent(conversationId)}/memories?${params.toString()}`,
  );
}

export async function deleteGeneralAgentMemory(
  memoryId: string,
): Promise<AgentMemoryDeleteResponse> {
  return apiRequest<AgentMemoryDeleteResponse>(
    `${PREFIX}/memories/${encodeURIComponent(memoryId)}`,
    { method: "DELETE" },
  );
}

export async function deleteGeneralAgentConversation(
  conversationId: string,
): Promise<GeneralAgentConversationDeleteResponse> {
  return apiRequest<GeneralAgentConversationDeleteResponse>(
    `${PREFIX}/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
}

export async function getGeneralAgentRun(
  runId: string,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
  );
}

export async function resumeGeneralAgentRun(
  runId: string,
  request: GeneralAgentResumeRequest,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/resume`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

export async function cancelGeneralAgentRun(
  runId: string,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
}

export async function deleteGeneralAgentRun(
  runId: string,
): Promise<{ run_id: string; deleted: boolean }> {
  return apiRequest<{ run_id: string; deleted: boolean }>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  );
}

export async function listGeneralAgentTraces(
  runId: string,
  limit = 500,
): Promise<GeneralAgentTraceListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiRequest<GeneralAgentTraceListResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/traces?${params.toString()}`,
  );
}

export async function getGeneralAgentRecovery(
  runId: string,
): Promise<GeneralAgentRecoveryResponse> {
  return apiRequest<GeneralAgentRecoveryResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/recovery`,
  );
}
