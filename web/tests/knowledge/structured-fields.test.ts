import assert from "node:assert/strict";

import {
  humanReadableListItem,
  humanReadableStructuredContent,
} from "../../src/lib/ai/human-readable-content";
import {
  CANDIDATE_LOCKED_FIELD_KEYS,
  displayKnowledgeFieldValue,
  formStateFromKnowledgeValues,
  knowledgePayloadFromForm,
  validateKnowledgeForm,
  type KnowledgeReferenceOptions,
} from "../../src/lib/knowledge/structured-fields";
import type {
  KnowledgeFieldSchema,
  KnowledgeTypeSchema,
} from "../../src/lib/types/mvp";

const fields: KnowledgeFieldSchema[] = [
  field("name", "名称", "short_text", true),
  field("aliases", "别名", "string_array"),
  field("summary", "摘要", "long_text", true),
  {
    ...field("importance", "重要程度", "enum"),
    options: [
      { value: "normal", label: "普通" },
      { value: "core", label: "核心" },
    ],
  },
  field("status", "状态", "enum", true),
  field("source_origin", "来源方式", "enum", true),
  field("source_note", "来源说明", "long_text", true),
  field("level_order", "境界排序值", "number"),
  field("first_seen_chapter_id", "首次出现章节", "chapter_ref"),
];

const schema: KnowledgeTypeSchema = {
  type: "realm",
  label: "境界",
  fields,
};

const references: KnowledgeReferenceOptions = {
  first_seen_chapter_id: [{ value: "chapter-1", label: "第一章 山门" }],
};

const form = formStateFromKnowledgeValues(schema, {
  name: "炼气一层",
  aliases: ["炼气初阶", "第一层"],
  summary: "修行的第一个层次。",
  importance: "normal",
  status: "active",
  source_origin: "agent_extract",
  source_note: "来自第一章。",
  level_order: 1,
  first_seen_chapter_id: "chapter-1",
  entity_group_id: "internal-1",
});

assert.equal(form.aliases, "炼气初阶\n第一层");
assert.equal(form.level_order, "1");
assert.equal(form.entity_group_id, undefined);

const payload = knowledgePayloadFromForm(
  schema,
  form,
  CANDIDATE_LOCKED_FIELD_KEYS,
);
assert.deepEqual(payload.aliases, ["炼气初阶", "第一层"]);
assert.equal(payload.level_order, 1);
assert.equal(payload.status, undefined);
assert.equal(payload.source_origin, undefined);
assert.equal(payload.entity_group_id, undefined);

assert.equal(
  displayKnowledgeFieldValue(fields[3], "normal", references),
  "普通",
);
assert.equal(
  displayKnowledgeFieldValue(fields[8], "chapter-1", references),
  "第一章 山门",
);
assert.equal(
  displayKnowledgeFieldValue(fields[8], "missing", references),
  "引用内容已不存在",
);
assert.equal(displayKnowledgeFieldValue(fields[1], [], references), "暂未填写");

const errors = validateKnowledgeForm(
  schema,
  { ...form, name: "", source_note: "" },
  CANDIDATE_LOCKED_FIELD_KEYS,
);
assert.equal(errors.name, "请填写名称");
assert.equal(errors.source_note, "请填写来源说明");
assert.equal(errors.status, undefined);

assert.equal(
  humanReadableListItem({ title: "血脉觉醒", body: "力量增强" }),
  "血脉觉醒；力量增强",
);
const readable = humanReadableStructuredContent({
  summary: "本章完成入门。",
  events: [{ title: "参加选苗", result: "成功入选" }],
});
assert.match(readable, /本章完成入门/);
assert.match(readable, /参加选苗；成功入选/);
assert.doesNotMatch(readable, /[{}\[\]"]/);

console.log("结构化知识字段测试通过");

function field(
  fieldKey: string,
  label: string,
  fieldType: KnowledgeFieldSchema["field_type"],
  requiredWhenActive = false,
): KnowledgeFieldSchema {
  return {
    field_key: fieldKey,
    label,
    field_type: fieldType,
    required_when_active: requiredWhenActive,
    options: [],
    placeholder: "",
    display_group: "基础信息",
    list_display: true,
    ai_usage: "",
  };
}
