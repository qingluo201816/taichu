import { Suspense } from "react";

import { GeneralAgentEvaluationShell } from "@/components/agent-task-monitor/general-agent-evaluation-shell";

export default function GeneralAgentEvaluationPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#202020] px-8 py-10 text-[#f4f4f4]">
          <p className="text-sm text-[#a7a7a7]">正在加载评测工作台…</p>
        </main>
      }
    >
      <GeneralAgentEvaluationShell />
    </Suspense>
  );
}
