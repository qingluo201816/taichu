"use client";

import Link from "next/link";
import { Activity, Scale } from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const items = [
  {
    href: "/task-monitor/knowledge-extraction",
    label: "运行监控",
    icon: Activity,
  },
  {
    href: "/task-monitor/knowledge-extraction/evaluation",
    label: "效果评估",
    icon: Scale,
  },
];

export function KnowledgeExtractionMonitorNav({
  className,
}: {
  className?: string;
}) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="知识沉淀智能体任务视图"
      className={cn(
        "flex w-fit max-w-full gap-1 overflow-x-auto rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-1",
        className,
      )}
    >
      {items.map(item => {
        const Icon = item.icon;
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[var(--tc-radius-control)] px-2.5 text-xs font-medium transition-colors",
              active
                ? "bg-[var(--tc-surface-card)] text-[var(--tc-text-primary)]"
                : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
            )}
          >
            <Icon className="size-3.5" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
