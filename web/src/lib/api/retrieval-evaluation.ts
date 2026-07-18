import { apiRequest } from "@/lib/api-client";
import type {
  RetrievalEvaluationDatasetResponse,
  RetrievalEvaluationListResponse,
  RetrievalEvaluationResponse,
} from "@/lib/types/retrieval-evaluation";

const PREFIX = "/api/agent-evaluations/retrieval";

export function getRetrievalEvaluationDataset(
  datasetId = "retrieval_knowledge_core",
): Promise<RetrievalEvaluationDatasetResponse> {
  return apiRequest<RetrievalEvaluationDatasetResponse>(
    `${PREFIX}/datasets/${encodeURIComponent(datasetId)}`,
  );
}

export function listRetrievalEvaluations(
  limit = 20,
): Promise<RetrievalEvaluationListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiRequest<RetrievalEvaluationListResponse>(
    `${PREFIX}/evaluations?${params.toString()}`,
  );
}

export function getRetrievalEvaluation(
  evaluationId: string,
): Promise<RetrievalEvaluationResponse> {
  return apiRequest<RetrievalEvaluationResponse>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}`,
  );
}
