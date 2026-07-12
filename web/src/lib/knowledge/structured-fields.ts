import type {
  KnowledgeFieldSchema,
  KnowledgeTypeSchema,
  StructuredKnowledgeCard,
} from "@/lib/types/mvp";
import type { ChapterInfo } from "@/lib/types/chapters";

export type KnowledgeFormState = Record<string, string>;

export type KnowledgeReferenceOption = {
  value: string;
  label: string;
};

export type KnowledgeReferenceOptions = Record<
  string,
  KnowledgeReferenceOption[]
>;

export type KnowledgeFormErrors = Record<string, string>;

export const CANDIDATE_LOCKED_FIELD_KEYS = new Set([
  "lifecycle",
  "source_origin",
  "appearance_chapter_count",
]);

export function knowledgeGroupLabel(
  schema: KnowledgeTypeSchema,
  displayGroup: string,
): string {
  if (!displayGroup || displayGroup === "基础信息") {
    return "基础信息";
  }
  if (displayGroup === "类型字段") {
    return `${schema.label}信息`;
  }
  if (displayGroup === "来源") {
    return "来源与依据";
  }
  return displayGroup;
}

export function groupKnowledgeFields(
  schema: KnowledgeTypeSchema,
  hiddenFieldKeys: ReadonlySet<string> = new Set(),
): Array<{ label: string; fields: KnowledgeFieldSchema[] }> {
  const groups: Array<{ label: string; fields: KnowledgeFieldSchema[] }> = [];
  for (const field of schema.fields) {
    if (hiddenFieldKeys.has(field.field_key)) {
      continue;
    }
    const label = knowledgeGroupLabel(schema, field.display_group);
    let group = groups.find(item => item.label === label);
    if (!group) {
      group = { label, fields: [] };
      groups.push(group);
    }
    group.fields.push(field);
  }
  return groups;
}

export function formStateFromKnowledgeValues(
  schema: KnowledgeTypeSchema,
  values: Record<string, unknown>,
  defaults: KnowledgeFormState = {},
): KnowledgeFormState {
  const form: KnowledgeFormState = {};
  for (const field of schema.fields) {
    const value = values[field.field_key];
    if (Array.isArray(value)) {
      form[field.field_key] = value
        .map(item => (typeof item === "string" ? item : ""))
        .filter(Boolean)
        .join("\n");
    } else if (value === null || value === undefined) {
      form[field.field_key] = defaults[field.field_key] ?? "";
    } else if (typeof value === "boolean") {
      form[field.field_key] = value ? "true" : "false";
    } else {
      form[field.field_key] = String(value);
    }
  }
  return { ...defaults, ...form };
}

export function knowledgePayloadFromForm(
  schema: KnowledgeTypeSchema,
  form: KnowledgeFormState,
  excludedFieldKeys: ReadonlySet<string> = new Set(),
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of schema.fields) {
    if (
      excludedFieldKeys.has(field.field_key) ||
      field.author_editable === false ||
      field.field_type === "record_array"
    ) {
      continue;
    }
    const rawValue = form[field.field_key] ?? "";
    if (field.field_type === "string_array") {
      payload[field.field_key] = splitKnowledgeList(rawValue);
    } else if (field.field_type === "number") {
      payload[field.field_key] = rawValue.trim() ? Number(rawValue) : null;
    } else if (field.field_type === "boolean") {
      payload[field.field_key] =
        rawValue === "" ? null : rawValue === "true";
    } else if (field.field_type === "enum") {
      payload[field.field_key] = rawValue || null;
    } else if (
      field.field_key === "name" ||
      field.field_key === "summary" ||
      field.field_key === "source_note"
    ) {
      payload[field.field_key] = rawValue;
    } else {
      payload[field.field_key] = rawValue.trim() ? rawValue.trim() : null;
    }
  }
  return payload;
}

export function validateKnowledgeForm(
  schema: KnowledgeTypeSchema,
  form: KnowledgeFormState,
  excludedFieldKeys: ReadonlySet<string> = new Set(),
  validateConfirmedFields = true,
): KnowledgeFormErrors {
  const errors: KnowledgeFormErrors = {};
  for (const field of schema.fields) {
    if (
      excludedFieldKeys.has(field.field_key) ||
      field.author_editable === false
    ) {
      continue;
    }
    const value = form[field.field_key] ?? "";
    if (
      validateConfirmedFields &&
      field.required_when_confirmed &&
      !value.trim()
    ) {
      errors[field.field_key] = `请填写${field.label}`;
    } else if (
      field.field_type === "number" &&
      value.trim() &&
      !Number.isFinite(Number(value))
    ) {
      errors[field.field_key] = `${field.label}必须是有效数字`;
    }
  }
  return errors;
}

export function displayKnowledgeFieldValue(
  field: KnowledgeFieldSchema,
  value: unknown,
  referenceOptions: KnowledgeReferenceOptions = {},
): string {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  ) {
    return "暂未填写";
  }
  if (Array.isArray(value)) {
    const readable = value
      .map(item => structuredItemText(item))
      .filter(Boolean)
      .join("、");
    return readable || "暂未填写";
  }
  if (field.field_type === "boolean") {
    return value ? "是" : "否";
  }
  if (field.field_key === "appearance_chapter_count") {
    return `已出现 ${String(value)} 章`;
  }
  if (
    field.field_type === "chapter_ref" ||
    field.field_type === "knowledge_ref"
  ) {
    const resolved = referenceOptions[field.field_key]?.find(
      option => option.value === String(value),
    );
    return resolved?.label ?? "引用内容已不存在";
  }
  const option = field.options.find(item => item.value === value);
  return option?.label ?? String(value);
}

export function splitKnowledgeList(value: string): string[] {
  return value
    .split(/[，,\n]/)
    .map(item => item.trim())
    .filter(Boolean)
    .filter((item, index, items) => items.indexOf(item) === index);
}

export function referenceKnowledgeTypeForField(
  fieldKey: string,
): "character" | "faction" | null {
  if (["owner_faction_id", "controlling_faction_id"].includes(fieldKey)) {
    return "faction";
  }
  if (["leader_id", "current_holder_id"].includes(fieldKey)) {
    return "character";
  }
  return null;
}

export function buildKnowledgeReferenceOptions(
  schemas: KnowledgeTypeSchema[],
  chapters: ChapterInfo[],
  characters: StructuredKnowledgeCard[],
  factions: StructuredKnowledgeCard[],
): KnowledgeReferenceOptions {
  const options: KnowledgeReferenceOptions = {};
  const chapterOptions = chapters.map(chapter => ({
    value: chapter.id,
    label: chapter.title,
  }));
  const knowledgeOptions = {
    character: characters.map(card => ({ value: card.id, label: card.name })),
    faction: factions.map(card => ({ value: card.id, label: card.name })),
  };
  for (const schema of schemas) {
    for (const field of schema.fields) {
      if (field.field_type === "chapter_ref") {
        options[field.field_key] = chapterOptions;
      } else if (field.field_type === "knowledge_ref") {
        const targetType = referenceKnowledgeTypeForField(field.field_key);
        options[field.field_key] = targetType
          ? knowledgeOptions[targetType]
          : [];
      }
    }
  }
  return options;
}

function structuredItemText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (typeof value === "object" && value !== null) {
    return Object.values(value)
      .filter(item => ["string", "number", "boolean"].includes(typeof item))
      .map(String)
      .join("；");
  }
  return "";
}
