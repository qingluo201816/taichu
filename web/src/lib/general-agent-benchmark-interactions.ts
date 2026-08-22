export interface InboxIssueLinkContract {
  namespace: string;
  relation_id: string;
  subject_id: string;
  relation_kind: "documents" | "caused_by" | "observed_in" | "closes";
  subject_content_sha256: string;
}

export interface InboxIssueContract {
  id: string;
  title: string;
  content: string;
  source_chapter_id?: string | null;
  priority: "low" | "normal" | "high";
  status: "todo" | "processed" | "deprecated";
  revision: number;
  links: InboxIssueLinkContract[];
  created_at: string;
  updated_at: string;
}

export interface ComparisonSelection {
  iterationId: string | null;
  comparisonId: string | null;
}

export function normalizeInboxIssueContract(
  value: Omit<InboxIssueContract, "revision" | "links"> &
    Partial<Pick<InboxIssueContract, "revision" | "links">>,
): InboxIssueContract {
  return {
    ...value,
    revision: value.revision ?? 0,
    links: value.links ?? [],
  };
}

export function inboxIssuePatchRequest(
  issue: Pick<InboxIssueContract, "revision">,
  updates: Partial<
    Pick<
      InboxIssueContract,
      "title" | "content" | "source_chapter_id" | "priority" | "status" | "links"
    >
  >,
) {
  return {
    expected_revision: issue.revision,
    updates,
  };
}

export function inboxCasConflictNotice(error: unknown): string | null {
  if (!isConflictError(error)) return null;
  return "记录已被其他操作更新，已刷新，请确认后重试。";
}

export function issueIntentConflictNotice(error: unknown): string | null {
  if (!isConflictError(error)) return null;
  return "已存在内容不同的问题关联意图，请先核对原记录。";
}

export function benchmarkRevisionConflictNotice(error: unknown): string | null {
  if (!isConflictError(error)) return null;
  return "评测状态已被其他操作更新，已刷新，请确认后重试。";
}

export function symmetryGateNotice(missingSides: string[]): string {
  const labels: Record<string, string> = {
    relation_manifest: "关联记录",
    inbox_issue: "系统问题",
    iteration_manifest: "首轮迭代",
    observation_log: "核对观察",
  };
  const missing = missingSides.map(item => labels[item] ?? item).join("、");
  return missing
    ? `问题闭环尚未完成：${missing}未对称确认。`
    : "问题闭环四方记录已对称确认。";
}

export function comparisonSelectionFromSearch(
  search: URLSearchParams,
): ComparisonSelection {
  return {
    iterationId: nonEmpty(search.get("iteration")),
    comparisonId: nonEmpty(search.get("comparison")),
  };
}

export function withComparisonSelection(
  current: URLSearchParams,
  selection: ComparisonSelection,
): URLSearchParams {
  const next = new URLSearchParams(current);
  setOptional(next, "iteration", selection.iterationId);
  setOptional(next, "comparison", selection.comparisonId);
  return next;
}

function setOptional(
  search: URLSearchParams,
  key: string,
  value: string | null,
): void {
  if (value) search.set(key, value);
  else search.delete(key);
}

function nonEmpty(value: string | null): string | null {
  return value?.trim() || null;
}

function isConflictError(
  error: unknown,
): error is { status: number; requestId: string | null } {
  return (
    error instanceof Error &&
    "status" in error &&
    error.status === 409 &&
    "requestId" in error &&
    (typeof error.requestId === "string" || error.requestId === null)
  );
}
