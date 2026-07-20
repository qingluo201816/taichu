"use client";

import { X } from "lucide-react";
import { useId, useMemo, useState } from "react";

import {
  appearanceImportanceLabel,
  displayKnowledgeFieldValue,
  groupKnowledgeFields,
  splitKnowledgeList,
  type KnowledgeFormErrors,
  type KnowledgeFormState,
  type KnowledgeReferenceOption,
  type KnowledgeReferenceOptions,
} from "@/lib/knowledge/structured-fields";
import type {
  KnowledgeFieldSchema,
  KnowledgeTypeSchema,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type CommonProps = {
  schema: KnowledgeTypeSchema;
  hiddenFieldKeys?: ReadonlySet<string>;
  referenceOptions?: KnowledgeReferenceOptions;
  chapterCount?: number;
  className?: string;
  density?: "default" | "compact";
};

export function StructuredKnowledgeView({
  schema,
  values,
  hiddenFieldKeys = new Set(),
  referenceOptions = {},
  chapterCount = 0,
  className,
  density = "default",
  showEmptyFields = false,
  highlightedFieldKeys = new Set(),
  highlightTone = "candidate",
}: CommonProps & {
  values: Record<string, unknown>;
  showEmptyFields?: boolean;
  highlightedFieldKeys?: ReadonlySet<string>;
  highlightTone?: "baseline" | "candidate";
}) {
  const groups = groupKnowledgeFields(schema, hiddenFieldKeys);
  const compact = density === "compact";

  return (
    <div
      data-knowledge-card
      className={cn(
        "max-h-[640px] max-w-[680px] overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3",
        className,
      )}
    >
      <div className={cn("grid", compact ? "gap-2" : "gap-3")}>
      {groups.map(group => {
        const visibleFields = group.fields.filter(field => {
          const value = values[field.field_key];
          return (
            showEmptyFields ||
            highlightedFieldKeys.has(field.field_key) ||
            field.required_when_confirmed ||
            field.field_key === "appearance_chapter_count" ||
            !isEmptyKnowledgeValue(value)
          );
        });
        if (!visibleFields.length) {
          return null;
        }
        return (
        <section
          key={group.label}
          className={cn("grid", compact ? "gap-1" : "gap-1.5")}
        >
          <h4 className="text-xs font-medium text-[var(--tc-text-muted)]">
            {group.label}
          </h4>
          <dl className={cn("grid", compact ? "gap-0.5" : "gap-1.5")}>
            {visibleFields.map(field => {
              const value = values[field.field_key];
              const empty = isEmptyKnowledgeValue(value);
              const highlighted = highlightedFieldKeys.has(field.field_key);
              const highlightStyle = highlighted
                ? highlightTone === "candidate"
                  ? {
                      background:
                        "color-mix(in srgb, var(--tc-agent-knowledge) 10%, transparent)",
                      boxShadow: "inset 2px 0 0 var(--tc-agent-knowledge)",
                    }
                  : { boxShadow: "inset 2px 0 0 var(--tc-border-strong)" }
                : undefined;
              return (
                <div
                  key={field.field_key}
                  style={highlightStyle}
                  className={cn(
                    "grid items-start rounded-[var(--tc-radius-control)]",
                    compact
                      ? "grid-cols-[72px_minmax(0,1fr)] gap-1.5 text-xs"
                      : "grid-cols-[88px_minmax(0,1fr)] gap-2 text-sm",
                    highlighted &&
                      (compact ? "-mx-1.5 px-1.5 py-0.5" : "-mx-2 px-2 py-1"),
                    highlighted && highlightTone === "baseline"
                      ? "bg-[var(--tc-surface-muted)]"
                      : "",
                  )}
                >
                  <dt
                    className={cn(
                      "text-xs leading-5 text-[var(--tc-text-muted)]",
                      highlighted && highlightTone === "candidate"
                        ? "text-[var(--tc-agent-knowledge)]"
                        : "",
                    )}
                  >
                    {field.label}
                  </dt>
                  <dd
                    className={cn(
                      "min-w-0 whitespace-pre-wrap break-words text-sm leading-5",
                      compact && "text-xs",
                      empty
                        ? "text-[var(--tc-text-muted)]"
                        : "text-[var(--tc-text-primary)]",
                    )}
                  >
                    {field.field_type === "string_array" && Array.isArray(value) && value.length ? (
                      <span className={cn("flex flex-wrap", compact ? "gap-1" : "gap-1.5")}>
                        {value.map(item => (
                          <span
                            key={String(item)}
                            className={cn(
                              "rounded-[var(--tc-radius-badge)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] py-0.5 text-xs",
                              compact ? "px-1" : "px-1.5",
                            )}
                          >
                            {String(item)}
                          </span>
                        ))}
                      </span>
                    ) : (
                      field.field_key === "appearance_chapter_count"
                        ? appearanceImportanceLabel(value, chapterCount)
                        : displayKnowledgeFieldValue(field, value, referenceOptions)
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
        );
      })}
      </div>
    </div>
  );
}

export function StructuredKnowledgeForm({
  schema,
  form,
  onChange,
  hiddenFieldKeys = new Set(),
  referenceOptions = {},
  errors = {},
  className,
  density = "default",
}: CommonProps & {
  form: KnowledgeFormState;
  onChange: (form: KnowledgeFormState) => void;
  errors?: KnowledgeFormErrors;
}) {
  const groups = groupKnowledgeFields(schema, hiddenFieldKeys);
  const compact = density === "compact";

  return (
    <div
      data-knowledge-form
      className={cn(
        "max-h-[640px] max-w-[680px] overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3",
        className,
      )}
    >
      <div className={cn("grid", compact ? "gap-2" : "gap-3")}>
      {groups.map(group => {
        const editableFields = group.fields.filter(
          field => field.author_editable !== false,
        );
        if (!editableFields.length) return null;
        return (
          <section
            key={group.label}
            className={cn("grid", compact ? "gap-1.5" : "gap-2")}
          >
            <h4 className="text-xs font-medium text-[var(--tc-text-muted)]">
              {group.label}
            </h4>
            <div className={cn("grid sm:grid-cols-2", compact ? "gap-1.5" : "gap-2")}>
              {editableFields.map(field => (
                <KnowledgeFieldControl
                  key={field.field_key}
                  field={field}
                  value={form[field.field_key] ?? ""}
                  options={referenceOptions[field.field_key] ?? []}
                  error={errors[field.field_key]}
                  density={density}
                  onChange={value =>
                    onChange({ ...form, [field.field_key]: value })
                  }
                />
              ))}
            </div>
          </section>
        );
      })}
      </div>
    </div>
  );
}

function KnowledgeFieldControl({
  field,
  value,
  options,
  error,
  density,
  onChange,
}: {
  field: KnowledgeFieldSchema;
  value: string;
  options: KnowledgeReferenceOption[];
  error?: string;
  density: "default" | "compact";
  onChange: (value: string) => void;
}) {
  const compact = density === "compact";
  const fullWidth = ["long_text", "string_array", "record_array"].includes(
    field.field_type,
  );
  const controlClassName = cn(
    "mt-1 w-full rounded-[var(--tc-radius-control)] border bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]",
    compact ? "px-2 text-xs" : "px-2.5 text-sm",
    error
      ? "border-[var(--tc-text-primary)]"
      : "border-[var(--tc-border-subtle)]",
  );

  return (
    <label
      className={cn(
        "block text-sm text-[var(--tc-text-secondary)]",
        fullWidth ? "sm:col-span-2" : "",
      )}
    >
      <span className="text-xs">{field.label}</span>
      {field.required_when_confirmed ? (
        <span className="ml-1 text-xs text-[var(--tc-text-muted)]">必填</span>
      ) : null}
      {field.field_type === "enum" ? (
        <select
          value={value}
          onChange={event => onChange(event.target.value)}
          className={cn(controlClassName, compact ? "h-7" : "h-8")}
        >
          {!field.required_when_confirmed ? <option value="">未选择</option> : null}
          {field.options.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : field.field_type === "boolean" ? (
        <select
          value={value}
          onChange={event => onChange(event.target.value)}
          className={cn(controlClassName, compact ? "h-7" : "h-8")}
        >
          <option value="">未设置</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      ) : field.field_type === "string_array" ? (
        <ArrayTagInput
          value={value}
          placeholder={field.placeholder || `添加${field.label}`}
          className={controlClassName}
          compact={compact}
          onChange={onChange}
        />
      ) : field.field_type === "chapter_ref" || field.field_type === "knowledge_ref" ? (
        <ReferenceSearchInput
          value={value}
          options={options}
          placeholder={field.placeholder || `搜索并选择${field.label}`}
          className={cn(controlClassName, compact ? "h-7" : "h-8")}
          onChange={onChange}
        />
      ) : field.field_type === "record_array" ? (
        <div
          className={cn(
            "mt-1 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]",
            compact ? "px-2 py-1.5 text-xs" : "px-3 py-2 text-sm",
          )}
        >
          该复合字段暂不支持直接编辑，原内容会保持不变。
        </div>
      ) : field.field_type === "long_text" ? (
        <textarea
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={field.placeholder}
          className={cn(
            controlClassName,
            compact
              ? "min-h-16 resize-y py-1.5 leading-5"
              : "min-h-20 resize-y py-2 leading-5",
          )}
        />
      ) : (
        <input
          type={field.field_type === "number" ? "number" : "text"}
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={field.placeholder}
          className={cn(controlClassName, compact ? "h-7" : "h-8")}
        />
      )}
      {error ? (
        <span className="mt-1 block text-xs text-[var(--tc-text-primary)]">
          {error}
        </span>
      ) : null}
    </label>
  );
}

function ArrayTagInput({
  value,
  placeholder,
  className,
  compact,
  onChange,
}: {
  value: string;
  placeholder: string;
  className: string;
  compact: boolean;
  onChange: (value: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const items = useMemo(() => splitKnowledgeList(value), [value]);

  function commitDraft() {
    const additions = splitKnowledgeList(draft);
    if (!additions.length) {
      setDraft("");
      return;
    }
    onChange([...new Set([...items, ...additions])].join("\n"));
    setDraft("");
  }

  return (
    <span
      className={cn(
        className,
        "flex flex-wrap items-center",
        compact ? "min-h-8 gap-1 py-0.5" : "min-h-9 gap-1.5 py-1",
      )}
    >
      {items.map(item => (
        <span
          key={item}
          className={cn(
            "inline-flex items-center gap-1 rounded-[var(--tc-radius-badge)] border border-[var(--tc-border-subtle)] py-0.5 text-xs text-[var(--tc-text-primary)]",
            compact ? "px-1.5" : "px-2",
          )}
        >
          {item}
          <button
            type="button"
            aria-label={`移除${item}`}
            onClick={() => onChange(items.filter(current => current !== item).join("\n"))}
            className="text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={event => setDraft(event.target.value)}
        onBlur={commitDraft}
        onKeyDown={event => {
          if (event.key === "Enter" || event.key === "," || event.key === "，") {
            event.preventDefault();
            commitDraft();
          } else if (event.key === "Backspace" && !draft && items.length) {
            onChange(items.slice(0, -1).join("\n"));
          }
        }}
        placeholder={items.length ? "继续添加" : placeholder}
        className={cn(
          "min-w-32 flex-1 bg-transparent outline-none placeholder:text-[var(--tc-text-muted)]",
          compact ? "h-6 text-xs" : "h-7 text-sm",
        )}
      />
    </span>
  );
}

function isEmptyKnowledgeValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function ReferenceSearchInput({
  value,
  options,
  placeholder,
  className,
  onChange,
}: {
  value: string;
  options: KnowledgeReferenceOption[];
  placeholder: string;
  className: string;
  onChange: (value: string) => void;
}) {
  const listId = useId();
  const current = options.find(option => option.value === value);
  const defaultQuery = current?.label ?? (value ? "引用内容已不存在" : "");
  const [draft, setDraft] = useState({
    value,
    defaultQuery,
    query: defaultQuery,
  });
  const query =
    draft.value === value && draft.defaultQuery === defaultQuery
      ? draft.query
      : defaultQuery;

  return (
    <span className="block">
      <input
        list={listId}
        value={query}
        onChange={event => {
          const nextQuery = event.target.value;
          setDraft({ value, defaultQuery, query: nextQuery });
          if (!nextQuery) {
            onChange("");
            return;
          }
          const match = options.find(
            option => option.label === nextQuery || option.value === nextQuery,
          );
          if (match) {
            onChange(match.value);
          }
        }}
        onBlur={() => {
          const match = options.find(
            option => option.label === query || option.value === query,
          );
          if (match) {
            setDraft({ value: match.value, defaultQuery: match.label, query: match.label });
            onChange(match.value);
          } else if (!query) {
            onChange("");
          } else {
            setDraft({ value, defaultQuery, query: defaultQuery });
          }
        }}
        placeholder={placeholder}
        className={className}
      />
      <datalist id={listId}>
        {options.map(option => (
          <option key={option.value} value={option.label} />
        ))}
      </datalist>
      <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
        输入关键词后从候选项中选择
      </span>
    </span>
  );
}
