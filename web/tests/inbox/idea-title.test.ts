import assert from "node:assert/strict";

import { inboxIdeaDisplayTitle } from "../../src/lib/inbox-idea-title";

assert.equal(
  inboxIdeaDisplayTitle({ title: "  山门伏笔  ", content: "不会使用这段内容" }),
  "山门伏笔",
);

assert.equal(
  inboxIdeaDisplayTitle({ title: "", content: "旧灵感会使用内容作为兼容标题" }),
  "旧灵感会使用内容作为兼容标题",
);

assert.equal(
  inboxIdeaDisplayTitle({
    content: "这是一个超过二十八个字符的旧灵感内容，用来验证列表标题会被安全截断而不是一直显示灵感",
  }),
  "这是一个超过二十八个字符的旧灵感内容，用来验证列表标题会…",
);

assert.equal(inboxIdeaDisplayTitle({ title: "", content: "  " }), "未命名灵感");

console.log("灵感标题显示兼容逻辑测试通过。");
