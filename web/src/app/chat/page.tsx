"use client";

import { Database, FileText, Loader2, Send, Sparkles } from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import BackButton from "@/components/back-button";
import { Button } from "@/components/ui/button";
import { runAgentChat } from "@/lib/api/agents";
import { listChapters } from "@/lib/api/chapters";
import type { AgentChatResponse } from "@/lib/types/agents";
import type { ChapterInfo } from "@/lib/types/chapters";

export default function ChatPage() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterId, setChapterId] = useState<string>("");
  const [message, setMessage] = useState("");
  const [includeChapter, setIncludeChapter] = useState(true);
  const [includeFacts, setIncludeFacts] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentChatResponse | null>(null);

  useEffect(() => {
    let active = true;
    listChapters()
      .then(response => {
        if (!active) {
          return;
        }
        setChapters(response.chapters);
        setChapterId(response.chapters[0]?.id ?? "");
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "章节加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const answer = useMemo(() => {
    if (!result) {
      return "";
    }
    const content = result.card.content;
    if (typeof content === "string") {
      return content;
    }
    const value = content.answer ?? content.body ?? content.summary;
    return typeof value === "string" ? value : JSON.stringify(content, null, 2);
  }, [result]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || loading) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await runAgentChat({
        message: trimmed,
        chapter_id: chapterId || null,
        include_current_chapter: includeChapter,
        include_confirmed_facts: includeFacts,
      });
      setResult(response);
      setMessage("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "对话生成失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="tc-workspace-page min-h-screen px-5 py-7 md:px-6">
      <BackButton />
      <div className="mx-auto flex min-h-[calc(100vh-56px)] w-full max-w-6xl flex-col gap-5 pt-12">
        <header className="flex flex-col gap-3 border-b border-[var(--tc-workspace-border-weak)] pb-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-[var(--tc-workspace-text-secondary)]">
              <Sparkles className="size-4" />
              智能对话
            </div>
            <h1 className="text-3xl font-semibold text-[var(--tc-workspace-focus)]">
              对话写作
            </h1>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="tc-tag px-3 py-1">
              回复保存为结果卡片
            </span>
            <span className="tc-tag px-3 py-1">
              仅使用正式事实范围
            </span>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[360px_1fr]">
          <form
            onSubmit={submit}
            className="tc-panel flex flex-col gap-4 p-4"
          >
            <label className="flex flex-col gap-2 text-sm font-medium text-[var(--tc-workspace-text-secondary)]">
              当前章节
              <select
                value={chapterId}
                onChange={event => setChapterId(event.target.value)}
                className="tc-input h-10 px-3 text-sm"
              >
                {chapters.map(chapter => (
                  <option key={chapter.id} value={chapter.id}>
                    {chapter.title}
                  </option>
                ))}
              </select>
            </label>

            <ToggleRow
              icon={<FileText className="size-4" />}
              label="使用当前章节"
              checked={includeChapter}
              onChange={setIncludeChapter}
            />
            <ToggleRow
              icon={<Database className="size-4" />}
              label="使用已确认知识"
              checked={includeFacts}
              onChange={setIncludeFacts}
            />

            <label className="flex min-h-0 flex-1 flex-col gap-2 text-sm font-medium text-[var(--tc-workspace-text-secondary)]">
              问题
              <textarea
                value={message}
                onChange={event => setMessage(event.target.value)}
                className="tc-input min-h-44 flex-1 resize-none p-3 text-sm leading-6"
                placeholder="写下你想和太初讨论的创作问题"
              />
              <span className="text-xs font-normal text-[var(--tc-workspace-text-muted)]">
                输入问题后，“发送”按钮会自动点亮。
              </span>
            </label>

            <Button
              type="submit"
              disabled={loading || !message.trim()}
              className="h-11"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
              发送
            </Button>
            {error ? (
              <p className="tc-danger rounded-[var(--tc-panel-radius)] border px-3 py-2 text-sm font-medium">
                {error}
              </p>
            ) : null}
          </form>

          <section className="tc-panel min-h-[520px] p-5">
            {result ? (
              <div className="flex h-full flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tc-workspace-border-weak)] pb-3">
                  <div>
                    <p className="font-mono text-sm text-[var(--tc-workspace-text-muted)]">
                      {result.card.id}
                    </p>
                    <h2 className="text-xl font-semibold text-[var(--tc-workspace-focus)]">
                      太初回复
                    </h2>
                  </div>
                  <span className="tc-tag px-3 py-1">
                    {cardStatusText(result.card.status)}
                  </span>
                </div>
                <div className="tc-paper-card whitespace-pre-wrap px-4 py-4 text-sm leading-7">
                  {answer}
                </div>
                <div className="mt-auto border-t border-[var(--tc-workspace-border-weak)] pt-4">
                  <h3 className="mb-3 text-sm font-semibold text-[var(--tc-workspace-focus)]">
                    来源
                  </h3>
                  {result.conversation.source_refs.length ? (
                    <div className="grid gap-2">
                      {result.conversation.source_refs.map((sourceRef, index) => (
                        <div
                          key={`${sourceRef.source_type}-${sourceRef.source_id}-${index}`}
                          className="tc-panel-soft p-3 text-xs"
                        >
                          <p className="font-medium text-[var(--tc-workspace-text-secondary)]">
                            来源 {index + 1} · {sourceTypeText(sourceRef.source_type)} ·{" "}
                            {sourceRef.source_id}
                          </p>
                          <p className="mt-1 break-all font-mono text-[var(--tc-workspace-text-muted)]">
                            {sourceRef.path}
                          </p>
                          <p className="mt-2 leading-5 text-[var(--tc-workspace-text-secondary)]">
                            {sourceRef.excerpt}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--tc-workspace-text-muted)]">
                      以下为推测
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm font-medium text-[var(--tc-workspace-text-muted)]">
                等待一次对话
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

function cardStatusText(status: string): string {
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

function sourceTypeText(sourceType: string): string {
  const labels: Record<string, string> = {
    chapter: "正文",
    knowledge: "已确认知识",
  };
  return labels[sourceType] ?? "来源";
}

function ToggleRow({
  icon,
  label,
  checked,
  onChange,
}: {
  icon: ReactNode;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="tc-panel-soft flex h-11 items-center justify-between gap-3 px-3 text-sm font-medium text-[var(--tc-workspace-text-secondary)]">
      <span className="flex items-center gap-2">
        {icon}
        {label}
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={event => onChange(event.target.checked)}
        className="size-4 accent-[var(--tc-workspace-focus)]"
      />
    </label>
  );
}
