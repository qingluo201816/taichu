import { apiRequest } from "@/lib/api-client";
import type {
  CreateKnowledgeExtractionRunRequest,
  CreateBatchKnowledgeExtractionRunRequest,
  EditConfirmCandidateRequest,
  KnowledgeExtractionCandidateActionResponse,
  KnowledgeExtractionCandidateListResponse,
  KnowledgeExtractionRunCreateResponse,
  KnowledgeExtractionRunDetailResponse,
  KnowledgeExtractionRunListResponse,
  KnowledgeExtractionStreamEvent,
  KnowledgeSedimentationProgress,
} from "@/lib/types/agent-workbench";

const PREFIX = "/api/agent-workbench/knowledge-extraction";
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function createKnowledgeExtractionRun(
  request: CreateKnowledgeExtractionRunRequest,
): Promise<KnowledgeExtractionRunCreateResponse> {
  return apiRequest<KnowledgeExtractionRunCreateResponse>(`${PREFIX}/runs`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function streamKnowledgeExtractionRun(
  request: CreateKnowledgeExtractionRunRequest,
  onEvent: (event: KnowledgeExtractionStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${PREFIX}/runs/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(await streamErrorMessage(response));
  }
  if (!response.body) {
    throw new Error("浏览器未返回流式响应正文。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      dispatchStreamLine(line, onEvent);
    }
  }

  buffer += decoder.decode();
  dispatchStreamLine(buffer, onEvent);
}

export async function startKnowledgeExtractionRun(
  request: CreateKnowledgeExtractionRunRequest,
): Promise<KnowledgeExtractionRunCreateResponse> {
  return apiRequest<KnowledgeExtractionRunCreateResponse>(`${PREFIX}/runs/start`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function streamBatchKnowledgeExtractionRun(
  request: CreateBatchKnowledgeExtractionRunRequest,
  onEvent: (event: KnowledgeExtractionStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${PREFIX}/batch-runs/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(await streamErrorMessage(response));
  }
  if (!response.body) {
    throw new Error("浏览器未返回流式响应正文。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      dispatchStreamLine(line, onEvent);
    }
  }

  buffer += decoder.decode();
  dispatchStreamLine(buffer, onEvent);
}

export async function startBatchKnowledgeExtractionRun(
  request: CreateBatchKnowledgeExtractionRunRequest,
): Promise<KnowledgeExtractionRunCreateResponse> {
  return apiRequest<KnowledgeExtractionRunCreateResponse>(
    `${PREFIX}/batch-runs/start`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export async function getKnowledgeSedimentationProgress(): Promise<KnowledgeSedimentationProgress> {
  return apiRequest<KnowledgeSedimentationProgress>(`${PREFIX}/progress`);
}

export async function acceptKnowledgeExtractionRun(
  runId: string,
): Promise<KnowledgeSedimentationProgress> {
  return apiRequest<KnowledgeSedimentationProgress>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/accept`,
    { method: "POST" },
  );
}

export async function retryFailedKnowledgeExtractionSummaries(
  runId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/summaries/retry`,
    { method: "POST" },
  );
}

export async function listKnowledgeExtractionRuns(): Promise<KnowledgeExtractionRunListResponse> {
  return apiRequest<KnowledgeExtractionRunListResponse>(
    `${PREFIX}/runs?page=1&page_size=20&status=all`,
  );
}

export async function listAgentTasks(): Promise<KnowledgeExtractionRunListResponse> {
  return apiRequest<KnowledgeExtractionRunListResponse>(
    "/api/agent-tasks?page=1&page_size=50&status=all",
  );
}

export async function getAgentTask(
  taskId: string,
): Promise<KnowledgeExtractionRunDetailResponse> {
  return apiRequest<KnowledgeExtractionRunDetailResponse>(
    `/api/agent-tasks/${encodeURIComponent(taskId)}`,
  );
}

export async function deleteAgentTask(
  taskId: string,
): Promise<{ run_id: string; deleted: boolean }> {
  return apiRequest<{ run_id: string; deleted: boolean }>(
    `/api/agent-tasks/${encodeURIComponent(taskId)}`,
    { method: "DELETE" },
  );
}

export async function streamAgentTaskEvents(
  onEvent: (event: KnowledgeExtractionStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/agent-tasks/stream/events`, {
    signal,
  });
  if (!response.ok) {
    throw new Error(await streamErrorMessage(response));
  }
  if (!response.body) {
    throw new Error("浏览器未返回任务监控流。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      dispatchStreamLine(line, onEvent);
    }
  }
  buffer += decoder.decode();
  dispatchStreamLine(buffer, onEvent);
}

export async function getKnowledgeExtractionRun(
  runId: string,
): Promise<KnowledgeExtractionRunDetailResponse> {
  return apiRequest<KnowledgeExtractionRunDetailResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
  );
}

export async function deleteKnowledgeExtractionRun(
  runId: string,
): Promise<{ run_id: string; deleted: boolean }> {
  return apiRequest<{ run_id: string; deleted: boolean }>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
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
  runId: string,
  candidateId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/confirm`,
    { method: "POST" },
  );
}

export async function editConfirmKnowledgeExtractionCandidate(
  runId: string,
  candidateId: string,
  request: EditConfirmCandidateRequest,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/edit-confirm`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export async function rejectKnowledgeExtractionCandidate(
  runId: string,
  candidateId: string,
): Promise<KnowledgeExtractionCandidateActionResponse> {
  return apiRequest<KnowledgeExtractionCandidateActionResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/reject`,
    { method: "POST" },
  );
}

function dispatchStreamLine(
  line: string,
  onEvent: (event: KnowledgeExtractionStreamEvent) => void,
) {
  const trimmed = line.trim();
  if (!trimmed) {
    return;
  }
  onEvent(JSON.parse(trimmed) as KnowledgeExtractionStreamEvent);
}

async function streamErrorMessage(response: Response): Promise<string> {
  const detail = await response.text();
  if (!detail) {
    return `接口请求失败：${response.status}`;
  }
  try {
    const parsed = JSON.parse(detail) as unknown;
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      !Array.isArray(parsed)
    ) {
      const error = (parsed as Record<string, unknown>).error;
      if (
        typeof error === "object" &&
        error !== null &&
        !Array.isArray(error)
      ) {
        const message = (error as Record<string, unknown>).message;
        if (typeof message === "string") {
          return message;
        }
      }
    }
  } catch {
    return detail;
  }
  return detail;
}
