"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, History, Loader2 } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { listChapters } from "@/lib/api/chapters";
import { listAIHistory, readAIHistory } from "@/lib/api/mvp";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  AIWorkspaceConversation,
  AIWorkspaceMessage,
  AIWorkspaceTaskType,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

const taskOptions: Array<{ value: "" | AIWorkspaceTaskType; label: string }> = [
  { value: "", label: "全部记录" },
  { value: "continue", label: "续写" },
  { value: "polish", label: "润色" },
  { value: "setting", label: "设定" },
  { value: "suggestion", label: "建议" },
  { value: "evidence", label: "证据" },
  { value: "chapter_summary", label: "章节摘要" },
];
const HISTORY_PAGE_SIZE = 10;

export default function AIHistoryPage() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterQuery, setChapterQuery] = useState("");
  const [taskType, setTaskType] = useState<"" | AIWorkspaceTaskType>("");
  const [conversations, setConversations] = useState<AIWorkspaceConversation[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedConversation, setExpandedConversation] =
    useState<AIWorkspaceConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chapterTitleById = useMemo(
    () => new Map(chapters.map(chapter => [chapter.id, chapter.title])),
    [chapters],
  );
  const activeTaskLabel =
    taskOptions.find(option => option.value === taskType)?.label ?? "全部记录";

  useEffect(() => {
    let cancelled = false;
    listChapters()
      .then(response => {
        if (!cancelled) {
          setChapters(response.chapters);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        const response = await listAIHistory({
          chapterName: chapterQuery || undefined,
          taskType: taskType || undefined,
          page: currentPage,
          pageSize: HISTORY_PAGE_SIZE,
        });
        if (!cancelled) {
          setConversations(response.conversations);
          setTotalCount(response.total);
          setExpandedId(null);
          setExpandedConversation(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "AI 历史加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [chapterQuery, currentPage, taskType]);

  async function toggleConversation(conversation: AIWorkspaceConversation) {
    if (expandedId === conversation.id) {
      setExpandedId(null);
      setExpandedConversation(null);
      return;
    }
    setExpandedId(conversation.id);
    setExpandedConversation(conversation);
    setDetailLoading(true);
    setError(null);
    try {
      setExpandedConversation((await readAIHistory(conversation.id)).conversation);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "记录读取失败");
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <AppShell activePath="/ai-history">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[176px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <div className="px-2 py-2">
            <p className="text-xs text-[var(--tc-text-muted)]">AI 历史</p>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
              模块
            </h1>
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
              共 {totalCount} 条
            </p>
          </div>
          <div className="mt-2 grid gap-1">
            {taskOptions.map(option => (
              <button
                key={option.value || "all"}
                type="button"
                onClick={() => {
                  setTaskType(option.value);
                  setCurrentPage(1);
                }}
                className={cn(
                  "h-9 rounded-[var(--tc-radius-control)] px-3 text-left text-sm transition-colors",
                  taskType === option.value
                    ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </aside>

        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
                <History className="size-4" />
                {activeTaskLabel}
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                当前模块记录
              </h2>
            </div>
            {loading ? (
              <span className="inline-flex items-center gap-2 text-sm text-[var(--tc-text-muted)]">
                <Loader2 className="size-4 animate-spin" />
                加载中
              </span>
            ) : null}
          </div>

          <div className="mb-4 flex max-w-[980px] flex-wrap gap-2">
            <input
              value={chapterQuery}
              onChange={event => {
                setChapterQuery(event.target.value);
                setCurrentPage(1);
              }}
              placeholder="搜索章节名称"
              className="h-9 w-60 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)]"
            />
          </div>

          {error ? (
            <p className="tc-warning mb-3 max-w-[860px] rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}

          <div className="max-w-[980px]">
            {loading ? (
              <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : conversations.length ? (
              <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                {conversations.map(conversation => {
                  const expanded = expandedId === conversation.id;
                  const detail =
                    expanded && expandedConversation?.id === conversation.id
                      ? expandedConversation
                      : conversation;
                  return (
                    <article key={conversation.id}>
                      <button
                        type="button"
                        onClick={() => void toggleConversation(conversation)}
                        className="flex min-h-12 w-full items-center gap-3 px-1 py-2 text-left"
                      >
                        <span className="inline-flex size-7 shrink-0 items-center justify-center text-[var(--tc-text-muted)]">
                          {expanded ? (
                            <ChevronDown className="size-4" />
                          ) : (
                            <ChevronRight className="size-4" />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-[var(--tc-text-primary)]">
                            {taskLabel(conversation.task_type)} ·{" "}
                            {chapterTitleById.get(conversation.chapter_id) ??
                              "当前章节"}
                          </span>
                          <span className="block truncate text-xs text-[var(--tc-text-muted)]">
                            {dateLabel(conversation.updated_at)} ·{" "}
                            {conversation.is_mock ? "模拟输出" : "真实输出"}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-[var(--tc-text-muted)]">
                            {firstUserInput(conversation)}
                          </span>
                        </span>
                      </button>
                      {expanded ? (
                        <ConversationDetail
                          conversation={detail}
                          loading={detailLoading}
                        />
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="border-y border-dashed border-[var(--tc-border-subtle)] px-3 py-16 text-center text-sm text-[var(--tc-text-muted)]">
                暂无 AI 历史
              </div>
            )}
            <PaginationControls
              page={currentPage}
              pageSize={HISTORY_PAGE_SIZE}
              total={totalCount}
              onPageChange={setCurrentPage}
            />
          </div>
        </section>
      </section>
    </AppShell>
  );
}

function ConversationDetail({
  conversation,
  loading,
}: {
  conversation: AIWorkspaceConversation;
  loading: boolean;
}) {
  return (
    <div className="pb-5 pl-10 pr-2">
      {loading ? (
        <p className="mb-3 inline-flex items-center gap-2 text-sm text-[var(--tc-text-muted)]">
          <Loader2 className="size-4 animate-spin" />
          读取详情
        </p>
      ) : null}
      <div className="mb-3 flex flex-wrap gap-2 text-xs text-[var(--tc-text-muted)]">
        <span>{conversation.is_mock ? "模拟输出" : "真实输出"}</span>
        <span>参考范围：{scopeLabel(conversation.reference_scope)}</span>
      </div>
      <div className="grid max-w-[900px] gap-4">
        {conversation.messages.map(message => (
          <MessageBlock key={message.message_id} message={message} />
        ))}
      </div>
    </div>
  );
}

function MessageBlock({ message }: { message: AIWorkspaceMessage }) {
  return (
    <article className="border-l border-[var(--tc-border-subtle)] pl-3">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-[var(--tc-text-muted)]">
        <span>{roleLabel(message.role)}</span>
        <span>本轮任务：{taskLabel(message.task_type)}</span>
        <span>参考范围：{scopeLabel(message.reference_scope)}</span>
        {message.output_type ? (
          <span>输出类型：{outputLabel(message.output_type)}</span>
        ) : null}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
        {contentText(message.content)}
      </p>
      {message.prompt_snapshot ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-[var(--tc-text-secondary)]">
            提示词快照
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap border-l border-[var(--tc-border-subtle)] pl-3 text-xs leading-5 text-[var(--tc-text-muted)]">
            {message.prompt_snapshot.final_prompt}
          </pre>
        </details>
      ) : null}
    </article>
  );
}

function firstUserInput(conversation: AIWorkspaceConversation): string {
  const message = conversation.messages.find(item => item.role === "user");
  if (!message) {
    return "暂无输入";
  }
  return contentText(message.content);
}

function contentText(content: Record<string, unknown> | string): string {
  if (typeof content === "string") {
    return content;
  }
  if (typeof content.text === "string") {
    return content.text;
  }
  if (typeof content.summary === "string") {
    return content.summary;
  }
  if (typeof content.setting_addition === "string") {
    return [
      `设定补充：${content.setting_addition}`,
      `使用建议：${stringValue(content.usage_suggestion)}`,
      `可能影响：${stringValue(content.possible_impact)}`,
    ].join("\n");
  }
  if (typeof content.suggestion === "string") {
    return [
      `问题：${stringValue(content.problem)}`,
      `判断：${stringValue(content.judgement)}`,
      `建议：${content.suggestion}`,
    ].join("\n");
  }
  if (typeof content.conclusion === "string") {
    return `结论：${content.conclusion}\n推断：${stringValue(content.inference)}`;
  }
  return JSON.stringify(content, null, 2);
}

function taskLabel(task: string): string {
  const labels: Record<string, string> = {
    chat: "纯对话",
    continue: "续写",
    polish: "润色",
    setting: "设定",
    suggestion: "建议",
    evidence: "证据",
    chapter_summary: "章节摘要",
  };
  return labels[task] ?? "功能入口";
}

function scopeLabel(scope: string): string {
  const labels: Record<string, string> = {
    none: "无小说上下文",
    selection: "选区",
    chapter: "本章",
    fulltext: "全文",
  };
  return labels[scope] ?? "正文参考";
}

function outputLabel(output: string): string {
  const labels: Record<string, string> = {
    text_candidate: "正文候选",
    setting_result: "设定结果",
    suggestion_result: "建议结果",
    evidence_result: "证据结果",
    chapter_summary: "章节摘要",
    error: "系统消息",
  };
  return labels[output] ?? "输出";
}

function roleLabel(role: string): string {
  if (role === "user") {
    return "作者";
  }
  if (role === "assistant") {
    return "助手";
  }
  return "系统消息";
}

function PaginationControls({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  function submitPageJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem(
      "page",
    ) as HTMLInputElement | null;
    const parsedPage = Number(input?.value);
    if (!Number.isFinite(parsedPage)) {
      if (input) {
        input.value = String(page);
      }
      return;
    }
    const nextPage = Math.min(totalPages, Math.max(1, Math.trunc(parsedPage)));
    if (input) {
      input.value = String(nextPage);
    }
    onPageChange(nextPage);
  }

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--tc-text-muted)]">
      <span className="shrink-0">
        第 {page} / {totalPages} 页
      </span>
      <form
        className="flex items-center gap-2"
        onSubmit={submitPageJump}
        aria-label="按页搜索"
      >
        <label
          htmlFor="ai-history-page-jump"
          className="text-xs text-[var(--tc-text-muted)]"
        >
          跳至
        </label>
        <input
          key={page}
          id="ai-history-page-jump"
          name="page"
          type="number"
          min={1}
          max={totalPages}
          defaultValue={page}
          className="h-8 w-16 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-center text-sm text-[var(--tc-text-primary)] outline-none"
        />
        <Button type="submit" size="sm" variant="outline">
          前往
        </Button>
      </form>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
        >
          上一页
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={page >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}

function dateLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间未知";
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "暂无";
}
