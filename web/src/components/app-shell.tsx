"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Bot,
  History,
  Inbox,
  Library,
  Settings,
} from "lucide-react";
import { useEffect, type CSSProperties, type ReactNode } from "react";

import { cn } from "@/lib/utils";

const navigation = [
  { label: "写作", href: "/editor", icon: BookOpen },
  { label: "知识库", href: "/knowledge", icon: Library },
  { label: "智能体工作台", href: "/agent-workbench", icon: Bot },
  { label: "收件箱", href: "/inbox", icon: Inbox },
  { label: "AI 历史", href: "/ai-history", icon: History },
  { label: "设置", href: "/settings", icon: Settings },
];

export function AppShell({
  children,
  activePath,
  escapeToHome,
  showNavigation = true,
  headerActions,
  workspaceStyle,
}: {
  children: ReactNode;
  activePath?: string;
  escapeToHome?: boolean;
  showNavigation?: boolean;
  headerActions?: ReactNode;
  workspaceStyle?: CSSProperties;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const currentPath = activePath ?? pathname;
  const shouldEscapeToHome = escapeToHome ?? (currentPath !== "/home");

  useEffect(() => {
    if (!shouldEscapeToHome) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      event.preventDefault();
      router.push("/home");
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [router, shouldEscapeToHome]);

  return (
    <main className="tc-workspace-page min-h-screen" style={workspaceStyle}>
      <header className="sticky top-0 z-40 border-b border-[var(--tc-nav-border)] bg-[var(--tc-nav-bg)]/92 backdrop-blur">
        <div
          className={cn(
            "mx-auto flex max-w-[1440px] flex-col gap-3 px-4 md:px-6 xl:flex-row xl:items-center xl:justify-between",
            headerActions ? "py-2" : "py-3",
          )}
        >
          <Link
            href="/home"
            className="flex min-w-0 items-center gap-3 text-[var(--tc-midnight-ink)]"
          >
            <span
              className={cn(
                "tc-display-font inline-flex items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-midnight-ink)] bg-[var(--tc-deep-forest-teal)] text-[var(--tc-action-primary-text)]",
                headerActions ? "size-8 text-base" : "size-10 text-lg",
              )}
            >
              初
            </span>
            <span className="min-w-0">
              <span
                className={cn(
                  "tc-display-font block truncate leading-none",
                  headerActions ? "text-xl" : "text-2xl",
                )}
              >
                太初
              </span>
              <span
                className={cn(
                  "block text-[var(--tc-smoke)]",
                  headerActions ? "text-[11px]" : "text-xs",
                )}
              >
                为长篇幻想而生的写作空间
              </span>
            </span>
          </Link>

          {headerActions ? (
            <div className="flex min-w-0 flex-1 justify-end overflow-visible">
              {headerActions}
            </div>
          ) : showNavigation ? (
            <nav className="flex gap-2 overflow-x-auto rounded-[var(--tc-radius-control)] border border-[var(--tc-nav-border)] bg-[var(--tc-nav-bg)] p-1">
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
                        ? ""
                        : "text-[var(--tc-smoke)] hover:bg-[var(--tc-cream-paper)] hover:text-[var(--tc-midnight-ink)]",
                    )}
                    style={
                      active
                        ? {
                            background: "var(--tc-nav-active-bg)",
                            color: "var(--tc-nav-active-text)",
                          }
                        : undefined
                    }
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          ) : null}
        </div>
      </header>
      {children}
    </main>
  );
}
