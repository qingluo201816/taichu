import { apiRequest } from "@/lib/api-client";
import type {
  ChapterListResponse,
  ChapterReadResponse,
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
