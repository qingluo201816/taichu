"use client";

import { Dialog } from "@base-ui/react/dialog";
import { AlertTriangle, Check } from "lucide-react";

import { Button } from "@/components/ui/button";

export type BulkAcceptConfirmationStep = "first" | "second" | null;

export function BulkAcceptConfirmDialogs({
  step,
  pendingCount,
  onStepChange,
  onConfirm,
}: {
  step: BulkAcceptConfirmationStep;
  pendingCount: number;
  onStepChange: (step: BulkAcceptConfirmationStep) => void;
  onConfirm: () => void;
}) {
  return (
    <>
      <SmallConfirmDialog
        open={step === "first"}
        title="一键采纳本次沉淀？"
        description={
          pendingCount > 0
            ? `将自动确认 ${pendingCount} 条待处理候选。已有知识卡按合并更新处理，新知识卡直接创建。`
            : "本次没有待处理候选，将直接采纳当前章节范围。"
        }
        confirmLabel="继续"
        onCancel={() => onStepChange(null)}
        onConfirm={() => onStepChange("second")}
      />
      <SmallConfirmDialog
        open={step === "second"}
        title="请再次确认"
        description={
          pendingCount > 0
            ? `确认后会把 ${pendingCount} 条候选写入知识库，并推进本次沉淀进度。此操作不会采纳已经废弃的候选。`
            : "确认后会推进本次沉淀进度。"
        }
        confirmLabel="确认并采纳"
        warning
        onCancel={() => onStepChange(null)}
        onConfirm={onConfirm}
      />
    </>
  );
}

function SmallConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  warning = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  warning?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-[70] bg-black/55 data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 motion-safe:transition-opacity motion-safe:duration-150 motion-reduce:transition-none" />
        <Dialog.Viewport className="fixed inset-0 z-[80] grid place-items-center p-4">
          <Dialog.Popup className="w-full max-w-[400px] rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4 text-[var(--tc-text-primary)] outline-none data-[starting-style]:scale-[0.98] data-[starting-style]:opacity-0 data-[ending-style]:scale-[0.98] data-[ending-style]:opacity-0 motion-safe:transition-[opacity,transform] motion-safe:duration-150 motion-reduce:transition-none">
            <div className="flex items-start gap-3">
              {warning ? (
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--tc-surface-muted)]">
                  <AlertTriangle aria-hidden="true" className="size-4" />
                </span>
              ) : null}
              <div className="min-w-0">
                <Dialog.Title className="text-base font-semibold">
                  {title}
                </Dialog.Title>
                <Dialog.Description className="mt-1.5 text-sm leading-6 text-[var(--tc-text-muted)]">
                  {description}
                </Dialog.Description>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onCancel}>
                取消
              </Button>
              <Button type="button" size="sm" onClick={onConfirm}>
                {warning ? <Check aria-hidden="true" className="size-3.5" /> : null}
                {confirmLabel}
              </Button>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
