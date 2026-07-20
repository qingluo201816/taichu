import type { EditConfirmMergeMode } from "@/lib/types/agent-workbench";
import type {
  KnowledgeFieldMergeStrategy,
  KnowledgeTypeSchema,
} from "@/lib/types/mvp";

export function buildCandidateReviewPreview(
  currentCard: Record<string, unknown> | null,
  candidateCard: Record<string, unknown>,
  schema: KnowledgeTypeSchema,
  mergeMode: EditConfirmMergeMode,
): Record<string, unknown> {
  if (!currentCard) {
    return { ...candidateCard };
  }

  const preview = { ...currentCard };
  const strategies = new Map(
    schema.fields.map(field => [field.field_key, field.merge_strategy]),
  );
  for (const [key, incoming] of Object.entries(candidateCard)) {
    preview[key] =
      mergeMode === "overwrite" && key !== "appearance_chapter_count"
        ? incoming
        : mergeCandidateValue(
            strategies.get(key) ?? "preserve_existing",
            preview[key],
            incoming,
          );
  }
  return preview;
}

export function changedKnowledgeFieldKeys(
  schema: KnowledgeTypeSchema,
  currentCard: Record<string, unknown>,
  previewCard: Record<string, unknown>,
): Set<string> {
  return new Set(
    schema.fields
      .filter(
        field =>
          !knowledgeValuesEqual(
            currentCard[field.field_key],
            previewCard[field.field_key],
          ),
      )
      .map(field => field.field_key),
  );
}

function mergeCandidateValue(
  strategy: KnowledgeFieldMergeStrategy,
  current: unknown,
  incoming: unknown,
): unknown {
  switch (strategy) {
    case "replace":
      return isEmptyKnowledgeValue(incoming) ? current : incoming;
    case "append_unique":
      return appendUniqueTextBlocks(current, incoming);
    case "union":
      return mergeAliases(current, incoming);
    case "sum": {
      const currentCount =
        typeof current === "number" && Number.isInteger(current) ? current : 0;
      const incomingCount =
        typeof incoming === "number" && Number.isInteger(incoming) ? incoming : 0;
      return currentCount + incomingCount;
    }
    case "latest":
      return isEmptyKnowledgeValue(incoming) ? current : incoming;
    case "preserve_existing":
      break;
  }
  if (isEmptyKnowledgeValue(current) || knowledgeValuesEqual(current, incoming)) {
    return incoming;
  }
  return current;
}

function mergeAliases(current: unknown, incoming: unknown): string[] {
  const aliases: string[] = [];
  for (const value of [...stringList(current), ...stringList(incoming)]) {
    if (!aliases.includes(value)) {
      aliases.push(value);
    }
  }
  return aliases;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && Boolean(item.trim()),
      )
    : [];
}

function appendUniqueTextBlocks(current: unknown, incoming: unknown): string {
  const blocks: string[] = [];
  const seen = new Set<string>();
  for (const value of [current, incoming]) {
    for (const block of String(value ?? "").split(/\n\s*\n/)) {
      const cleaned = block.trim();
      const normalized = cleaned.replace(/\s+/g, " ");
      if (!cleaned || seen.has(normalized)) {
        continue;
      }
      seen.add(normalized);
      blocks.push(cleaned);
    }
  }
  return blocks.join("\n\n");
}

function isEmptyKnowledgeValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function knowledgeValuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true;
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return (
      left.length === right.length &&
      left.every((item, index) => knowledgeValuesEqual(item, right[index]))
    );
  }
  if (isPlainRecord(left) && isPlainRecord(right)) {
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every(
        (key, index) =>
          key === rightKeys[index] && knowledgeValuesEqual(left[key], right[key]),
      )
    );
  }
  return false;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
