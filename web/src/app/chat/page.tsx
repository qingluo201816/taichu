"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Bot, FileText, Loader2, Send } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { runAgentChat } from "@/lib/api/agents";
import { listChapters } from "@/lib/api/chapters";
import type { AgentChatResponse } from "@/lib/types/agents";
import type { ChapterInfo } from "@/lib/types/chapters";

export default function AgentWorkspacePage() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterId, setChapterId] = useState("");
  const [message, setMessage] = useState("");
  const [includeChapter, setIncludeChapter] = useState(true);
  const [includeFacts, setIncludeFacts] = useState(false);
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
      setError(caught instanceof Error ? caught.message : "工作台处理失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell activePath="/chat">
      <section className="mx-auto grid max-w-6xl gap-6 px-5 py-8 lg:grid-cols-[360px_1fr]">
        <header className="lg:col-span-2">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--tc-deep-forest-teal)] px-3 py-1 text-sm text-[var(--tc-deep-forest-teal)]">
            <Bot className="size-4" />
            实验功能
          </div>
          <h1 className="font-serif text-4xl text-[var(--tc-midnight-ink)]">
            智能体工作台
          </h1>
        </header>

        <form
          onSubmit={submit}
          className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-5"
        >
          <label className="block text-sm font-medium text-[var(--tc-midnight-ink)]">
            当前章节
            <select
              value={chapterId}
              onChange={event => setChapterId(event.target.value)}
              className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
            >
              {chapters.map(chapter => (
                <option key={chapter.id} value={chapter.id}>
                  {chapter.title}
                </option>
              ))}
            </select>
          </label>

          <div className="mt-4 grid gap-2">
            <ToggleRow
              label="使用当前章节"
              checked={includeChapter}
              onChange={setIncludeChapter}
            />
            <ToggleRow
              label="使用已确认知识"
              checked={includeFacts}
              onChange={setIncludeFacts}
            />
          </div>

          <label className="mt-4 block text-sm font-medium text-[var(--tc-midnight-ink)]">
            输入
            <textarea
              value={message}
              onChange={event => setMessage(event.target.value)}
              className="mt-2 min-h-44 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 leading-6 outline-none"
              placeholder="写下要交给实验工作台处理的问题"
            />
          </label>

          <Button
            type="submit"
            disabled={loading || !message.trim()}
            className="mt-4 w-full"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            发送
          </Button>
          {error ? (
            <p className="tc-warning mt-3 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
        </form>

        <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-5">
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-[var(--tc-smoke)]">
                <FileText className="size-4" />
                实验工作台输出
              </div>
              <div className="whitespace-pre-wrap rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-4 text-sm leading-7">
                {answer}
              </div>
            </div>
          ) : (
            <div className="flex min-h-80 items-center justify-center text-sm text-[var(--tc-smoke)]">
              暂无输出
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex h-10 items-center justify-between rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm">
      {label}
      <input
        type="checkbox"
        checked={checked}
        onChange={event => onChange(event.target.checked)}
        className="size-4 accent-[var(--tc-deep-forest-teal)]"
      />
    </label>
  );
}
