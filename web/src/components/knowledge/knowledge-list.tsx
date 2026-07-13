"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CheckCircle2,
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
import {
  StructuredKnowledgeForm,
  StructuredKnowledgeView,
} from "@/components/knowledge/structured-knowledge-fields";
import { Button } from "@/components/ui/button";
import { listChapters } from "@/lib/api/chapters";
import {
  confirmKnowledgeCard,
  createKnowledgeCard,
  listKnowledgeCards,
  listKnowledgeSchemas,
  listKnowledgeTypes,
  patchKnowledgeCard,
  rejectKnowledgeCard,
} from "@/lib/api/mvp";
import {
  appearanceImportanceLabel,
  buildKnowledgeReferenceOptions,
  displayKnowledgeFieldValue,
  formStateFromKnowledgeValues,
  knowledgePayloadFromForm,
  validateKnowledgeForm,
  type KnowledgeFormErrors,
  type KnowledgeFormState,
  type KnowledgeReferenceOptions,
} from "@/lib/knowledge/structured-fields";
import type {
  KnowledgeTypeInfo,
  KnowledgeTypeSchema,
  KnowledgeTypeValue,
  StructuredKnowledgeCard,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type LifecycleFilter = "all" | "draft" | "confirmed" | "rejected";
type KnowledgeToastState = {
  id: number;
  message: string;
};
const KNOWLEDGE_PAGE_SIZE = 10;
const KNOWLEDGE_DETAIL_HIDDEN_FIELD_KEYS = new Set([
  "name",
  "lifecycle",
  "source_origin",
]);
const KNOWLEDGE_FORM_HIDDEN_FIELD_KEYS = new Set([
  "lifecycle",
  "appearance_chapter_count",
]);

const lifecycleFilters: Array<{ value: LifecycleFilter; label: string }> = [
  { value: "confirmed", label: "已确认" },
  { value: "draft", label: "草稿" },
  { value: "all", label: "已确认和草稿" },
  { value: "rejected", label: "已废弃" },
];

export function KnowledgeList() {
  const [types, setTypes] = useState<KnowledgeTypeInfo[]>([]);
  const [schemas, setSchemas] = useState<KnowledgeTypeSchema[]>([]);
  const [activeType, setActiveType] = useState<KnowledgeTypeValue>("character");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("confirmed");
  const [query, setQuery] = useState("");
  const [cards, setCards] = useState<StructuredKnowledgeCard[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedCard, setSelectedCard] =
    useState<StructuredKnowledgeCard | null>(null);
  const [editingCardId, setEditingCardId] = useState<string | null>(null);
  const [isCreating, setCreating] = useState(false);
  const [form, setForm] = useState<KnowledgeFormState>({});
  const [formErrors, setFormErrors] = useState<KnowledgeFormErrors>({});
  const [referenceOptions, setReferenceOptions] =
    useState<KnowledgeReferenceOptions>({});
  const [chapterCount, setChapterCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<KnowledgeToastState | null>(null);
  const [isFilterOpen, setFilterOpen] = useState(false);
  const toastTimerRef = useRef<number | null>(null);
  const toastIdRef = useRef(0);

  const schemaByType = useMemo(
    () => new Map(schemas.map(schema => [schema.type, schema])),
    [schemas],
  );
  const activeSchema = schemaByType.get(activeType) ?? schemas[0] ?? null;
  const activeTypeLabel =
    types.find(type => type.value === activeType)?.label ?? activeSchema?.label ?? "角色";
  const selectedCardId = selectedCard?.id ?? null;

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  function clearKnowledgeToast() {
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
    setToast(null);
  }

  function showKnowledgeToast(message: string) {
    toastIdRef.current += 1;
    setToast({ id: toastIdRef.current, message });
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 1900);
  }

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
      setFormErrors({});
      setForm(nextSelected && schema ? formFromCard(schema, nextSelected) : {});
    },
    [],
  );

  async function reloadCards(
    preferredCardId?: string | null,
    pageOverride = currentPage,
    lifecycleOverride = lifecycle,
  ) {
    if (!activeSchema) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await listKnowledgeCards({
        type: activeType,
        lifecycle: lifecycleOverride,
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
        const [typeResponse, schemaResponse, chapterResponse] = await Promise.all([
          listKnowledgeTypes(),
          listKnowledgeSchemas(),
          listChapters(),
        ]);
        const [characterResult, factionResult] = await Promise.allSettled([
          listKnowledgeCards({
            type: "character",
            lifecycle: "confirmed",
            page: 1,
            pageSize: 100,
          }),
          listKnowledgeCards({
            type: "faction",
            lifecycle: "confirmed",
            page: 1,
            pageSize: 100,
          }),
        ]);
        if (!cancelled) {
          setTypes(typeResponse.types);
          setSchemas(schemaResponse.schemas);
          setReferenceOptions(
            buildKnowledgeReferenceOptions(
              schemaResponse.schemas,
              chapterResponse.chapters,
              characterResult.status === "fulfilled"
                ? characterResult.value.cards
                : [],
              factionResult.status === "fulfilled"
                ? factionResult.value.cards
                : [],
            ),
          );
          setChapterCount(chapterResponse.chapters.length);
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
          lifecycle,
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
  }, [activeSchema, activeType, applyLoadedCards, currentPage, lifecycle, query]);

  function openCard(card: StructuredKnowledgeCard) {
    if (selectedCard?.id === card.id) {
      setSelectedCard(null);
      setCreating(false);
      setEditingCardId(null);
      setFormErrors({});
      setForm({});
      return;
    }
    const schema = schemaByType.get(card.type);
    setSelectedCard(card);
    setCreating(false);
    setEditingCardId(null);
    setFormErrors({});
    setForm(schema ? formFromCard(schema, card) : {});
  }

  function startCreateCard() {
    if (!activeSchema) {
      return;
    }
    setSelectedCard(null);
    setCreating(true);
    setFormErrors({});
    setForm(defaultForm(activeSchema));
    clearKnowledgeToast();
    setError(null);
  }

  async function saveCard() {
    if (!activeSchema || (!selectedCard && !isCreating)) {
      return;
    }
    setError(null);
    clearKnowledgeToast();
    const nextErrors = validateKnowledgeForm(
      activeSchema,
      form,
      KNOWLEDGE_FORM_HIDDEN_FIELD_KEYS,
      selectedCard?.lifecycle === "confirmed",
    );
    setFormErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      setError("请先补全必填字段后再保存。");
      return;
    }
    setSaving(true);
    try {
      const payload = payloadFromForm(activeSchema, form);
      const response = selectedCard
        ? await patchKnowledgeCard(selectedCard.id, payload)
        : await createKnowledgeCard(activeType, payload);
      const nextPage = selectedCard ? currentPage : 1;
      setCurrentPage(nextPage);
      setEditingCardId(null);
      if (selectedCard) {
        await reloadCards(response.card.id, nextPage);
        showKnowledgeToast("已保存知识卡");
      } else {
        setLifecycle("draft");
        await reloadCards(response.card.id, nextPage, "draft");
        showKnowledgeToast("草稿已创建，请补全后确认入库");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存知识卡失败");
    } finally {
      setSaving(false);
    }
  }

  async function confirmCard() {
    if (!selectedCard) {
      return;
    }
    setSaving(true);
    setError(null);
    clearKnowledgeToast();
    try {
      const response = await confirmKnowledgeCard(selectedCard.id);
      setLifecycle("confirmed");
      setCurrentPage(1);
      await reloadCards(response.card.id, 1, "confirmed");
      showKnowledgeToast("已确认入库");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认入库失败");
    } finally {
      setSaving(false);
    }
  }

  async function rejectCard() {
    if (!selectedCard) {
      return;
    }
    setSaving(true);
    setError(null);
    clearKnowledgeToast();
    try {
      await rejectKnowledgeCard(selectedCard.id);
      setSelectedCard(null);
      setEditingCardId(null);
      setForm({});
      await reloadCards(null);
      showKnowledgeToast("已删除知识卡");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除知识卡失败");
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
                    {lifecycleFilters.map(filter => (
                      <button
                        key={filter.value}
                        type="button"
                        onClick={() => {
                          setLifecycle(filter.value);
                          setCurrentPage(1);
                          setFilterOpen(false);
                        }}
                        className={cn(
                          "block h-8 w-full rounded-[var(--tc-radius-control)] px-2 text-left text-sm",
                          lifecycle === filter.value
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

          <div className="flex min-h-0 max-w-[980px] flex-1 flex-col">
            <div className="min-h-0 flex-1">
              {isCreating && activeSchema ? (
              <NewCardPanel
                schema={activeSchema}
                form={form}
                errors={formErrors}
                referenceOptions={referenceOptions}
                saving={saving}
                onFormChange={nextForm => {
                  setForm(nextForm);
                  setFormErrors({});
                  setError(null);
                }}
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
                            {cardMetadata(card)}
                          </span>
                        </span>
                        <span className="hidden max-w-[360px] truncate text-xs text-[var(--tc-text-muted)] md:block">
                          {listDisplayText(
                            schema,
                            card,
                            referenceOptions,
                            chapterCount,
                          )}
                        </span>
                      </button>
                      {expanded && schema ? (
                        editing ? (
                          <KnowledgeEditor
                            schema={schema}
                            form={form}
                            errors={formErrors}
                            referenceOptions={referenceOptions}
                            saving={saving}
                            isCreating={false}
                            onFormChange={nextForm => {
                              setForm(nextForm);
                              setFormErrors({});
                              setError(null);
                            }}
                            onSave={() => void saveCard()}
                            onCancel={() => {
                              setEditingCardId(null);
                              setForm(formFromCard(schema, card));
                              setFormErrors({});
                              setError(null);
                            }}
                            onConfirm={
                              card.lifecycle === "draft"
                                ? () => void confirmCard()
                                : undefined
                            }
                            onReject={
                              card.lifecycle === "rejected"
                                ? undefined
                                : () => void rejectCard()
                            }
                          />
                        ) : (
                          <KnowledgeCardDetail
                            schema={schema}
                            card={card}
                            referenceOptions={referenceOptions}
                            chapterCount={chapterCount}
                            saving={saving}
                            onEdit={
                              card.lifecycle === "rejected"
                                ? undefined
                                : () => setEditingCardId(card.id)
                            }
                            onConfirm={
                              card.lifecycle === "draft"
                                ? () => void confirmCard()
                                : undefined
                            }
                            onReject={
                              card.lifecycle === "rejected"
                                ? undefined
                                : () => void rejectCard()
                            }
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
      <KnowledgeFloatingToast toast={toast} />
    </AppShell>
  );
}

function KnowledgeFloatingToast({ toast }: { toast: KnowledgeToastState | null }) {
  if (!toast) {
    return null;
  }
  return (
    <div
      key={toast.id}
      role="status"
      className="pointer-events-none fixed bottom-6 right-6 z-[80] flex max-w-[min(420px,calc(100vw-32px))] items-center gap-3 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] bg-[color-mix(in_srgb,var(--tc-surface-panel)_92%,transparent)] px-4 py-3 text-sm font-medium text-[var(--tc-text-primary)] shadow-[0_18px_54px_rgba(0,0,0,0.22)] backdrop-blur"
    >
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--tc-success-soft)] text-[var(--tc-success-text)]">
        <CheckCircle2 className="size-4" />
      </span>
      <span className="truncate">{toast.message}</span>
    </div>
  );
}

function NewCardPanel({
  schema,
  form,
  errors,
  referenceOptions,
  saving,
  onFormChange,
  onSave,
}: {
  schema: KnowledgeTypeSchema;
  form: KnowledgeFormState;
  errors: KnowledgeFormErrors;
  referenceOptions: KnowledgeReferenceOptions;
  saving: boolean;
  onFormChange: (form: KnowledgeFormState) => void;
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
        errors={errors}
        referenceOptions={referenceOptions}
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
  referenceOptions,
  chapterCount,
  saving,
  onEdit,
  onConfirm,
  onReject,
}: {
  schema: KnowledgeTypeSchema;
  card: StructuredKnowledgeCard;
  referenceOptions: KnowledgeReferenceOptions;
  chapterCount: number;
  saving: boolean;
  onEdit?: () => void;
  onConfirm?: () => void;
  onReject?: () => void;
}) {
  return (
    <div className="pb-5 pl-10 pr-2">
      <div className="grid max-w-[720px] gap-2">
        <div className="flex flex-wrap gap-2 text-xs text-[var(--tc-text-muted)]">
          {card.lifecycle !== "confirmed" ? (
            <span>{lifecycleLabel(card.lifecycle)}</span>
          ) : null}
          <span>{sourceOriginLabel(card.source_origin)}</span>
          <span>{dateLabel(card.updated_at)}</span>
        </div>
        <StructuredKnowledgeView
          schema={schema}
          values={card as Record<string, unknown>}
          hiddenFieldKeys={KNOWLEDGE_DETAIL_HIDDEN_FIELD_KEYS}
          referenceOptions={referenceOptions}
          chapterCount={chapterCount}
        />
        <div className="flex flex-wrap gap-2 pt-1">
          {onEdit ? (
            <Button type="button" size="sm" onClick={onEdit} disabled={saving}>
              <Pencil className="size-4" />
              编辑
            </Button>
          ) : null}
          {onConfirm ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onConfirm}
              disabled={saving}
            >
              <ShieldCheck className="size-4" />
              确认入库
            </Button>
          ) : null}
          {onReject ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onReject}
              disabled={saving}
            >
              <Trash2 className="size-4" />
              删除
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function KnowledgeEditor({
  schema,
  form,
  errors,
  referenceOptions,
  saving,
  isCreating,
  onFormChange,
  onSave,
  onCancel,
  onConfirm,
  onReject,
}: {
  schema: KnowledgeTypeSchema;
  form: KnowledgeFormState;
  errors: KnowledgeFormErrors;
  referenceOptions: KnowledgeReferenceOptions;
  saving: boolean;
  isCreating: boolean;
  onFormChange: (form: KnowledgeFormState) => void;
  onSave: () => void;
  onCancel?: () => void;
  onConfirm?: () => void;
  onReject?: () => void;
}) {
  return (
    <div className={cn("pb-5 pr-2", isCreating ? "" : "pl-10")}>
      <div className="grid max-w-[720px] gap-3">
        <StructuredKnowledgeForm
          schema={schema}
          form={form}
          errors={errors}
          hiddenFieldKeys={KNOWLEDGE_FORM_HIDDEN_FIELD_KEYS}
          referenceOptions={referenceOptions}
          onChange={onFormChange}
        />

        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="button" onClick={onSave} disabled={saving}>
            {saving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            保存
          </Button>
          {onCancel ? (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={saving}
            >
              取消编辑
            </Button>
          ) : null}
          {!isCreating && onConfirm ? (
            <Button
              type="button"
              variant="outline"
              onClick={onConfirm}
              disabled={saving}
            >
              <ShieldCheck className="size-4" />
              确认入库
            </Button>
          ) : null}
          {!isCreating && onReject ? (
              <Button
                type="button"
                variant="outline"
                onClick={onReject}
                disabled={saving}
              >
                <Trash2 className="size-4" />
                删除
              </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function defaultForm(schema: KnowledgeTypeSchema): KnowledgeFormState {
  return formStateFromKnowledgeValues(schema, {}, {
    lifecycle: "draft",
    source_origin: "manual",
    source_note: "作者手动添加。可写章节、原文摘录、人工说明。",
  });
}

function formFromCard(
  schema: KnowledgeTypeSchema,
  card: StructuredKnowledgeCard,
): KnowledgeFormState {
  return formStateFromKnowledgeValues(
    schema,
    card as Record<string, unknown>,
    defaultForm(schema),
  );
}

function payloadFromForm(
  schema: KnowledgeTypeSchema,
  form: KnowledgeFormState,
): Record<string, unknown> {
  return knowledgePayloadFromForm(
    schema,
    form,
    KNOWLEDGE_FORM_HIDDEN_FIELD_KEYS,
  );
}

function listDisplayText(
  schema: KnowledgeTypeSchema | null,
  card: StructuredKnowledgeCard,
  referenceOptions: KnowledgeReferenceOptions,
  chapterCount: number,
): string {
  if (!schema) {
    return card.summary;
  }
  const values = card as Record<string, unknown>;
  const parts = schema.fields
    .filter(
      field =>
        field.list_display &&
        !["name", "lifecycle"].includes(field.field_key),
    )
    .map(field => {
      const value = values[field.field_key];
      if (
        value === null ||
        value === undefined ||
        value === "" ||
        (Array.isArray(value) && !value.length)
      ) {
        return "";
      }
      const readable =
        field.field_key === "appearance_chapter_count"
          ? appearanceImportanceLabel(value, chapterCount)
          : displayKnowledgeFieldValue(field, value, referenceOptions);
      return `${field.label}：${readable}`;
    })
    .filter(Boolean);
  return parts.join(" · ") || card.summary;
}

function lifecycleLabel(lifecycle: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    confirmed: "已确认",
    rejected: "已废弃",
  };
  return labels[lifecycle] ?? "草稿";
}

function cardMetadata(card: StructuredKnowledgeCard): string {
  const details = [
    sourceOriginLabel(card.source_origin),
    dateLabel(card.updated_at),
  ];
  if (card.lifecycle !== "confirmed") {
    details.unshift(lifecycleLabel(card.lifecycle));
  }
  return details.join(" · ");
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
