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
  Replace,
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
      <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-gray-600">
        <MessageSquare className="size-4" />
        AI 卡片
      </div>

      <div className="rounded-lg border-2 border-black px-4 py-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <Scissors className="size-4" />
          当前选区
        </div>
        {selection ? (
          <div className="space-y-3 text-sm">
            <p className="max-h-24 overflow-auto rounded-md bg-gray-50 p-2 leading-6">
              {selection.selected_text}
            </p>
            <dl className="grid grid-cols-2 gap-2 text-xs text-gray-600">
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
          <p className="text-sm text-gray-500">未选择正文</p>
        )}
      </div>

      <div className="mt-4 space-y-3 rounded-lg border-2 border-black px-4 py-4">
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
          className="min-h-20 w-full resize-none rounded-lg border-2 border-black bg-white px-3 py-2 text-sm outline-none focus:bg-[#fffefc]"
          placeholder="给 AI 的一句话"
        />
        {selectedMode === "continue_text" ? (
          <input
            value={targetWords}
            onChange={event => onTargetWordsChange(event.target.value)}
            inputMode="numeric"
            className="h-9 w-full rounded-lg border-2 border-black px-3 text-sm outline-none"
            placeholder="目标字数"
          />
        ) : null}
        <Button
          size="sm"
          disabled={!selection || loading}
          onClick={() => onRunSelection(selectedMode)}
          className="w-full rounded-full border-2 border-black"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : null}
          生成卡片
        </Button>
        <Button
          size="sm"
          disabled={loading}
          onClick={onRunChapterSummary}
          className="w-full rounded-full border-2 border-black bg-white text-black hover:bg-gray-100"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
          整理本章
        </Button>
        {error ? <p className="text-xs font-semibold text-red-700">{error}</p> : null}
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
        "inline-flex h-9 items-center justify-center gap-1 rounded-lg border-2 border-black text-xs font-semibold",
        active ? "bg-black text-white" : "bg-white hover:bg-gray-100",
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
  return (
    <article className="rounded-lg border-2 border-black bg-white px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">{cardTitle(card)}</p>
          <p className="text-xs text-gray-500">{statusText(card.status)}</p>
        </div>
        <button
          type="button"
          title="丢弃"
          aria-label="丢弃"
          disabled={!generated}
          onClick={() => onDiscard(card)}
          className="inline-flex size-8 items-center justify-center rounded-lg border-2 border-black disabled:opacity-40"
        >
          <Trash2 className="size-4" />
        </button>
      </div>
      <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-gray-50 p-2 text-sm leading-6">
        {cardContent(card)}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {card.type === "text_candidate" ? (
          <>
            <SmallAction
              label="插入"
              disabled={!generated}
              onClick={() => onApplyText(card, "insert_cursor")}
            >
              <CornerDownLeft className="size-4" />
            </SmallAction>
            <SmallAction
              label="替换"
              disabled={!generated}
              onClick={() => onApplyText(card, "replace_selection")}
            >
              <Replace className="size-4" />
            </SmallAction>
            <SmallAction
              label="追加"
              disabled={!generated}
              onClick={() => onApplyText(card, "append_after_selection")}
            >
              <ListPlus className="size-4" />
            </SmallAction>
            <SmallAction label="复制" onClick={() => onCopyText(card)}>
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
        <SmallAction
          label="重试"
          disabled={!generated}
          onClick={() => onRetry(card)}
        >
          <RotateCcw className="size-4" />
        </SmallAction>
      </div>
    </article>
  );
}

function SmallAction({
  label,
  disabled = false,
  children,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex h-8 items-center gap-1 rounded-lg border-2 border-black px-2 text-xs font-semibold disabled:opacity-40"
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
