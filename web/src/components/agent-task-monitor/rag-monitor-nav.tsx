"use client";

import { Network, Scale } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

const items = [
  { key: "monitor", href: "/task-monitor/rag", label: "建模监控", icon: Network },
  {
    key: "evaluation",
    href: "/task-monitor/rag/evaluation",
    label: "质量评测",
    icon: Scale,
  },
] as const;

export function RAGMonitorNav({
  active,
}: {
  active: (typeof items)[number]["key"];
}) {
  return (
    <nav
      aria-label="RAG 监控与评测"
      className="flex w-fit gap-1 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] p-1"
    >
      {items.map(item => {
        const Icon = item.icon;
        const selected = item.key === active;
        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={selected ? "page" : undefined}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-[var(--tc-radius-control)] px-2.5 text-xs font-medium transition-colors duration-150 motion-reduce:transition-none",
              selected
                ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
            )}
          >
            <Icon className="size-3.5 text-[var(--tc-monitor-rag)]" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
