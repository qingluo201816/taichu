import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const apiSource = readFileSync("src/lib/api/vector-graph.ts", "utf8");
const monitorSource = readFileSync(
  "src/components/agent-task-monitor/vector-graph-monitor-shell.tsx",
  "utf8",
);
const typesSource = readFileSync("src/lib/types/vector-graph.ts", "utf8");

assert.match(apiSource, /startVectorGraphUpdate/);
assert.match(apiSource, /\/api\/vector-graph\/update/);
assert.doesNotMatch(apiSource, /\/api\/vector-graph\/rebuild/);

assert.match(monitorSource, /开始增量更新/);
assert.match(monitorSource, /未变化来源会直接跳过/);
assert.match(monitorSource, /现有 Milvus 索引不会被整体覆盖/);
assert.match(monitorSource, /progress\.processed_sources/);
assert.match(monitorSource, /progress\.total_sources/);
assert.match(monitorSource, /progress\.stage === "completed"/);
assert.match(monitorSource, /当前来源：/);
assert.match(monitorSource, /本次结果：更新/);
assert.doesNotMatch(monitorSource, /全量建模/);
assert.doesNotMatch(monitorSource, /RAG 建模/);

for (const field of [
  "processed_sources",
  "total_sources",
  "current_source_key",
  "updated_source_count",
  "deleted_source_count",
  "unchanged_source_count",
]) {
  assert.match(typesSource, new RegExp(`\\b${field}\\b`));
}

console.log("RAG 增量更新入口与用户提示测试通过。");
