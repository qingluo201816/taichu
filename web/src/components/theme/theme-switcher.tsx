"use client";

import { Palette } from "lucide-react";

import { useThemeStyle } from "./theme-provider";

export function ThemeSwitcher({ className = "" }: { className?: string }) {
  const { currentTheme, nextTheme, toggleThemeStyle } = useThemeStyle();

  return (
    <button
      type="button"
      onClick={toggleThemeStyle}
      className={[
        "inline-flex h-10 items-center gap-2 rounded-[var(--tc-radius-pill)]",
        "border px-4 text-sm font-medium",
        "transition-colors duration-[var(--tc-duration-fast)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--tc-border-strong)]",
        className,
      ].join(" ")}
      style={{
        borderColor: "var(--tc-border-strong)",
        background: "var(--tc-surface-muted)",
        color: "var(--tc-text-primary)",
      }}
      aria-label={`切换为${nextTheme.label}`}
      title={`当前：${currentTheme.label}；点击切换为${nextTheme.label}`}
    >
      <Palette className="size-4" aria-hidden="true" />
      <span>切换为{nextTheme.shortLabel}</span>
    </button>
  );
}
