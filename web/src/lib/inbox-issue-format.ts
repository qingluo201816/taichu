export type InboxIssueDetailKey =
  | "date"
  | "status"
  | "symptom"
  | "cause"
  | "impact"
  | "fix"
  | "verification"
  | "code";

export type InboxIssueDetailField = {
  key: InboxIssueDetailKey;
  label: string;
  value: string;
};

export const inboxIssueDetailOrder: Array<{
  key: InboxIssueDetailKey;
  label: string;
}> = [
  { key: "date", label: "记录日期" },
  { key: "status", label: "状态" },
  { key: "symptom", label: "现象" },
  { key: "cause", label: "根因" },
  { key: "impact", label: "影响" },
  { key: "fix", label: "修复" },
  { key: "verification", label: "验证" },
  { key: "code", label: "相关代码" },
];

const detailByLabel = new Map(
  inboxIssueDetailOrder.map(field => [field.label, field]),
);
const detailPattern =
  /^(记录日期|状态|现象|根因|影响|修复|验证|相关代码)：\s*(.*)$/;
const labelLikePattern = /^[^：\s]{1,16}：/;

export function parseInboxIssueContent(
  content: string,
): InboxIssueDetailField[] | null {
  const fields: InboxIssueDetailField[] = [];
  let currentField: InboxIssueDetailField | null = null;

  for (const rawLine of content.split(/\r?\n/)) {
    const match = rawLine.match(detailPattern);
    if (match) {
      const detail = detailByLabel.get(match[1]);
      const expected = inboxIssueDetailOrder[fields.length];
      if (!detail || !expected || detail.key !== expected.key) {
        return null;
      }
      currentField = { ...detail, value: match[2].trim() };
      fields.push(currentField);
      continue;
    }

    if (labelLikePattern.test(rawLine)) {
      return null;
    }
    if (!currentField) {
      if (rawLine.trim()) {
        return null;
      }
      continue;
    }
    currentField.value = `${currentField.value}\n${rawLine.trimEnd()}`.trim();
  }

  return fields.length === inboxIssueDetailOrder.length ? fields : null;
}

export function createInboxIssueTemplate(
  recordDate = currentShanghaiDate(),
): string {
  return [
    `记录日期：${recordDate}`,
    "状态：待处理",
    "现象：",
    "根因：待调查",
    "影响：",
    "修复：待处理",
    "验证：待验证",
    "相关代码：暂无",
  ].join("\n");
}

function currentShanghaiDate(): string {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
