export function humanReadableStructuredContent(
  value: unknown,
  emptyMessage = "结构化结果暂时无法按卡片展示，请在技术详情中查看原始数据。",
): string {
  const lines = readableLines(value, 0);
  return lines.length ? lines.join("\n") : emptyMessage;
}

export function humanReadableListItem(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    return value.map(humanReadableListItem).filter(Boolean).join("；");
  }
  if (isRecord(value)) {
    return Object.values(value)
      .map(humanReadableListItem)
      .filter(Boolean)
      .join("；");
  }
  return "";
}

function readableLines(value: unknown, depth: number): string[] {
  if (value === null || value === undefined || depth > 4) {
    return [];
  }
  if (typeof value !== "object") {
    const text = humanReadableListItem(value);
    return text ? [text] : [];
  }
  if (Array.isArray(value)) {
    return value
      .map(humanReadableListItem)
      .filter(Boolean)
      .map(item => `- ${item}`);
  }
  return Object.values(value).flatMap(item => readableLines(item, depth + 1));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
