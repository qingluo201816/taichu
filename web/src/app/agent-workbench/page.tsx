import { Suspense } from "react";

import { AgentWorkbenchShell } from "@/components/agent-workbench/agent-workbench-shell";

export default function AgentWorkbenchPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[var(--tc-canvas)] p-8 text-sm text-[var(--tc-text-muted)]">
          正在加载智能体工作台…
        </main>
      }
    >
      <AgentWorkbenchShell />
    </Suspense>
  );
}
