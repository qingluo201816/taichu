"use client";

import Link from "next/link";
import { Activity, Bot, ChevronRight, RefreshCw, Scale } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { listAgentTasks } from "@/lib/api/agent-workbench";
import type { AgentRunSummary } from "@/lib/types/agent-workbench";

export function TaskMonitorOverview() {
  const [tasks, setTasks] = useState<AgentRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const runningCount = useMemo(
    () => tasks.filter(task => task.status === "running").length,
    [tasks],
  );

  async function load() {
    try {
      const response = await listAgentTasks();
      setTasks(response.runs);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "任务监控加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    async function loadFromEffect() {
      try {
        const response = await listAgentTasks();
        if (ignore) {
          return;
        }
        setTasks(response.runs);
        setError("");
      } catch (caught) {
        if (!ignore) {
          setError(caught instanceof Error ? caught.message : "任务监控加载失败");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    void loadFromEffect();
    const timer = window.setInterval(() => {
      void loadFromEffect();
    }, 3000);
    return () => {
      ignore = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <AppShell activePath="/task-monitor">
      <section className="mx-auto max-w-[760px] px-5 py-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-xs text-[var(--tc-text-muted)]">任务监控</p>
            <h1 className="text-lg font-semibold text-[var(--tc-text-primary)]">
              智能体任务入口
            </h1>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="刷新任务概览"
            onClick={() => void load()}
          >
            <RefreshCw className="size-4" />
          </Button>
        </div>

        {error ? (
          <div className="mb-3 rounded-[var(--tc-radius-control)] border border-red-700/70 bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            {error}
          </div>
        ) : null}

        <div className="grid gap-2">
          <Link
            href="/task-monitor/knowledge-extraction"
            className="flex items-center justify-between gap-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-3 py-3 text-sm text-[var(--tc-text-primary)] hover:bg-[var(--tc-surface-muted)]"
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)]">
                <Bot className="size-4" />
              </span>
              <span className="min-w-0">
                <span className="block font-medium">知识沉淀智能体运行监控</span>
                <span className="mt-0.5 flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
                  <Activity className="size-3" />
                  {loading
                    ? "正在读取任务"
                    : `共 ${tasks.length} 个任务，${runningCount > 0 ? `${runningCount} 个运行中` : "当前无运行中任务"}`}
                </span>
              </span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-[var(--tc-text-muted)]" />
          </Link>

          <Link
            href="/task-monitor/knowledge-extraction/evaluation"
            className="flex items-center justify-between gap-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-3 py-3 text-sm text-[var(--tc-text-primary)] hover:bg-[var(--tc-surface-muted)]"
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)]">
                <Scale className="size-4" />
              </span>
              <span className="min-w-0">
                <span className="block font-medium">知识沉淀智能体效果评估</span>
                <span className="mt-0.5 block text-xs text-[var(--tc-text-muted)]">
                  对比历史任务输出、期望知识卡与差异明细
                </span>
              </span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-[var(--tc-text-muted)]" />
          </Link>
        </div>
      </section>
    </AppShell>
  );
}
