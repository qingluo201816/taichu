import assert from "node:assert/strict";

import { parseInboxDecisionContent } from "../../src/lib/inbox-decision-format";

const structured = [
  "决策日期：2026-08-16",
  "决策状态：已实施",
  "决策背景：全量重建成本过高。",
  "决策内容：按稳定来源键执行增量替换。",
  "安全边界：集合结构异常时停止写入。",
  "验证结果：来源级回归测试通过。",
].join("\n");

const blocks = parseInboxDecisionContent(structured);
assert.deepEqual(
  blocks?.filter(block => block.kind === "field").map(block => block.label),
  ["决策日期", "决策状态", "决策背景", "决策内容", "安全边界", "验证结果"],
);

const mixed = parseInboxDecisionContent(
  [
    "决策日期：2026-07-22",
    "决策状态：已确认并进入实施",
    "一、五层记忆是模型可见输入的唯一业务分类",
    "1. 稳定记忆。",
  ].join("\n"),
);
assert.equal(mixed?.at(-1)?.kind, "prose");
assert.match(mixed?.at(-1)?.value ?? "", /五层记忆/);

assert.equal(parseInboxDecisionContent("测试"), null);

console.log("决策结构化展示格式测试通过。");
