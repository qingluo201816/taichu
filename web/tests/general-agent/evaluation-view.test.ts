import assert from "node:assert/strict";

import {
  evaluationOutcomeLabel,
  generalAgentRunRequestForCase,
  generalAgentEvaluationCategoryLabels,
  isGeneralAgentRunEvaluable,
  matchingRunsForCase,
  scoreLabel,
} from "../../src/lib/general-agent-evaluation-view";
import type {
  GeneralAgentEvaluationCase,
  GeneralAgentEvaluationRecord,
} from "../../src/lib/types/general-agent-evaluation";
import type { GeneralAgentRunSummary } from "../../src/lib/types/general-agent";

assert.equal(generalAgentEvaluationCategoryLabels.authorization_boundary, "授权边界");
assert.equal(scoreLabel(84.6), "85 分");

const evaluationCase = {
  user_goal: "写冲突场景时应该先明确什么？",
} as GeneralAgentEvaluationCase;
const runs = [
  { run_id: "a", user_goal: " 写冲突场景时应该先明确什么？ " },
  { run_id: "b", user_goal: "另一个问题" },
] as GeneralAgentRunSummary[];
assert.deepEqual(matchingRunsForCase(runs, evaluationCase).map(run => run.run_id), ["a"]);

assert.equal(isGeneralAgentRunEvaluable("executing"), false);
assert.equal(isGeneralAgentRunEvaluable("waiting_human"), true);
assert.equal(isGeneralAgentRunEvaluable("completed"), true);

const executableCase = {
  user_goal: "把选区改得更紧张。",
  run_input: {
    scope: {
      scope_type: "selection",
      current_chapter_id: "chapter-82",
      chapter_ids: ["chapter-82"],
      selection_text: "门外传来脚步声。",
      direct_context: "",
    },
    author_constraints: ["只返回改写候选。"],
    external_access_allowed: false,
  },
} as GeneralAgentEvaluationCase;
assert.deepEqual(generalAgentRunRequestForCase(executableCase), {
  user_goal: "把选区改得更紧张。",
  start_new_conversation: true,
  scope: executableCase.run_input.scope,
  author_constraints: ["只返回改写候选。"],
  external_access_allowed: false,
});

assert.equal(
  evaluationOutcomeLabel({ passed: true, semantic_review_required: true } as GeneralAgentEvaluationRecord),
  "确定性检查通过，待语义复核",
);
assert.equal(
  evaluationOutcomeLabel({ passed: false, semantic_review_required: false } as GeneralAgentEvaluationRecord),
  "未通过",
);

console.log("通用写作助手评测视图逻辑测试通过。");
