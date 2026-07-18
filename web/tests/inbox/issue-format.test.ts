import assert from "node:assert/strict";

import {
  createInboxIssueTemplate,
  parseInboxIssueContent,
} from "../../src/lib/inbox-issue-format";

const canonical = [
  "记录日期：2026-07-18",
  "状态：已完成并验证",
  "现象：页面只显示了部分字段。",
  "根因：写入入口没有校验固定格式。",
  "影响：错误内容直到展示时才暴露。",
  "修复：写入时校验全部固定字段。",
  "验证：错误字段会被拒绝。",
  "相关代码：src/taichu/application/services/mvp_inbox_service.py",
].join("\n");

assert.deepEqual(
  parseInboxIssueContent(canonical)?.map(field => field.label),
  ["记录日期", "状态", "现象", "根因", "影响", "修复", "验证", "相关代码"],
);

assert.equal(
  parseInboxIssueContent(
    canonical.replace("根因：写入入口没有校验固定格式。", "原因：写入入口没有校验固定格式。"),
  ),
  null,
);

assert.match(createInboxIssueTemplate("2026-07-18"), /^记录日期：2026-07-18/m);
assert.match(createInboxIssueTemplate("2026-07-18"), /^根因：待调查$/m);
assert.match(createInboxIssueTemplate("2026-07-18"), /^相关代码：暂无$/m);

console.log("系统问题固定记录格式测试通过。");
