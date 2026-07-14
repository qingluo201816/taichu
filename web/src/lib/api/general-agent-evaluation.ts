import { apiRequest } from "@/lib/api-client";
import type {
  GeneralAgentEvaluationDatasetListResponse,
  GeneralAgentEvaluationListResponse,
  GeneralAgentEvaluationResponse,
} from "@/lib/types/general-agent-evaluation";

const PREFIX = "/api/agent-evaluations/general-agent";

export function listGeneralAgentEvaluationDatasets(): Promise<GeneralAgentEvaluationDatasetListResponse> {
  return apiRequest<GeneralAgentEvaluationDatasetListResponse>(`${PREFIX}/datasets`);
}

export function createGeneralAgentEvaluation(request: {
  dataset_id: string;
  case_id: string;
  run_id: string;
}): Promise<GeneralAgentEvaluationResponse> {
  return apiRequest<GeneralAgentEvaluationResponse>(`${PREFIX}/evaluations`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listGeneralAgentEvaluations(
  status = "all",
): Promise<GeneralAgentEvaluationListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "100", status });
  return apiRequest<GeneralAgentEvaluationListResponse>(
    `${PREFIX}/evaluations?${params.toString()}`,
  );
}

export function getGeneralAgentEvaluation(
  evaluationId: string,
): Promise<GeneralAgentEvaluationResponse> {
  return apiRequest<GeneralAgentEvaluationResponse>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}`,
  );
}

export function deleteGeneralAgentEvaluation(
  evaluationId: string,
): Promise<{ evaluation_id: string; deleted: boolean }> {
  return apiRequest<{ evaluation_id: string; deleted: boolean }>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}`,
    { method: "DELETE" },
  );
}
