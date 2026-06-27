import { apiRequest } from "@/lib/api-client";
import type {
  AICardAction,
  AICardListResponse,
  AICardResponse,
  SelectionAIRequest,
} from "@/lib/types/ai-cards";

export async function listAICards(
  chapterId?: string,
): Promise<AICardListResponse> {
  const query = chapterId ? `?chapter_id=${encodeURIComponent(chapterId)}` : "";
  return apiRequest<AICardListResponse>(`/api/ai-cards${query}`);
}

export async function createSelectionAICard(
  request: SelectionAIRequest,
): Promise<AICardResponse> {
  return apiRequest<AICardResponse>("/api/ai-cards/selection", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function applyAICardAction(
  cardId: string,
  action: AICardAction,
): Promise<AICardResponse> {
  return apiRequest<AICardResponse>(`/api/ai-cards/${cardId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}
