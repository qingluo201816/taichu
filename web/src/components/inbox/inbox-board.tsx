"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  CheckCircle2,
  ExternalLink,
  FileQuestion,
  Inbox,
  Lightbulb,
  Loader2,
  PencilLine,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { readInbox } from "@/lib/api/inbox";
import {
  confirmEditedPendingFact,
  confirmPendingFact,
  rejectPendingFact,
} from "@/lib/api/knowledge";
import type {
  ChapterIssueInfo,
  IdeaCardInfo,
  InboxResponse,
  PendingFactInfo,
  SavedAICardInfo,
} from "@/lib/types/inbox";
import type { ConfirmEditedPendingFactRequest } from "@/lib/types/knowledge";

type LaneTone = "idea" | "pending" | "ai" | "issue";

const emptyInbox: InboxResponse = {
  ideas: [],
  pending_facts: [],
  saved_ai_cards: [],
  chapter_issues: [],
};

export function InboxBoard() {
  const [snapshot, setSnapshot] = useState<InboxResponse>(emptyInbox);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyPendingFactId, setBusyPendingFactId] = useState<string | null>(null);

  const totals = useMemo(
    () =>
      snapshot.ideas.length +
      snapshot.pending_facts.length +
      snapshot.saved_ai_cards.length +
      snapshot.chapter_issues.length,
    [snapshot],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await readInbox());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "收件箱加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadInitialInbox() {
      try {
        const nextSnapshot = await readInbox();
        if (!cancelled) {
          setSnapshot(nextSnapshot);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "收件箱加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInitialInbox();
    return () => {
      cancelled = true;
    };
  }, []);

  const removePendingFact = useCallback((pendingFactId: string) => {
    setSnapshot(current => ({
      ...current,
      pending_facts: current.pending_facts.filter(
        pendingFact => pendingFact.id !== pendingFactId,
      ),
    }));
  }, []);

  const onConfirmPendingFact = useCallback(
    async (pendingFactId: string) => {
      setBusyPendingFactId(pendingFactId);
      setError(null);
      setMessage(null);
      try {
        const response = await confirmPendingFact(pendingFactId);
        removePendingFact(pendingFactId);
        setMessage(`已确认入库：${response.knowledge_card.name}`);
      } catch (confirmError) {
        setError(
          confirmError instanceof Error ? confirmError.message : "确认入库失败",
        );
      } finally {
        setBusyPendingFactId(null);
      }
    },
    [removePendingFact],
  );

  const onConfirmPendingFactWithEdits = useCallback(
    async (
      pendingFactId: string,
      request: ConfirmEditedPendingFactRequest,
    ) => {
      setBusyPendingFactId(pendingFactId);
      setError(null);
      setMessage(null);
      try {
        const response = await confirmEditedPendingFact(pendingFactId, request);
        removePendingFact(pendingFactId);
        setMessage(`已编辑确认：${response.knowledge_card.name}`);
      } catch (confirmError) {
        setError(
          confirmError instanceof Error ? confirmError.message : "编辑确认失败",
        );
      } finally {
        setBusyPendingFactId(null);
      }
    },
    [removePendingFact],
  );

  const onRejectPendingFact = useCallback(
    async (pendingFactId: string) => {
      setBusyPendingFactId(pendingFactId);
      setError(null);
      setMessage(null);
      try {
        await rejectPendingFact(pendingFactId);
        removePendingFact(pendingFactId);
        setMessage("已驳回候选设定");
      } catch (rejectError) {
        setError(rejectError instanceof Error ? rejectError.message : "驳回失败");
      } finally {
        setBusyPendingFactId(null);
      }
    },
    [removePendingFact],
  );

  return (
    <main className="tc-workspace-page min-h-screen">
      <header className="tc-workspace-header">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/home"
              className="inline-flex size-10 items-center justify-center rounded-[var(--tc-panel-radius)] border border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-recess)] text-[var(--tc-workspace-text-secondary)] transition-colors hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]"
              aria-label="返回太初"
              title="返回太初"
            >
              <ArrowLeft className="size-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--tc-workspace-text-muted)]">
                <Inbox className="size-4" />
                工作区范围 / 非事实
              </div>
              <h1 className="mt-1 text-2xl font-semibold text-[var(--tc-workspace-focus)]">
                创作收件箱
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="tc-tag px-3 py-1 text-sm">
              {totals} 条
            </span>
            <Button
              size="sm"
              onClick={() => void refresh()}
              disabled={loading}
              variant="outline"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              刷新
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-5 py-5">
        {error ? (
          <div className="tc-danger mb-4 rounded-[var(--tc-panel-radius)] border px-4 py-3 text-sm font-medium">
            {error}
          </div>
        ) : null}
        {message ? (
          <div className="tc-success mb-4 rounded-[var(--tc-panel-radius)] border px-4 py-3 text-sm font-medium">
            {message}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-4">
          <Lane
            title="灵感"
            count={snapshot.ideas.length}
            icon={<Lightbulb className="size-4" />}
            tone="idea"
            loading={loading}
          >
            {snapshot.ideas.map(idea => (
              <IdeaItem key={idea.id} idea={idea} />
            ))}
          </Lane>

          <Lane
            title="待确认设定"
            count={snapshot.pending_facts.length}
            icon={<FileQuestion className="size-4" />}
            tone="pending"
            loading={loading}
          >
            {snapshot.pending_facts.map(pendingFact => (
              <PendingFactItem
                key={pendingFact.id}
                pendingFact={pendingFact}
                busy={busyPendingFactId === pendingFact.id}
                onConfirm={() => void onConfirmPendingFact(pendingFact.id)}
                onConfirmEdited={request =>
                  void onConfirmPendingFactWithEdits(pendingFact.id, request)
                }
                onReject={() => void onRejectPendingFact(pendingFact.id)}
              />
            ))}
          </Lane>

          <Lane
            title="已保存智能助手卡片"
            count={snapshot.saved_ai_cards.length}
            icon={<Sparkles className="size-4" />}
            tone="ai"
            loading={loading}
          >
            {snapshot.saved_ai_cards.map(card => (
              <SavedAICardItem key={card.id} card={card} />
            ))}
          </Lane>

          <Lane
            title="章节问题"
            count={snapshot.chapter_issues.length}
            icon={<AlertTriangle className="size-4" />}
            tone="issue"
            loading={loading}
          >
            {snapshot.chapter_issues.map(issue => (
              <ChapterIssueItem key={issue.id} issue={issue} />
            ))}
          </Lane>
        </div>
      </section>
    </main>
  );
}

function Lane({
  title,
  count,
  icon,
  tone,
  loading,
  children,
}: {
  title: string;
  count: number;
  icon: ReactNode;
  tone: LaneTone;
  loading: boolean;
  children: ReactNode;
}) {
  return (
    <section className="tc-panel min-h-[520px] overflow-hidden">
      <div className={laneHeaderClass(tone)}>
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--tc-workspace-focus)]">
          {icon}
          {title}
        </div>
        <span className="tc-tag px-2 py-0.5 text-xs">
          {count}
        </span>
      </div>
      <div className="space-y-3 p-3">
        {loading ? (
          <div className="flex h-28 items-center justify-center text-sm font-medium text-[var(--tc-workspace-text-muted)]">
            <Loader2 className="mr-2 size-4 animate-spin" />
            加载中
          </div>
        ) : count === 0 ? (
          <div className="rounded-[var(--tc-panel-radius)] border border-dashed border-[var(--tc-workspace-border)] px-3 py-8 text-center text-sm text-[var(--tc-workspace-text-muted)]">
            暂无条目
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

function IdeaItem({ idea }: { idea: IdeaCardInfo }) {
  return (
    <InboxItem href={idea.source_href}>
      <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--tc-workspace-text-secondary)]">
        {idea.content}
      </p>
      <ItemFooter
        meta={`${ideaSourceText(idea.source)} / ${ideaStatusText(idea.status)}`}
        chapterId={idea.linked_chapter_id}
      />
    </InboxItem>
  );
}

function PendingFactItem({
  pendingFact,
  busy,
  onConfirm,
  onConfirmEdited,
  onReject,
}: {
  pendingFact: PendingFactInfo;
  busy: boolean;
  onConfirm: () => void;
  onConfirmEdited: (request: ConfirmEditedPendingFactRequest) => void;
  onReject: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(pendingFact.title);
  const [summary, setSummary] = useState(contentText(pendingFact.content));
  const [aliases, setAliases] = useState("");
  const [fieldsJson, setFieldsJson] = useState(
    JSON.stringify(fieldsObject(pendingFact.content), null, 2),
  );
  const [localError, setLocalError] = useState<string | null>(null);

  function submitEditedConfirmation() {
    setLocalError(null);
    let fields: Record<string, unknown>;
    try {
      const parsed = JSON.parse(fieldsJson) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setLocalError("字段必须是 JSON 对象");
        return;
      }
      fields = parsed as Record<string, unknown>;
    } catch {
      setLocalError("字段 JSON 格式不正确");
      return;
    }
    onConfirmEdited({
      name: name.trim() || pendingFact.title,
      summary: summary.trim() || contentText(pendingFact.content),
      aliases: aliases
        .split(",")
        .map(alias => alias.trim())
        .filter(Boolean),
      fields,
    });
  }

  return (
    <InboxItem href={pendingFact.source_href}>
      <div className="space-y-2">
        <div>
          <p className="text-sm font-semibold text-[var(--tc-workspace-focus)]">
            {pendingFact.title}
          </p>
          <p className="text-xs text-[var(--tc-workspace-text-muted)]">
            {pendingFactTypeText(pendingFact.fact_type)}
          </p>
        </div>
        <p className="tc-paper-fragment max-h-28 overflow-auto whitespace-pre-wrap p-2 text-sm leading-6">
          {contentText(pendingFact.content)}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            onClick={onConfirm}
            disabled={busy}
            className="h-8"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <CheckCircle2 className="size-4" />
            )}
            确认
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setEditing(current => !current)}
            disabled={busy}
            variant="outline"
            className="h-8"
          >
            <PencilLine className="size-4" />
            编辑确认
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={onReject}
            disabled={busy}
            variant="destructive"
            className="h-8"
          >
            <Ban className="size-4" />
            驳回
          </Button>
        </div>
        {editing ? (
          <div className="space-y-2 border-t border-[var(--tc-workspace-border-weak)] pt-3">
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              className="tc-input h-9 w-full px-2 text-sm"
              placeholder="知识名称"
            />
            <textarea
              value={summary}
              onChange={event => setSummary(event.target.value)}
              className="tc-input min-h-20 w-full resize-y px-2 py-2 text-sm"
              placeholder="确认摘要"
            />
            <input
              value={aliases}
              onChange={event => setAliases(event.target.value)}
              className="tc-input h-9 w-full px-2 text-sm"
              placeholder="别名，用英文逗号分隔"
            />
            <textarea
              value={fieldsJson}
              onChange={event => setFieldsJson(event.target.value)}
              className="tc-input min-h-24 w-full resize-y px-2 py-2 font-mono text-xs"
              placeholder="字段 JSON"
            />
            {localError ? (
              <p className="tc-danger rounded-[var(--tc-panel-radius)] border px-2 py-1 text-xs font-medium">
                {localError}
              </p>
            ) : null}
            <Button
              type="button"
              size="sm"
              onClick={submitEditedConfirmation}
              disabled={busy}
              className="h-8"
            >
              <CheckCircle2 className="size-4" />
              提交确认
            </Button>
          </div>
        ) : null}
      </div>
      <ItemFooter
        meta={pendingFactStatusText(pendingFact.status)}
        chapterId={chapterFromRefs(pendingFact)}
      />
    </InboxItem>
  );
}

function SavedAICardItem({ card }: { card: SavedAICardInfo }) {
  return (
    <InboxItem href={card.source_href}>
      <div className="space-y-2">
        <p className="text-sm font-semibold text-[var(--tc-workspace-focus)]">
          {cardTypeText(card.type)}
        </p>
        <p className="tc-paper-fragment max-h-28 overflow-auto whitespace-pre-wrap p-2 text-sm leading-6">
          {contentText(card.content)}
        </p>
      </div>
      <ItemFooter meta={aiCardStatusText(card.status)} chapterId={card.chapter_id} />
    </InboxItem>
  );
}

function ChapterIssueItem({ issue }: { issue: ChapterIssueInfo }) {
  return (
    <InboxItem href={issue.source_href}>
      <div className="space-y-2">
        <p className="text-sm font-semibold text-[var(--tc-workspace-focus)]">
          {issue.title}
        </p>
        <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--tc-workspace-text-secondary)]">
          {issue.description || "未填写描述"}
        </p>
      </div>
      <ItemFooter
        meta={`${issueSourceText(issue.source)} / ${chapterIssueStatusText(issue.status)}`}
        chapterId={issue.chapter_id}
      />
    </InboxItem>
  );
}

function InboxItem({
  href,
  children,
}: {
  href?: string | null;
  children: ReactNode;
}) {
  return (
    <article className="tc-panel-soft px-3 py-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] font-medium">
        <span className="tc-tag px-2 py-0.5">
          工作区范围
        </span>
        <span className="tc-tag px-2 py-0.5">
          非事实
        </span>
        {href ? (
          <Link
            href={href}
            className="ml-auto inline-flex items-center gap-1 rounded-full border border-[var(--tc-workspace-border)] px-2 py-0.5 normal-case text-[var(--tc-workspace-text-secondary)] transition-colors hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]"
          >
            <ExternalLink className="size-3" />
            正文
          </Link>
        ) : null}
      </div>
      {children}
    </article>
  );
}

function ItemFooter({
  meta,
  chapterId,
}: {
  meta: string;
  chapterId?: string | null;
}) {
  return (
    <div className="mt-3 flex flex-wrap justify-between gap-2 border-t border-[var(--tc-workspace-border-weak)] pt-2 text-xs text-[var(--tc-workspace-text-muted)]">
      <span>{meta}</span>
      {chapterId ? <span>{chapterLabel(chapterId)}</span> : null}
    </div>
  );
}

function laneHeaderClass(tone: LaneTone): string {
  const base =
    "flex items-center justify-between border-b border-[var(--tc-workspace-border-weak)] bg-[var(--tc-workspace-panel-soft)] px-3 py-3";
  if (tone === "idea") {
    return `${base} border-t-2 border-t-[var(--tc-paper-lime)]`;
  }
  if (tone === "pending") {
    return `${base} border-t-2 border-t-[var(--tc-paper-spring)]`;
  }
  if (tone === "ai") {
    return `${base} border-t-2 border-t-[var(--tc-aurora-violet)]`;
  }
  return `${base} border-t-2 border-t-[var(--tc-warning-text)]`;
}

function contentText(content: Record<string, unknown> | string): string {
  if (typeof content === "string") {
    return content;
  }
  const title = content.title;
  const body = content.body ?? content.summary ?? content.content ?? content.text;
  if (typeof title === "string" && typeof body === "string") {
    return `${title}\n${body}`;
  }
  if (typeof body === "string") {
    return body;
  }
  return JSON.stringify(content, null, 2);
}

function fieldsObject(content: Record<string, unknown> | string) {
  if (typeof content === "string") {
    return { text: content };
  }
  return content;
}

function cardTypeText(type: string): string {
  if (type === "suggestion") {
    return "建议卡片";
  }
  if (type === "pending_fact") {
    return "待确认设定卡片";
  }
  if (type === "text_candidate") {
    return "正文候选卡片";
  }
  return "智能助手卡片";
}

function pendingFactTypeText(type: string): string {
  const labels: Record<string, string> = {
    character: "人物",
    realm: "境界",
    technique: "功法",
    location: "地点",
    faction: "势力",
    item: "物品",
    rule: "规则/设定",
    event: "事件",
    foreshadow: "伏笔",
    other: "其他设定",
  };
  return labels[type] ?? "其他设定";
}

function pendingFactStatusText(status: string): string {
  const labels: Record<string, string> = {
    pending: "待确认",
    confirmed: "已确认",
    edited_confirmed: "已编辑确认",
    ignored: "已驳回",
  };
  return labels[status] ?? "待确认";
}

function aiCardStatusText(status: string): string {
  const labels: Record<string, string> = {
    generated: "待处理",
    inserted: "已插入正文",
    saved_to_inbox: "已保存到收件箱",
    converted_to_pending_fact: "已转为待确认设定",
    discarded: "已丢弃",
    retried: "已重试",
  };
  return labels[status] ?? "待处理";
}

function ideaSourceText(source: string): string {
  if (source === "ai") {
    return "智能助手建议";
  }
  if (source === "author") {
    return "作者记录";
  }
  return "来源未知";
}

function ideaStatusText(status: string): string {
  if (status === "open") {
    return "待处理";
  }
  if (status === "archived") {
    return "已归档";
  }
  return "待处理";
}

function issueSourceText(source: string): string {
  if (source === "ai") {
    return "智能助手发现";
  }
  if (source === "author") {
    return "作者记录";
  }
  return "来源未知";
}

function chapterIssueStatusText(status: string): string {
  if (status === "open") {
    return "待处理";
  }
  if (status === "resolved") {
    return "已解决";
  }
  if (status === "ignored") {
    return "已忽略";
  }
  return "待处理";
}

function chapterLabel(chapterId: string): string {
  const match = /^chapter_(\d+)$/.exec(chapterId);
  if (!match) {
    return `章节：${chapterId}`;
  }
  return `第 ${Number(match[1])} 章`;
}

function chapterFromRefs(pendingFact: PendingFactInfo): string | null {
  for (const sourceRef of pendingFact.source_refs) {
    if (sourceRef.chapter_id) {
      return sourceRef.chapter_id;
    }
  }
  return null;
}
