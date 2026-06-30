"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpenCheck, Loader2, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  createKnowledgeCard,
  listKnowledgeCards,
  listKnowledgeTypes,
  markKnowledgeCardActive,
  markKnowledgeCardDeprecated,
  patchKnowledgeCard,
} from "@/lib/api/mvp";
import type {
  KnowledgeTypeInfo,
  KnowledgeTypeValue,
  SourceReference,
  StructuredKnowledgeCard,
  StructuredKnowledgeImportance,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "draft" | "active" | "deprecated";

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "draft", label: "草稿" },
  { value: "active", label: "有效" },
  { value: "deprecated", label: "只看废弃" },
];

const emptySourceRef: SourceReference = {
  source_type: "author_note",
  source_id: "作者手动记录",
  display_name: "作者手动记录",
  excerpt: "作者手动记录",
  note: "",
  author_note_body: "作者手动记录",
};

export function KnowledgeList() {
  const [types, setTypes] = useState<KnowledgeTypeInfo[]>([]);
  const [activeType, setActiveType] = useState<KnowledgeTypeValue>("character");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [cards, setCards] = useState<StructuredKnowledgeCard[]>([]);
  const [selectedCard, setSelectedCard] =
    useState<StructuredKnowledgeCard | null>(null);
  const [form, setForm] = useState<CardFormState>(emptyCardForm());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const activeTypeLabel = useMemo(
    () => types.find(type => type.value === activeType)?.label ?? "角色",
    [activeType, types],
  );

  const selectedCardId = selectedCard?.id ?? null;

  const applyLoadedCards = useCallback(
    (
      nextCards: StructuredKnowledgeCard[],
      preferredCardId?: string | null,
    ) => {
      const nextSelected =
        nextCards.find(card => card.id === preferredCardId) ??
        nextCards[0] ??
        null;
      setCards(nextCards);
      setSelectedCard(nextSelected);
      setForm(nextSelected ? formFromCard(nextSelected) : emptyCardForm());
    },
    [],
  );

  async function reloadCards(preferredCardId?: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await listKnowledgeCards({
        type: activeType,
        status,
        q: query,
      });
      applyLoadedCards(response.cards, preferredCardId ?? selectedCardId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "知识库加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadTypes() {
      try {
        const response = await listKnowledgeTypes();
        if (!cancelled) {
          setTypes(response.types);
          setActiveType(response.types[0]?.value ?? "character");
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "知识类型加载失败");
        }
      }
    }
    void loadTypes();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadCurrentCards() {
      try {
        const response = await listKnowledgeCards({
          type: activeType,
          status,
          q: query,
        });
        if (!cancelled) {
          applyLoadedCards(response.cards, selectedCardId);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "知识库加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadCurrentCards();
    return () => {
      cancelled = true;
    };
  }, [activeType, applyLoadedCards, query, selectedCardId, status]);

  async function createCurrentTypeCard() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await createKnowledgeCard(activeType);
      setSelectedCard(response.card);
      setForm(formFromCard(response.card));
      await reloadCards(response.card.id);
      setMessage("已新建知识卡");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建知识卡失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveCard() {
    if (!selectedCard) {
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await patchKnowledgeCard(selectedCard.id, {
        name: form.name,
        aliases: splitList(form.aliases),
        summary: form.summary,
        body: form.body,
        tags: splitList(form.tags),
        importance: form.importance,
        source_refs: form.sourceRefs.filter(source => source.excerpt.trim()),
        fields: form.fieldNote.trim() ? { note: form.fieldNote.trim() } : {},
      });
      setSelectedCard(response.card);
      setForm(formFromCard(response.card));
      await reloadCards(response.card.id);
      setMessage("已保存知识卡");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存知识卡失败");
    } finally {
      setSaving(false);
    }
  }

  async function markActive() {
    if (!selectedCard) {
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await markKnowledgeCardActive(selectedCard.id);
      setSelectedCard(response.card);
      setForm(formFromCard(response.card));
      await reloadCards(response.card.id);
      setMessage("已标记为有效");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "标记有效失败");
    } finally {
      setSaving(false);
    }
  }

  async function markDeprecated() {
    if (!selectedCard) {
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await markKnowledgeCardDeprecated(selectedCard.id);
      setSelectedCard(response.card);
      setForm(formFromCard(response.card));
      await reloadCards(response.card.id);
      setMessage("已标记废弃");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "标记废弃失败");
    } finally {
      setSaving(false);
    }
  }

  function updateSourceRef(index: number, updates: Partial<SourceReference>) {
    setForm(current => ({
      ...current,
      sourceRefs: current.sourceRefs.map((source, sourceIndex) =>
        sourceIndex === index ? { ...source, ...updates } : source,
      ),
    }));
  }

  return (
    <AppShell activePath="/knowledge">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-smoke)]">知识库</p>
              <h1 className="font-serif text-3xl text-[var(--tc-midnight-ink)]">
                知识卡
              </h1>
            </div>
            <Button type="button" size="icon" title="新建知识卡" onClick={createCurrentTypeCard}>
              <Plus className="size-4" />
            </Button>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {types.map(type => (
              <button
                key={type.value}
                type="button"
                onClick={() => {
                  setLoading(true);
                  setActiveType(type.value);
                  setSelectedCard(null);
                  setForm(emptyCardForm());
                }}
                className={cn(
                  "h-10 rounded-[var(--tc-radius-control)] border text-sm transition-colors",
                  activeType === type.value
                    ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)]"
                    : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)]",
                )}
              >
                {type.label}
              </button>
            ))}
          </div>

          <div className="mt-4 space-y-3">
            <input
              value={query}
              onChange={event => {
                setLoading(true);
                setQuery(event.target.value);
              }}
              placeholder="搜索知识卡"
              className="h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm outline-none"
            />
            <div className="grid grid-cols-2 gap-2">
              {statusFilters.map(filter => (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => {
                    setLoading(true);
                    setStatus(filter.value);
                  }}
                  className={cn(
                    "h-9 rounded-[var(--tc-radius-control)] border text-sm",
                    status === filter.value
                      ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)]"
                      : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)]",
                  )}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {loading ? (
              <div className="flex h-24 items-center justify-center text-sm text-[var(--tc-smoke)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : cards.length ? (
              cards.map(card => (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => setSelectedCard(card)}
                  className={cn(
                    "w-full rounded-[var(--tc-radius-control)] border px-3 py-3 text-left transition-colors",
                    selectedCard?.id === card.id
                      ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)]"
                      : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)]",
                  )}
                >
                  <span className="block truncate font-medium">
                    {card.name || "未命名知识卡"}
                  </span>
                  <span className="text-xs text-[var(--tc-smoke)]">
                    {statusLabel(card.status)} · 来源 {card.source_refs.length} 条
                  </span>
                </button>
              ))
            ) : (
              <div className="rounded-[var(--tc-radius-control)] border border-dashed border-[var(--tc-stone-mist)] px-3 py-8 text-center text-sm text-[var(--tc-smoke)]">
                当前类型暂无知识卡
              </div>
            )}
          </div>
        </aside>

        <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-5">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-sm text-[var(--tc-deep-forest-teal)]">
                <BookOpenCheck className="size-4" />
                {activeTypeLabel}
              </p>
              <h2 className="font-serif text-4xl text-[var(--tc-midnight-ink)]">
                {selectedCard ? form.name || "编辑知识卡" : "新建当前类型知识卡"}
              </h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={saveCard} disabled={!selectedCard || saving}>
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                保存
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={markActive}
                disabled={!selectedCard || saving}
              >
                <ShieldCheck className="size-4" />
                标记为有效
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={markDeprecated}
                disabled={!selectedCard || saving}
              >
                <Trash2 className="size-4" />
                标记废弃
              </Button>
            </div>
          </div>

          {error ? (
            <p className="tc-warning mb-4 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="tc-success mb-4 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {message}
            </p>
          ) : null}

          {selectedCard ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <TextField label="名称" value={form.name} onChange={name => setForm({ ...form, name })} />
              <TextField label="别名" value={form.aliases} onChange={aliases => setForm({ ...form, aliases })} placeholder="多个别名用逗号分隔" />
              <TextAreaField label="摘要" value={form.summary} onChange={summary => setForm({ ...form, summary })} />
              <TextAreaField label="正文补充" value={form.body} onChange={body => setForm({ ...form, body })} />
              <TextField label="标签" value={form.tags} onChange={tags => setForm({ ...form, tags })} placeholder="多个标签用逗号分隔" />
              <label className="block text-sm font-medium">
                重要程度
                <select
                  value={form.importance}
                  onChange={event =>
                    setForm({
                      ...form,
                      importance: event.target.value as StructuredKnowledgeImportance,
                    })
                  }
                  className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
                >
                  <option value="core">核心</option>
                  <option value="major">重要</option>
                  <option value="normal">普通</option>
                  <option value="minor">轻量</option>
                </select>
              </label>
              <TextAreaField label="结构字段补充" value={form.fieldNote} onChange={fieldNote => setForm({ ...form, fieldNote })} />
              <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">来源引用</h3>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setForm(current => ({
                        ...current,
                        sourceRefs: [...current.sourceRefs, emptySourceRef],
                      }))
                    }
                  >
                    添加来源
                  </Button>
                </div>
                <div className="space-y-3">
                  {form.sourceRefs.map((source, index) => (
                    <div
                      key={`${source.source_id}-${index}`}
                      className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-3"
                    >
                      <TextField
                        label="来源名称"
                        value={source.display_name}
                        onChange={display_name =>
                          updateSourceRef(index, { display_name })
                        }
                      />
                      <TextField
                        label="来源编号"
                        value={source.source_id}
                        onChange={source_id => updateSourceRef(index, { source_id })}
                      />
                      <TextAreaField
                        label="摘录"
                        value={source.excerpt}
                        onChange={excerpt => updateSourceRef(index, { excerpt })}
                      />
                      <TextField
                        label="备注"
                        value={source.note}
                        onChange={note => updateSourceRef(index, { note })}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={createCurrentTypeCard}
              className="flex min-h-80 w-full items-center justify-center rounded-[var(--tc-radius-card)] border border-dashed border-[var(--tc-stone-mist)] text-sm text-[var(--tc-smoke)]"
            >
              新建当前类型知识卡
            </button>
          )}
        </section>
      </section>
    </AppShell>
  );
}

type CardFormState = {
  name: string;
  aliases: string;
  summary: string;
  body: string;
  tags: string;
  importance: StructuredKnowledgeImportance;
  fieldNote: string;
  sourceRefs: SourceReference[];
};

function emptyCardForm(): CardFormState {
  return {
    name: "",
    aliases: "",
    summary: "",
    body: "",
    tags: "",
    importance: "normal",
    fieldNote: "",
    sourceRefs: [],
  };
}

function formFromCard(card: StructuredKnowledgeCard): CardFormState {
  return {
    name: card.name,
    aliases: card.aliases.join("，"),
    summary: card.summary,
    body: card.body,
    tags: card.tags.join("，"),
    importance: card.importance,
    fieldNote: typeof card.fields.note === "string" ? card.fields.note : "",
    sourceRefs: card.source_refs.length ? card.source_refs : [emptySourceRef],
  };
}

function splitList(value: string): string[] {
  return value
    .split(/[，,]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    active: "有效",
    deprecated: "已废弃",
  };
  return labels[status] ?? "草稿";
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 outline-none"
      />
    </label>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <textarea
        value={value}
        onChange={event => onChange(event.target.value)}
        className="mt-2 min-h-28 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 leading-6 outline-none"
      />
    </label>
  );
}
