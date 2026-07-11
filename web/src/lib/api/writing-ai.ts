import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type {
  CreateWritingAIRunRequest,
  WritingAIButtonType,
  WritingAIRun,
  WritingAIRunListResponse,
  WritingAIRunStatus,
  WritingAIStreamEvent,
} from "@/lib/types/writing-ai";

export async function createWritingAIRun(
  request: CreateWritingAIRunRequest,
): Promise<WritingAIRun> {
  return apiRequest<WritingAIRun>("/api/writing-ai/runs", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function streamWritingAIRun(
  request: CreateWritingAIRunRequest,
  onEvent: (event: WritingAIStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/writing-ai/runs/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    throw new Error(`模型流式请求失败：${response.status}`);
  }
  if (!response.body) {
    throw new Error("浏览器未返回模型流式响应正文。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    lines.forEach(line => dispatchLine(line, onEvent));
  }
  buffer += decoder.decode();
  dispatchLine(buffer, onEvent);
}

function dispatchLine(
  line: string,
  onEvent: (event: WritingAIStreamEvent) => void,
) {
  const value = line.trim();
  if (!value) return;
  onEvent(JSON.parse(value) as WritingAIStreamEvent);
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
