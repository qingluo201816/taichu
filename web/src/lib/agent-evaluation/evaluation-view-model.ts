import type {
  EligibleEvaluationRun,
  EvaluationIssueType,
  EvaluationKnowledgeType,
  EvaluationMetrics,
  EvaluationNotice,
  EvaluationPhase,
  EvaluationQualityState,
  EvaluationStatus,
  EvaluationPreviewRun,
  KnowledgeEvaluation,
  KnowledgeEvaluationComparison,
} from "../types/agent-evaluation";

export const evaluationStatusLabels: Record<EvaluationStatus, string> = {
  pending: "等待中",
  running: "评估中",
  completed: "已完成",
  completed_with_warnings: "已完成但有警告",
  failed: "失败",
};

export const evaluationPhaseLabels: Record<EvaluationPhase, string> = {
  queued: "正在校验评测集",
  deterministic: "正在进行确定性比对",
  judging: "正在进行语义裁判",
  aggregating: "正在聚合结果",
  finished: "评估已结束",
};

export const qualityStateLabels: Record<EvaluationQualityState, string> = {
  stable: "表现稳定",
  usable: "基本可用",
  needs_review: "需要复核",
  high_risk: "高风险",
  not_comparable: "不可比较",
};

export const issueTypeLabels: Record<EvaluationIssueType, string> = {
  missing_candidate: "漏提取",
  extra_candidate: "多提取",
  field_difference: "字段不同",
  semantic_issue: "语义问题",
  evidence_issue: "证据问题",
  judge_disagreement: "裁判意见不一致",
};

export const knowledgeTypeLabels: Record<EvaluationKnowledgeType, string> = {
  character: "角色",
  realm: "境界",
  technique: "功法",
  location: "地点",
  faction: "势力",
  item: "物品",
  rule: "规则",
  event: "事件",
};

export const errorCodeMessages: Record<string, string> = {
  EVALUATION_DATASET_NOT_FOUND: "未找到指定评测集",
  EVALUATION_DATASET_INVALID: "评测集校验未通过",
  EVALUATION_SCOPE_MISMATCH: "所选任务与评测范围不匹配",
  EVALUATION_SOURCE_CHANGED: "任务使用的正文与评测集来源不一致",
  EVALUATION_RUN_NOT_FOUND: "未找到指定历史任务",
  EVALUATION_CANDIDATE_SNAPSHOT_MISSING: "历史任务缺少可冻结的候选结果",
  EVALUATION_JUDGE_UNAVAILABLE: "语义裁判当前不可用",
  EVALUATION_PROCESS_INTERRUPTED: "评估进程已中断，已保留冻结输入",
  EVALUATION_ALREADY_RUNNING: "相同评估正在执行，请勿重复提交",
  EVALUATION_INVALID_TRANSITION: "当前状态不允许执行此操作",
  EVALUATION_ID_INVALID: "评估标识格式不正确",
  EVALUATION_SNAPSHOT_CORRUPTED: "评估快照损坏，无法继续执行",
  EVALUATION_NOT_FOUND: "未找到指定评估记录",
};

export function isTerminalEvaluation(status: EvaluationStatus): boolean {
  return (
    status === "completed" ||
    status === "completed_with_warnings" ||
    status === "failed"
  );
}

export function shouldPollEvaluation(evaluation: KnowledgeEvaluation | null): boolean {
  return Boolean(evaluation && !isTerminalEvaluation(evaluation.status));
}

export function canRetryEvaluation(evaluation: KnowledgeEvaluation): boolean {
  return (
    evaluation.lifecycle !== "rejected" &&
    (evaluation.status === "failed" ||
      evaluation.status === "completed_with_warnings")
  );
}

export function evaluationProgressText(evaluation: KnowledgeEvaluation): string {
  if (evaluation.status === "completed_with_warnings") {
    return "语义裁判部分失败，确定性结果已保留";
  }
  if (evaluation.status === "failed") {
    return evaluation.error_code
      ? errorCodeMessages[evaluation.error_code] ?? "效果评估失败"
      : "效果评估失败";
  }
  if (evaluation.phase === "deterministic") {
    return `${evaluationPhaseLabels.deterministic} · ${evaluation.progress.run_completed}/${evaluation.progress.run_total} 个任务`;
  }
  if (evaluation.phase === "judging") {
    return `${evaluationPhaseLabels.judging} · ${evaluation.progress.judge_card_completed}/${evaluation.progress.judge_card_total} 张卡`;
  }
  return evaluationPhaseLabels[evaluation.phase];
}

export function formatEvaluationScore(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "不适用";
  }
  const percentage = Math.round(value * 10000) / 100;
  return `${percentage.toFixed(percentage % 1 === 0 ? 0 : 2)}%`;
}

export function metricValue(
  metrics: EvaluationMetrics | null | undefined,
  ...keys: string[]
): number | null {
  if (!metrics) return null;
  for (const key of keys) {
    const value = metrics[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

export function evaluationTaskTitle(run: EligibleEvaluationRun): string {
  if (run.scope_type === "chapter_batch") {
    const count =
      run.total_chapter_count ??
      run.chapter_ids?.length ??
      run.chapter_titles?.length ??
      0;
    return `批量知识沉淀 · ${count} 章`;
  }
  return run.chapter_title || run.chapter_id || "未命名任务";
}

export function evaluationModelLabel(run: EligibleEvaluationRun): string {
  const identity = run.generation_model_identity;
  if (identity?.known && identity.model_id) {
    return identity.model_id;
  }
  return run.requested_model_name || run.model_name || "模型身份未知";
}

export function visibleEvaluationRuns(
  runs: EligibleEvaluationRun[],
  showDiagnostic: boolean,
): EligibleEvaluationRun[] {
  return runs.filter(run =>
    showDiagnostic ? true : run.eligibility_level === "full",
  );
}

export function selectableEvaluationRun(run: EligibleEvaluationRun): boolean {
  return run.eligibility_level !== "ineligible";
}

export function toggleEvaluationRunSelection(
  selected: string[],
  runId: string,
  maxCount = 10,
): string[] {
  if (selected.includes(runId)) {
    return selected.filter(item => item !== runId);
  }
  return selected.length >= maxCount ? selected : [...selected, runId];
}

export function comparisonMatchesIssue(
  comparison: KnowledgeEvaluationComparison,
  issueType: EvaluationIssueType | "all",
): boolean {
  return issueType === "all" || comparison.issue_type === issueType;
}

export function groupComparisonsByIssue(
  comparisons: KnowledgeEvaluationComparison[],
): Partial<Record<EvaluationIssueType, KnowledgeEvaluationComparison[]>> {
  return comparisons.reduce<
    Partial<Record<EvaluationIssueType, KnowledgeEvaluationComparison[]>>
  >((groups, item) => {
    const group = groups[item.issue_type] ?? [];
    groups[item.issue_type] = [...group, item];
    return groups;
  }, {});
}

export function qualityStateLabel(
  state: EvaluationQualityState | null | undefined,
): string {
  return state ? qualityStateLabels[state] : "暂无结论";
}

export function evaluationErrorMessage(evaluation: KnowledgeEvaluation): string {
  if (evaluation.error_message) return evaluation.error_message;
  if (evaluation.error_code) {
    return errorCodeMessages[evaluation.error_code] ?? "效果评估失败";
  }
  return noticeMessage(evaluation.errors[0]) || "效果评估失败";
}

export function noticeMessage(
  notice: string | EvaluationNotice | null | undefined,
): string {
  if (typeof notice === "string") return notice;
  return notice?.message ?? "";
}

export function shortChecksum(checksum: string | null | undefined): string {
  if (!checksum) return "无校验摘要";
  return checksum.length > 12 ? checksum.slice(0, 12) : checksum;
}

export function previewIndependenceLabel(runs: EvaluationPreviewRun[]): string {
  const levels = new Set(runs.map(run => run.independence_level));
  if (levels.has("same_model")) return "同模型自评";
  if (levels.has("unknown")) return "模型独立性未知";
  if (levels.has("same_provider_family")) return "同供应商模型";
  if (levels.has("different_model")) return "不同模型";
  return "未启用裁判";
}
