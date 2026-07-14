import assert from "node:assert/strict";

import {
  currentGeneralAgentNodes,
  generalCapabilityLabel,
  generalNodeStatusLabels,
  generalRunStatusLabels,
  isGeneralAgentRunActive,
} from "../../src/lib/general-agent-display";
import type { GeneralAgentRun } from "../../src/lib/types/general-agent";

assert.equal(generalRunStatusLabels.waiting_human, "等待作者");
assert.equal(generalNodeStatusLabels.skipped, "已跳过");
assert.equal(generalCapabilityLabel("canon_evidence"), "小说事实取证");
assert.equal(generalCapabilityLabel("unknown_internal_name"), "未识别能力");

assert.equal(isGeneralAgentRunActive("planning"), true);
assert.equal(isGeneralAgentRunActive("waiting_human"), false);
assert.equal(isGeneralAgentRunActive("completed"), false);

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

console.log("通用写作助手前端显示逻辑测试通过。");
