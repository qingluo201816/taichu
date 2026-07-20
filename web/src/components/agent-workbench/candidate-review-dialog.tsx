"use client";

import { Dialog } from "@base-ui/react/dialog";
import { Ban, Check, Eye, PencilLine, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import {
  StructuredKnowledgeForm,
  StructuredKnowledgeView,
} from "@/components/knowledge/structured-knowledge-fields";
import { Button } from "@/components/ui/button";
import {
  CANDIDATE_LOCKED_FIELD_KEYS,
  knowledgePayloadFromForm,
  type KnowledgeFormErrors,
  type KnowledgeFormState,
  type KnowledgeReferenceOptions,
} from "@/lib/knowledge/structured-fields";
import {
  buildCandidateReviewPreview,
  changedKnowledgeFieldKeys,
} from "@/lib/knowledge/candidate-review-preview";
import type {
  AgentReviewItem,
  EditConfirmMergeMode,
} from "@/lib/types/agent-workbench";
import type {
  KnowledgeTypeSchema,
  StructuredKnowledgeCard,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type CandidateReviewAction = "confirm" | "edit-confirm" | "reject";
type CandidateContentMode = "preview" | "edit";
type CandidateContentState = {
  candidateId: string;
  mode: CandidateContentMode;
};

const mergeModeLabel: Record<EditConfirmMergeMode, string> = {
  merge: "合并更新",
  overwrite: "整卡覆盖",
};

const candidateStatusLabel: Record<AgentReviewItem["candidate_status"], string> = {
  pending: "待处理",
  confirmed: "已确认",
  rejected: "已废弃",
};

export function CandidateReviewDialog({
  open,
  candidate,
  schema,
  draft,
  formErrors,
  referenceOptions,
  isEditing,
  targetCard,
  targetCardError,
  mergeMode,
  actionBusyKey,
  knowledgeTypeText,
  candidateActionText,
  onOpenChange,
  onMergeModeChange,
  onDraftChange,
  onStartEdit,
  onCancelEdit,
  onAction,
}: {
  open: boolean;
  candidate: AgentReviewItem | null;
  schema: KnowledgeTypeSchema | null;
  draft: KnowledgeFormState;
  formErrors: KnowledgeFormErrors;
  referenceOptions: KnowledgeReferenceOptions;
  isEditing: boolean;
  targetCard?: StructuredKnowledgeCard | null;
  targetCardError: string;
  mergeMode: EditConfirmMergeMode;
  actionBusyKey: string;
  knowledgeTypeText: string;
  candidateActionText: string;
  onOpenChange: (open: boolean) => void;
  onMergeModeChange: (value: EditConfirmMergeMode) => void;
  onDraftChange: (value: KnowledgeFormState) => void;
  onStartEdit: (candidate: AgentReviewItem) => void;
  onCancelEdit: (candidate: AgentReviewItem) => void;
  onAction: (
    candidate: AgentReviewItem,
    action: CandidateReviewAction,
    mergeMode?: EditConfirmMergeMode,
  ) => void;
}) {
  const [contentState, setContentState] = useState<CandidateContentState>({
    candidateId: "",
    mode: "preview",
  });

  const candidatePayload = useMemo(() => {
    if (!candidate) {
      return {};
    }
    if (!schema) {
      return candidate.suggested_card;
    }
    return {
      ...candidate.suggested_card,
      ...knowledgePayloadFromForm(schema, draft, CANDIDATE_LOCKED_FIELD_KEYS),
    };
  }, [candidate, draft, schema]);

  const resultPreview = useMemo(
    () =>
      schema
        ? buildCandidateReviewPreview(
            targetCard ? (targetCard as Record<string, unknown>) : null,
            candidatePayload,
            schema,
            mergeMode,
          )
        : candidatePayload,
    [candidatePayload, mergeMode, schema, targetCard],
  );

  const changedFieldKeys = useMemo(
    () =>
      schema && targetCard
        ? changedKnowledgeFieldKeys(
            schema,
            targetCard as Record<string, unknown>,
            resultPreview,
          )
        : new Set<string>(),
    [resultPreview, schema, targetCard],
  );

  if (!candidate) {
    return null;
  }

  const currentCandidate = candidate;
  const contentMode =
    contentState.candidateId === currentCandidate.review_item_id
      ? contentState.mode
      : isEditing
        ? "edit"
        : "preview";
  const hasTarget = Boolean(candidate.target_card_id);
  const processed = candidate.candidate_status !== "pending";
  const canConfirm = candidate.candidate_action !== "ignore";
  const requiresEditedConfirm =
    candidate.candidate_action === "conflict" || hasTarget;
  const busy = actionBusyKey !== "";
  function handleEditToggle() {
    if (contentMode === "edit") {
      setContentState({
        candidateId: currentCandidate.review_item_id,
        mode: "preview",
      });
      return;
    }
    if (!isEditing) {
      onStartEdit(currentCandidate);
    }
    setContentState({
      candidateId: currentCandidate.review_item_id,
      mode: "edit",
    });
  }

  function handleCancelEdit() {
    onCancelEdit(currentCandidate);
    setContentState({
      candidateId: currentCandidate.review_item_id,
      mode: "preview",
    });
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      if (isEditing) {
        onCancelEdit(currentCandidate);
      }
      setContentState({ candidateId: "", mode: "preview" });
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-transparent" />
        <Dialog.Viewport className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-6">
          <Dialog.Popup
            style={{ maxHeight: "min(760px, calc(100dvh - 48px))" }}
            className="flex w-full max-w-[960px] flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-card)] text-[var(--tc-text-primary)] shadow-[0_8px_24px_rgba(0,0,0,0.18)] outline-none"
          >
            <header className="flex shrink-0 items-start justify-between gap-3 bg-[var(--tc-surface-muted)] px-4 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Dialog.Title className="truncate text-base font-semibold">
                    {candidate.display_title}
                  </Dialog.Title>
                  <ReviewTag>{knowledgeTypeText}</ReviewTag>
                  <ReviewTag>{candidateActionText}</ReviewTag>
                  <ReviewTag>{candidateStatusLabel[candidate.candidate_status]}</ReviewTag>
                </div>
                <Dialog.Description className="mt-1 text-xs text-[var(--tc-text-muted)]">
                  {hasTarget
                    ? "对照现有知识卡与本次入库结果，确认无误后再处理。"
                    : "检查候选新卡的完整字段，确认无误后再入库。"}
                </Dialog.Description>
              </div>
              <Dialog.Close
                type="button"
                aria-label="关闭候选审核"
                disabled={busy}
                className="flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)] disabled:opacity-50"
              >
                <X className="size-4" />
              </Dialog.Close>
            </header>

            <div className="min-h-0 overflow-y-auto px-4 py-3">
              {schema ? (
                hasTarget ? (
                  <div className="grid grid-cols-2 items-start gap-3">
                    <ComparisonPanel
                      title="现有知识卡"
                      subtitle={candidate.matched_card_name || targetCard?.name || "已匹配知识卡"}
                      tone="baseline"
                    >
                      {targetCardError ? (
                        <UnavailableCard text={targetCardError} />
                      ) : targetCard === undefined ? (
                        <UnavailableCard text="正在读取现有知识卡..." />
                      ) : targetCard ? (
                        <StructuredKnowledgeView
                          schema={schema}
                          values={targetCard as Record<string, unknown>}
                          referenceOptions={referenceOptions}
                          highlightedFieldKeys={changedFieldKeys}
                          highlightTone="baseline"
                          density="compact"
                          className="max-h-none max-w-none overflow-visible rounded-none border-0 bg-transparent p-0"
                        />
                      ) : (
                        <UnavailableCard text="未找到现有知识卡，暂时无法生成对照结果。" />
                      )}
                    </ComparisonPanel>

                    <ComparisonPanel
                      title={
                        contentMode === "edit"
                          ? "编辑候选字段"
                          : mergeMode === "merge"
                            ? "合并后预览"
                            : "整卡覆盖预览"
                      }
                      subtitle={
                        contentMode === "edit"
                          ? "编辑内容会实时用于结果预览"
                          : `${changedFieldKeys.size} 个字段发生变化`
                      }
                      tone="candidate"
                      action={
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {(["merge", "overwrite"] as EditConfirmMergeMode[]).map(
                            mode => (
                              <Button
                                key={mode}
                                type="button"
                                variant={mergeMode === mode ? "default" : "outline"}
                                size="xs"
                                aria-pressed={mergeMode === mode}
                                disabled={processed || busy}
                                onClick={() => onMergeModeChange(mode)}
                              >
                                {mergeModeLabel[mode]}
                              </Button>
                            ),
                          )}
                          {!processed && canConfirm ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="xs"
                              disabled={!schema || busy}
                              onClick={handleEditToggle}
                            >
                              {contentMode === "edit" ? (
                                <Eye className="size-3.5" />
                              ) : (
                                <PencilLine className="size-3.5" />
                              )}
                              {contentMode === "edit" ? "查看结果" : "编辑字段"}
                            </Button>
                          ) : null}
                        </div>
                      }
                    >
                      {contentMode === "edit" ? (
                        <StructuredKnowledgeForm
                          schema={schema}
                          form={draft}
                          errors={formErrors}
                          hiddenFieldKeys={CANDIDATE_LOCKED_FIELD_KEYS}
                          referenceOptions={referenceOptions}
                          density="compact"
                          onChange={onDraftChange}
                          className="max-h-none max-w-none overflow-visible rounded-none border-0 bg-transparent p-0"
                        />
                      ) : targetCardError ? (
                        <UnavailableCard text="现有知识卡读取失败，暂时无法生成入库结果。" />
                      ) : targetCard === undefined ? (
                        <UnavailableCard text="正在生成入库结果..." />
                      ) : targetCard ? (
                        <StructuredKnowledgeView
                          schema={schema}
                          values={resultPreview}
                          referenceOptions={referenceOptions}
                          highlightedFieldKeys={changedFieldKeys}
                          highlightTone="candidate"
                          density="compact"
                          className="max-h-none max-w-none overflow-visible rounded-none border-0 bg-transparent p-0"
                        />
                      ) : (
                        <UnavailableCard text="未找到现有知识卡，暂时无法生成入库结果。" />
                      )}
                    </ComparisonPanel>
                  </div>
                ) : (
                  <div className="mx-auto max-w-[620px]">
                    <ComparisonPanel
                      title={contentMode === "edit" ? "编辑候选新卡" : "候选新卡"}
                      subtitle="确认后将创建为正式知识卡"
                      tone="candidate"
                      action={
                        !processed && canConfirm ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="xs"
                            disabled={busy}
                            onClick={handleEditToggle}
                          >
                            {contentMode === "edit" ? (
                              <Eye className="size-3.5" />
                            ) : (
                              <PencilLine className="size-3.5" />
                            )}
                            {contentMode === "edit" ? "查看预览" : "编辑字段"}
                          </Button>
                        ) : null
                      }
                    >
                      {contentMode === "edit" ? (
                        <StructuredKnowledgeForm
                          schema={schema}
                          form={draft}
                          errors={formErrors}
                          hiddenFieldKeys={CANDIDATE_LOCKED_FIELD_KEYS}
                          referenceOptions={referenceOptions}
                          density="compact"
                          onChange={onDraftChange}
                          className="max-h-none max-w-none overflow-visible rounded-none border-0 bg-transparent p-0"
                        />
                      ) : (
                        <StructuredKnowledgeView
                          schema={schema}
                          values={candidatePayload}
                          referenceOptions={referenceOptions}
                          density="compact"
                          className="max-h-none max-w-none overflow-visible rounded-none border-0 bg-transparent p-0"
                        />
                      )}
                    </ComparisonPanel>
                  </div>
                )
              ) : (
                <UnavailableCard text="知识字段配置加载失败，请刷新后重试。" />
              )}
            </div>

            <footer className="flex shrink-0 items-center justify-between gap-3 bg-[var(--tc-surface-muted)] px-4 py-2.5">
              <p className="text-xs text-[var(--tc-text-muted)]">
                {processed
                  ? "该候选已经处理，当前仅供阅读。"
                  : candidate.schema_validation.passed
                    ? "结构校验通过，可以确认入库。"
                    : "存在校验提示，建议编辑后再确认。"}
              </p>
              {!processed ? (
                <div className="flex flex-wrap justify-end gap-2">
                  {canConfirm && isEditing ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={handleCancelEdit}
                    >
                      取消编辑
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={busy}
                    onClick={() => onAction(candidate, "reject")}
                  >
                    <Ban className="size-4" />
                    废弃
                  </Button>
                  {canConfirm ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy || !schema}
                      onClick={() =>
                        onAction(
                          candidate,
                          isEditing || requiresEditedConfirm
                            ? "edit-confirm"
                            : "confirm",
                          mergeMode,
                        )
                      }
                    >
                      <Check className="size-4" />
                      {isEditing ? "保存并确认" : "确认入库"}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </footer>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ComparisonPanel({
  title,
  subtitle,
  tone,
  action,
  children,
}: {
  title: string;
  subtitle: string;
  tone: "baseline" | "candidate";
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      style={
        tone === "candidate"
          ? {
              borderColor:
                "color-mix(in srgb, var(--tc-agent-knowledge) 42%, var(--tc-border-subtle))",
            }
          : undefined
      }
      className="min-w-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3"
    >
      <div className="mb-3 flex min-h-7 items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={cn(
                "size-2 shrink-0 rounded-full",
                tone === "baseline"
                  ? "bg-[var(--tc-text-muted)]"
                  : "bg-[var(--tc-agent-knowledge)]",
              )}
            />
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">{title}</h3>
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--tc-text-muted)]">
            {subtitle}
          </p>
        </div>
        {action}
      </div>
      <div
        style={{ maxHeight: "min(440px, calc(100dvh - 320px))" }}
        className="min-h-0 overflow-y-auto pr-1"
      >
        {children}
      </div>
    </section>
  );
}

function ReviewTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-[var(--tc-radius-badge)] border border-[var(--tc-border-subtle)] px-1.5 py-0.5 text-xs text-[var(--tc-text-secondary)]">
      {children}
    </span>
  );
}

function UnavailableCard({ text }: { text: string }) {
  return (
    <p className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-4 text-sm text-[var(--tc-text-muted)]">
      {text}
    </p>
  );
}
