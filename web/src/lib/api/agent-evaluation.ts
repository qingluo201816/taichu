import { apiRequest } from "@/lib/api-client";
import type {
  CreateKnowledgeEvaluationRequest,
  EligibleEvaluationRun,
  EligibleEvaluationRunListResponse,
  EvaluationDatasetListResponse,
  EvaluationJudgeCall,
  EvaluationJudgeCallResponse,
  KnowledgeEvaluation,
  KnowledgeEvaluationComparison,
  KnowledgeEvaluationComparisonListResponse,
  KnowledgeEvaluationDetailResponse,
  KnowledgeEvaluationListResponse,
  KnowledgeEvaluationPreview,
} from "@/lib/types/agent-evaluation";

const PREFIX = "/api/agent-evaluations/knowledge-extraction";

export async function listEvaluationDatasets(): Promise<EvaluationDatasetListResponse> {
  const payload = await apiRequest<unknown>(`${PREFIX}/datasets`);
  return { datasets: collection(payload, "datasets") } as EvaluationDatasetListResponse;
}

export async function listEligibleEvaluationRuns(
  datasetId: string,
  page = 1,
  pageSize = 50,
): Promise<EligibleEvaluationRunListResponse> {
  const params = new URLSearchParams({
    dataset_id: datasetId,
    page: String(page),
    page_size: String(pageSize),
  });
  const payload = await apiRequest<unknown>(`${PREFIX}/eligible-runs?${params}`);
  const runs = collection<EligibleEvaluationRun>(payload, "runs");
  const metadata = objectValue(payload);
  return {
    runs,
    page: numberValue(metadata?.page, page),
    page_size: numberValue(metadata?.page_size, pageSize),
    total: numberValue(metadata?.total, runs.length),
  };
}

export async function previewKnowledgeEvaluation(
  request: CreateKnowledgeEvaluationRequest,
): Promise<KnowledgeEvaluationPreview> {
  const payload = await apiRequest<unknown>(`${PREFIX}/preview`, {
    method: "POST",
    body: JSON.stringify(request),
  });
  return nestedObject<KnowledgeEvaluationPreview>(payload, "preview");
}

export async function createKnowledgeEvaluation(
  request: CreateKnowledgeEvaluationRequest,
): Promise<KnowledgeEvaluation> {
  const payload = await apiRequest<unknown>(`${PREFIX}/evaluations`, {
    method: "POST",
    body: JSON.stringify(request),
  });
  return evaluationFrom(payload);
}

export async function listKnowledgeEvaluations(
  page = 1,
  pageSize = 20,
  status = "all",
): Promise<KnowledgeEvaluationListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    status,
  });
  const payload = await apiRequest<unknown>(`${PREFIX}/evaluations?${params}`);
  const evaluations = collection<unknown>(payload, "evaluations").map(
    evaluationFrom,
  );
  const metadata = objectValue(payload);
  return {
    evaluations,
    page: numberValue(metadata?.page, page),
    page_size: numberValue(metadata?.page_size, pageSize),
    total: numberValue(metadata?.total, evaluations.length),
  };
}

export async function getKnowledgeEvaluation(
  evaluationId: string,
): Promise<KnowledgeEvaluationDetailResponse> {
  const payload = await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}`,
  );
  return { evaluation: evaluationFrom(payload) };
}

export async function listKnowledgeEvaluationComparisons(
  evaluationId: string,
  options: {
    page?: number;
    pageSize?: number;
    runId?: string;
    knowledgeType?: string;
    issueType?: string;
  } = {},
): Promise<KnowledgeEvaluationComparisonListResponse> {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 50;
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (options.runId) params.set("run_id", options.runId);
  if (options.knowledgeType) params.set("knowledge_type", options.knowledgeType);
  if (options.issueType && options.issueType !== "all") {
    params.set("issue_type", options.issueType);
  }
  const payload = await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}/comparisons?${params}`,
  );
  const comparisons = collection<unknown>(payload, "comparisons").map(
    normalizeComparison,
  );
  const metadata = objectValue(payload);
  return {
    comparisons,
    page: numberValue(metadata?.page, page),
    page_size: numberValue(metadata?.page_size, pageSize),
    total: numberValue(metadata?.total, comparisons.length),
  };
}

export async function getKnowledgeEvaluationJudgeCall(
  evaluationId: string,
  callId: string,
): Promise<EvaluationJudgeCallResponse> {
  const payload = await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}/judge-calls/${encodeURIComponent(callId)}`,
  );
  return {
    judge_call: nestedObject<EvaluationJudgeCall>(payload, "judge_call"),
  };
}

export async function retryKnowledgeEvaluation(
  evaluationId: string,
): Promise<KnowledgeEvaluation> {
  const payload = await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}/retry`,
    { method: "POST" },
  );
  return evaluationFrom(payload);
}

export async function confirmKnowledgeEvaluation(
  evaluationId: string,
): Promise<KnowledgeEvaluation> {
  const payload = await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}/confirm`,
    { method: "POST" },
  );
  return evaluationFrom(payload);
}

export async function rejectKnowledgeEvaluation(
  evaluationId: string,
): Promise<void> {
  await apiRequest<unknown>(
    `${PREFIX}/evaluations/${encodeURIComponent(evaluationId)}`,
    { method: "DELETE" },
  );
}

function evaluationFrom(payload: unknown): KnowledgeEvaluation {
  type FlatEvaluationRecord = Partial<KnowledgeEvaluation> & {
    dataset_id?: string;
    dataset_label?: string;
    dataset_checksum?: string;
  };
  const value = nestedObject<FlatEvaluationRecord>(payload, "evaluation");
  const dataset = objectValue(value.dataset) ?? {};
  const judge = objectValue(value.judge) ?? {};
  const progress = objectValue(value.progress) ?? {};
  const createdAt =
    typeof value.created_at === "string" ? value.created_at : new Date(0).toISOString();
  return {
    ...value,
    evaluation_id:
      typeof value.evaluation_id === "string" ? value.evaluation_id : "",
    parent_evaluation_id:
      typeof value.parent_evaluation_id === "string"
        ? value.parent_evaluation_id
        : null,
    evaluation_mode:
      value.evaluation_mode === "deterministic_only"
        ? "deterministic_only"
        : "deterministic_and_judge",
    lifecycle:
      value.lifecycle === "confirmed" || value.lifecycle === "rejected"
        ? value.lifecycle
        : "draft",
    status: value.status ?? "pending",
    phase: value.phase ?? "queued",
    dataset: {
      ...(dataset as KnowledgeEvaluation["dataset"]),
      dataset_id:
        typeof dataset.dataset_id === "string"
          ? dataset.dataset_id
          : value.dataset_id ?? "",
      display_name:
        typeof dataset.display_name === "string"
          ? dataset.display_name
          : value.dataset_label,
      checksum:
        typeof dataset.checksum === "string"
          ? dataset.checksum
          : value.dataset_checksum ?? "",
    },
    metric_profile_id:
      typeof value.metric_profile_id === "string"
        ? value.metric_profile_id
        : "knowledge_extraction_balanced",
    judge: {
      ...(judge as KnowledgeEvaluation["judge"]),
      model_identity:
        objectValue(judge.model_identity) as KnowledgeEvaluation["judge"]["model_identity"],
      self_judge:
        typeof judge.self_judge === "boolean" ? judge.self_judge : null,
      independence_by_run:
        objectValue(judge.independence_by_run) as KnowledgeEvaluation["judge"]["independence_by_run"] ?? {},
    },
    progress: {
      run_total: numberValue(progress.run_total, 0),
      run_completed: numberValue(progress.run_completed, 0),
      judge_card_total: numberValue(progress.judge_card_total, 0),
      judge_card_completed: numberValue(progress.judge_card_completed, 0),
    },
    run_results: Array.isArray(value.run_results) ? value.run_results : [],
    aggregate_metrics: value.aggregate_metrics ?? {},
    warnings: Array.isArray(value.warnings) ? value.warnings : [],
    errors: Array.isArray(value.errors) ? value.errors : [],
    error_code: typeof value.error_code === "string" ? value.error_code : null,
    error_message:
      typeof value.error_message === "string" ? value.error_message : null,
    created_at: createdAt,
    started_at: typeof value.started_at === "string" ? value.started_at : null,
    updated_at:
      typeof value.updated_at === "string" ? value.updated_at : createdAt,
    heartbeat_at:
      typeof value.heartbeat_at === "string" ? value.heartbeat_at : null,
    finished_at:
      typeof value.finished_at === "string" ? value.finished_at : null,
  } as KnowledgeEvaluation;
}

function normalizeComparison(
  payload: unknown,
  index: number,
): KnowledgeEvaluationComparison {
  const value = objectValue(payload) ?? {};
  const expectedCard = objectValue(value.expected_card);
  const actualCard = objectValue(value.actual_card);
  const judgeResult = objectValue(value.judge_result);
  const fieldDiffs = Array.isArray(value.field_diffs)
    ? value.field_diffs.map(item => {
        const diff = objectValue(item) ?? {};
        return {
          field:
            stringValue(diff.field) || stringValue(diff.field_name) || "未知字段",
          label: stringValue(diff.label) || null,
          issue: stringValue(diff.issue) || stringValue(diff.reason) || null,
          expected:
            "expected" in diff ? diff.expected : diff.expected_value ?? null,
          actual: "actual" in diff ? diff.actual : diff.actual_value ?? null,
        };
      })
    : [];
  const runId = stringValue(value.run_id);
  const expectedId = stringValue(value.expected_card_id);
  const actualId =
    stringValue(value.actual_review_item_id) ||
    stringValue(value.actual_candidate_id);
  const comparisonId =
    stringValue(value.comparison_id) ||
    `${runId}:${expectedId || "none"}:${actualId || "none"}:${index}`;
  return {
    ...(value as Partial<KnowledgeEvaluationComparison>),
    comparison_id: comparisonId,
    run_id: runId,
    case_id: stringValue(value.case_id) || null,
    expected_card_id: expectedId || null,
    actual_review_item_id: actualId || null,
    knowledge_type:
      (stringValue(value.knowledge_type) || "event") as KnowledgeEvaluationComparison["knowledge_type"],
    issue_type:
      (stringValue(value.issue_type) || "field_difference") as KnowledgeEvaluationComparison["issue_type"],
    display_title:
      stringValue(value.display_title) ||
      stringValue(expectedCard?.name) ||
      stringValue(actualCard?.name) ||
      expectedId ||
      actualId ||
      "未命名知识卡",
    match_basis:
      stringValue(value.match_basis) || stringValue(value.match_kind) || null,
    expected_card: expectedCard,
    actual_card: actualCard,
    field_diffs: fieldDiffs,
    judge_reason:
      stringValue(value.judge_reason) ||
      stringValue(judgeResult?.reason) ||
      null,
    judge_confidence:
      numberOrNull(value.judge_confidence) ??
      numberOrNull(judgeResult?.confidence),
    judge_status:
      stringValue(value.judge_status) || stringValue(judgeResult?.status) || null,
    judge_call_ids: stringArray(
      value.judge_call_ids ?? judgeResult?.judge_call_ids,
    ),
  };
}

function collection<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }
  const record = objectValue(payload);
  const value = record?.[key] ?? record?.items;
  return Array.isArray(value) ? (value as T[]) : [];
}

function nestedObject<T>(payload: unknown, key: string): T {
  const record = objectValue(payload);
  const value = objectValue(record?.[key]);
  return (value ?? record ?? {}) as T;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}
