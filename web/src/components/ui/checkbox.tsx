"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

function Checkbox({
  className,
  ...props
}: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] text-[var(--tc-action-primary-text)] outline-none transition-colors duration-150",
        "focus-visible:border-[var(--tc-text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--tc-border-strong)]",
        "[&[data-checked]]:border-[var(--tc-action-primary-bg)] [&[data-checked]]:bg-[var(--tc-action-primary-bg)]",
        "[&[data-disabled]]:cursor-not-allowed [&[data-disabled]]:opacity-45",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center"
      >
        <Check className="size-3" strokeWidth={2.5} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
