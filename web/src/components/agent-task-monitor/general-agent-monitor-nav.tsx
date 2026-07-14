"use client";

import Link from "next/link";
import { GitBranch } from "lucide-react";

import { cn } from "@/lib/utils";

export function GeneralAgentMonitorNav({
  active,
}: {
  active: "monitor" | "evaluation";
}) {
  const items = [
    {
      key: "monitor" as const,
      href: "/task-monitor/general-agent",
      label: "节点监控",
      icon: GitBranch,
    },
  ];
  return (
    <nav
      aria-label="通用写作助手任务监控"
      className="flex items-center gap-1 border-b border-[var(--tc-border-subtle)]"
    >
      {items.map(item => {
        const Icon = item.icon;
        return (
          <Link
            key={item.key}
            href={item.href}
            className={cn(
              "inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm",
              active === item.key
                ? "border-white text-[var(--tc-text-primary)]"
                : "border-transparent text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
            )}
          >
            <Icon className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
