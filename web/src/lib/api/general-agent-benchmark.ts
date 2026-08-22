import { API_BASE_URL } from "../api-client";
import type {
  BenchmarkCaseResult,
  BenchmarkComparison,
  BenchmarkExperiment,
  BenchmarkFirstLiveIteration,
  BenchmarkPage,
  BenchmarkRunSubmission,
  BenchmarkSuiteRun,
  BenchmarkSuiteArtifact,
  BenchmarkSuiteDetail,
  BenchmarkSuiteSummary,
} from "../types/general-agent-benchmark";

const BENCHMARK_API_PREFIX = "/api/general-agent-benchmarks";

interface BenchmarkErrorDetail {
  error?: unknown;
  message?: unknown;
  request_id?: unknown;
  details?: unknown;
}

export class BenchmarkApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(options: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    details?: Record<string, unknown>;
  }) {
    super(options.message);
    this.name = "BenchmarkApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId ?? null;
    this.details = options.details ?? {};
  }
}

export async function benchmarkApiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${BENCHMARK_API_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw await parseBenchmarkApiError(response);
  }
  return (await response.json()) as T;
}

export interface BenchmarkPageQuery {
  page: number;
  pageSize: number;
  totalSnapshot?: string | null;
}

export function benchmarkPageQuery(query: BenchmarkPageQuery): string {
  const params = new URLSearchParams({
    page: String(query.page),
    page_size: String(query.pageSize),
  });
  if (query.totalSnapshot) {
    params.set("total_snapshot", query.totalSnapshot);
  }
  return params.toString();
}

export function listBenchmarkSuites(
  query: Omit<BenchmarkPageQuery, "totalSnapshot">,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkSuiteSummary>> {
  return benchmarkApiRequest(`/suites?${benchmarkPageQuery(query)}`, { signal });
}

export async function getBenchmarkSuite(
  suiteId: string,
  signal?: AbortSignal,
): Promise<BenchmarkSuiteDetail> {
  const response = await benchmarkApiRequest<{ suite: BenchmarkSuiteDetail }>(
    `/suites/${encodeURIComponent(suiteId)}`,
    { signal },
  );
  return response.suite;
}

export function listBenchmarkRuns(
  query: BenchmarkPageQuery,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkSuiteRun>> {
  return benchmarkApiRequest(`/runs?${benchmarkPageQuery(query)}`, { signal });
}

export async function getBenchmarkRun(
  runId: string,
  signal?: AbortSignal,
): Promise<BenchmarkSuiteRun> {
  const response = await benchmarkApiRequest<{ run: BenchmarkSuiteRun }>(
    `/runs/${encodeURIComponent(runId)}`,
    { signal },
  );
  return response.run;
}

export async function submitBenchmarkRun(
  request: BenchmarkRunSubmission,
  signal?: AbortSignal,
): Promise<BenchmarkSuiteRun> {
  const response = await benchmarkApiRequest<{ run: BenchmarkSuiteRun }>(
    "/runs",
    {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    },
  );
  return response.run;
}

export async function changeBenchmarkRunLifecycle(
  runId: string,
  command: "cancel" | "resume",
  expectedRevision: number,
  signal?: AbortSignal,
): Promise<BenchmarkSuiteRun> {
  const response = await benchmarkApiRequest<{ run: BenchmarkSuiteRun }>(
    `/runs/${encodeURIComponent(runId)}/${command}`,
    {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
      signal,
    },
  );
  return response.run;
}

export function listBenchmarkCases(
  runId: string,
  query: Omit<BenchmarkPageQuery, "totalSnapshot">,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkCaseResult>> {
  return benchmarkApiRequest(
    `/runs/${encodeURIComponent(runId)}/cases?${benchmarkPageQuery(query)}`,
    { signal },
  );
}

export function listBenchmarkExperiments(
  query: Omit<BenchmarkPageQuery, "totalSnapshot">,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkExperiment>> {
  return benchmarkApiRequest(`/experiments?${benchmarkPageQuery(query)}`, {
    signal,
  });
}

export function listBenchmarkIterations(
  query: Omit<BenchmarkPageQuery, "totalSnapshot">,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkFirstLiveIteration>> {
  return benchmarkApiRequest(`/iterations?${benchmarkPageQuery(query)}`, {
    signal,
  });
}

export async function getBenchmarkIteration(
  iterationId: string,
  signal?: AbortSignal,
): Promise<BenchmarkFirstLiveIteration> {
  const response = await benchmarkApiRequest<{
    iteration: BenchmarkFirstLiveIteration;
  }>(`/iterations/${encodeURIComponent(iterationId)}`, { signal });
  return response.iteration;
}

export async function getBenchmarkSuiteArtifact(
  runId: string,
  signal?: AbortSignal,
): Promise<BenchmarkSuiteArtifact> {
  const response = await benchmarkApiRequest<{
    artifact: BenchmarkSuiteArtifact;
  }>(`/runs/${encodeURIComponent(runId)}/artifact`, { signal });
  return response.artifact;
}

export function listBenchmarkComparisons(
  query: Omit<BenchmarkPageQuery, "totalSnapshot">,
  signal?: AbortSignal,
): Promise<BenchmarkPage<BenchmarkComparison>> {
  return benchmarkApiRequest(`/comparisons?${benchmarkPageQuery(query)}`, {
    signal,
  });
}

export async function getBenchmarkComparison(
  comparisonId: string,
  signal?: AbortSignal,
): Promise<BenchmarkComparison> {
  const response = await benchmarkApiRequest<{
    comparison: BenchmarkComparison;
  }>(`/comparisons/${encodeURIComponent(comparisonId)}`, { signal });
  return response.comparison;
}

async function parseBenchmarkApiError(
  response: Response,
): Promise<BenchmarkApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const root = isRecord(payload) ? payload : {};
  const candidate = isRecord(root.detail) ? root.detail : root;
  const detail = candidate as BenchmarkErrorDetail;
  return new BenchmarkApiError({
    status: response.status,
    code:
      typeof detail.error === "string"
        ? detail.error
        : "benchmark_request_failed",
    message:
      typeof detail.message === "string"
        ? detail.message
        : `评测接口请求失败：${response.status}`,
    requestId:
      typeof detail.request_id === "string" ? detail.request_id : null,
    details: isRecord(detail.details) ? detail.details : {},
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
