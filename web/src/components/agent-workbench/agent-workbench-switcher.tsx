"use client";

import { Bot, Workflow } from "lucide-react";

import { cn } from "@/lib/utils";

export type WorkbenchAgent = "general" | "knowledge";

const agents: Array<{
  key: WorkbenchAgent;
  label: string;
  description: string;
  icon: typeof Bot;
}> = [
  {
    key: "general",
    label: "通用写作助手",
    description: "从简短问答到多步骤写作任务",
    icon: Bot,
  },
  {
    key: "knowledge",
    label: "正文知识沉淀",
    description: "章节正文到候选知识卡",
    icon: Workflow,
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
          const active = agent.key === activeAgent;
          return (
            <button
              key={agent.key}
              type="button"
              aria-pressed={active}
              onClick={() => onAgentChange(agent.key)}
              className={cn(
                "rounded-[var(--tc-radius-control)] px-2.5 py-2 text-left text-sm transition-colors duration-150",
                active
                  ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                  : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
              )}
            >
              <span className="flex items-center gap-2 font-medium">
                <Icon className="size-3.5" />
                {agent.label}
              </span>
              <span className="mt-0.5 block truncate pl-[22px] text-[11px] text-[var(--tc-text-muted)]">
                {agent.description}
              </span>
            </button>
          );
        })}
      </nav>
    </>
  );
}
