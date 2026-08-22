import assert from "node:assert/strict";
import test from "node:test";

import {
  hasExactKnowledgeIdentityOverlap,
  normalizeKnowledgeIdentity,
} from "../../src/lib/knowledge/identity-match";

test("名称与别名规范化后完全相同才视为身份交集", () => {
  assert.equal(normalizeKnowledgeIdentity(" 徐 羽 "), "徐羽");
  assert.equal(normalizeKnowledgeIdentity("ＡＢＣ"), "abc");
  assert.equal(
    hasExactKnowledgeIdentityOverlap(
      { name: "徐羽", aliases: ["徐师姐"] },
      { name: "徐师姐", aliases: [] },
    ),
    true,
  );
});

test("名称子串或摘要提及不能构成身份交集", () => {
  assert.equal(
    hasExactKnowledgeIdentityOverlap(
      { name: "主角", aliases: [] },
      { name: "主角师兄", aliases: [] },
    ),
    false,
  );
  const summaryMentionOnly = {
    name: "潘汉忠",
    aliases: [],
    summary: "曾经帮助过秦浩轩",
  };
  assert.equal(
    hasExactKnowledgeIdentityOverlap(
      { name: "秦浩轩", aliases: [] },
      summaryMentionOnly,
    ),
    false,
  );
});
