import { apiRequest } from "@/lib/api-client";
import type {
  ChapterSummaryActionRequest,
  ChapterSummaryListResponse,
  ChapterSummaryResponse,
  ChapterSummaryRunResponse,
  ChapterListResponse,
  ChapterReadResponse,
  PendingFactResponse,
} from "@/lib/types/chapters";

export async function listChapters(): Promise<ChapterListResponse> {
  return apiRequest<ChapterListResponse>("/api/chapters");
}

export async function readChapter(
  chapterId: string,
): Promise<ChapterReadResponse> {
  return apiRequest<ChapterReadResponse>(`/api/chapters/${chapterId}`);
}

export async function saveChapter(
  chapterId: string,
  markdown: string,
): Promise<ChapterReadResponse> {
  return apiRequest<ChapterReadResponse>(`/api/chapters/${chapterId}`, {
    method: "PUT",
    body: JSON.stringify({ markdown }),
  });
}

export async function summarizeChapter(
  chapterId: string,
): Promise<ChapterSummaryRunResponse> {
  return apiRequest<ChapterSummaryRunResponse>(
    `/api/chapters/${chapterId}/summary`,
    { method: "POST" },
  );
}

export async function listChapterSummaries(
  chapterId: string,
): Promise<ChapterSummaryListResponse> {
  return apiRequest<ChapterSummaryListResponse>(
    `/api/chapters/${chapterId}/summaries`,
  );
}

export async function applyChapterSummaryAction(
  summaryId: string,
  request: ChapterSummaryActionRequest,
): Promise<ChapterSummaryResponse> {
  return apiRequest<ChapterSummaryResponse>(
    `/api/chapter-summaries/${summaryId}/actions`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export async function convertSummaryCandidateToPendingFact(
  summaryId: string,
  pendingFactId: string,
): Promise<PendingFactResponse> {
  return apiRequest<PendingFactResponse>(
    `/api/chapter-summaries/${summaryId}/pending-facts/${pendingFactId}`,
    { method: "POST" },
  );
}
