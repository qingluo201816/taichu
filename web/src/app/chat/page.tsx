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
    <main className="min-h-screen bg-[#fbfaf7] px-6 py-7 text-zinc-950">
      <BackButton />
      <div className="mx-auto flex min-h-[calc(100vh-56px)] w-full max-w-6xl flex-col gap-5 pt-12">
        <header className="flex flex-col gap-2 border-b-2 border-black pb-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-600">
              <Sparkles className="size-4" />
              智能对话
            </div>
            <h1 className="text-3xl font-bold">对话写作</h1>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-semibold text-zinc-600">
            <span className="rounded-full border-2 border-black bg-white px-3 py-1">
              回复保存为结果卡片
            </span>
            <span className="rounded-full border-2 border-black bg-white px-3 py-1">
              仅使用正式事实范围
            </span>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[360px_1fr]">
          <form
            onSubmit={submit}
            className="flex flex-col gap-4 border-2 border-black bg-white p-4"
          >
            <label className="flex flex-col gap-2 text-sm font-semibold">
              当前章节
              <select
                value={chapterId}
                onChange={event => setChapterId(event.target.value)}
                className="h-10 rounded-md border-2 border-black bg-white px-3 text-sm outline-none"
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

            <label className="flex min-h-0 flex-1 flex-col gap-2 text-sm font-semibold">
              问题
              <textarea
                value={message}
                onChange={event => setMessage(event.target.value)}
                className="min-h-44 flex-1 resize-none rounded-md border-2 border-black bg-white p-3 text-sm leading-6 outline-none focus:bg-[#fffefc]"
                placeholder="写下你想和太初讨论的创作问题"
              />
            </label>

            <Button
              type="submit"
              disabled={loading || !message.trim()}
              className="h-11 rounded-full border-2 border-black"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
              发送
            </Button>
            {error ? (
              <p className="text-sm font-semibold text-red-700">{error}</p>
            ) : null}
          </form>

          <section className="min-h-[520px] border-2 border-black bg-white p-5">
            {result ? (
              <div className="flex h-full flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black pb-3">
                  <div>
                    <p className="text-sm font-semibold text-zinc-500">
                      {result.card.id}
                    </p>
                    <h2 className="text-xl font-bold">太初回复</h2>
                  </div>
                  <span className="rounded-full border-2 border-black px-3 py-1 text-xs font-semibold">
                    {cardStatusText(result.card.status)}
                  </span>
                </div>
                <div className="whitespace-pre-wrap text-sm leading-7">
                  {answer}
                </div>
                <div className="mt-auto border-t-2 border-black pt-4">
                  <h3 className="mb-3 text-sm font-bold">来源</h3>
                  {result.conversation.source_refs.length ? (
                    <div className="grid gap-2">
                      {result.conversation.source_refs.map((sourceRef, index) => (
                        <div
                          key={`${sourceRef.source_type}-${sourceRef.source_id}-${index}`}
                          className="rounded-md border-2 border-black p-3 text-xs"
                        >
                          <p className="font-semibold">
                            来源 {index + 1} · {sourceTypeText(sourceRef.source_type)} ·{" "}
                            {sourceRef.source_id}
                          </p>
                          <p className="mt-1 break-all text-zinc-500">
                            {sourceRef.path}
                          </p>
                          <p className="mt-2 leading-5">{sourceRef.excerpt}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-500">以下为推测</p>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm font-semibold text-zinc-400">
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
    <label className="flex h-11 items-center justify-between gap-3 rounded-md border-2 border-black px-3 text-sm font-semibold">
      <span className="flex items-center gap-2">
        {icon}
        {label}
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={event => onChange(event.target.checked)}
        className="size-4 accent-black"
      />
    </label>
  );
}
