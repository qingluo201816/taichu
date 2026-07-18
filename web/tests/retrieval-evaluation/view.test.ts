import assert from "node:assert/strict";

import { resolveAppShellEscapeDestination } from "../../src/lib/app-shell-navigation";
import {
  formatPercent,
  metricAtK,
  retrievalCaseOutcome,
  retrievalEvaluationCategoryLabels,
  retrievalStrategyLabel,
} from "../../src/lib/retrieval-evaluation-view";
import type {
  RetrievalEvaluationRecord,
  RetrievalEvaluationSummary,
} from "../../src/lib/types/retrieval-evaluation";

const summary: RetrievalEvaluationSummary = {
  case_count: 60,
  relevance_case_count: 55,
  at_k: [
    { k: 1, recall: 0.86, precision: 0.92, ndcg: 0.92 },
    { k: 3, recall: 0.98, precision: 0.38, ndcg: 0.97 },
    { k: 5, recall: 1, precision: 0.24, ndcg: 0.97 },
    { k: 10, recall: 1, precision: 0.12, ndcg: 0.97 },
  ],
  mrr: 0.96,
  empty_result_accuracy: 0.2,
  forbidden_hit_rate: 0.05,
  average_latency_ms: 7.9,
  p95_latency_ms: 11,
  average_candidate_count: 11.15,
  truncation_rate: 0.05,
  content_budget_hit_rate: 0,
};

const evaluation = {
  cases: [{ case_id: "passed_case" }, { case_id: "failed_case" }],
  failures: [{ case_id: "failed_case" }],
} as RetrievalEvaluationRecord;

assert.equal(metricAtK(summary, 3)?.recall, 0.98);
assert.equal(formatPercent(0.868182), "86.8%");
assert.equal(retrievalCaseOutcome("passed_case", evaluation), "通过");
assert.equal(retrievalCaseOutcome("failed_case", evaluation), "未通过");
assert.equal(retrievalCaseOutcome("missing_case", evaluation), "未评测");
assert.equal(
  retrievalEvaluationCategoryLabels.no_answer_adversarial,
  "无答案与对抗查询",
);
assert.equal(retrievalStrategyLabel("mongo_lexical"), "MongoDB 词法召回");

assert.equal(
  resolveAppShellEscapeDestination(
    "/task-monitor/general-agent/evaluation",
  ),
  "/task-monitor",
);
assert.equal(
  resolveAppShellEscapeDestination("/task-monitor/retrieval/evaluation"),
  "/task-monitor",
);
assert.equal(resolveAppShellEscapeDestination("/knowledge"), "/home");
assert.equal(resolveAppShellEscapeDestination("/home"), null);
assert.equal(resolveAppShellEscapeDestination("/task-monitor", false), null);

console.log("统一召回评测视图与任务监控返回规则测试通过。");
