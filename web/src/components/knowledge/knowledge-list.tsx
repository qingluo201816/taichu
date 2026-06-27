"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BookOpenCheck,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { readKnowledge } from "@/lib/api/knowledge";
import type { KnowledgeCardInfo } from "@/lib/types/knowledge";

export function KnowledgeList() {
  const [cards, setCards] = useState<KnowledgeCardInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const response = await readKnowledge();
      setCards(response.cards);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "知识库加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadInitialKnowledge() {
      try {
        const response = await readKnowledge();
        if (!cancelled) {
          setCards(response.cards);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "知识库加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInitialKnowledge();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="tc-workspace-page min-h-screen">
      <header className="tc-workspace-header">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4">
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
                <BookOpenCheck className="size-4" />
                正式事实范围 / 已确认知识
              </div>
              <h1 className="mt-1 text-2xl font-semibold text-[var(--tc-workspace-focus)]">
                知识库
              </h1>
            </div>
          </div>
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
      </header>

      <section className="mx-auto max-w-6xl px-5 py-5">
        {error ? (
          <div className="tc-danger mb-4 rounded-[var(--tc-panel-radius)] border px-4 py-3 text-sm font-medium">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex h-40 items-center justify-center text-sm font-medium text-[var(--tc-workspace-text-muted)]">
            <Loader2 className="mr-2 size-4 animate-spin" />
            加载中
          </div>
        ) : cards.length === 0 ? (
          <div className="rounded-[var(--tc-panel-radius)] border border-dashed border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-panel)] px-4 py-12 text-center text-sm text-[var(--tc-workspace-text-muted)]">
            暂无已确认知识
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {cards.map(card => (
              <KnowledgeCardItem key={card.id} card={card} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function KnowledgeCardItem({ card }: { card: KnowledgeCardInfo }) {
  return (
    <article className="tc-paper-card px-4 py-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">
            {card.name}
          </p>
          <p className="font-sans text-xs font-medium text-[var(--tc-paper-ink-muted)]">
            {knowledgeTypeText(card.type)} / {knowledgeStatusText(card.status)}
          </p>
        </div>
        <span className="tc-paper-tag px-2 py-0.5">
          正式事实
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6">{card.summary}</p>
      {card.aliases.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {card.aliases.map(alias => (
            <span
              key={alias}
              className="rounded-full border border-[var(--tc-paper-border)] px-2 py-0.5 font-sans text-xs"
            >
              {alias}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--tc-paper-border-soft)] pt-2 font-sans text-xs text-[var(--tc-paper-ink-muted)]">
        <span className="inline-flex items-center gap-1">
          <FileText className="size-3" />
          证据来源 {card.source_refs.length}
        </span>
        <span className="font-mono">知识编号：{card.id}</span>
      </div>
    </article>
  );
}

function knowledgeTypeText(type: string): string {
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
  };
  return labels[type] ?? "设定";
}

function knowledgeStatusText(status: string): string {
  const labels: Record<string, string> = {
    confirmed: "已确认",
    archived: "已归档",
  };
  return labels[status] ?? "已确认";
}
