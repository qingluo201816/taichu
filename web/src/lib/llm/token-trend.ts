import type { LLMTokenTrendPoint } from "../types/llm";

export type TokenTrendRange = "24h" | "7d" | "30d" | "all";

export type TrendWindow = { startedFrom?: string; startedTo?: string };

// The usage API aggregates UTC buckets; date filters use the same calendar.
export function customTrendWindow(start: string, end: string): TrendWindow | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) return null;
  const from = Date.parse(`${start}T00:00:00Z`);
  const to = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(from) || !Number.isFinite(to) || new Date(from).toISOString().slice(0, 10) !== start || new Date(to).toISOString().slice(0, 10) !== end) return null;
  return { startedFrom: new Date(from).toISOString(), startedTo: new Date(to + 86400000 - 1).toISOString() };
}

export function trendBucketWindow(start: string, bucket: "hour" | "day", scope: TrendWindow): TrendWindow {
  const from = Math.max(Date.parse(start), scope.startedFrom ? Date.parse(scope.startedFrom) : -Infinity);
  const to = Math.min(Date.parse(start) + (bucket === "hour" ? 3600000 : 86400000) - 1, scope.startedTo ? Date.parse(scope.startedTo) : Infinity);
  return { startedFrom: new Date(from).toISOString(), startedTo: new Date(to).toISOString() };
}

export function trendCsv(points: LLMTokenTrendPoint[]): string {
  const rows = points.map(point => [point.bucket_start, point.call_count, point.total_tokens, point.input_tokens, point.output_tokens, point.cached_input_tokens, point.reasoning_tokens]);
  return "\uFEFF" + [["时间（协调世界时）", "调用次数", "总 Token", "输入 Token", "输出 Token", "缓存 Token", "推理 Token"], ...rows]
    .map(row => row.map(value => `"${String(value ?? "未返回").replaceAll('"', '""')}"`).join(",")).join("\r\n");
}

export function tokenTrendRangeStart(
  range: TokenTrendRange,
  now = Date.now(),
): string | undefined {
  if (range === "all") return undefined;
  const hours = range === "24h" ? 24 : range === "7d" ? 24 * 7 : 24 * 30;
  return new Date(now - hours * 60 * 60 * 1000).toISOString();
}

export function tokenTrendTickIndexes(length: number): number[] {
  if (length <= 1) return length ? [0] : [];
  const step = Math.max(1, Math.ceil((length - 1) / 5));
  const indexes = Array.from(
    { length: Math.ceil(length / step) },
    (_, index) => Math.min(index * step, length - 1),
  );
  if (indexes[indexes.length - 1] !== length - 1) indexes.push(length - 1);
  return [...new Set(indexes)];
}
