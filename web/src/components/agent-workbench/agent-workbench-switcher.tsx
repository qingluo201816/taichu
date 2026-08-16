"use client";

import { Activity, Bot, GitBranch, Workflow } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type WorkbenchAgent = "general" | "knowledge";

const agents: Array<{
  key: WorkbenchAgent;
  label: string;
  description: string;
  icon: typeof Bot;
  iconClassName: string;
  monitorHref: string;
  monitorLabel: string;
  monitorIcon: typeof Bot;
  monitorIconClassName: string;
}> = [
  {
    key: "general",
    label: "通用写作助手 Agent",
    description: "从简短问答到多步骤写作任务",
    icon: Bot,
    iconClassName: "text-sky-300",
    monitorHref: "/task-monitor/general-agent",
    monitorLabel: "查看通用写作助手监控",
    monitorIcon: GitBranch,
    monitorIconClassName: "text-sky-300",
  },
  {
    key: "knowledge",
    label: "正文知识沉淀 Workflow",
    description: "章节正文到候选知识卡",
    icon: Workflow,
    iconClassName: "text-emerald-300",
    monitorHref: "/task-monitor/knowledge-extraction",
    monitorLabel: "查看正文知识沉淀监控",
    monitorIcon: Activity,
    monitorIconClassName: "text-emerald-300",
  },
];

export function AgentWorkbenchSwitcher({
  activeAgent,
  onAgentChange,
}: {
  activeAgent: WorkbenchAgent;
  onAgentChange: (agent: WorkbenchAgent) => void;
}) {
  return (
    <>
      <div className="px-2 py-1">
        <p className="text-xs text-[var(--tc-text-muted)]">智能体工作台</p>
        <h1 className="mt-1 text-sm font-semibold text-[var(--tc-text-primary)]">
          选择助手
        </h1>
      </div>

      <nav aria-label="选择智能体" className="mt-2 grid gap-1">
        {agents.map(agent => {
          const Icon = agent.icon;
          const MonitorIcon = agent.monitorIcon;
          const active = agent.key === activeAgent;
          return (
            <div
              key={agent.key}
              className="grid grid-cols-[minmax(0,1fr)_32px] items-stretch gap-1"
            >
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onAgentChange(agent.key)}
                className={cn(
                  "min-w-0 rounded-[var(--tc-radius-control)] px-2.5 py-2 text-left text-sm transition-colors duration-150",
                  active
                    ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                )}
              >
                <span className="flex items-center gap-2 font-medium">
                  <Icon className={cn("size-3.5", agent.iconClassName)} />
                  {agent.label}
                </span>
                <span className="mt-0.5 block truncate pl-[22px] text-[11px] text-[var(--tc-text-muted)]">
                  {agent.description}
                </span>
              </button>
              <Link
                href={agent.monitorHref}
                aria-label={agent.monitorLabel}
                title={agent.monitorLabel}
                className="flex min-h-12 w-8 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] transition-colors duration-150 hover:bg-[var(--tc-surface-card)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--tc-workspace-focus)]"
              >
                <MonitorIcon
                  aria-hidden="true"
                  className={cn("size-4", agent.monitorIconClassName)}
                />
              </Link>
            </div>
          );
        })}
      </nav>
    </>
  );
}
