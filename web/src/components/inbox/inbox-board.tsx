"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  { value: "issues", label: "待处理问题" },
];

type InboxEntry = MVPInboxIdea | MVPInboxPendingFact | MVPInboxIssue;

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
  const [isCreateOpen, setCreateOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const activeItems = useMemo(() => {
    if (activeTab === "ideas") {
      return ideas;
    }
    if (activeTab === "pending-facts") {
      return pendingFacts;
    }
    return issues;
  }, [activeTab, ideas, issues, pendingFacts]);

  const totalCount = ideas.length + pendingFacts.length + issues.length;
  const activeTabLabel = tabs.find(tab => tab.value === activeTab)?.label ?? "灵感";

  const preparePendingFactConfirm = useCallback((item: MVPInboxPendingFact) => {
    setConfirmName(item.title || item.content.slice(0, 24));
    setConfirmSummary(item.content);
  }, []);

  async function reloadTab(tab: InboxTab, preferredExpandedId?: string | null) {
    setLoading(true);
    setError(null);
    try {
      if (tab === "ideas") {
        setIdeas((await listInboxItems("ideas")).items);
      }
      if (tab === "pending-facts") {
        setPendingFacts((await listInboxItems("pending-facts")).items);
      }
      if (tab === "issues") {
        setIssues((await listInboxItems("issues")).items);
      }
      setExpandedItemId(preferredExpandedId ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Inbox 加载失败");
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
        if (activeTab === "ideas") {
          const response = await listInboxItems("ideas");
          if (!cancelled) {
            setIdeas(response.items);
          }
        }
        if (activeTab === "pending-facts") {
          const response = await listInboxItems("pending-facts");
          if (!cancelled) {
            setPendingFacts(response.items);
          }
        }
        if (activeTab === "issues") {
          const response = await listInboxItems("issues");
          if (!cancelled) {
            setIssues(response.items);
          }
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Inbox 加载失败");
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
  }, [activeTab]);

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
    setMessage(null);
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
      setMessage("已添加到收件箱");
      await reloadTab(activeTab);
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
    setMessage(null);
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
      await reloadTab(tab, itemId);
      setMessage("已更新收件箱");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPendingFact(item: MVPInboxPendingFact) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await confirmInboxPendingFact(item.id, confirmType, {
        name: confirmName,
        summary: confirmSummary,
        body: item.content,
        source_refs: [
          {
            source_type: "author_note",
            source_id: "作者手动记录",
            display_name: item.origin || "作者手动记录",
            excerpt: item.content.slice(0, 300),
            note: "作者在收件箱手动确认",
            author_note_body: item.content,
          },
        ],
      });
      setMessage("已确认入库，原记录保留为已处理");
      await reloadTab("pending-facts");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认入库失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell activePath="/inbox">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[176px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <div className="px-2 py-2">
            <p className="text-xs text-[var(--tc-text-muted)]">收件箱</p>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
              模块
            </h1>
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
              共 {totalCount} 条
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

        <section className="min-w-0">
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
            <p className="tc-warning mb-3 max-w-[760px] rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="tc-success mb-3 max-w-[760px] rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {message}
            </p>
          ) : null}

          <div className="max-w-[980px]">
            {loading ? (
              <div className="flex h-28 items-center justify-center text-sm text-[var(--tc-text-muted)]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载中
              </div>
            ) : activeItems.length ? (
              <div className="divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                {activeItems.map(item => (
                  <InboxRow
                    key={`${item.id}-${item.updated_at}`}
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
              <div className="border-y border-dashed border-[var(--tc-border-subtle)] px-3 py-16 text-center text-sm text-[var(--tc-text-muted)]">
                暂无条目
              </div>
            )}
          </div>
        </section>
      </section>
    </AppShell>
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
            {priorityLabel(item.priority)} · {statusLabel(item.status)} ·{" "}
            {dateLabel(item.updated_at)}
          </span>
        </span>
      </button>

      {expanded ? (
        <div className="pb-5 pl-10 pr-2">
          <p className="max-w-[860px] whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-secondary)]">
            {item.content}
          </p>

          {editing ? (
            <div className="mt-3 grid max-w-[760px] gap-2">
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
                className="min-h-20 resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none"
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
              onClick={() => setEditing(current => !current)}
            >
              <Save className="size-4" />
              编辑
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
