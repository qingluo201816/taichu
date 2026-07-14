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
      <div className="px-2 py-2">
        <p className="text-xs text-[var(--tc-text-muted)]">智能体工作台</p>
        <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
          智能体
        </h1>
        <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
          当前开放 {agents.length} 个
        </p>
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
                "rounded-[var(--tc-radius-control)] px-3 py-2 text-left text-sm transition-colors",
                active
                  ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                  : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
              )}
            >
              <span className="flex items-center gap-2 font-semibold">
                <Icon className="size-4" />
                {agent.label}
              </span>
              <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
                {agent.description}
              </span>
            </button>
          );
        })}
      </nav>
    </>
  );
}
