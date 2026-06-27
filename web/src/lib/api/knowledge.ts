import { apiRequest } from "@/lib/api-client";
import type {
  ConfirmEditedPendingFactRequest,
  KnowledgeListResponse,
  PendingFactConfirmationResponse,
  PendingFactRejectionResponse,
} from "@/lib/types/knowledge";

export async function readKnowledge(): Promise<KnowledgeListResponse> {
  return apiRequest<KnowledgeListResponse>("/api/knowledge");
}

export async function confirmPendingFact(
  pendingFactId: string,
): Promise<PendingFactConfirmationResponse> {
  return apiRequest<PendingFactConfirmationResponse>(
    `/api/pending-facts/${encodeURIComponent(pendingFactId)}/confirm`,
    {
      method: "POST",
    },
  );
}

export async function confirmEditedPendingFact(
  pendingFactId: string,
  request: ConfirmEditedPendingFactRequest,
): Promise<PendingFactConfirmationResponse> {
  return apiRequest<PendingFactConfirmationResponse>(
    `/api/pending-facts/${encodeURIComponent(pendingFactId)}/confirm-edited`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export async function rejectPendingFact(
  pendingFactId: string,
): Promise<PendingFactRejectionResponse> {
  return apiRequest<PendingFactRejectionResponse>(
    `/api/pending-facts/${encodeURIComponent(pendingFactId)}/reject`,
    {
      method: "POST",
    },
  );
}
