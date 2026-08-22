import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { formatAgentRunFailure } from "../../src/lib/agent-run-display";

const baseRun = {
  status: "failed" as const,
  failed_chapter_count: 1,
  model_display_name: "DeepSeek V4 Pro",
  model_name: "DeepSeek V4 Pro",
  batch_chapter_progress: [],
  nodes: [],
  llm_calls: [],
  errors: [],
};

test("模型权限失败时展示可执行的中文说明", () => {
  assert.equal(
    formatAgentRunFailure({
      ...baseRun,
      batch_chapter_progress: [
        {
          chapter_id: "chapter_071",
          chapter_title: "第71章",
          status: "failed",
          candidate_count: 0,
          error: "当前密钥无权调用该模型，请检查本机密钥权限。",
        },
      ],
    }),
    "模型调用失败：DeepSeek V4 Pro 无调用权限。请检查当前密钥权限，或更换可用模型后重新运行。",
  );
});

test("正常完成且没有失败章节时不展示失败说明", () => {
  assert.equal(
    formatAgentRunFailure({
      ...baseRun,
      status: "completed",
      failed_chapter_count: 0,
    }),
    null,
  );
});

test("摘要失败在候选列表区分超时与输出截断", () => {
  const source = readFileSync(
    "src/components/agent-workbench/agent-workbench-shell.tsx",
    "utf8",
  );

  assert.match(source, /errorText\.includes\("摘要超时"\)[\s\S]*return "超时"/);
  assert.match(
    source,
    /errorText\.includes\("摘要输出截断"\)[\s\S]*return "输出截断"/,
  );
});
