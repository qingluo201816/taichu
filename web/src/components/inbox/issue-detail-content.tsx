import {
  type InboxIssueDetailKey,
  parseInboxIssueContent,
} from "@/lib/inbox-issue-format";
import {
  type InboxDecisionDetailKey,
  parseInboxDecisionContent,
} from "@/lib/inbox-decision-format";
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

const decisionDetailToneClasses: Record<InboxDecisionDetailKey, string> = {
  date: "text-[var(--tc-issue-date)]",
  status: "text-[var(--tc-issue-status-done)]",
  background: "text-[var(--tc-issue-symptom)]",
  decision: "text-[var(--tc-issue-fix)]",
  recovery: "text-[var(--tc-issue-verification)]",
  safety: "text-[var(--tc-issue-impact)]",
  implementation: "text-[var(--tc-issue-code)]",
  verification: "text-[var(--tc-issue-verification)]",
  scope: "text-[var(--tc-issue-symptom)]",
  tradeoff: "text-[var(--tc-issue-fix)]",
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
    return <PlainDetailContent content={content} />;
  }

  return (
    <div className="max-w-[920px] space-y-3 select-text">
      {fields.map(field => {
        const toneClass =
          field.key === "status"
            ? issueStatusToneClass(status)
            : issueDetailToneClasses[field.key];

        return (
          <DetailFieldRow
            key={field.key}
            label={field.label}
            value={field.value}
            toneClass={toneClass}
            emphasize={field.key === "status"}
            mono={field.key === "code"}
          />
        );
      })}
    </div>
  );
}

export function DecisionDetailContent({
  content,
  status,
}: {
  content: string;
  status: string;
}) {
  const blocks = parseInboxDecisionContent(content);

  if (!blocks) {
    return <PlainDetailContent content={content} />;
  }

  return (
    <div className="max-w-[920px] space-y-3 select-text">
      {blocks.map((block, index) => {
        if (block.kind === "prose") {
          return (
            <p
              key={`prose-${index}`}
              className="whitespace-pre-wrap break-words text-sm leading-7 text-[var(--tc-text-secondary)] [overflow-wrap:anywhere]"
            >
              {block.value}
            </p>
          );
        }

        const toneClass =
          block.key === "status"
            ? issueStatusToneClass(status)
            : decisionDetailToneClasses[block.key];
        return (
          <DetailFieldRow
            key={`${block.key}-${index}`}
            label={block.label}
            value={block.value}
            toneClass={toneClass}
            emphasize={block.key === "status"}
            mono={block.key === "implementation"}
          />
        );
      })}
    </div>
  );
}

function DetailFieldRow({
  label,
  value,
  toneClass,
  emphasize = false,
  mono = false,
}: {
  label: string;
  value: string;
  toneClass: string;
  emphasize?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[112px_minmax(0,1fr)] items-start gap-x-4">
      <div
        className={cn(
          "flex items-center gap-2 pt-1 text-sm font-semibold",
          toneClass,
        )}
      >
        <span
          aria-hidden="true"
          className="size-1.5 shrink-0 rounded-full bg-current"
        />
        {label}
      </div>
      <div
        className={cn(
          "min-w-0 whitespace-pre-wrap break-words text-sm leading-7 text-[var(--tc-text-secondary)] [overflow-wrap:anywhere]",
          emphasize && ["font-medium", toneClass],
          mono && "break-all font-mono text-xs text-[var(--tc-text-muted)]",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function PlainDetailContent({ content }: { content: string }) {
  return (
    <p className="max-w-[860px] select-text whitespace-pre-wrap break-words text-sm leading-7 text-[var(--tc-text-secondary)] [overflow-wrap:anywhere]">
      {content}
    </p>
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
