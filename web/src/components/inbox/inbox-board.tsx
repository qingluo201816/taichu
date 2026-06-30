"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Inbox, Loader2, Plus, Save, Trash2 } from "lucide-react";

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
  const [selectedPendingFactId, setSelectedPendingFactId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const activePendingFact = useMemo(
    () => pendingFacts.find(item => item.id === selectedPendingFactId) ?? null,
    [pendingFacts, selectedPendingFactId],
  );

  const totalCount = ideas.length + pendingFacts.length + issues.length;

  const selectPendingFact = useCallback((item: MVPInboxPendingFact) => {
    setSelectedPendingFactId(item.id);
    setConfirmName(item.title || item.content.slice(0, 24));
    setConfirmSummary(item.content);
  }, []);

  const applyPendingFacts = useCallback(
    (items: MVPInboxPendingFact[], preferredId?: string | null) => {
      setPendingFacts(items);
      const nextSelected =
        items.find(item => item.id === preferredId) ?? items[0] ?? null;
      if (nextSelected) {
        selectPendingFact(nextSelected);
      } else {
        setSelectedPendingFactId(null);
        setConfirmName("");
        setConfirmSummary("");
      }
    },
    [selectPendingFact],
  );

  async function reloadTab(tab: InboxTab) {
    setLoading(true);
    setError(null);
    try {
      if (tab === "ideas") {
        setIdeas((await listInboxItems("ideas")).items);
      }
      if (tab === "pending-facts") {
        const response = await listInboxItems("pending-facts");
        applyPendingFacts(response.items, selectedPendingFactId);
      }
      if (tab === "issues") {
        setIssues((await listInboxItems("issues")).items);
      }
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
            applyPendingFacts(response.items, null);
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
          setLoading(false);
        }
      }
    }
    void loadCurrentTab();
    return () => {
      cancelled = true;
    };
  }, [activeTab, applyPendingFacts]);

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
      setMessage("已添加到 Inbox");
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
      await reloadTab(tab);
      setMessage("已更新 Inbox");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPendingFact() {
    if (!activePendingFact) {
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await confirmInboxPendingFact(activePendingFact.id, confirmType, {
        name: confirmName,
        summary: confirmSummary,
        body: activePendingFact.content,
        source_refs: [
          {
            source_type: "author_note",
            source_id: "作者手动记录",
            display_name: activePendingFact.origin || "作者手动记录",
            excerpt: activePendingFact.content.slice(0, 300),
            note: "作者在 Inbox 手动确认",
            author_note_body: activePendingFact.content,
          },
        ],
      });
      setMessage("已确认入库，原记录保留为已处理");
      setSelectedPendingFactId(null);
      await reloadTab("pending-facts");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认入库失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell activePath="/inbox">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
          <div className="mb-4">
            <p className="text-xs text-[var(--tc-smoke)]">Inbox</p>
            <h1 className="font-serif text-3xl text-[var(--tc-midnight-ink)]">
              创作收件箱
            </h1>
            <p className="mt-2 text-sm text-[var(--tc-smoke)]">
              当前待处理 {totalCount} 条
            </p>
          </div>

          <div className="grid gap-2">
            {tabs.map(tab => (
              <button
                key={tab.value}
                type="button"
                onClick={() => {
                  setLoading(true);
                  setActiveTab(tab.value);
                }}
                className={cn(
                  "h-11 rounded-[var(--tc-radius-control)] border px-3 text-left text-sm font-medium",
                  activeTab === tab.value
                    ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)]"
                    : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)]",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="mt-5 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-3">
            <h2 className="mb-3 text-sm font-semibold">
              新增{tabs.find(tab => tab.value === activeTab)?.label}
            </h2>
            {activeTab !== "ideas" ? (
              <input
                value={newTitle}
                onChange={event => setNewTitle(event.target.value)}
                placeholder="标题"
                className="mb-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm outline-none"
              />
            ) : null}
            <textarea
              value={newContent}
              onChange={event => setNewContent(event.target.value)}
              placeholder={activeTab === "ideas" ? "灵感内容" : "正文内容"}
              className="min-h-28 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm leading-6 outline-none"
            />
            <select
              value={priority}
              onChange={event => setPriority(event.target.value as InboxPriority)}
              className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm"
              aria-label="优先级"
            >
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
            </select>
            <Button
              type="button"
              onClick={createItem}
              disabled={busy || !newContent.trim() || (activeTab !== "ideas" && !newTitle.trim())}
              className="mt-3 w-full"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
              添加
            </Button>
          </div>
        </aside>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 font-serif text-3xl text-[var(--tc-midnight-ink)]">
                <Inbox className="size-6" />
                {tabs.find(tab => tab.value === activeTab)?.label}
              </h2>
              {loading ? <Loader2 className="size-5 animate-spin" /> : null}
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
            <div className="grid gap-3">
              {activeTab === "ideas" &&
                ideas.map(item => (
                  <InboxCard
                    key={item.id}
                    title="灵感"
                    content={item.content}
                    meta={`${priorityLabel(item.priority)} · ${statusLabel(item.status)}`}
                    selected={false}
                    onEdit={(_title, content) =>
                      void patchItem("ideas", item.id, { content })
                    }
                    onProcessed={() => void patchItem("ideas", item.id, { status: "processed" })}
                    onDeprecated={() => void patchItem("ideas", item.id, { status: "deprecated" })}
                  />
                ))}
              {activeTab === "pending-facts" &&
                pendingFacts.map(item => (
                  <InboxCard
                    key={item.id}
                    title={item.title || "待确认事实"}
                    content={item.content}
                    meta={`${priorityLabel(item.priority)} · ${statusLabel(item.status)}`}
                    selected={selectedPendingFactId === item.id}
                    onSelect={() => selectPendingFact(item)}
                    onEdit={(title, content) =>
                      void patchItem("pending-facts", item.id, { title, content })
                    }
                    onProcessed={() =>
                      void patchItem("pending-facts", item.id, { status: "processed" })
                    }
                    onDeprecated={() =>
                      void patchItem("pending-facts", item.id, { status: "deprecated" })
                    }
                  />
                ))}
              {activeTab === "issues" &&
                issues.map(item => (
                  <InboxCard
                    key={item.id}
                    title={item.title}
                    content={item.content}
                    meta={`${priorityLabel(item.priority)} · ${statusLabel(item.status)}`}
                    selected={false}
                    onEdit={(title, content) =>
                      void patchItem("issues", item.id, { title, content })
                    }
                    onProcessed={() => void patchItem("issues", item.id, { status: "processed" })}
                    onDeprecated={() => void patchItem("issues", item.id, { status: "deprecated" })}
                  />
                ))}
              {!loading && currentItemsCount(activeTab, ideas, pendingFacts, issues) === 0 ? (
                <div className="rounded-[var(--tc-radius-card)] border border-dashed border-[var(--tc-stone-mist)] px-4 py-16 text-center text-sm text-[var(--tc-smoke)]">
                  暂无条目
                </div>
              ) : null}
            </div>
          </div>

          <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
            <h2 className="font-serif text-2xl text-[var(--tc-midnight-ink)]">
              确认入库
            </h2>
            {activePendingFact ? (
              <div className="mt-4 space-y-3">
                <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-3 text-sm leading-6">
                  原事实：{activePendingFact.content}
                </p>
                <label className="block text-sm font-medium">
                  知识卡类型
                  <select
                    value={confirmType}
                    onChange={event =>
                      setConfirmType(event.target.value as KnowledgeTypeValue)
                    }
                    className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
                  >
                    {knowledgeTypes.map(type => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm font-medium">
                  知识卡预览
                  <input
                    value={confirmName}
                    onChange={event => setConfirmName(event.target.value)}
                    className="mt-2 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
                    placeholder="名称"
                  />
                </label>
                <textarea
                  value={confirmSummary}
                  onChange={event => setConfirmSummary(event.target.value)}
                  className="min-h-28 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 text-sm leading-6 outline-none"
                  placeholder="摘要"
                />
                <Button
                  type="button"
                  onClick={confirmPendingFact}
                  disabled={busy || !confirmName.trim() || !confirmSummary.trim()}
                  className="w-full"
                >
                  {busy ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                  确认入库
                </Button>
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--tc-radius-control)] border border-dashed border-[var(--tc-stone-mist)] px-3 py-12 text-center text-sm text-[var(--tc-smoke)]">
                选择一条待确认事实
              </div>
            )}
          </aside>
        </section>
      </section>
    </AppShell>
  );
}

function InboxCard({
  title,
  content,
  meta,
  selected,
  onSelect,
  onEdit,
  onProcessed,
  onDeprecated,
}: {
  title: string;
  content: string;
  meta: string;
  selected: boolean;
  onSelect?: () => void;
  onEdit: (title: string, content: string) => void;
  onProcessed: () => void;
  onDeprecated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [draftContent, setDraftContent] = useState(content);

  function submitEdit() {
    onEdit(draftTitle.trim() || title, draftContent);
    setEditing(false);
  }

  return (
    <article
      className={cn(
        "rounded-[var(--tc-radius-card)] border bg-[var(--tc-cream-paper)] p-4",
        selected ? "border-[var(--tc-midnight-ink)]" : "border-[var(--tc-stone-mist)]",
      )}
    >
      <button type="button" onClick={onSelect} className="w-full text-left">
        <h3 className="text-lg font-semibold text-[var(--tc-midnight-ink)]">
          {title}
        </h3>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-smoke)]">
          {content}
        </p>
        <p className="mt-3 text-xs text-[var(--tc-smoke)]">{meta}</p>
      </button>
      {editing ? (
        <div className="mt-4 space-y-2 border-t border-[var(--tc-stone-mist)] pt-3">
          <input
            value={draftTitle}
            onChange={event => setDraftTitle(event.target.value)}
            className="h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm outline-none"
            placeholder="标题"
          />
          <textarea
            value={draftContent}
            onChange={event => setDraftContent(event.target.value)}
            className="min-h-28 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm leading-6 outline-none"
            placeholder="内容"
          />
          <Button type="button" size="sm" onClick={submitEdit}>
            <Save className="size-4" />
            保存编辑
          </Button>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setEditing(current => !current)}
        >
          <Save className="size-4" />
          编辑
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onProcessed}>
          <CheckCircle2 className="size-4" />
          标记已处理
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDeprecated}>
          <Trash2 className="size-4" />
          废弃
        </Button>
      </div>
    </article>
  );
}

function currentItemsCount(
  tab: InboxTab,
  ideas: MVPInboxIdea[],
  pendingFacts: MVPInboxPendingFact[],
  issues: MVPInboxIssue[],
): number {
  if (tab === "ideas") {
    return ideas.length;
  }
  if (tab === "pending-facts") {
    return pendingFacts.length;
  }
  return issues.length;
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
