"use client";

import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ChevronDown, ChevronRight, History, Loader2, RotateCcw } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { listChapters } from "@/lib/api/chapters";
import {
  getWritingAIRun,
  listWritingAIRuns,
  replayWritingAIRun,
} from "@/lib/api/writing-ai";
import type { ChapterInfo } from "@/lib/types/chapters";
import type { WritingAIButtonType, WritingAIRun } from "@/lib/types/writing-ai";
import { cn } from "@/lib/utils";

const taskOptions: Array<{ value: "" | WritingAIButtonType; label: string }> = [
  { value: "", label: "全部记录" },
  { value: "chat", label: "纯对话" },
  { value: "continue", label: "续写" },
  { value: "polish", label: "润色" },
  { value: "setting", label: "设定" },
  { value: "suggestion", label: "建议" },
  { value: "evidence", label: "证据" },
  { value: "chapter_summary", label: "章节摘要" },
  { value: "inspiration", label: "灵感" },
  { value: "fact", label: "事实" },
];

const HISTORY_PAGE_SIZE = 10;

export default function AIHistoryPage() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterQuery, setChapterQuery] = useState("");
  const [buttonType, setButtonType] = useState<"" | WritingAIButtonType>("");
  const [runs, setRuns] = useState<WritingAIRun[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<WritingAIRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chapterTitleById = useMemo(
    () => new Map(chapters.map(chapter => [chapter.id, chapter.title])),
    [chapters],
  );
  const activeTaskLabel =
    taskOptions.find(option => option.value === buttonType)?.label ?? "全部记录";

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
        const response = await listWritingAIRuns({
          chapterName: chapterQuery || undefined,
          buttonType: buttonType || undefined,
          page: currentPage,
          pageSize: HISTORY_PAGE_SIZE,
        });
        if (!cancelled) {
          setRuns(response.runs);
          setTotalCount(response.total);
          setExpandedId(null);
          setExpandedRun(null);
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
  }, [chapterQuery, currentPage, buttonType]);

  async function toggleRun(run: WritingAIRun) {
    if (expandedId === run.run_id) {
      setExpandedId(null);
      setExpandedRun(null);
      return;
    }
    setExpandedId(run.run_id);
    setExpandedRun(run);
    setDetailLoading(true);
    setError(null);
    try {
      setExpandedRun(await getWritingAIRun(run.run_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "记录读取失败");
    } finally {
      setDetailLoading(false);
    }
  }

  async function replayRun(runId: string) {
    setDetailLoading(true);
    setError(null);
    try {
      const replayed = await replayWritingAIRun(runId);
      setExpandedRun(replayed);
      setRuns(current =>
        current.map(item => (item.run_id === replayed.run_id ? replayed : item)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "回放记录失败");
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
              运行记录
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
                  setButtonType(option.value);
                  setCurrentPage(1);
                }}
                className={cn(
                  "h-9 rounded-[var(--tc-radius-control)] px-3 text-left text-sm transition-colors",
                  buttonType === option.value
                    ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </aside>

        <section className="flex min-h-[calc(100vh-7rem)] min-w-0 flex-col">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
                <History className="size-4" />
                {activeTaskLabel}
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                写作 AI 运行记录
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

          <div className="flex min-h-0 max-w-[980px] flex-1 flex-col">
            <div className="min-h-0 flex-1">
              {loading ? (
                <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  加载中
                </div>
              ) : runs.length ? (
                <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                  {runs.map(run => {
                    const expanded = expandedId === run.run_id;
                    const detail =
                      expanded && expandedRun?.run_id === run.run_id
                        ? expandedRun
                        : run;
                    return (
                      <article key={run.run_id}>
                        <button
                          type="button"
                          onClick={() => void toggleRun(run)}
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
                              {buttonLabel(run.button_type)} ·{" "}
                              {chapterTitleById.get(run.chapter_id) ||
                                run.chapter_title ||
                                "当前章节"}
                            </span>
                            <span className="block truncate text-xs text-[var(--tc-text-muted)]">
                              {dateLabel(run.updated_at)} · {statusLabel(run.status)} ·
                              模型：{run.model || "未记录"}
                            </span>
                            <span className="mt-0.5 block truncate text-xs text-[var(--tc-text-muted)]">
                              {inputSummary(run)}
                            </span>
                          </span>
                          <span className="hidden shrink-0 text-xs text-[var(--tc-text-muted)] sm:inline">
                            知识库：{knowledgeState(run)} · 解析：{parseState(run)}
                          </span>
                        </button>
                        {expanded ? (
                          <RunDetail
                            run={detail}
                            loading={detailLoading}
                            onReplay={() => void replayRun(detail.run_id)}
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
            </div>
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

function RunDetail({
  run,
  loading,
  onReplay,
}: {
  run: WritingAIRun;
  loading: boolean;
  onReplay: () => void;
}) {
  return (
    <div className="pb-5 pl-10 pr-2">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs text-[var(--tc-text-muted)]">
          <span>状态：{statusLabel(run.status)}</span>
          <span>参考范围：{scopeLabel(run.reference_scope)}</span>
          <span>知识库：{knowledgeState(run)}</span>
          <span>解析：{parseState(run)}</span>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={loading}
          onClick={onReplay}
          className="h-8"
        >
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RotateCcw className="size-4" />
          )}
          回放记录
        </Button>
      </div>
      {loading ? (
        <p className="mb-3 inline-flex items-center gap-2 text-sm text-[var(--tc-text-muted)]">
          <Loader2 className="size-4 animate-spin" />
          读取详情
        </p>
      ) : null}
      <div className="grid max-w-[900px] gap-4">
        <TraceBlock title="输入">
          <p>作者输入：{run.input.user_input || "未填写额外要求"}</p>
          {run.input.selected_text ? <p>当前选区：{run.input.selected_text}</p> : null}
        </TraceBlock>
        <TraceBlock title="检索上下文">
          {run.retrieval_context ? (
            <>
              <p>{run.retrieval_context.empty_reason || "已检索到有效知识卡"}</p>
              {run.retrieval_context.items.map((item, index) => (
                <p key={item.item_id}>
                  来源 {index + 1}：{item.display_name} · {item.usage}
                  {item.excerpt ? ` · ${item.excerpt}` : ""}
                </p>
              ))}
            </>
          ) : (
            <p>未记录检索上下文</p>
          )}
        </TraceBlock>
        {run.prompt_snapshot ? (
          <details className="border-l border-[var(--tc-border-subtle)] pl-3">
            <summary className="cursor-pointer text-sm text-[var(--tc-text-secondary)]">
              Prompt 快照
            </summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[var(--tc-text-muted)]">
              {[
                "【系统提示词】",
                run.prompt_snapshot.system_prompt,
                "",
                "【用户提示词】",
                run.prompt_snapshot.user_prompt,
              ].join("\n")}
            </pre>
          </details>
        ) : null}
        <TraceBlock title="结构化输出">
          <pre className="whitespace-pre-wrap text-xs leading-5">
            {run.structured_output
              ? JSON.stringify(run.structured_output.content, null, 2)
              : "暂无结构化输出"}
          </pre>
        </TraceBlock>
        <TraceBlock title="模型原始输出">
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap text-xs leading-5">
            {run.raw_llm_output || "暂无原始输出"}
          </pre>
        </TraceBlock>
        {run.error ? (
          <TraceBlock title="错误信息">
            <p>{run.error}</p>
          </TraceBlock>
        ) : null}
      </div>
    </div>
  );
}

function TraceBlock({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="border-l border-[var(--tc-border-subtle)] pl-3">
      <h3 className="mb-1 text-xs text-[var(--tc-text-muted)]">{title}</h3>
      <div className="space-y-1 whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
        {children}
      </div>
    </section>
  );
}

function inputSummary(run: WritingAIRun): string {
  return run.input.user_input || run.input.selected_text || "未填写额外要求";
}

function knowledgeState(run: WritingAIRun): string {
  if (!run.retrieval_context) {
    return "未记录";
  }
  if (run.retrieval_context.items.length > 0) {
    return "有上下文";
  }
  return run.retrieval_context.empty_reason ? "空结果" : "无上下文";
}

function parseState(run: WritingAIRun): string {
  return run.structured_output ? "成功" : "未完成";
}

function buttonLabel(button: string): string {
  const labels: Record<string, string> = {
    chat: "纯对话",
    continue: "续写",
    polish: "润色",
    setting: "设定",
    suggestion: "建议",
    evidence: "证据",
    chapter_summary: "章节摘要",
    inspiration: "灵感",
    fact: "事实",
  };
  return labels[button] ?? "功能入口";
}

function scopeLabel(scope: string): string {
  const labels: Record<string, string> = {
    none: "无小说上下文",
    selection: "选区",
    chapter: "本章",
    full_text: "全文",
  };
  return labels[scope] ?? "正文参考";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    retrieving: "检索中",
    calling_llm: "调用模型中",
    parsing: "解析中",
    completed: "完成",
    failed: "失败",
  };
  return labels[status] ?? "未知状态";
}

function dateLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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
  const [jumpDraft, setJumpDraft] = useState({ page, value: String(page) });
  const jumpValue = jumpDraft.page === page ? jumpDraft.value : String(page);

  function submitPageJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPage = Number(jumpValue);
    if (!jumpValue.trim() || !Number.isFinite(parsedPage)) {
      setJumpDraft({ page, value: String(page) });
      return;
    }
    const nextPage = Math.min(totalPages, Math.max(1, Math.trunc(parsedPage)));
    setJumpDraft({ page: nextPage, value: String(nextPage) });
    onPageChange(nextPage);
  }

  return (
    <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[var(--tc-border-subtle)] pt-4 text-sm text-[var(--tc-text-muted)]">
      <span className="shrink-0">
        第 {page} / {totalPages} 页，共 {total} 条
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
        >
          上一页
        </Button>
        <form onSubmit={submitPageJump} className="flex items-center gap-1">
          <input
            value={jumpValue}
            onChange={event => setJumpDraft({ page, value: event.target.value })}
            className="h-8 w-14 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-center text-sm text-[var(--tc-text-primary)] outline-none"
            aria-label="页码"
          />
          <Button type="submit" variant="outline" size="sm">
            跳转
          </Button>
        </form>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
