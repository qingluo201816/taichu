export type TokenTrendRange = "24h" | "7d" | "30d" | "all";

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
