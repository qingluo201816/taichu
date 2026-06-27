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
    <main className="min-h-screen bg-[#fffefc] text-black">
      <header className="border-b-[3px] border-black bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="inline-flex size-10 items-center justify-center rounded-lg border-2 border-black bg-white hover:bg-gray-100"
              aria-label="返回太初"
              title="返回太初"
            >
              <ArrowLeft className="size-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-gray-500">
                <BookOpenCheck className="size-4" />
                fact_scope / confirmed knowledge
              </div>
              <h1 className="mt-1 text-2xl font-semibold">知识库</h1>
            </div>
          </div>
          <Button
            size="sm"
            onClick={() => void refresh()}
            disabled={loading}
            className="rounded-full border-2 border-black"
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
          <div className="mb-4 rounded-lg border-2 border-black bg-white px-4 py-3 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex h-40 items-center justify-center text-sm font-semibold text-gray-500">
            <Loader2 className="mr-2 size-4 animate-spin" />
            加载中
          </div>
        ) : cards.length === 0 ? (
          <div className="rounded-lg border-2 border-dashed border-black bg-white px-4 py-12 text-center text-sm text-gray-500">
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
    <article className="rounded-lg border-[3px] border-black bg-white px-4 py-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{card.name}</p>
          <p className="text-xs font-semibold uppercase text-gray-500">
            {card.type} / {card.status}
          </p>
        </div>
        <span className="rounded-full border-2 border-black bg-[#cce7df] px-2 py-0.5 text-xs font-semibold">
          fact
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6">{card.summary}</p>
      {card.aliases.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {card.aliases.map(alias => (
            <span
              key={alias}
              className="rounded-full border-2 border-black px-2 py-0.5 text-xs"
            >
              {alias}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t-2 border-black pt-2 text-xs text-gray-500">
        <span className="inline-flex items-center gap-1">
          <FileText className="size-3" />
          SourceRef {card.source_refs.length}
        </span>
        <span>{card.id}</span>
      </div>
    </article>
  );
}
