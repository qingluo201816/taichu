"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  BookOpen,
  History,
  Inbox,
  Library,
  Settings,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const navigation = [
  { label: "写作", href: "/editor", icon: BookOpen },
  { label: "知识库", href: "/knowledge", icon: Library },
  { label: "Inbox", href: "/inbox", icon: Inbox },
  { label: "AI 历史", href: "/ai-history", icon: History },
  { label: "智能体工作台", href: "/chat", icon: Bot, badge: "实验功能" },
  { label: "设置", href: "/settings", icon: Settings },
];

export function AppShell({
  children,
  activePath,
}: {
  children: ReactNode;
  activePath?: string;
}) {
  const pathname = usePathname();
  const currentPath = activePath ?? pathname;

  return (
    <main className="tc-workspace-page min-h-screen">
      <header className="sticky top-0 z-40 border-b border-[var(--tc-stone-mist)] bg-[var(--tc-white)]/92 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-3 px-4 py-3 md:px-6 xl:flex-row xl:items-center xl:justify-between">
          <Link
            href="/home"
            className="flex min-w-0 items-center gap-3 text-[var(--tc-midnight-ink)]"
          >
            <span className="inline-flex size-10 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-midnight-ink)] bg-[var(--tc-deep-forest-teal)] font-serif text-lg text-[var(--tc-white)]">
              初
            </span>
            <span className="min-w-0">
              <span className="block truncate font-serif text-2xl leading-none">
                太初
              </span>
              <span className="block text-xs text-[var(--tc-smoke)]">
                单本玄幻小说写作助手
              </span>
            </span>
          </Link>

          <nav className="flex gap-2 overflow-x-auto rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-1">
            {navigation.map(item => {
              const Icon = item.icon;
              const active =
                currentPath === item.href ||
                (item.href !== "/home" && currentPath.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "inline-flex h-10 shrink-0 items-center gap-2 rounded-[10px] px-3 text-sm font-medium transition-colors",
                    active
                      ? "bg-[var(--tc-lavender-whisper)] text-[var(--tc-midnight-ink)]"
                      : "text-[var(--tc-smoke)] hover:bg-[var(--tc-cream-paper)] hover:text-[var(--tc-midnight-ink)]",
                  )}
                >
                  <Icon className="size-4" />
                  {item.label}
                  {item.badge ? (
                    <span className="rounded-full border border-[var(--tc-deep-forest-teal)] px-2 py-0.5 text-[11px] text-[var(--tc-deep-forest-teal)]">
                      {item.badge}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      {children}
    </main>
  );
}
