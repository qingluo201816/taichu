"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Bot,
  GitBranch,
  History,
  Inbox,
  Library,
  Gauge,
  Settings,
} from "lucide-react";
import { useEffect, type CSSProperties, type ReactNode } from "react";

import { cn } from "@/lib/utils";

const navigation = [
  { label: "写作", href: "/editor", icon: BookOpen },
  { label: "知识库", href: "/knowledge", icon: Library },
  { label: "智能体工作台", href: "/agent-workbench", icon: Bot },
  { label: "任务监控", href: "/task-monitor", icon: GitBranch },
  { label: "模型监控", href: "/model-monitor", icon: Gauge },
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
  transparentHeader = false,
  viewportLocked = false,
}: {
  children: ReactNode;
  activePath?: string;
  escapeToHome?: boolean;
  showNavigation?: boolean;
  headerActions?: ReactNode;
  workspaceStyle?: CSSProperties;
  transparentHeader?: boolean;
  viewportLocked?: boolean;
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
    <main
      className={cn(
        "tc-workspace-page",
        viewportLocked ? "flex h-dvh flex-col overflow-hidden" : "min-h-screen",
      )}
      style={workspaceStyle}
    >
      <header
        className={cn(
          "top-0 z-40 w-full shrink-0 border-b",
          transparentHeader
            ? "absolute border-white/15 bg-black/15"
            : "sticky border-[var(--tc-nav-border)] bg-[var(--tc-nav-bg)]/92 backdrop-blur",
        )}
      >
        <div
          className={cn(
            "mx-auto flex max-w-[1440px] flex-col gap-3 px-4 md:px-6 xl:flex-row xl:items-center xl:justify-between",
            headerActions ? "py-2" : "py-3",
          )}
        >
          <Link
            href="/home"
            className={cn(
              "flex min-w-0 items-center gap-3",
              transparentHeader ? "text-white" : "text-[var(--tc-midnight-ink)]",
            )}
          >
            <span
              className={cn(
                "tc-display-font inline-flex items-center justify-center rounded-[var(--tc-radius-control)] border",
                transparentHeader
                  ? "border-white/30 bg-black/15 text-white"
                  : "border-[var(--tc-midnight-ink)] bg-[var(--tc-deep-forest-teal)] text-[var(--tc-action-primary-text)]",
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
                  "block",
                  transparentHeader ? "text-white/60" : "text-[var(--tc-smoke)]",
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
            <nav
              className={cn(
                "flex gap-2 overflow-x-auto rounded-[var(--tc-radius-control)] border p-1",
                transparentHeader
                  ? "border-white/15 bg-black/10"
                  : "border-[var(--tc-nav-border)] bg-[var(--tc-nav-bg)]",
              )}
            >
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
                        : transparentHeader
                          ? "text-white/70 hover:bg-white/10 hover:text-white"
                          : "text-[var(--tc-smoke)] hover:bg-[var(--tc-cream-paper)] hover:text-[var(--tc-midnight-ink)]",
                    )}
                    style={
                      active
                        ? {
                            background: transparentHeader
                              ? "rgba(255, 255, 255, 0.14)"
                              : "var(--tc-nav-active-bg)",
                            color: transparentHeader
                              ? "#ffffff"
                              : "var(--tc-nav-active-text)",
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
      {viewportLocked ? (
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      ) : (
        children
      )}
    </main>
  );
}
