"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Pencil,
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
  listKnowledgeSchemas,
  listKnowledgeTypes,
  markKnowledgeCardActive,
  markKnowledgeCardDeprecated,
  patchKnowledgeCard,
} from "@/lib/api/mvp";
import type {
  KnowledgeFieldSchema,
  KnowledgeTypeInfo,
  KnowledgeTypeSchema,
  KnowledgeTypeValue,
  StructuredKnowledgeCard,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "draft" | "active" | "deprecated";
type CardFormState = Record<string, string>;
const KNOWLEDGE_PAGE_SIZE = 10;

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "draft", label: "草稿" },
  { value: "active", label: "有效" },
  { value: "deprecated", label: "已废弃" },
];

export function KnowledgeList() {
  const [types, setTypes] = useState<KnowledgeTypeInfo[]>([]);
  const [schemas, setSchemas] = useState<KnowledgeTypeSchema[]>([]);
  const [activeType, setActiveType] = useState<KnowledgeTypeValue>("character");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [cards, setCards] = useState<StructuredKnowledgeCard[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedCard, setSelectedCard] =
    useState<StructuredKnowledgeCard | null>(null);
  const [editingCardId, setEditingCardId] = useState<string | null>(null);
  const [isCreating, setCreating] = useState(false);
  const [form, setForm] = useState<CardFormState>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isFilterOpen, setFilterOpen] = useState(false);

  const schemaByType = useMemo(
    () => new Map(schemas.map(schema => [schema.type, schema])),
    [schemas],
  );
  const activeSchema = schemaByType.get(activeType) ?? schemas[0] ?? null;
  const activeTypeLabel =
    types.find(type => type.value === activeType)?.label ?? activeSchema?.label ?? "角色";
  const selectedCardId = selectedCard?.id ?? null;

  const applyLoadedCards = useCallback(
    (
      nextCards: StructuredKnowledgeCard[],
      schema: KnowledgeTypeSchema | null,
      preferredCardId?: string | null,
    ) => {
      const nextSelected = preferredCardId
        ? nextCards.find(card => card.id === preferredCardId) ?? null
        : null;
      setCards(nextCards);
      setSelectedCard(nextSelected);
      setCreating(false);
      setForm(nextSelected && schema ? formFromCard(schema, nextSelected) : {});
    },
    [],
  );

  async function reloadCards(
    preferredCardId?: string | null,
    pageOverride = currentPage,
  ) {
    if (!activeSchema) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await listKnowledgeCards({
        type: activeType,
        status,
        q: query,
        page: pageOverride,
        pageSize: KNOWLEDGE_PAGE_SIZE,
      });
      setTotalCount(response.total);
      applyLoadedCards(response.cards, activeSchema, preferredCardId ?? selectedCardId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "知识库加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadBootstrap() {
      setLoading(true);
      try {
        const [typeResponse, schemaResponse] = await Promise.all([
          listKnowledgeTypes(),
          listKnowledgeSchemas(),
        ]);
        if (!cancelled) {
          setTypes(typeResponse.types);
          setSchemas(schemaResponse.schemas);
          setActiveType(typeResponse.types[0]?.value ?? "character");
          setCurrentPage(1);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "知识库配置加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadBootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeSchema) {
      return;
    }
    let cancelled = false;
    async function loadCurrentCards() {
      setLoading(true);
      try {
        const response = await listKnowledgeCards({
          type: activeType,
          status,
          q: query,
          page: currentPage,
          pageSize: KNOWLEDGE_PAGE_SIZE,
        });
        if (!cancelled) {
          setTotalCount(response.total);
          applyLoadedCards(response.cards, activeSchema, null);
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
  }, [activeSchema, activeType, applyLoadedCards, currentPage, query, status]);

  function openCard(card: StructuredKnowledgeCard) {
    if (selectedCard?.id === card.id) {
      setSelectedCard(null);
      setCreating(false);
      setEditingCardId(null);
      setForm({});
      return;
    }
    const schema = schemaByType.get(card.type);
    setSelectedCard(card);
    setCreating(false);
    setEditingCardId(null);
    setForm(schema ? formFromCard(schema, card) : {});
  }

  function startCreateCard() {
    if (!activeSchema) {
      return;
    }
    setSelectedCard(null);
    setCreating(true);
    setForm(defaultForm(activeSchema));
    setMessage(null);
    setError(null);
  }

  async function saveCard() {
    if (!activeSchema || (!selectedCard && !isCreating)) {
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload = payloadFromForm(activeSchema, form);
      const response = selectedCard
        ? await patchKnowledgeCard(selectedCard.id, payload)
        : await createKnowledgeCard(activeType, payload);
      const nextPage = selectedCard ? currentPage : 1;
      setCurrentPage(nextPage);
      setEditingCardId(null);
      await reloadCards(response.card.id, nextPage);
      setMessage(selectedCard ? "已保存知识卡" : "已创建知识卡");
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
                  setCurrentPage(1);
                  setSelectedCard(null);
                  setCreating(false);
                  setEditingCardId(null);
                  setForm({});
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

        <section className="flex min-h-[calc(100vh-7rem)] min-w-0 flex-col">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">
                {activeTypeLabel} · {totalCount} 条
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                知识条目
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={query}
                onChange={event => {
                  setQuery(event.target.value);
                  setCurrentPage(1);
                }}
                placeholder="搜索当前分类名称"
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
                          setCurrentPage(1);
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
              <Button type="button" onClick={startCreateCard} disabled={saving}>
                <Plus className="size-4" />
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

          <div className="flex min-h-0 max-w-[980px] flex-1 flex-col">
            <div className="min-h-0 flex-1">
              {isCreating && activeSchema ? (
              <NewCardPanel
                schema={activeSchema}
                form={form}
                saving={saving}
                onFormChange={setForm}
                onSave={() => void saveCard()}
              />
            ) : null}

            {loading ? (
              <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : cards.length ? (
              <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                {cards.map(card => {
                  const expanded = selectedCard?.id === card.id;
                  const schema = schemaByType.get(card.type) ?? activeSchema;
                  const editing = editingCardId === card.id;
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
                            {statusLabel(card.status)} · {sourceOriginLabel(card.source_origin)} ·{" "}
                            {dateLabel(card.updated_at)}
                          </span>
                        </span>
                        <span className="hidden max-w-[360px] truncate text-xs text-[var(--tc-text-muted)] md:block">
                          {listDisplayText(schema, card)}
                        </span>
                      </button>
                      {expanded && schema ? (
                        editing ? (
                          <KnowledgeEditor
                            schema={schema}
                            form={form}
                            saving={saving}
                            isCreating={false}
                            onFormChange={setForm}
                            onSave={() => void saveCard()}
                            onMarkActive={() => void markActive()}
                            onMarkDeprecated={() => void markDeprecated()}
                          />
                        ) : (
                          <KnowledgeCardDetail
                            schema={schema}
                            card={card}
                            saving={saving}
                            onEdit={() => setEditingCardId(card.id)}
                            onMarkActive={() => void markActive()}
                            onMarkDeprecated={() => void markDeprecated()}
                          />
                        )
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="border-y border-dashed border-[var(--tc-border-subtle)] px-3 py-8 text-center text-sm text-[var(--tc-text-muted)]">
                当前分类暂无知识卡
              </div>
            )}
            </div>
            <PaginationControls
              page={currentPage}
              pageSize={KNOWLEDGE_PAGE_SIZE}
              total={totalCount}
              onPageChange={setCurrentPage}
            />
          </div>
        </section>
      </section>
    </AppShell>
  );
}

function NewCardPanel({
  schema,
  form,
  saving,
  onFormChange,
  onSave,
}: {
  schema: KnowledgeTypeSchema;
  form: CardFormState;
  saving: boolean;
  onFormChange: (form: CardFormState) => void;
  onSave: () => void;
}) {
  return (
    <div className="mb-5 border-y border-[var(--tc-border-subtle)] py-4">
      <p className="mb-3 text-sm text-[var(--tc-text-muted)]">
        新建{schema.label}知识卡
      </p>
      <KnowledgeEditor
        schema={schema}
        form={form}
        saving={saving}
        isCreating
        onFormChange={onFormChange}
        onSave={onSave}
      />
    </div>
  );
}

function KnowledgeCardDetail({
  schema,
  card,
  saving,
  onEdit,
  onMarkActive,
  onMarkDeprecated,
}: {
  schema: KnowledgeTypeSchema;
  card: StructuredKnowledgeCard;
  saving: boolean;
  onEdit: () => void;
  onMarkActive: () => void;
  onMarkDeprecated: () => void;
}) {
  const fields = detailFields(schema, card);
  return (
    <div className="pb-5 pl-10 pr-2">
      <div className="grid max-w-[860px] gap-3">
        <div className="flex flex-wrap gap-2 text-xs text-[var(--tc-text-muted)]">
          <span>{statusLabel(card.status)}</span>
          <span>{sourceOriginLabel(card.source_origin)}</span>
          <span>{dateLabel(card.updated_at)}</span>
        </div>
        {card.summary ? (
          <p className="whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
            {card.summary}
          </p>
        ) : null}
        {fields.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {fields.map(field => (
              <div
                key={field.key}
                className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2"
              >
                <p className="text-xs text-[var(--tc-text-muted)]">{field.label}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-primary)]">
                  {field.value}
                </p>
              </div>
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="button" size="sm" onClick={onEdit} disabled={saving}>
            <Pencil className="size-4" />
            编辑
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onMarkActive}
            disabled={saving}
          >
            <ShieldCheck className="size-4" />
            标记有效
          </Button>
          <Button
            type="button"
            size="sm"
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

function KnowledgeEditor({
  schema,
  form,
  saving,
  isCreating,
  onFormChange,
  onSave,
  onMarkActive,
  onMarkDeprecated,
}: {
  schema: KnowledgeTypeSchema;
  form: CardFormState;
  saving: boolean;
  isCreating: boolean;
  onFormChange: (form: CardFormState) => void;
  onSave: () => void;
  onMarkActive?: () => void;
  onMarkDeprecated?: () => void;
}) {
  const groupedFields = groupFields(schema.fields);
  return (
    <div className={cn("pb-5 pr-2", isCreating ? "" : "pl-10")}>
      <div className="grid max-w-[860px] gap-5">
        {groupedFields.map(group => (
          <section key={group.label} className="grid gap-3">
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
              {group.label}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {group.fields.map(field => (
                <SchemaField
                  key={field.field_key}
                  field={field}
                  value={form[field.field_key] ?? ""}
                  onChange={value =>
                    onFormChange({ ...form, [field.field_key]: value })
                  }
                />
              ))}
            </div>
          </section>
        ))}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            保存
          </Button>
          {!isCreating ? (
            <>
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
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function SchemaField({
  field,
  value,
  onChange,
}: {
  field: KnowledgeFieldSchema;
  value: string;
  onChange: (value: string) => void;
}) {
  const className =
    "mt-1 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)]";
  const fullWidth =
    field.field_type === "long_text" || field.field_type === "string_array";

  return (
    <label
      className={cn(
        "block text-sm text-[var(--tc-text-secondary)]",
        fullWidth ? "sm:col-span-2" : "",
      )}
    >
      {field.label}
      {field.required_when_active ? (
        <span className="ml-1 text-[var(--tc-text-muted)]">有效必填</span>
      ) : null}
      {field.field_type === "enum" ? (
        <select
          value={value}
          onChange={event => onChange(event.target.value)}
          className={cn(className, "h-9")}
        >
          {!field.required_when_active ? <option value="">未选择</option> : null}
          {field.options.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : field.field_type === "long_text" || field.field_type === "string_array" ? (
        <textarea
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={field.placeholder}
          className={cn(className, "min-h-20 resize-y py-2 leading-6")}
        />
      ) : field.field_type === "boolean" ? (
        <select
          value={value}
          onChange={event => onChange(event.target.value)}
          className={cn(className, "h-9")}
        >
          <option value="">未设置</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      ) : (
        <input
          type={field.field_type === "number" ? "number" : "text"}
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={field.placeholder}
          className={cn(className, "h-9")}
        />
      )}
    </label>
  );
}

function groupFields(fields: KnowledgeFieldSchema[]) {
  const groups: Array<{ label: string; fields: KnowledgeFieldSchema[] }> = [];
  for (const field of fields) {
    const label = field.display_group || "基础信息";
    let group = groups.find(item => item.label === label);
    if (!group) {
      group = { label, fields: [] };
      groups.push(group);
    }
    group.fields.push(field);
  }
  return groups;
}

function defaultForm(schema: KnowledgeTypeSchema): CardFormState {
  const form: CardFormState = {};
  for (const field of schema.fields) {
    form[field.field_key] = "";
  }
  form.importance = "normal";
  form.status = "draft";
  form.source_origin = "manual";
  form.source_note = "作者手动添加。可写章节、原文摘录、人工说明。";
  return form;
}

function formFromCard(
  schema: KnowledgeTypeSchema,
  card: StructuredKnowledgeCard,
): CardFormState {
  const form = defaultForm(schema);
  const values = card as Record<string, unknown>;
  for (const field of schema.fields) {
    const value = values[field.field_key];
    if (Array.isArray(value)) {
      form[field.field_key] = value.join("，");
    } else if (value === null || value === undefined) {
      form[field.field_key] = "";
    } else {
      form[field.field_key] = String(value);
    }
  }
  return form;
}

function payloadFromForm(
  schema: KnowledgeTypeSchema,
  form: CardFormState,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of schema.fields) {
    const rawValue = form[field.field_key] ?? "";
    if (field.field_type === "string_array") {
      payload[field.field_key] = splitList(rawValue);
    } else if (field.field_type === "number") {
      payload[field.field_key] = rawValue.trim() ? Number(rawValue) : null;
    } else if (field.field_type === "boolean") {
      payload[field.field_key] =
        rawValue === "" ? null : rawValue === "true";
    } else if (field.field_type === "enum") {
      payload[field.field_key] = rawValue || null;
    } else if (field.field_key === "name" || field.field_key === "summary") {
      payload[field.field_key] = rawValue;
    } else if (field.field_key === "source_note") {
      payload[field.field_key] = rawValue;
    } else {
      payload[field.field_key] = rawValue.trim() ? rawValue : null;
    }
  }
  return payload;
}

function splitList(value: string): string[] {
  return value
    .split(/[，,\n]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function listDisplayText(
  schema: KnowledgeTypeSchema | null,
  card: StructuredKnowledgeCard,
): string {
  if (!schema) {
    return card.summary;
  }
  const values = card as Record<string, unknown>;
  const parts = schema.fields
    .filter(field => field.list_display && !["name", "status"].includes(field.field_key))
    .map(field => displayFieldValue(field, values[field.field_key]))
    .filter(Boolean);
  return parts.join(" · ") || card.summary;
}

function detailFields(
  schema: KnowledgeTypeSchema,
  card: StructuredKnowledgeCard,
): Array<{ key: string; label: string; value: string }> {
  const values = card as Record<string, unknown>;
  return schema.fields
    .filter(
      field =>
        ![
          "name",
          "summary",
          "status",
          "source_origin",
          "source_note",
        ].includes(field.field_key),
    )
    .map(field => ({
      key: field.field_key,
      label: field.label,
      value: displayFieldValue(field, values[field.field_key]).replace(
        `${field.label}：`,
        "",
      ),
    }))
    .filter(field => field.value);
}

function displayFieldValue(
  field: KnowledgeFieldSchema,
  value: unknown,
): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (Array.isArray(value)) {
    return `${field.label}：${value.join("、")}`;
  }
  const option = field.options.find(item => item.value === value);
  return `${field.label}：${option?.label ?? String(value)}`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    active: "有效",
    deprecated: "已废弃",
  };
  return labels[status] ?? "草稿";
}

function sourceOriginLabel(sourceOrigin?: string | null): string {
  const labels: Record<string, string> = {
    inbox_fact: "收件箱事实转化",
    agent_extract: "正文自动提取",
    manual: "人工添加",
  };
  return sourceOrigin ? labels[sourceOrigin] ?? "来源未知" : "无来源";
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
        第 {page} / {totalPages} 页
      </span>
      <form
        className="flex items-center gap-2"
        onSubmit={submitPageJump}
        aria-label="按页搜索"
      >
        <label
          htmlFor="knowledge-page-jump"
          className="text-xs text-[var(--tc-text-muted)]"
        >
          跳至
        </label>
        <input
          id="knowledge-page-jump"
          name="page"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          value={jumpValue}
          onChange={event =>
            setJumpDraft({ page, value: event.target.value })
          }
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
