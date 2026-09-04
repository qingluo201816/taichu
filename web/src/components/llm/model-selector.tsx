"use client";

import { Select } from "@base-ui/react/select";
import { Bot, Check, ChevronDown, Loader2, Zap } from "lucide-react";

import type { ReturnTypeOfModelSelection } from "@/components/llm/types";

export function ModelSelector({
  selection,
  compact = false,
}: {
  selection: ReturnTypeOfModelSelection;
  compact?: boolean;
}) {
  if (compact) {
    const items = selection.models.map(model => ({
      label: modelLabel(model),
      value: model.id,
    }));
    return (
      <div className="flex min-w-0 items-center gap-1.5 text-sm text-[var(--tc-text-primary)]">
        {selection.loading ? (
          <Loader2
            className="size-4 shrink-0 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        ) : (
          <Zap className="size-4 shrink-0" aria-hidden="true" />
        )}
        <Select.Root
          items={items}
          value={selection.modelId || null}
          disabled={selection.loading || selection.models.length === 0}
          onValueChange={value => {
            if (typeof value === "string") {
              selection.setModelId(value);
            }
          }}
        >
          <Select.Trigger
            aria-label="调用模型"
            className="flex h-8 min-w-0 max-w-56 items-center gap-1.5 bg-transparent p-0 font-medium text-[var(--tc-text-primary)] outline-none hover:text-white focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[var(--tc-text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Select.Value
              className="truncate"
              placeholder={selection.loading ? "模型加载中" : "暂无可用模型"}
            />
            <Select.Icon className="shrink-0 text-[var(--tc-text-muted)]">
              <ChevronDown className="size-4" aria-hidden="true" />
            </Select.Icon>
          </Select.Trigger>
          <Select.Portal>
            <Select.Positioner
              sideOffset={8}
              align="end"
              alignItemWithTrigger={false}
              className="z-50 select-none outline-none"
            >
              <Select.Popup className="min-w-[240px] overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-card)] p-1.5 text-[var(--tc-text-primary)] shadow-[0_12px_28px_rgba(0,0,0,0.28)] outline-none data-[starting-style]:translate-y-1 data-[starting-style]:opacity-0 data-[ending-style]:translate-y-1 data-[ending-style]:opacity-0 motion-safe:transition-[opacity,transform] motion-safe:duration-150 motion-reduce:transition-none">
                <Select.List className="tc-editor-scrollbar max-h-72 overflow-y-auto">
                  {selection.models.map(model => (
                    <Select.Item
                      key={model.id}
                      value={model.id}
                      disabled={!model.enabled || model.availability === "unavailable"}
                      className="grid cursor-default grid-cols-[minmax(0,1fr)_16px] items-center gap-3 rounded-[var(--tc-radius-control)] px-3 py-2 text-sm text-[var(--tc-text-secondary)] outline-none data-[highlighted]:bg-[var(--tc-surface-muted)] data-[highlighted]:text-[var(--tc-text-primary)] data-[selected]:text-[var(--tc-text-primary)] data-[disabled]:opacity-40"
                    >
                      <Select.ItemText className="truncate">
                        {modelLabel(model)}
                      </Select.ItemText>
                      <Select.ItemIndicator>
                        <Check className="size-4" aria-hidden="true" />
                      </Select.ItemIndicator>
                    </Select.Item>
                  ))}
                </Select.List>
              </Select.Popup>
            </Select.Positioner>
          </Select.Portal>
        </Select.Root>
        {selection.error ? (
          <span className="sr-only" role="status">
            {selection.error}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-[var(--tc-text-muted)]">
      {selection.loading ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <Bot className="size-3.5 shrink-0" aria-hidden="true" />
      )}
      <span className="shrink-0">调用模型</span>
      <select
        aria-label="调用模型"
        value={selection.modelId}
        disabled={selection.loading || selection.models.length === 0}
        onChange={event => selection.setModelId(event.target.value)}
        className="h-8 min-w-0 max-w-56 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-xs text-[var(--tc-text-primary)] outline-none disabled:cursor-not-allowed disabled:opacity-50 focus:border-[var(--tc-text-primary)]"
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
            {modelLabel(model)}
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

function modelLabel(model: ReturnTypeOfModelSelection["models"][number]): string {
  return [
    modelDisplayName(model.display_name),
    model.is_default ? "（默认）" : "",
    model.availability === "unavailable" ? "（不可用）" : "",
  ].join("");
}

export function modelDisplayName(value: string): string {
  return value.replaceAll("（官方）", "").replaceAll("(官方)", "").trim();
}
