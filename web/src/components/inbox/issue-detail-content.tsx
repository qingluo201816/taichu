import {
  type InboxIssueDetailKey,
  parseInboxIssueContent,
} from "@/lib/inbox-issue-format";
import { cn } from "@/lib/utils";

const issueDetailToneClasses: Record<InboxIssueDetailKey, string> = {
  date: "text-[var(--tc-issue-date)]",
  status: "text-[var(--tc-issue-status-done)]",
  symptom: "text-[var(--tc-issue-symptom)]",
  cause: "text-[var(--tc-issue-cause)]",
  impact: "text-[var(--tc-issue-impact)]",
  fix: "text-[var(--tc-issue-fix)]",
  verification: "text-[var(--tc-issue-verification)]",
  code: "text-[var(--tc-issue-code)]",
};

export function IssueDetailContent({
  content,
  status,
}: {
  content: string;
  status: string;
}) {
  const fields = parseInboxIssueContent(content);

  if (!fields) {
    return (
      <p className="max-w-[860px] select-text whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
        {content}
      </p>
    );
  }

  return (
    <dl className="max-w-[920px] space-y-3 select-text">
      {fields.map(field => {
        const toneClass =
          field.key === "status"
            ? issueStatusToneClass(status)
            : issueDetailToneClasses[field.key];

        return (
          <div
            key={field.key}
            className="grid grid-cols-[92px_minmax(0,1fr)] items-start gap-x-4"
          >
            <dt
              className={cn(
                "flex items-center gap-2 pt-1 text-sm font-semibold",
                toneClass,
              )}
            >
              <span
                aria-hidden="true"
                className="size-1.5 shrink-0 rounded-full bg-current"
              />
              {field.label}
            </dt>
            <dd
              className={cn(
                "min-w-0 whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]",
                field.key === "status" && ["font-medium", toneClass],
                field.key === "code" &&
                  "break-all font-mono text-xs text-[var(--tc-text-muted)]",
              )}
            >
              {field.value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function issueStatusToneClass(status: string): string {
  if (status === "processed") {
    return "text-[var(--tc-issue-status-done)]";
  }
  if (status === "deprecated") {
    return "text-[var(--tc-issue-status-deprecated)]";
  }
  return "text-[var(--tc-issue-status-open)]";
}
