import { apiRequest } from "@/lib/api-client";
import type {
  CreateKnowledgeExtractionRunRequest,
  EditConfirmCandidateRequest,
  KnowledgeExtractionCandidateActionResponse,
  KnowledgeExtractionCandidateListResponse,
  KnowledgeExtractionRunCreateResponse,
  KnowledgeExtractionRunDetailResponse,
  KnowledgeExtractionRunListResponse,
} from "@/lib/types/agent-workbench";

const PREFIX = "/api/agent-workbench/knowledge-extraction";

export async function createKnowledgeExtractionRun(
  request: CreateKnowledgeExtractionRunRequest,
): Promise<KnowledgeExtractionRunCreateResponse> {
  return apiRequest<KnowledgeExtractionRunCreateResponse>(`${PREFIX}/runs`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listKnowledgeExtractionRuns(): Promise<KnowledgeExtractionRunListResponse> {
  return apiRequest<KnowledgeExtractionRunListResponse>(
    `${PREFIX}/runs?page=1&page_size=20&status=all`,
  );
}

export async function getKnowledgeExtractionRun(
  runId: string,
): Promise<KnowledgeExtractionRunDetailResponse> {
  return apiRequest<KnowledgeExtractionRunDetailResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
  );
}

export async function listKnowledgeExtractionCandidates(
  runId: string,
): Promise<KnowledgeExtractionCandidateListResponse> {
  return apiRequest<KnowledgeExtractionCandidateListResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/candidates?status=all&action=all`,
  );
}

export async function confirmKnowledgeExtractionCandidate(
  candidateId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/candidates/${encodeURIComponent(candidateId)}/confirm`,
    { method: "POST" },
  );
}

export async function editConfirmKnowledgeExtractionCandidate(
  candidateId: string,
  request: EditConfirmCandidateRequest,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/candidates/${encodeURIComponent(candidateId)}/edit-confirm`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export async function rejectKnowledgeExtractionCandidate(
  candidateId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/candidates/${encodeURIComponent(candidateId)}/reject`,
    { method: "POST" },
  );
}

export async function deferKnowledgeExtractionCandidate(
  candidateId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/candidates/${encodeURIComponent(candidateId)}/defer`,
    { method: "POST" },
  );
}
