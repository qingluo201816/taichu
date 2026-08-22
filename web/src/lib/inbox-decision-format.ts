export type InboxDecisionDetailKey =
  | "date"
  | "status"
  | "background"
  | "decision"
  | "recovery"
  | "safety"
  | "implementation"
  | "verification"
  | "scope"
  | "tradeoff";

export type InboxDecisionDetailBlock =
  | {
      kind: "field";
      key: InboxDecisionDetailKey;
      label: string;
      value: string;
    }
  | {
      kind: "prose";
      value: string;
    };

const decisionDetailFields: Array<{
  key: InboxDecisionDetailKey;
  label: string;
}> = [
  { key: "date", label: "决策日期" },
  { key: "status", label: "决策状态" },
  { key: "background", label: "决策背景" },
  { key: "decision", label: "决策内容" },
  { key: "recovery", label: "一致性与恢复" },
  { key: "safety", label: "安全边界" },
  { key: "implementation", label: "实施入口" },
  { key: "verification", label: "验证结果" },
  { key: "scope", label: "实施边界" },
  { key: "tradeoff", label: "当前实施取舍" },
];

const decisionDetailByLabel = new Map(
  decisionDetailFields.map(field => [field.label, field]),
);
const decisionDetailPattern = /^([^：\s]{1,16})：\s*(.*)$/;

export function parseInboxDecisionContent(
  content: string,
): InboxDecisionDetailBlock[] | null {
  const blocks: InboxDecisionDetailBlock[] = [];
  let proseLines: string[] = [];
  let hasStructuredField = false;

  function flushProse() {
    const value = proseLines.join("\n").trim();
    if (value) {
      blocks.push({ kind: "prose", value });
    }
    proseLines = [];
  }

  for (const rawLine of content.split(/\r?\n/)) {
    const match = rawLine.match(decisionDetailPattern);
    const field = match ? decisionDetailByLabel.get(match[1]) : undefined;
    if (field && match) {
      flushProse();
      blocks.push({
        kind: "field",
        key: field.key,
        label: field.label,
        value: match[2].trim(),
      });
      hasStructuredField = true;
      continue;
    }

    if (!rawLine.trim()) {
      flushProse();
      continue;
    }
    proseLines.push(rawLine.trimEnd());
  }

  flushProse();
  return hasStructuredField ? blocks : null;
}
