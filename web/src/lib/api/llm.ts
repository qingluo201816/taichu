import { apiRequest } from "@/lib/api-client";
import type {
  LLMCallListResponse,
  LLMCallRecord,
  LLMCallStatus,
  LLMModelListResponse,
  LLMModelProbeResponse,
  LLMProviderListResponse,
  LLMUsageSummary,
  LLMTokenTrendResponse,
} from "@/lib/types/llm";

export function listLLMModels(): Promise<LLMModelListResponse> {
  return apiRequest<LLMModelListResponse>("/api/llm/models");
}

export function listLLMProviders(): Promise<LLMProviderListResponse> {
  return apiRequest<LLMProviderListResponse>("/api/llm/providers");
}

export function switchLLMProvider(
  providerId: LLMProviderListResponse["active_provider_id"],
): Promise<LLMProviderListResponse> {
  return apiRequest<LLMProviderListResponse>("/api/llm/providers/active", {
    method: "PUT",
    body: JSON.stringify({ provider_id: providerId }),
  });
}

export function probeLLMModel(modelId: string): Promise<LLMModelProbeResponse> {
  return apiRequest<LLMModelProbeResponse>(
    `/api/llm/models/${encodeURIComponent(modelId)}/probe`,
    { method: "POST" },
  );
}

export type LLMUsageFilters = {
  page?: number;
  pageSize?: number;
  startedFrom?: string;
  startedTo?: string;
  modelId?: string;
  taskType?: string;
  status?: LLMCallStatus;
};

export function listLLMCalls(filters: LLMUsageFilters = {}): Promise<LLMCallListResponse> {
  return apiRequest<LLMCallListResponse>(`/api/llm/usage/calls?${query(filters, true)}`);
}

export function getLLMCall(callId: string): Promise<LLMCallRecord> {
  return apiRequest<LLMCallRecord>(
    `/api/llm/usage/calls/${encodeURIComponent(callId)}`,
  );
}

export function getLLMUsageSummary(
  filters: LLMUsageFilters = {},
): Promise<LLMUsageSummary> {
  return apiRequest<LLMUsageSummary>(`/api/llm/usage/summary?${query(filters, false)}`);
}

export function getLLMTokenTrend(
  filters: LLMUsageFilters = {},
  bucket: "hour" | "day" = "day",
): Promise<LLMTokenTrendResponse> {
  const search = query(filters, false);
  const suffix = search ? `&${search}` : "";
  return apiRequest<LLMTokenTrendResponse>(
    `/api/llm/usage/trend?bucket=${bucket}${suffix}`,
  );
}

function query(filters: LLMUsageFilters, paginated: boolean): string {
  const search = new URLSearchParams();
  if (paginated) {
    search.set("page", String(filters.page ?? 1));
    search.set("page_size", String(filters.pageSize ?? 20));
  }
  if (filters.startedFrom) search.set("started_from", filters.startedFrom);
  if (filters.startedTo) search.set("started_to", filters.startedTo);
  if (filters.modelId) search.set("model_id", filters.modelId);
  if (filters.taskType) search.set("task_type", filters.taskType);
  if (filters.status) search.set("status", filters.status);
  return search.toString();
}
