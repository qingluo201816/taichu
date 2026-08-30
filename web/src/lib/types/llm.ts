export type LLMAvailability = "unknown" | "available" | "unavailable";

export type PublicLLMModel = {
  id: string;
  display_name: string;
  provider: "rightcode" | "deepseek_official";
  enabled: boolean;
  is_default: boolean;
  supports_streaming: boolean;
  availability: LLMAvailability;
  last_probed_at?: string | null;
  availability_error?: string | null;
  upstream_verified: boolean;
};

export type LLMModelListResponse = {
  default_model_id: string;
  models: PublicLLMModel[];
};

export type LLMProvider = {
  id: "rightcode" | "deepseek_official";
  display_name: string;
  description: string;
  configured: boolean;
  model_count: number;
  model_names: string[];
};

export type LLMProviderListResponse = {
  active_provider_id: LLMProvider["id"];
  providers: LLMProvider[];
};

export type LLMModelProbeResponse = {
  model_id: string;
  availability: LLMAvailability;
  last_probed_at?: string | null;
  message: string;
};

export type LLMCallStatus = "running" | "completed" | "failed";
export type LLMCostKind = "actual" | "estimated" | "unavailable";

export type LLMCallRecord = {
  call_id: string;
  run_id?: string | null;
  task_type: string;
  task_name: string;
  feature: string;
  chapter_ids: string[];
  model_id: string;
  model_display_name: string;
  upstream_model: string;
  wire_protocol: string;
  status: LLMCallStatus;
  started_at: string;
  finished_at?: string | null;
  duration_ms: number;
  input_tokens?: number | null;
  cached_input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  total_tokens?: number | null;
  cost_amount?: string | number | null;
  cost_currency: string;
  cost_kind: LLMCostKind;
  provider_request_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type LLMCallListResponse = {
  items: LLMCallRecord[];
  page: number;
  page_size: number;
  total: number;
};

export type LLMUsageGroup = {
  key: string;
  display_name: string;
  total_calls: number;
  completed_calls: number;
  failed_calls: number;
  input_tokens?: number | null;
  cached_input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  total_tokens?: number | null;
  actual_cost: string | number;
  estimated_cost: string | number;
  unavailable_cost_calls: number;
  average_duration_ms: number;
};

export type LLMUsageSummary = Omit<LLMUsageGroup, "key" | "display_name"> & {
  by_model: LLMUsageGroup[];
  by_task_type: LLMUsageGroup[];
};

export type LLMTokenTrendPoint = {
  bucket_start: string;
  call_count: number;
  input_tokens?: number | null;
  cached_input_tokens?: number | null;
  output_tokens?: number | null;
  reasoning_tokens?: number | null;
  total_tokens?: number | null;
};

export type LLMTokenTrendResponse = {
  bucket: "hour" | "day";
  points: LLMTokenTrendPoint[];
};
