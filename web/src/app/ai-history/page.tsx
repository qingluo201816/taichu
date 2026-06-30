"use client";

import { useEffect, useMemo, useState } from "react";
import { History, Loader2, Search } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { listChapters } from "@/lib/api/chapters";
import { listAIHistory, readAIHistory } from "@/lib/api/mvp";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  AIWorkspaceConversation,
  AIWorkspaceTaskType,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

const taskOptions: Array<{ value: "" | AIWorkspaceTaskType; label: string }> = [
  { value: "", label: "全部入口" },
  { value: "continue", label: "续写" },
  { value: "polish", label: "润色" },
  { value: "setting", label: "设定" },
  { value: "suggestion", label: "建议" },
  { value: "evidence", label: "证据" },
  { value: "chapter_summary", label: "章节摘要" },
];

export default function AIHistoryPage() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterId, setChapterId] = useState("");
  const [taskType, setTaskType] = useState<"" | AIWorkspaceTaskType>("");
  const [hasSource, setHasSource] = useState("");
  const [hasError, setHasError] = useState("");
  const [conversations, setConversations] = useState<AIWorkspaceConversation[]>([]);
  const [selected, setSelected] = useState<AIWorkspaceConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const chapterTitleById = useMemo(
    () => new Map(chapters.map(chapter => [chapter.id, chapter.title])),
    [chapters],
  );

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
          chapterId: chapterId || undefined,
          taskType: taskType || undefined,
          hasSource: hasSource || undefined,
          hasError: hasError || undefined,
        });
        if (!cancelled) {
          setConversations(response.conversations);
          setSelected(current => current ?? response.conversations[0] ?? null);
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
  }, [chapterId, hasError, hasSource, taskType]);

  async function selectConversation(conversationId: string) {
    try {
      setSelected((await readAIHistory(conversationId)).conversation);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "记录读取失败");
    }
  }

  return (
    <AppShell activePath="/ai-history">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
          <div className="mb-4">
            <p className="flex items-center gap-2 text-xs text-[var(--tc-smoke)]">
              <History className="size-4" />
              AI 历史
            </p>
            <h1 className="font-serif text-3xl text-[var(--tc-midnight-ink)]">
              写作区记录
            </h1>
          </div>

          <div className="grid gap-2">
            <select
              value={chapterId}
              onChange={event => {
                setChapterId(event.target.value);
                setSelected(null);
              }}
              className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
              aria-label="章节筛选"
            >
              <option value="">全部章节</option>
              {chapters.map(chapter => (
                <option key={chapter.id} value={chapter.id}>
                  {chapter.title}
                </option>
              ))}
            </select>
            <select
              value={taskType}
              onChange={event => {
                setTaskType(event.target.value as "" | AIWorkspaceTaskType);
                setSelected(null);
              }}
              className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
              aria-label="功能入口筛选"
            >
              {taskOptions.map(option => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={hasSource}
              onChange={event => {
                setHasSource(event.target.value);
                setSelected(null);
              }}
              className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
              aria-label="来源筛选"
            >
              <option value="">是否有来源</option>
              <option value="true">有来源</option>
              <option value="false">无来源</option>
            </select>
            <select
              value={hasError}
              onChange={event => {
                setHasError(event.target.value);
                setSelected(null);
              }}
              className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
              aria-label="错误筛选"
            >
              <option value="">是否错误</option>
              <option value="true">有错误</option>
              <option value="false">无错误</option>
            </select>
          </div>

          <div className="mt-4 space-y-2">
            {loading ? (
              <div className="flex h-24 items-center justify-center text-sm text-[var(--tc-smoke)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : conversations.length ? (
              conversations.map(conversation => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => void selectConversation(conversation.id)}
                  className={cn(
                    "w-full rounded-[var(--tc-radius-control)] border px-3 py-3 text-left",
                    selected?.id === conversation.id
                      ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)]"
                      : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)]",
                  )}
                >
                  <span className="block text-sm font-medium">
                    {taskLabel(conversation.task_type)}
                  </span>
                  <span className="text-xs text-[var(--tc-smoke)]">
                    {dateLabel(conversation.updated_at)} ·{" "}
                    {chapterTitleById.get(conversation.chapter_id) ?? "当前章节"} ·{" "}
                    {conversation.source_refs.length ? "有来源" : "无来源"}
                  </span>
                  <span className="mt-1 block truncate text-xs text-[var(--tc-smoke)]">
                    {firstUserInput(conversation)}
                  </span>
                </button>
              ))
            ) : (
              <div className="rounded-[var(--tc-radius-control)] border border-dashed border-[var(--tc-stone-mist)] px-3 py-8 text-center text-sm text-[var(--tc-smoke)]">
                暂无 AI 历史
              </div>
            )}
          </div>
        </aside>

        <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-5">
          {error ? (
            <p className="tc-warning mb-4 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
          {selected ? (
            <div>
              <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-[var(--tc-stone-mist)] pb-4">
                <div>
                  <p className="text-sm text-[var(--tc-deep-forest-teal)]">
                    {taskLabel(selected.task_type)}
                  </p>
                  <h2 className="font-serif text-4xl text-[var(--tc-midnight-ink)]">
                    {chapterTitleById.get(selected.chapter_id) ?? "当前章节"}
                  </h2>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-[var(--tc-smoke)]">
                  <span className="rounded-full border border-[var(--tc-stone-mist)] px-3 py-1">
                    模型：模拟模型
                  </span>
                  <span className="rounded-full border border-[var(--tc-stone-mist)] px-3 py-1">
                    {selected.is_mock ? "模拟输出" : "非模拟输出"}
                  </span>
                  <span className="rounded-full border border-[var(--tc-stone-mist)] px-3 py-1">
                    {hasErrorConversation(selected) ? "有错误" : "无错误"}
                  </span>
                </div>
              </div>

              <div className="space-y-4">
                {selected.messages.map(message => (
                  <article
                    key={message.message_id}
                    className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-4"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--tc-smoke)]">
                      <span>{roleLabel(message.role)}</span>
                      <span>本轮任务：{taskLabel(message.task_type)}</span>
                      <span>参考范围：{scopeLabel(message.reference_scope)}</span>
                      {message.output_type ? (
                        <span>输出类型：{outputLabel(message.output_type)}</span>
                      ) : null}
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-7">
                      {contentText(message.content)}
                    </p>
                    {message.source_refs.length ? (
                      <div className="mt-3 space-y-2 border-t border-[var(--tc-stone-mist)] pt-3">
                        {message.source_refs.map((source, index) => (
                          <div
                            key={`${source.source_id}-${index}`}
                            className="rounded-[var(--tc-radius-control)] bg-[var(--tc-white)] px-3 py-2 text-sm"
                          >
                            <p className="font-medium">
                              来源引用 {index + 1}：{source.display_name}
                            </p>
                            <p className="mt-1 text-[var(--tc-smoke)]">
                              {source.excerpt}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {message.prompt_snapshot ? (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-sm text-[var(--tc-deep-forest-teal)]">
                          提示词快照
                        </summary>
                        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-3 text-xs leading-5">
                          {message.prompt_snapshot.final_prompt}
                        </pre>
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex min-h-96 items-center justify-center gap-2 text-sm text-[var(--tc-smoke)]">
              <Search className="size-4" />
              选择一条 AI 历史
            </div>
          )}
        </section>
      </section>
    </AppShell>
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
    error: "错误",
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
  return "错误";
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

function hasErrorConversation(conversation: AIWorkspaceConversation): boolean {
  return conversation.messages.some(message => message.role === "error");
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "暂无";
}
