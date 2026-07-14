import assert from "node:assert/strict";

import {
  canRetryEvaluation,
  evaluationErrorMessage,
  evaluationFieldLabel,
  evaluationMatchBasisLabel,
  evaluationModelLabel,
  evaluationPhaseLabels,
  evaluationProgressText,
  evaluationStatusLabels,
  evaluationTaskTitle,
  formatEvaluationScore,
  groupComparisonsByIssue,
  isTerminalEvaluation,
  issueTypeLabels,
  modelIdentityLabel,
  previewIndependenceLabel,
  qualityStateLabel,
  shouldPollEvaluation,
  toggleEvaluationRunSelection,
  visibleEvaluationRuns,
} from "../../src/lib/agent-evaluation/evaluation-view-model";
import type {
  EligibleEvaluationRun,
  KnowledgeEvaluation,
  KnowledgeEvaluationComparison,
} from "../../src/lib/types/agent-evaluation";

const tests: Array<[string, () => void]> = [];

function test(name: string, run: () => void): void {
  tests.push([name, run]);
}

test("内部评估状态映射为中文文案", () => {
  assert.equal(evaluationStatusLabels.completed_with_warnings, "已完成但有警告");
  assert.equal(evaluationPhaseLabels.explaining, "正在生成差异说明");
  assert.equal(issueTypeLabels.judge_failed, "裁判调用失败");
  assert.equal(issueTypeLabels.judge_inconclusive, "有效裁判结果不足");
  assert.equal(qualityStateLabel("not_comparable"), "不可比较");
});

test("字段与匹配依据使用准确中文说明", () => {
  assert.equal(evaluationFieldLabel(null, "aliases"), "别名");
  assert.equal(evaluationFieldLabel(null, "role_type"), "角色定位");
  assert.equal(
    evaluationMatchBasisLabel("accepted_name"),
    "评测集认可名称一致",
  );
  assert.equal(
    evaluationMatchBasisLabel("evidence_anchor"),
    "同章原文证据一致",
  );
  assert.equal(
    evaluationMatchBasisLabel("event_semantic"),
    "事件名称与内容语义一致",
  );
  assert.equal(
    evaluationMatchBasisLabel("unexpected_internal_value"),
    "匹配依据未知",
  );
});

test("百分比分数保持零值并把空值显示为不适用", () => {
  assert.equal(formatEvaluationScore(0), "0%");
  assert.equal(formatEvaluationScore(0.8734), "87.34%");
  assert.equal(formatEvaluationScore(null), "不适用");
});

test("选择新任务时替换已有选择，取消时清空", () => {
  const selected = ["run-1"];
  assert.deepEqual(
    toggleEvaluationRunSelection(selected, "run-2"),
    ["run-2"],
  );
  assert.deepEqual(
    toggleEvaluationRunSelection(selected, "run-1"),
    [],
  );
});

test("展示名称不回退暴露内部任务编号或模型标识", () => {
  const unknown = {
    ...run("full"),
    display_title: "",
    model_display_name: "",
    chapter_id: "chapter-internal-id",
    requested_model_name: "internal-model-name",
  };
  assert.equal(evaluationTaskTitle(unknown), "未命名章节");
  assert.equal(evaluationModelLabel(unknown), "模型信息未记录");
  assert.equal(
    modelIdentityLabel({
      ...unknown.generation_model_identity,
      known: false,
      model_id: "internal-model-name",
    }),
    "模型信息未记录",
  );
});

test("默认只显示完整可评估任务，展开后保留降级和不可评估项", () => {
  const runs = [run("full"), run("diagnostic"), run("ineligible")];
  assert.deepEqual(
    visibleEvaluationRuns(runs, false).map(item => item.eligibility_level),
    ["full"],
  );
  assert.equal(visibleEvaluationRuns(runs, true).length, 3);
});

test("确定性和裁判阶段使用各自的真实进度分母", () => {
  const deterministic = evaluation({
    status: "running",
    phase: "deterministic",
    progress: {
      run_total: 5,
      run_completed: 2,
      judge_card_total: 67,
      judge_card_completed: 0,
    },
  });
  const judging = evaluation({
    status: "running",
    phase: "judging",
    progress: {
      run_total: 5,
      run_completed: 5,
      judge_card_total: 67,
      judge_card_completed: 18,
    },
  });
  assert.equal(
    evaluationProgressText(deterministic),
    "正在进行确定性比对 · 2/5 个任务",
  );
  assert.equal(
    evaluationProgressText(judging),
    "正在进行语义裁判 · 18/67 张卡",
  );
});

test("终态停止轮询且仅失败和警告结果允许重试", () => {
  const running = evaluation({ status: "running", phase: "judging" });
  const failed = evaluation({ status: "failed", phase: "finished" });
  const completed = evaluation({ status: "completed", phase: "finished" });
  assert.equal(shouldPollEvaluation(running), true);
  assert.equal(shouldPollEvaluation(failed), false);
  assert.equal(isTerminalEvaluation(completed.status), true);
  assert.equal(canRetryEvaluation(failed), true);
  assert.equal(canRetryEvaluation(completed), false);
});

test("进程中断使用明确中文解释而不是把内部错误码直接当主文案", () => {
  const interrupted = evaluation({
    status: "failed",
    phase: "finished",
    error_code: "EVALUATION_PROCESS_INTERRUPTED",
  });
  assert.equal(
    evaluationErrorMessage(interrupted),
    "评估进程已中断，已保留冻结输入",
  );
});

test("模型独立性完全使用后端结论并优先暴露自评和未知状态", () => {
  const base = {
    run_id: "run-1",
    case_id: "chapter_001",
    display_title: "第一章",
    model_display_name: "DeepSeek V4 Pro",
    eligibility_level: "full" as const,
    reason: null,
    generation_model_identity: run("full").generation_model_identity,
    expected_card_count: 1,
    estimated_matched_card_count: 1,
    estimated_judge_card_count: 1,
  };
  assert.equal(
    previewIndependenceLabel([
      { ...base, independence_level: "different_model" },
      { ...base, run_id: "run-2", independence_level: "same_provider_family" },
    ]),
    "同供应商模型",
  );
  assert.equal(
    previewIndependenceLabel([
      { ...base, independence_level: "unknown" },
      { ...base, run_id: "run-2", independence_level: "same_model" },
    ]),
    "同模型自评",
  );
});

test("差异按问题类型稳定分组", () => {
  const groups = groupComparisonsByIssue([
    comparison("missing_candidate", "a"),
    comparison("field_difference", "b"),
    comparison("missing_candidate", "c"),
    comparison("ambiguous_match", "d"),
  ]);
  assert.deepEqual(
    groups.missing_candidate?.map(item => item.comparison_id),
    ["a", "c"],
  );
  assert.equal(groups.field_difference?.length, 1);
  assert.equal(groups.ambiguous_match?.length, 1);
});

for (const [name, runTest] of tests) {
  runTest();
  console.log(`ok - ${name}`);
}

function run(
  eligibilityLevel: EligibleEvaluationRun["eligibility_level"],
): EligibleEvaluationRun {
  return {
    run_id: `run-${eligibilityLevel}`,
    case_id: "chapter_001",
    display_title: "第一章",
    model_display_name: "DeepSeek Chat",
    scope_type: "chapter",
    chapter_id: "chapter-001",
    chapter_title: "第一章",
    started_at: "2026-07-11T08:00:00Z",
    generation_model_identity: {
      provider: "deepseek",
      model_id: "deepseek-chat",
      family: "deepseek-chat",
      endpoint_kind: "openai_compatible",
      fingerprint: null,
      known: true,
      unknown_reason: null,
    },
    prompt_version: "knowledge-extraction",
    schema_version: "knowledge-card",
    eligibility_level: eligibilityLevel,
    reason: eligibilityLevel === "full" ? null : "仅用于测试",
  };
}

function evaluation(
  overrides: Partial<KnowledgeEvaluation> = {},
): KnowledgeEvaluation {
  return {
    evaluation_id: "knowledge_eval_20260711_120000_a1b2c3",
    parent_evaluation_id: null,
    evaluation_mode: "deterministic_and_judge",
    lifecycle: "draft",
    status: "pending",
    phase: "queued",
    dataset: {
      dataset_id: "dataset-id",
      checksum: "sha256",
    },
    metric_profile_id: "knowledge_extraction_balanced",
    judge: {
      model_identity: null,
      self_judge: false,
      independence_by_run: {},
    },
    progress: {
      run_total: 1,
      run_completed: 0,
      judge_card_total: 1,
      judge_card_completed: 0,
    },
    run_results: [],
    aggregate_metrics: {},
    warnings: [],
    errors: [],
    error_code: null,
    created_at: "2026-07-11T08:00:00Z",
    started_at: null,
    updated_at: "2026-07-11T08:00:00Z",
    heartbeat_at: null,
    finished_at: null,
    ...overrides,
  };
}

function comparison(
  issueType: KnowledgeEvaluationComparison["issue_type"],
  id: string,
): KnowledgeEvaluationComparison {
  return {
    comparison_id: id,
    run_id: "extract_run_20260711_120000_a1b2c3",
    knowledge_type: "character",
    issue_type: issueType,
    display_title: "秦浩轩",
  };
}
