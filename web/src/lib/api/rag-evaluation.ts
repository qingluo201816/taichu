import { apiRequest } from "@/lib/api-client";
import type {
  RAGEvaluationConfiguration,
  RAGEvaluationResultDetail,
  RAGEvaluationResultSummary,
  RAGGoldenSuite,
} from "@/lib/types/rag-evaluation";

export function getCurrentRAGEvaluationSuite(): Promise<RAGGoldenSuite> {
  return apiRequest<RAGGoldenSuite>("/api/rag-evaluations/suite");
}

export function getRAGEvaluationResult(
  runId: string,
): Promise<RAGEvaluationResultDetail> {
  return apiRequest<RAGEvaluationResultDetail>(
    `/api/rag-evaluations/results/${encodeURIComponent(runId)}`,
  );
}

export function getRAGEvaluationConfiguration(): Promise<RAGEvaluationConfiguration> {
  return apiRequest<RAGEvaluationConfiguration>(
    "/api/rag-evaluations/configuration",
  );
}

export function listRAGEvaluationResults(
  limit = 10,
): Promise<RAGEvaluationResultSummary[]> {
  return apiRequest<RAGEvaluationResultSummary[]>(
    `/api/rag-evaluations/results?limit=${limit}`,
  );
}
