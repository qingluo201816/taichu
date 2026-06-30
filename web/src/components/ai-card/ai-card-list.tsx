"use client";

import {
  Copy,
  CornerDownLeft,
  FileQuestion,
  FileText,
  Lightbulb,
  ListPlus,
  Loader2,
  MessageSquare,
  PenLine,
  RotateCcw,
  Scissors,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type {
  AIResultCard,
  SelectionMode,
} from "@/lib/types/ai-cards";
import { cn } from "@/lib/utils";

type SelectionSummary = {
  selected_text: string;
  source_ref: {
    paragraph_start: number;
    char_start: number;
    char_end: number;
  };
};

type AICardListProps = {
  cards: AIResultCard[];
  selection: SelectionSummary | null;
  prompt: string;
  targetWords: string;
  selectedMode: SelectionMode;
  loading: boolean;
  error: string | null;
  onPromptChange: (value: string) => void;
  onTargetWordsChange: (value: string) => void;
  onModeChange: (mode: SelectionMode) => void;
  onRunSelection: (mode: SelectionMode) => void;
  onRunChapterSummary: () => void;
  onApplyText: (
    card: AIResultCard,
    placement: "insert_cursor" | "replace_selection" | "append_after_selection",
  ) => void;
  onCopyText: (card: AIResultCard) => void;
  onSaveIdea: (card: AIResultCard) => void;
  onConvertPendingFact: (card: AIResultCard) => void;
  onRetry: (card: AIResultCard) => void;
  onDiscard: (card: AIResultCard) => void;
};

export function AICardList({
  cards,
  selection,
  prompt,
  targetWords,
  selectedMode,
  loading,
  error,
  onPromptChange,
  onTargetWordsChange,
  onModeChange,
  onRunSelection,
  onRunChapterSummary,
  onApplyText,
  onCopyText,
  onSaveIdea,
  onConvertPendingFact,
  onRetry,
  onDiscard,
}: AICardListProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="mb-5 flex items-center gap-2 text-sm font-medium text-[var(--tc-workspace-text-secondary)]">
        <MessageSquare className="size-4" />
        智能助手卡片
      </div>

      <div className="tc-panel-soft tc-aurora-line px-4 py-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-[var(--tc-workspace-focus)]">
          <Scissors className="size-4" />
          当前选区
        </div>
        {selection ? (
          <div className="space-y-3 text-sm">
            <p className="tc-paper-fragment max-h-24 overflow-auto p-2 leading-6">
              {selection.selected_text}
            </p>
            <dl className="grid grid-cols-2 gap-2 font-mono text-xs text-[var(--tc-workspace-text-muted)]">
              <dt>段落</dt>
              <dd>{selection.source_ref.paragraph_start}</dd>
              <dt>起止</dt>
              <dd>
                {selection.source_ref.char_start}-
                {selection.source_ref.char_end}
              </dd>
            </dl>
          </div>
        ) : (
          <p className="text-sm text-[var(--tc-workspace-text-muted)]">未选择正文</p>
        )}
      </div>

      <div className="tc-panel mt-4 space-y-3 px-4 py-4">
        <div className="grid grid-cols-3 gap-2">
          <ModeButton
            active={selectedMode === "ask"}
            label="问答"
            onClick={() => onModeChange("ask")}
          >
            <Sparkles className="size-4" />
          </ModeButton>
          <ModeButton
            active={selectedMode === "enrich_setting"}
            label="设定"
            onClick={() => onModeChange("enrich_setting")}
          >
            <Wand2 className="size-4" />
          </ModeButton>
          <ModeButton
            active={selectedMode === "continue_text"}
            label="续写"
            onClick={() => onModeChange("continue_text")}
          >
            <PenLine className="size-4" />
          </ModeButton>
        </div>
        <textarea
          value={prompt}
          onChange={event => onPromptChange(event.target.value)}
          className="tc-input min-h-20 w-full resize-none px-3 py-2 text-sm"
          placeholder="给智能助手的一句话"
        />
        {selectedMode === "continue_text" ? (
          <input
            value={targetWords}
            onChange={event => onTargetWordsChange(event.target.value)}
            inputMode="numeric"
            className="tc-input h-9 w-full px-3 text-sm"
            placeholder="目标字数"
          />
        ) : null}
        <Button
          size="sm"
          disabled={!selection || loading}
          onClick={() => onRunSelection(selectedMode)}
          className="w-full"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : null}
          生成卡片
        </Button>
        <p className="text-xs leading-5 text-[var(--tc-workspace-text-muted)]">
          {selection ? "选区已就绪，可以生成智能助手卡片。" : "请先在正文中选中一段文字，生成卡片按钮会自动点亮。"}
        </p>
        <Button
          size="sm"
          disabled={loading}
          onClick={onRunChapterSummary}
          variant="outline"
          className="w-full"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
          整理本章
        </Button>
        {error ? (
          <p className="tc-danger rounded-[var(--tc-panel-radius)] border px-3 py-2 text-xs font-medium">
            {error}
          </p>
        ) : null}
      </div>

      <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-auto pr-1">
        {[...cards].reverse().map(card => (
          <ResultCard
            key={card.id}
            card={card}
            onApplyText={onApplyText}
            onCopyText={onCopyText}
            onSaveIdea={onSaveIdea}
            onConvertPendingFact={onConvertPendingFact}
            onRetry={onRetry}
            onDiscard={onDiscard}
          />
        ))}
      </div>
    </div>
  );
}

function ModeButton({
  active,
  label,
  children,
  onClick,
}: {
  active: boolean;
  label: string;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "inline-flex h-9 items-center justify-center gap-1 rounded-[var(--tc-panel-radius)] border text-xs font-medium transition-colors",
        active
          ? "border-[var(--tc-workspace-focus)] bg-[var(--tc-workspace-focus)] text-[var(--tc-workspace-shell)]"
          : "border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-recess)] text-[var(--tc-workspace-text-secondary)] hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]",
      )}
    >
      {children}
      {label}
    </button>
  );
}

function ResultCard({
  card,
  onApplyText,
  onCopyText,
  onSaveIdea,
  onConvertPendingFact,
  onRetry,
  onDiscard,
}: {
  card: AIResultCard;
  onApplyText: AICardListProps["onApplyText"];
  onCopyText: AICardListProps["onCopyText"];
  onSaveIdea: AICardListProps["onSaveIdea"];
  onConvertPendingFact: AICardListProps["onConvertPendingFact"];
  onRetry: AICardListProps["onRetry"];
  onDiscard: AICardListProps["onDiscard"];
}) {
  const generated = card.status === "generated";
  const paperTone =
    card.type === "text_candidate" || card.type === "chapter_summary";
  return (
    <article
      className={cn(
        "px-3 py-3",
        paperTone ? "tc-paper-card" : "tc-panel tc-aurora-line",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">{cardTitle(card)}</p>
          <p
            className={cn(
              "text-xs",
              paperTone
                ? "text-[var(--tc-paper-ink-muted)]"
                : "text-[var(--tc-workspace-text-muted)]",
            )}
          >
            {statusText(card.status)}
          </p>
        </div>
        <button
          type="button"
          title="丢弃"
          aria-label="丢弃"
          disabled={!generated}
          onClick={() => onDiscard(card)}
          className={cn(
            "inline-flex size-8 items-center justify-center rounded-[var(--tc-panel-radius)] border transition-colors disabled:opacity-40",
            paperTone
              ? "border-[var(--tc-paper-border)] hover:bg-[var(--tc-paper-mark-soft)]"
              : "border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-recess)] text-[var(--tc-workspace-text-secondary)] hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]",
          )}
        >
          <Trash2 className="size-4" />
        </button>
      </div>
      <div
        className={cn(
          "max-h-48 overflow-auto whitespace-pre-wrap rounded-[var(--tc-panel-radius)] p-2 text-sm leading-6",
          paperTone
            ? "border border-[var(--tc-paper-border-soft)] bg-[var(--tc-paper-bg-soft)]"
            : "tc-recess text-[var(--tc-workspace-text-secondary)]",
        )}
      >
        {cardContent(card)}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {card.type === "text_candidate" ? (
          <>
            <SmallAction
              label="插入"
              disabled={!generated}
              onClick={() => onApplyText(card, "insert_cursor")}
              tone="paper"
            >
              <CornerDownLeft className="size-4" />
            </SmallAction>
            <SmallAction
              label="追加"
              disabled={!generated}
              onClick={() => onApplyText(card, "append_after_selection")}
              tone="paper"
            >
              <ListPlus className="size-4" />
            </SmallAction>
            <SmallAction label="复制" tone="paper" onClick={() => onCopyText(card)}>
              <Copy className="size-4" />
            </SmallAction>
          </>
        ) : null}
        {card.type === "suggestion" ? (
          <SmallAction
            label="灵感"
            disabled={!generated}
            onClick={() => onSaveIdea(card)}
          >
            <Lightbulb className="size-4" />
          </SmallAction>
        ) : null}
        {card.type === "pending_fact" ? (
          <SmallAction
            label="待确认"
            disabled={!generated}
            onClick={() => onConvertPendingFact(card)}
          >
            <FileQuestion className="size-4" />
          </SmallAction>
        ) : null}
        {card.type !== "chapter_summary" ? (
          <SmallAction
            label="重试"
            disabled={!generated}
            onClick={() => onRetry(card)}
            tone={paperTone ? "paper" : "workspace"}
          >
            <RotateCcw className="size-4" />
          </SmallAction>
        ) : null}
      </div>
    </article>
  );
}

function SmallAction({
  label,
  disabled = false,
  children,
  onClick,
  tone = "workspace",
}: {
  label: string;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
  tone?: "workspace" | "paper";
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1 rounded-[var(--tc-panel-radius)] border px-2 text-xs font-medium transition-colors disabled:opacity-40",
        tone === "paper"
          ? "border-[var(--tc-paper-border)] text-[var(--tc-paper-ink)] hover:bg-[var(--tc-paper-mark-soft)]"
          : "border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-recess)] text-[var(--tc-workspace-text-secondary)] hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]",
      )}
    >
      {children}
      {label}
    </button>
  );
}

function cardTitle(card: AIResultCard): string {
  if (card.type === "text_candidate") {
    return "续写正文";
  }
  if (card.type === "pending_fact") {
    return "待确认设定";
  }
  if (card.type === "chapter_summary") {
    return "章节整理";
  }
  return "建议";
}

function cardContent(card: AIResultCard): string {
  if (typeof card.content === "string") {
    return card.content;
  }
  if (card.type === "chapter_summary") {
    return chapterSummaryContent(card.content);
  }
  const title = card.content.title;
  const body = card.content.body ?? card.content.summary ?? card.content.content;
  if (typeof title === "string" && typeof body === "string") {
    return `${title}\n${body}`;
  }
  if (typeof body === "string") {
    return body;
  }
  return JSON.stringify(card.content, null, 2);
}

function chapterSummaryContent(content: Record<string, unknown>): string {
  const lines: string[] = [];
  const summary = content.summary;
  if (typeof summary === "string") {
    lines.push(summary);
  }
  const keyEvents = stringArray(content.key_events);
  if (keyEvents.length) {
    lines.push(`关键事件\n${keyEvents.map(item => `- ${item}`).join("\n")}`);
  }
  const candidates = Array.isArray(content.new_setting_candidates)
    ? content.new_setting_candidates.length
    : 0;
  if (candidates) {
    lines.push(`待确认设定候选：${candidates} 条`);
  }
  const hooks = stringArray(content.next_chapter_hooks);
  if (hooks.length) {
    lines.push(`后续钩子\n${hooks.map(item => `- ${item}`).join("\n")}`);
  }
  return lines.join("\n\n") || JSON.stringify(content, null, 2);
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function statusText(status: AIResultCard["status"]): string {
  if (status === "generated") {
    return "待处理";
  }
  if (status === "inserted") {
    return "已插入";
  }
  if (status === "saved_to_inbox") {
    return "已保存";
  }
  if (status === "discarded") {
    return "已丢弃";
  }
  if (status === "retried") {
    return "已重试";
  }
  return "已转换";
}
