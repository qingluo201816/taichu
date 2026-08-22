import assert from "node:assert/strict";

import {
  vectorGraphCollectionLabels,
  vectorGraphProgressPercent,
  vectorGraphStageLabels,
  vectorGraphStateLabels,
} from "../../src/lib/vector-graph-status";

assert.equal(vectorGraphStateLabels.not_built, "尚未建立索引");
assert.equal(vectorGraphStateLabels.building, "正在更新索引");
assert.equal(vectorGraphStateLabels.ready, "可以使用");
assert.equal(vectorGraphStateLabels.failed, "索引更新失败");
assert.equal(vectorGraphStageLabels.planning, "整理索引来源");
assert.equal(vectorGraphStageLabels.extracting, "抽取实体与关系");
assert.equal(vectorGraphStageLabels.completed, "增量更新完成");
assert.equal(vectorGraphCollectionLabels.passages, "正文与知识卡片段");
assert.equal(vectorGraphProgressPercent(321, 2058), 16);
assert.equal(vectorGraphProgressPercent(0, 0), 0);
assert.equal(vectorGraphProgressPercent(3000, 2058), 100);
assert.equal(vectorGraphProgressPercent(1, 1), 100);

console.log("RAG 索引监控中文状态与进度计算测试通过。");
