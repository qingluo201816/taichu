import assert from "node:assert/strict";

import {
  currentGeneralAgentNodes,
  generalAgentContinuationRequestIndex,
  generalCapabilityLabel,
  generalNodeErrorMessage,
  generalNodeStatusLabel,
  generalNodeStatusLabels,
  generalNodeVisualStatus,
  generalRunProgressSummary,
  generalRunStatusLabels,
  isGeneralAgentRunActive,
} from "../../src/lib/general-agent-display";
import { shouldSubmitGeneralAgentComposer } from "../../src/lib/general-agent-composer";
import type { GeneralAgentRun } from "../../src/lib/types/general-agent";

assert.equal(generalRunStatusLabels.waiting_human, "等待作者");
assert.equal(generalNodeStatusLabels.skipped, "已跳过");
assert.equal(generalCapabilityLabel("canon_evidence"), "小说事实取证");
assert.equal(
  generalCapabilityLabel("get_knowledge_chapter_coverage"),
  "统计知识库章节覆盖",
);
assert.equal(generalCapabilityLabel("unknown_internal_name"), "未识别能力");
assert.equal(generalNodeStatusLabel("failed", "replanning"), "等待自动修复");
assert.equal(generalNodeStatusLabel("failed", "completed"), "失败");
assert.equal(generalNodeVisualStatus("failed", "executing"), "running");
assert.equal(generalNodeVisualStatus("failed", "failed"), "failed");
assert.equal(
  generalNodeErrorMessage("result.content 不存在", "replanning"),
  null,
);
assert.equal(
  generalNodeErrorMessage("重试后仍然失败", "failed"),
  "重试后仍然失败",
);

assert.equal(isGeneralAgentRunActive("planning"), true);
assert.equal(isGeneralAgentRunActive("waiting_human"), false);
assert.equal(isGeneralAgentRunActive("completed"), false);

assert.equal(
  generalRunProgressSummary({
    status: "replanning",
    node_runs: [
      { status: "success", plan_revision: 1 },
      { status: "failed", plan_revision: 1 },
    ],
    plan_revision: 1,
  } as GeneralAgentRun),
  "正在修复执行问题",
);
assert.equal(
  generalRunProgressSummary({
    status: "executing",
    node_runs: [
      { status: "success", plan_revision: 1 },
      { status: "failed", plan_revision: 1 },
    ],
    plan_revision: 1,
  } as GeneralAgentRun),
  "正在修复执行问题",
);

assert.equal(
  shouldSubmitGeneralAgentComposer({
    key: "Enter",
    shiftKey: false,
    isComposing: false,
  }),
  true,
);
assert.equal(
  shouldSubmitGeneralAgentComposer({
    key: "Enter",
    shiftKey: true,
    isComposing: false,
  }),
  false,
);
assert.equal(
  shouldSubmitGeneralAgentComposer({
    key: "Enter",
    shiftKey: false,
    isComposing: true,
  }),
  false,
);

const run = {
  plan_revision: 2,
  node_runs: [
    { node_id: "old", plan_revision: 1 },
    { node_id: "current-a", plan_revision: 2 },
    { node_id: "current-b", plan_revision: 2 },
  ],
} as GeneralAgentRun;

assert.deepEqual(
  currentGeneralAgentNodes(run).map(node => node.node_id),
  ["current-a", "current-b"],
);

const completedParent = {
  run_id: "completed-parent",
  request_index: 1,
  status: "completed",
} as GeneralAgentRun;
const waitingParent = {
  run_id: "waiting-parent",
  request_index: 1,
  status: "waiting_human",
} as GeneralAgentRun;
const normalNextRequest = {
  run_id: "normal-next",
  request_index: 2,
  parent_run_id: completedParent.run_id,
} as GeneralAgentRun;
const resumedRequest = {
  run_id: "resumed",
  request_index: 2,
  parent_run_id: waitingParent.run_id,
} as GeneralAgentRun;

assert.equal(
  generalAgentContinuationRequestIndex(completedParent, [
    completedParent,
    normalNextRequest,
  ]),
  undefined,
);
assert.equal(
  generalAgentContinuationRequestIndex(waitingParent, [
    waitingParent,
    resumedRequest,
  ]),
  2,
);

console.log("通用写作助手前端显示逻辑测试通过。");
