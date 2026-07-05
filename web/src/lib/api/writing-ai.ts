import { apiRequest } from "@/lib/api-client";
import type {
  CreateWritingAIRunRequest,
  WritingAIButtonType,
  WritingAIRun,
  WritingAIRunListResponse,
  WritingAIRunStatus,
} from "@/lib/types/writing-ai";

export async function createWritingAIRun(
  request: CreateWritingAIRunRequest,
): Promise<WritingAIRun> {
  return apiRequest<WritingAIRun>("/api/writing-ai/runs", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listWritingAIRuns(params: {
  chapterId?: string;
  chapterName?: string;
  buttonType?: WritingAIButtonType;
  status?: WritingAIRunStatus;
  page?: number;
  pageSize?: number;
} = {}): Promise<WritingAIRunListResponse> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  if (params.chapterId) {
    search.set("chapter_id", params.chapterId);
  }
  if (params.chapterName?.trim()) {
    search.set("chapter_name", params.chapterName.trim());
  }
  if (params.buttonType) {
    search.set("button_type", params.buttonType);
  }
  if (params.status) {
    search.set("status", params.status);
  }
  return apiRequest<WritingAIRunListResponse>(
    `/api/writing-ai/runs?${search.toString()}`,
  );
}

export async function getWritingAIRun(runId: string): Promise<WritingAIRun> {
  return apiRequest<WritingAIRun>(
    `/api/writing-ai/runs/${encodeURIComponent(runId)}`,
  );
}

export async function replayWritingAIRun(runId: string): Promise<WritingAIRun> {
  return apiRequest<WritingAIRun>(
    `/api/writing-ai/runs/${encodeURIComponent(runId)}/replay`,
    { method: "POST" },
  );
}
