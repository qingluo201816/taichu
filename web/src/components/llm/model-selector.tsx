"use client";

import { Bot, Loader2 } from "lucide-react";

import type { ReturnTypeOfModelSelection } from "@/components/llm/types";

export function ModelSelector({
  selection,
  compact = false,
}: {
  selection: ReturnTypeOfModelSelection;
  compact?: boolean;
}) {
  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-[var(--tc-text-muted)]">
      {selection.loading ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <Bot className="size-3.5 shrink-0" aria-hidden="true" />
      )}
      <span className={compact ? "sr-only" : "shrink-0"}>调用模型</span>
      <select
        aria-label="调用模型"
        value={selection.modelId}
        disabled={selection.loading || selection.models.length === 0}
        onChange={event => selection.setModelId(event.target.value)}
        className="h-8 min-w-0 max-w-56 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-xs text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-text-primary)]"
      >
        {selection.loading ? <option value="">模型加载中</option> : null}
        {!selection.loading && selection.models.length === 0 ? (
          <option value="">暂无可用模型</option>
        ) : null}
        {selection.models.map(model => (
          <option
            key={model.id}
            value={model.id}
            disabled={!model.enabled || model.availability === "unavailable"}
          >
            {model.display_name}
            {model.is_default ? "（默认）" : ""}
            {model.availability === "unavailable" ? "（不可用）" : ""}
          </option>
        ))}
      </select>
      {selection.error ? (
        <span className="truncate text-[var(--tc-text-muted)]" title={selection.error}>
          {selection.error}
        </span>
      ) : null}
    </label>
  );
}
