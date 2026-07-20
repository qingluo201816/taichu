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
  EvaluationModelIdentity,
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
  explaining: "正在生成差异说明",
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
  ambiguous_match: "匹配待复核",
  field_difference: "字段不同",
  semantic_issue: "语义问题",
  evidence_issue: "证据问题",
  judge_disagreement: "裁判评分存在分歧",
  judge_inconclusive: "有效裁判结果不足",
  judge_failed: "裁判调用失败",
};

export function evaluationFieldLabel(
  label: string | null | undefined,
  field: string,
): string {
  if (label) return label;
  const labels: Record<string, string> = {
    name: "名称",
    aliases: "别名",
    summary: "摘要",
    description: "事件说明",
    source_note: "来源说明",
    source_origin: "来源方式",
    evidence_excerpt: "原文证据",
    chapter_id: "所属章节",
    type: "知识类型",
    lifecycle: "生命周期",
    appearance_chapter_count: "出现章节数",
    role_type: "角色定位",
    identity: "身份",
    relationship_summary: "关系摘要",
    death_chapter_id: "死亡章节",
    current_realm_text: "当前境界",
    first_seen_chapter_id: "首次出现章节",
    last_seen_chapter_id: "最近出现章节",
    system: "修炼体系",
    level_order: "境界排序值",
    technique_type: "功法类型",
    grade: "品阶",
    practice_condition: "修炼条件",
    owner_faction_id: "所属势力",
    controlling_faction_id: "控制势力",
    faction_type: "势力类型",
    leader_id: "当前首领",
    item_type: "物品类型",
    current_holder_id: "当前持有人",
    exceptions: "例外情况",
  };
  return labels[field] ?? "字段内容";
}

export function evaluationMatchBasisLabel(
  value: string | null | undefined,
): string {
  const labels: Record<string, string> = {
    exact_name: "名称一致",
    accepted_name: "评测集认可名称一致",
    alias_cross: "名称与别名对应",
    evidence_anchor: "同章原文证据一致",
    event_semantic: "事件名称与内容语义一致",
    ambiguous_match: "存在多个可能对应，等待复核",
  };
  return labels[value ?? ""] ?? "匹配依据未知";
}

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
  EVALUATION_ID_INVALID: "请求参数格式不正确",
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
  return run.display_title || "未命名章节";
}

export function evaluationModelLabel(run: EligibleEvaluationRun): string {
  return run.model_display_name || "模型信息未记录";
}

export function modelIdentityLabel(
  identity: EvaluationModelIdentity | null | undefined,
): string {
  if (!identity?.known || !identity.model_id) return "模型信息未记录";
  const labels: Record<string, string> = {
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek-chat": "DeepSeek Chat",
    "deepseek-reasoner": "DeepSeek Reasoner",
  };
  return labels[identity.model_id] ?? "已配置模型";
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
): string[] {
  if (selected.includes(runId)) {
    return selected.filter(item => item !== runId);
  }
  return [runId];
}

export function evaluationIndependenceLabel(evaluation: KnowledgeEvaluation): string {
  const levels = Object.values(evaluation.judge?.independence_by_run ?? {});
  if (levels.includes("same_model")) return "同模型自评";
  if (levels.includes("unknown")) return "模型独立性未知";
  if (levels.includes("same_provider_family")) return "同供应商模型";
  if (levels.includes("different_model")) return "不同模型";
  return "未启用语义裁判";
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

export function previewIndependenceLabel(runs: EvaluationPreviewRun[]): string {
  const levels = new Set(runs.map(run => run.independence_level));
  if (levels.has("same_model")) return "同模型自评";
  if (levels.has("unknown")) return "模型独立性未知";
  if (levels.has("same_provider_family")) return "同供应商模型";
  if (levels.has("different_model")) return "不同模型";
  return "未启用裁判";
}

export function buildKnowledgeEvaluationCodexAnalysisRequest(
  evaluation: KnowledgeEvaluation,
): string {
  const evaluationRoot =
    "project_assets/derived/agent_evaluations/knowledge_extraction/" +
    evaluation.evaluation_id;
  const datasetLabel =
    evaluation.dataset.display_name ||
    evaluation.dataset.name ||
    evaluation.dataset.dataset_id;
  const runSummary = evaluation.run_results.map(run => ({
    run_id: run.run_id,
    case_id: run.case_id ?? null,
    display_title: run.display_title ?? run.chapter_title ?? "未命名章节",
    eligibility_level: run.eligibility_level ?? null,
    metrics: run.metrics ?? {},
    semantic_score: run.semantic_score ?? null,
    judge_coverage: run.judge_coverage ?? null,
    overall_quality_score: run.overall_quality_score ?? null,
    final_quality_state: run.final_quality_state ?? null,
    warnings: (run.warnings ?? []).map(noticeMessage),
  }));
  const diagnostics = [
    ...(evaluation.warnings ?? []).map(noticeMessage),
    ...(evaluation.errors ?? []).map(noticeMessage),
  ].filter(Boolean);

  return `请对太初“知识沉淀 Workflow”的本次评测做一次证据化诊断。先分析，不要直接修改代码、评测集、正文或 MongoDB；完成后给出等待我确认的修订清单。

本次评测定位：
- 评估标识：${evaluation.evaluation_id}
- 评估对象：${evaluation.subject_title || "未命名章节"}
- 评测集：${datasetLabel}（${evaluation.dataset.dataset_id}）
- 评测集校验和：${evaluation.dataset.checksum}
- 状态：${evaluationStatusLabels[evaluation.status]}
- 报告生命周期：${evaluation.lifecycle}
- 创建时间：${evaluation.created_at}
- 快照根哈希：${evaluation.snapshot_root_hash || "未记录"}
- 持久化目录（相对仓库根目录）：${evaluationRoot}

请从当前仓库直接读取并交叉核对这些真实资料：
1. \`${evaluationRoot}/summary.json\`。
2. \`${evaluationRoot}/input_snapshot/_snapshot_manifest.json\`、\`request.json\`、\`dataset_manifest.json\`、\`metric_profile.json\` 与 \`evaluation_schema.json\`。
3. \`${evaluationRoot}/input_snapshot/runs/\`、\`cases/\`、\`chapters/\` 下的全部冻结输入。
4. \`${evaluationRoot}/judge_calls/\` 下的全部裁判调用；区分裁判协议失败、裁判分歧与 Workflow 本身的问题。
5. 当前实现：\`src/taichu/application/agents/knowledge_extraction/\`、\`src/taichu/application/services/knowledge_extraction_service.py\` 和评测实现；不要只依据历史文档推断。

分析要求：
1. 先验证评估是否完整、快照是否可读、正文与评测范围是否一致；若结果不可比较，先说明原因。
2. 汇总候选识别、结构字段、语义、证据、负样本抑制、Schema、执行覆盖和裁判覆盖的短板，不要只复述综合分。
3. 逐项检查漏提取、多提取、错误合并、重复候选、字段差异、无依据断言、证据遗漏和裁判异常；每个结论引用 run_id、case_id、候选或期望卡标识及原文证据。
4. 把确认属于 Workflow 的问题映射到当前具体节点、Prompt、Schema、聚合、匹配或质量闸门，并给出源码路径和代码证据。
5. 明确区分四类原因：评测集标注问题、裁判噪声、模型偶发波动、Workflow 可修复缺陷。没有证据时标记为待验证。
6. 给出按影响排序的最小修订方案、预期改善指标和必须补充的回归测试；不要为了单个样例硬编码小说专名或章节规则。
7. 如果仓库中存在同评测集、同范围且口径兼容的历史报告，补充前后对比；口径不兼容时不得直接比较分数。

前端携带的快速摘要仅用于定位，最终结论以持久化快照为准：

聚合指标：
\`\`\`json
${JSON.stringify(evaluation.aggregate_metrics ?? {}, null, 2)}
\`\`\`

单任务摘要：
\`\`\`json
${JSON.stringify(runSummary, null, 2)}
\`\`\`

诊断与错误：
\`\`\`json
${JSON.stringify(diagnostics, null, 2)}
\`\`\`

请按“结论 → 指标瓶颈 → 具体失败证据 → 根因定位 → 修订优先级 → 回归验证方案”的顺序输出。`;
}
