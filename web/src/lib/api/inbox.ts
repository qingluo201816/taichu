import { apiRequest } from "@/lib/api-client";
import type {
  ConvertPendingFactResponse,
  InboxResponse,
  PendingFactActionResponse,
  SaveIdeaResponse,
} from "@/lib/types/inbox";

export async function readInbox(): Promise<InboxResponse> {
  return apiRequest<InboxResponse>("/api/inbox");
}

export async function saveAICardAsIdea(
  cardId: string,
): Promise<SaveIdeaResponse> {
  return apiRequest<SaveIdeaResponse>(
    `/api/inbox/cards/${encodeURIComponent(cardId)}/save-idea`,
    {
      method: "POST",
    },
  );
}

export async function convertAICardToPendingFact(
  cardId: string,
): Promise<ConvertPendingFactResponse> {
  return apiRequest<ConvertPendingFactResponse>(
    `/api/inbox/cards/${encodeURIComponent(cardId)}/convert-pending-fact`,
    {
      method: "POST",
    },
  );
}

export async function ignorePendingFact(
  pendingFactId: string,
): Promise<PendingFactActionResponse> {
  return apiRequest<PendingFactActionResponse>(
    `/api/inbox/pending-facts/${encodeURIComponent(pendingFactId)}/ignore`,
    {
      method: "POST",
    },
  );
}
