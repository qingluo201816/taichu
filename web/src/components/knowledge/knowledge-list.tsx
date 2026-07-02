"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

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
  { value: "deprecated", label: "已废弃" },
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
  const [isFilterOpen, setFilterOpen] = useState(false);

  const activeTypeLabel = useMemo(
    () => types.find(type => type.value === activeType)?.label ?? "角色",
    [activeType, types],
  );
  const selectedCardId = selectedCard?.id ?? null;

  const applyLoadedCards = useCallback(
    (nextCards: StructuredKnowledgeCard[], preferredCardId?: string | null) => {
      const nextSelected = preferredCardId
        ? nextCards.find(card => card.id === preferredCardId) ?? null
        : null;
      setCards(nextCards);
      setSelectedCard(nextSelected);
      setForm(nextSelected ? formFromCard(nextSelected) : emptyCardForm());
    },
    [],
  );

  async function reloadCards(preferredCardId?: string | null) {
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
      setLoading(true);
      try {
        const response = await listKnowledgeCards({
          type: activeType,
          status,
          q: query,
        });
        if (!cancelled) {
          applyLoadedCards(response.cards, null);
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
  }, [activeType, applyLoadedCards, query, status]);

  function openCard(card: StructuredKnowledgeCard) {
    if (selectedCard?.id === card.id) {
      setSelectedCard(null);
      setForm(emptyCardForm());
      return;
    }
    setSelectedCard(card);
    setForm(formFromCard(card));
  }

  async function createCurrentTypeCard() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await createKnowledgeCard(activeType);
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
    <AppShell activePath="/knowledge" escapeToHome>
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[176px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <div className="px-2 py-2">
            <p className="text-xs text-[var(--tc-text-muted)]">知识库</p>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
              分类
            </h1>
          </div>
          <div className="mt-2 grid gap-1">
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
                  "h-9 rounded-[var(--tc-radius-control)] px-3 text-left text-sm transition-colors",
                  activeType === type.value
                    ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                )}
              >
                {type.label}
              </button>
            ))}
          </div>
        </aside>

        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">
                {activeTypeLabel} · {cards.length} 条
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                知识条目
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="搜索当前分类"
                className="h-9 w-52 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)]"
              />
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setFilterOpen(current => !current)}
                  className="inline-flex h-9 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-3 text-sm text-[var(--tc-text-secondary)] hover:text-[var(--tc-text-primary)]"
                >
                  <SlidersHorizontal className="size-4" />
                  筛选
                </button>
                {isFilterOpen ? (
                  <div className="absolute right-0 top-[calc(100%+8px)] z-20 w-36 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
                    {statusFilters.map(filter => (
                      <button
                        key={filter.value}
                        type="button"
                        onClick={() => {
                          setStatus(filter.value);
                          setFilterOpen(false);
                        }}
                        className={cn(
                          "block h-8 w-full rounded-[var(--tc-radius-control)] px-2 text-left text-sm",
                          status === filter.value
                            ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                            : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)]",
                        )}
                      >
                        {filter.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <Button
                type="button"
                onClick={createCurrentTypeCard}
                disabled={saving}
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Plus className="size-4" />
                )}
                新建
              </Button>
            </div>
          </div>

          {error ? (
            <p className="tc-warning mb-3 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="tc-success mb-3 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {message}
            </p>
          ) : null}

          <div className="max-w-[980px]">
            {loading ? (
              <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : cards.length ? (
              <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                {cards.map(card => {
                  const expanded = selectedCard?.id === card.id;
                  return (
                    <article key={card.id}>
                      <button
                        type="button"
                        onClick={() => openCard(card)}
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
                            {card.name || "未命名知识卡"}
                          </span>
                          <span className="block truncate text-xs text-[var(--tc-text-muted)]">
                            {statusLabel(card.status)} · 来源{" "}
                            {card.source_refs.length} 条 ·{" "}
                            {dateLabel(card.updated_at)}
                          </span>
                        </span>
                      </button>
                      {expanded ? (
                        <KnowledgeEditor
                          form={form}
                          saving={saving}
                          onFormChange={setForm}
                          onSave={() => void saveCard()}
                          onMarkActive={() => void markActive()}
                          onMarkDeprecated={() => void markDeprecated()}
                          onAddSource={() =>
                            setForm(current => ({
                              ...current,
                              sourceRefs: [...current.sourceRefs, emptySourceRef],
                            }))
                          }
                          onUpdateSource={updateSourceRef}
                        />
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="border-y border-dashed border-[var(--tc-border-subtle)] px-3 py-16 text-center text-sm text-[var(--tc-text-muted)]">
                当前类型暂无知识卡
              </div>
            )}
          </div>
        </section>
      </section>
    </AppShell>
  );
}

function KnowledgeEditor({
  form,
  saving,
  onFormChange,
  onSave,
  onMarkActive,
  onMarkDeprecated,
  onAddSource,
  onUpdateSource,
}: {
  form: CardFormState;
  saving: boolean;
  onFormChange: (form: CardFormState) => void;
  onSave: () => void;
  onMarkActive: () => void;
  onMarkDeprecated: () => void;
  onAddSource: () => void;
  onUpdateSource: (index: number, updates: Partial<SourceReference>) => void;
}) {
  return (
    <div className="pb-5 pl-10 pr-2">
      <div className="grid max-w-[860px] gap-3">
        <TextField
          label="名称"
          value={form.name}
          onChange={name => onFormChange({ ...form, name })}
        />
        <TextField
          label="别名"
          value={form.aliases}
          onChange={aliases => onFormChange({ ...form, aliases })}
          placeholder="多个别名用逗号分隔"
        />
        <TextAreaField
          label="摘要"
          value={form.summary}
          onChange={summary => onFormChange({ ...form, summary })}
        />
        <TextAreaField
          label="正文补充"
          value={form.body}
          onChange={body => onFormChange({ ...form, body })}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="标签"
            value={form.tags}
            onChange={tags => onFormChange({ ...form, tags })}
            placeholder="多个标签用逗号分隔"
          />
          <label className="block text-sm text-[var(--tc-text-secondary)]">
            重要程度
            <select
              value={form.importance}
              onChange={event =>
                onFormChange({
                  ...form,
                  importance: event.target.value as StructuredKnowledgeImportance,
                })
              }
              className="mt-1 h-9 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-[var(--tc-text-primary)] outline-none"
            >
              <option value="core">核心</option>
              <option value="major">重要</option>
              <option value="normal">普通</option>
              <option value="minor">轻量</option>
            </select>
          </label>
        </div>
        <TextAreaField
          label="结构字段补充"
          value={form.fieldNote}
          onChange={fieldNote => onFormChange({ ...form, fieldNote })}
        />

        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
              来源引用
            </h3>
            <button
              type="button"
              onClick={onAddSource}
              className="text-sm text-[var(--tc-text-secondary)] hover:text-[var(--tc-text-primary)]"
            >
              添加来源
            </button>
          </div>
          <div className="grid gap-2">
            {form.sourceRefs.map((source, index) => (
              <div
                key={`${source.source_id}-${index}`}
                className="grid gap-2 border-l border-[var(--tc-border-subtle)] pl-3"
              >
                <div className="grid gap-2 sm:grid-cols-2">
                  <TextField
                    label="来源名称"
                    value={source.display_name}
                    onChange={display_name =>
                      onUpdateSource(index, { display_name })
                    }
                  />
                  <TextField
                    label="来源编号"
                    value={source.source_id}
                    onChange={source_id => onUpdateSource(index, { source_id })}
                  />
                </div>
                <TextAreaField
                  label="摘录"
                  value={source.excerpt}
                  onChange={excerpt => onUpdateSource(index, { excerpt })}
                />
                <TextField
                  label="备注"
                  value={source.note}
                  onChange={note => onUpdateSource(index, { note })}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2">
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            保存
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onMarkActive}
            disabled={saving}
          >
            <ShieldCheck className="size-4" />
            标记有效
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onMarkDeprecated}
            disabled={saving}
          >
            <Trash2 className="size-4" />
            标记废弃
          </Button>
        </div>
      </div>
    </div>
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
    <label className="block text-sm text-[var(--tc-text-secondary)]">
      {label}
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1 h-9 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)]"
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
    <label className="block text-sm text-[var(--tc-text-secondary)]">
      {label}
      <textarea
        value={value}
        onChange={event => onChange(event.target.value)}
        className="mt-1 min-h-20 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 leading-6 text-[var(--tc-text-primary)] outline-none"
      />
    </label>
  );
}
