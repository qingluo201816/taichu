import { apiRequest } from "@/lib/api-client";
import type {
  GeneralAgentResumeRequest,
  GeneralAgentRunListResponse,
  GeneralAgentRunRequest,
  GeneralAgentRunResponse,
} from "@/lib/types/general-agent";

const PREFIX = "/api/agent-workbench/general-assistant";

export async function startGeneralAgentRun(
  request: GeneralAgentRunRequest,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(`${PREFIX}/runs/start`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listGeneralAgentRuns(): Promise<GeneralAgentRunListResponse> {
  return apiRequest<GeneralAgentRunListResponse>(
    `${PREFIX}/runs?page=1&page_size=30&status=all`,
  );
}

export async function getGeneralAgentRun(
  runId: string,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
  );
}

export async function resumeGeneralAgentRun(
  runId: string,
  request: GeneralAgentResumeRequest,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/resume`,
    { method: "POST", body: JSON.stringify(request) },
  );
}

export async function cancelGeneralAgentRun(
  runId: string,
): Promise<GeneralAgentRunResponse> {
  return apiRequest<GeneralAgentRunResponse>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
}

export async function deleteGeneralAgentRun(
  runId: string,
): Promise<{ run_id: string; deleted: boolean }> {
  return apiRequest<{ run_id: string; deleted: boolean }>(
    `${PREFIX}/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  );
}
