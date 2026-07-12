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
  Inbox,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  confirmInboxPendingFact,
  createInboxIdea,
  createInboxIssue,
  createInboxPendingFact,
  listInboxItems,
  listKnowledgeTypes,
  patchInboxIdea,
  patchInboxIssue,
  patchInboxPendingFact,
} from "@/lib/api/mvp";
import type {
  InboxPriority,
  InboxTab,
  KnowledgeTypeInfo,
  KnowledgeTypeValue,
  MVPInboxIdea,
  MVPInboxIssue,
  MVPInboxPendingFact,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

const tabs: Array<{ value: InboxTab; label: string }> = [
  { value: "ideas", label: "灵感" },
  { value: "pending-facts", label: "待确认事实" },
  { value: "issues", label: "系统问题与改进项记录" },
];

type InboxEntry = MVPInboxIdea | MVPInboxPendingFact | MVPInboxIssue;
type InboxStatusFilter = "todo" | "processed";
type InboxPriorityFilter = InboxPriority | "all";
type InboxToastState = {
  id: number;
  message: string;
};

const INBOX_PAGE_SIZE = 6;
const defaultTabPages: Record<InboxTab, number> = {
  ideas: 1,
  "pending-facts": 1,
  issues: 1,
};
const defaultTabTotals: Record<InboxTab, number> = {
  ideas: 0,
  "pending-facts": 0,
  issues: 0,
};
const statusFilters: Array<{ value: InboxStatusFilter; label: string }> = [
  { value: "todo", label: "待处理" },
  { value: "processed", label: "已处理" },
];
const priorityFilters: Array<{ value: InboxPriorityFilter; label: string }> = [
  { value: "all", label: "全部优先级" },
  { value: "high", label: "高优先级" },
  { value: "normal", label: "普通优先级" },
  { value: "low", label: "低优先级" },
];

export function InboxBoard() {
  const [activeTab, setActiveTab] = useState<InboxTab>("ideas");
  const [ideas, setIdeas] = useState<MVPInboxIdea[]>([]);
  const [pendingFacts, setPendingFacts] = useState<MVPInboxPendingFact[]>([]);
  const [issues, setIssues] = useState<MVPInboxIssue[]>([]);
  const [knowledgeTypes, setKnowledgeTypes] = useState<KnowledgeTypeInfo[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [priority, setPriority] = useState<InboxPriority>("normal");
  const [confirmType, setConfirmType] = useState<KnowledgeTypeValue>("character");
  const [confirmName, setConfirmName] = useState("");
  const [confirmSummary, setConfirmSummary] = useState("");
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null);
  const [pageByTab, setPageByTab] =
    useState<Record<InboxTab, number>>(defaultTabPages);
  const [totalByTab, setTotalByTab] =
    useState<Record<InboxTab, number>>(defaultTabTotals);
  const [statusFilter, setStatusFilter] =
    useState<InboxStatusFilter>("todo");
  const [priorityFilter, setPriorityFilter] =
    useState<InboxPriorityFilter>("all");
  const [isCreateOpen, setCreateOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<InboxToastState | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const toastIdRef = useRef(0);

  const activeItems = useMemo(() => {
    if (activeTab === "ideas") {
      return ideas;
    }
    if (activeTab === "pending-facts") {
      return pendingFacts;
    }
    return issues;
  }, [activeTab, ideas, issues, pendingFacts]);

  const activePage = pageByTab[activeTab];
  const activeTotal = totalByTab[activeTab];
  const activeTabLabel = tabs.find(tab => tab.value === activeTab)?.label ?? "灵感";

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  function showInboxToast(message: string) {
    toastIdRef.current += 1;
    setToast({ id: toastIdRef.current, message });
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
    }, 1900);
  }

  const preparePendingFactConfirm = useCallback((item: MVPInboxPendingFact) => {
    setConfirmName(item.title || item.content.slice(0, 24));
    setConfirmSummary(item.content);
  }, []);

  const requestParams = useCallback((page: number) => {
    return {
      page,
      pageSize: INBOX_PAGE_SIZE,
      status: statusFilter,
      priority: priorityFilter,
    };
  }, [priorityFilter, statusFilter]);

  async function reloadTab(
    tab: InboxTab,
    preferredExpandedId?: string | null,
    pageOverride = pageByTab[tab],
  ) {
    setLoading(true);
    setError(null);
    try {
      const params = requestParams(pageOverride);
      if (tab === "ideas") {
        const response = await listInboxItems("ideas", params);
        setIdeas(response.items);
        setTotalByTab(current => ({ ...current, ideas: response.total }));
      }
      if (tab === "pending-facts") {
        const response = await listInboxItems("pending-facts", params);
        setPendingFacts(response.items);
        setTotalByTab(current => ({
          ...current,
          "pending-facts": response.total,
        }));
      }
      if (tab === "issues") {
        const response = await listInboxItems("issues", params);
        setIssues(response.items);
        setTotalByTab(current => ({ ...current, issues: response.total }));
      }
      setExpandedItemId(preferredExpandedId ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "收件箱加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    listKnowledgeTypes()
      .then(response => {
        if (!cancelled) {
          setKnowledgeTypes(response.types);
          setConfirmType(response.types[0]?.value ?? "character");
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadCurrentTab() {
      setLoading(true);
      try {
        const params = requestParams(activePage);
        if (activeTab === "ideas") {
          const response = await listInboxItems("ideas", params);
          if (!cancelled) {
            setIdeas(response.items);
            setTotalByTab(current => ({ ...current, ideas: response.total }));
          }
        }
        if (activeTab === "pending-facts") {
          const response = await listInboxItems("pending-facts", params);
          if (!cancelled) {
            setPendingFacts(response.items);
            setTotalByTab(current => ({
              ...current,
              "pending-facts": response.total,
            }));
          }
        }
        if (activeTab === "issues") {
          const response = await listInboxItems("issues", params);
          if (!cancelled) {
            setIssues(response.items);
            setTotalByTab(current => ({ ...current, issues: response.total }));
          }
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "收件箱加载失败");
        }
      } finally {
        if (!cancelled) {
          setExpandedItemId(null);
          setLoading(false);
        }
      }
    }
    void loadCurrentTab();
    return () => {
      cancelled = true;
    };
  }, [activePage, activeTab, requestParams]);

  function toggleItem(item: InboxEntry) {
    if (expandedItemId === item.id) {
      setExpandedItemId(null);
      return;
    }
    setExpandedItemId(item.id);
    if (activeTab === "pending-facts" && isPendingFact(item)) {
      preparePendingFactConfirm(item);
    }
  }

  async function createItem() {
    setBusy(true);
    setError(null);
    try {
      if (activeTab === "ideas") {
        await createInboxIdea({
          content: newContent,
          priority,
        });
      }
      if (activeTab === "pending-facts") {
        await createInboxPendingFact({
          title: newTitle,
          content: newContent,
          origin: "作者手动记录",
          priority,
        });
      }
      if (activeTab === "issues") {
        await createInboxIssue({
          title: newTitle,
          content: newContent,
          priority,
        });
      }
      setNewTitle("");
      setNewContent("");
      setCreateOpen(false);
      showInboxToast("已添加到收件箱");
      setPageByTab(current => ({ ...current, [activeTab]: 1 }));
      await reloadTab(activeTab, null, 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "添加失败");
    } finally {
      setBusy(false);
    }
  }

  async function patchItem(
    tab: InboxTab,
    itemId: string,
    updates: Record<string, unknown>,
  ) {
    setBusy(true);
    setError(null);
    try {
      if (tab === "ideas") {
        await patchInboxIdea(itemId, updates);
      }
      if (tab === "pending-facts") {
        await patchInboxPendingFact(itemId, updates);
      }
      if (tab === "issues") {
        await patchInboxIssue(itemId, updates);
      }
      const deleted = updates.status === "deprecated";
      await reloadTab(tab, deleted ? null : itemId);
      showInboxToast(deleted ? "已删除条目" : "已更新收件箱");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPendingFact(item: MVPInboxPendingFact) {
    setBusy(true);
    setError(null);
    try {
      await confirmInboxPendingFact(item.id, confirmType, {
        name: confirmName,
        summary: confirmSummary,
        source_origin: "inbox_fact",
        source_note: item.origin
          ? `${item.origin}：${item.content.slice(0, 120)}`
          : `收件箱确认：${item.content.slice(0, 120)}`,
      });
      showInboxToast("已确认入库，原记录保留为已处理");
      await reloadTab("pending-facts");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认入库失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell activePath="/inbox" viewportLocked>
      <section className="mx-auto grid h-full min-h-0 max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[176px_minmax(0,1fr)]">
        <aside className="h-full min-h-0 overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <div className="px-2 py-2">
            <p className="text-xs text-[var(--tc-text-muted)]">收件箱</p>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
              模块
            </h1>
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
              共 {activeTotal} 条
            </p>
          </div>
          <div className="mt-2 grid gap-1">
            {tabs.map(tab => (
              <button
                key={tab.value}
                type="button"
                onClick={() => {
                  setActiveTab(tab.value);
                  setCreateOpen(false);
                }}
                className={cn(
                  "h-9 rounded-[var(--tc-radius-control)] px-3 text-left text-sm transition-colors",
                  activeTab === tab.value
                    ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </aside>

        <section className="flex h-full min-h-0 min-w-0 flex-col">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
                <Inbox className="size-4" />
                {activeTabLabel}
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                当前模块条目
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setCreateOpen(current => !current)}
              className="inline-flex h-9 items-center gap-2 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] px-4 text-sm text-[var(--tc-text-secondary)] hover:text-[var(--tc-text-primary)]"
            >
              <Plus className="size-4" />
              新增
            </button>
          </div>

          <div className="mb-4 flex max-w-[980px] flex-wrap gap-2">
            <select
              value={statusFilter}
              onChange={event => {
                setStatusFilter(event.target.value as InboxStatusFilter);
                setPageByTab(current => ({ ...current, [activeTab]: 1 }));
              }}
              className="h-9 min-w-32 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)]"
              aria-label="状态筛选"
            >
              {statusFilters.map(filter => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
            </select>
            <select
              value={priorityFilter}
              onChange={event => {
                setPriorityFilter(event.target.value as InboxPriorityFilter);
                setPageByTab(current => ({ ...current, [activeTab]: 1 }));
              }}
              className="h-9 min-w-36 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)]"
              aria-label="优先级筛选"
            >
              {priorityFilters.map(filter => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
            </select>
          </div>

          {isCreateOpen ? (
            <div className="mb-4 max-w-[760px] border-y border-[var(--tc-border-subtle)] py-4">
              <div className="grid gap-2">
                {activeTab !== "ideas" ? (
                  <input
                    value={newTitle}
                    onChange={event => setNewTitle(event.target.value)}
                    placeholder="标题"
                    className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none"
                  />
                ) : null}
                <textarea
                  value={newContent}
                  onChange={event => setNewContent(event.target.value)}
                  placeholder={activeTab === "ideas" ? "灵感内容" : "正文内容"}
                  className="min-h-20 resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={priority}
                    onChange={event =>
                      setPriority(event.target.value as InboxPriority)
                    }
                    className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)]"
                    aria-label="优先级"
                  >
                    <option value="low">低</option>
                    <option value="normal">普通</option>
                    <option value="high">高</option>
                  </select>
                  <Button
                    type="button"
                    onClick={createItem}
                    disabled={
                      busy ||
                      !newContent.trim() ||
                      (activeTab !== "ideas" && !newTitle.trim())
                    }
                  >
                    {busy ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Plus className="size-4" />
                    )}
                    添加
                  </Button>
                </div>
              </div>
            </div>
          ) : null}

          {error ? (
            <p className="mb-3 max-w-[760px] px-1 text-sm leading-6 text-[var(--tc-warning-text)]">
              {error}
            </p>
          ) : null}

          <div className="flex min-h-0 max-w-[980px] flex-1 flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  加载中
                </div>
              ) : activeItems.length ? (
                <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                  {activeItems.map(item => (
                    <InboxRow
                      key={item.id}
                      tab={activeTab}
                      item={item}
                      expanded={expandedItemId === item.id}
                      busy={busy}
                      knowledgeTypes={knowledgeTypes}
                      confirmType={confirmType}
                      confirmName={confirmName}
                      confirmSummary={confirmSummary}
                      onToggle={() => toggleItem(item)}
                      onPatch={updates => void patchItem(activeTab, item.id, updates)}
                      onProcessed={() =>
                        void patchItem(activeTab, item.id, { status: "processed" })
                      }
                      onDeprecated={() =>
                        void patchItem(activeTab, item.id, { status: "deprecated" })
                      }
                      onConfirm={
                        activeTab === "pending-facts" && isPendingFact(item)
                          ? () => void confirmPendingFact(item)
                          : undefined
                      }
                      onConfirmTypeChange={setConfirmType}
                      onConfirmNameChange={setConfirmName}
                      onConfirmSummaryChange={setConfirmSummary}
                    />
                  ))}
                </div>
              ) : (
                <div className="grid h-full min-h-28 place-items-center border-y border-dashed border-[var(--tc-border-subtle)] px-3 text-center text-sm text-[var(--tc-text-muted)]">
                  暂无条目
                </div>
              )}
            </div>
            <PaginationControls
              page={activePage}
              pageSize={INBOX_PAGE_SIZE}
              total={activeTotal}
              onPageChange={page =>
                setPageByTab(current => ({ ...current, [activeTab]: page }))
              }
            />
          </div>
          <InboxFloatingToast toast={toast} />
        </section>
      </section>
    </AppShell>
  );
}

function InboxFloatingToast({ toast }: { toast: InboxToastState | null }) {
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

function InboxRow({
  tab,
  item,
  expanded,
  busy,
  knowledgeTypes,
  confirmType,
  confirmName,
  confirmSummary,
  onToggle,
  onPatch,
  onProcessed,
  onDeprecated,
  onConfirm,
  onConfirmTypeChange,
  onConfirmNameChange,
  onConfirmSummaryChange,
}: {
  tab: InboxTab;
  item: InboxEntry;
  expanded: boolean;
  busy: boolean;
  knowledgeTypes: KnowledgeTypeInfo[];
  confirmType: KnowledgeTypeValue;
  confirmName: string;
  confirmSummary: string;
  onToggle: () => void;
  onPatch: (updates: Record<string, unknown>) => void;
  onProcessed: () => void;
  onDeprecated: () => void;
  onConfirm?: () => void;
  onConfirmTypeChange: (value: KnowledgeTypeValue) => void;
  onConfirmNameChange: (value: string) => void;
  onConfirmSummaryChange: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(itemTitle(tab, item));
  const [draftContent, setDraftContent] = useState(item.content);

  function toggleEditing() {
    if (editing) {
      setEditing(false);
      return;
    }
    setDraftTitle(itemTitle(tab, item));
    setDraftContent(item.content);
    setEditing(true);
  }

  function submitEdit() {
    onPatch(
      tab === "ideas"
        ? { content: draftContent }
        : { title: draftTitle.trim() || itemTitle(tab, item), content: draftContent },
    );
    setEditing(false);
  }

  return (
    <article>
      <button
        type="button"
        onClick={onToggle}
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
            {itemTitle(tab, item)}
          </span>
          <span className="block truncate text-xs text-[var(--tc-text-muted)]">
            {priorityLabel(item.priority)} · {statusLabel(item.status)}
          </span>
        </span>
      </button>

      {expanded ? (
        <div className="pb-5 pl-10 pr-2">
          <p className="max-w-[860px] select-text whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
            {item.content}
          </p>

          {editing ? (
            <div
              className="mt-3 grid max-w-[760px] gap-2"
              onClick={event => event.stopPropagation()}
              onMouseDown={event => event.stopPropagation()}
            >
              {tab !== "ideas" ? (
                <input
                  value={draftTitle}
                  onChange={event => setDraftTitle(event.target.value)}
                  className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none"
                  placeholder="标题"
                />
              ) : null}
              <textarea
                value={draftContent}
                onChange={event => setDraftContent(event.target.value)}
                className="min-h-20 resize-y select-text rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none"
                placeholder="内容"
              />
              <div>
                <Button type="button" size="sm" onClick={submitEdit}>
                  <Save className="size-4" />
                  保存编辑
                </Button>
              </div>
            </div>
          ) : null}

          {tab === "pending-facts" && isPendingFact(item) ? (
            <div className="mt-4 grid max-w-[760px] gap-2 border-l border-[var(--tc-border-subtle)] pl-3">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block text-sm text-[var(--tc-text-secondary)]">
                  知识类型
                  <select
                    value={confirmType}
                    onChange={event =>
                      onConfirmTypeChange(
                        event.target.value as KnowledgeTypeValue,
                      )
                    }
                    className="mt-1 h-9 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-[var(--tc-text-primary)] outline-none"
                  >
                    {knowledgeTypes.map(type => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm text-[var(--tc-text-secondary)]">
                  知识名称
                  <input
                    value={confirmName}
                    onChange={event => onConfirmNameChange(event.target.value)}
                    className="mt-1 h-9 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-[var(--tc-text-primary)] outline-none"
                  />
                </label>
              </div>
              <label className="block text-sm text-[var(--tc-text-secondary)]">
                入库摘要
                <textarea
                  value={confirmSummary}
                  onChange={event => onConfirmSummaryChange(event.target.value)}
                  className="mt-1 min-h-20 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 leading-6 text-[var(--tc-text-primary)] outline-none"
                />
              </label>
            </div>
          ) : null}

          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={toggleEditing}
            >
              <Save className="size-4" />
              {editing ? "收起编辑" : "编辑"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onProcessed}
              disabled={busy}
            >
              <CheckCircle2 className="size-4" />
              标记已处理
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onDeprecated}
              disabled={busy}
            >
              <Trash2 className="size-4" />
              废弃
            </Button>
            {onConfirm ? (
              <Button
                type="button"
                size="sm"
                onClick={onConfirm}
                disabled={busy || !confirmName.trim() || !confirmSummary.trim()}
              >
                {busy ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="size-4" />
                )}
                确认入库
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function isPendingFact(item: InboxEntry): item is MVPInboxPendingFact {
  return "origin" in item;
}

function itemTitle(tab: InboxTab, item: InboxEntry): string {
  if (tab === "ideas") {
    return "灵感";
  }
  return "title" in item && item.title ? item.title : "未命名条目";
}

function priorityLabel(priority: string): string {
  const labels: Record<string, string> = {
    low: "低优先级",
    normal: "普通优先级",
    high: "高优先级",
  };
  return labels[priority] ?? "普通优先级";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    todo: "待处理",
    processed: "已处理",
    deprecated: "已废弃",
  };
  return labels[status] ?? "待处理";
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
          htmlFor="inbox-page-jump"
          className="text-xs text-[var(--tc-text-muted)]"
        >
          跳至
        </label>
        <input
          id="inbox-page-jump"
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
