"use client";

import Link from "next/link";
import { Bot, ChevronLeft, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { KnowledgeExtractionMonitorNav } from "@/components/agent-task-monitor/knowledge-extraction-monitor-nav";
import { TaskFlowGraph } from "@/components/agent-task-monitor/task-flow-graph";
import { Button } from "@/components/ui/button";
import { CompactPagination } from "@/components/ui/compact-pagination";
import {
  deleteAgentTask,
  getAgentTask,
  listAgentTasks,
  streamAgentTaskEvents,
} from "@/lib/api/agent-workbench";
import { formatBatchRunTitle } from "@/lib/agent-run-display";
import type {
  AgentBatchChapterProgress,
  AgentLLMCall,
  AgentRun,
  AgentRunNode,
  AgentRunStatus,
  AgentRunSummary,
} from "@/lib/types/agent-workbench";
import { cn } from "@/lib/utils";

type TaskStatusFilter = AgentRunStatus | "all" | "chapter" | "chapter_batch";

const statusLabel: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const statusFilters: Array<{ value: TaskStatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "running", label: "运行中" },
  { value: "failed", label: "失败" },
  { value: "completed", label: "已完成" },
  { value: "chapter", label: "单章任务" },
  { value: "chapter_batch", label: "批量任务" },
];
const TASK_PAGE_SIZE = 6;

export function TaskMonitorShell() {
  const [tasks, setTasks] = useState<AgentRunSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [currentTask, setCurrentTask] = useState<AgentRun | null>(null);
  const [statusFilter, setStatusFilter] = useState<TaskStatusFilter>("all");
  const [taskPage, setTaskPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingTaskId, setDeletingTaskId] = useState("");
  const selectedTaskIdRef = useRef("");

  const visibleTasks = useMemo(
    () => {
      if (statusFilter === "all") {
        return tasks;
      }
      if (statusFilter === "chapter") {
        return tasks.filter(task => task.scope_type !== "chapter_batch");
      }
      if (statusFilter === "chapter_batch") {
        return tasks.filter(task => task.scope_type === "chapter_batch");
      }
      return tasks.filter(task => task.status === statusFilter);
    },
    [statusFilter, tasks],
  );
  const taskPageCount = Math.max(1, Math.ceil(visibleTasks.length / TASK_PAGE_SIZE));
  const currentTaskPage = Math.min(taskPage, taskPageCount);
  const pagedTasks = useMemo(
    () =>
      visibleTasks.slice(
        (currentTaskPage - 1) * TASK_PAGE_SIZE,
        currentTaskPage * TASK_PAGE_SIZE,
      ),
    [currentTaskPage, visibleTasks],
  );

  const openTask = useCallback(async (taskId: string) => {
    setSelectedTaskId(taskId);
    selectedTaskIdRef.current = taskId;
    const response = await getAgentTask(taskId);
    setCurrentTask(response.run);
  }, []);

  const reload = useCallback(async () => {
    const response = await listAgentTasks();
    setTasks(response.runs);
    const selectedStillExists = response.runs.some(
      task => task.run_id === selectedTaskId,
    );
    if ((!selectedTaskId || !selectedStillExists) && response.runs[0]) {
      await openTask(response.runs[0].run_id);
    } else if (!selectedStillExists) {
      selectedTaskIdRef.current = "";
      setSelectedTaskId("");
      setCurrentTask(null);
    }
  }, [openTask, selectedTaskId]);

  const handleDeleteTask = useCallback(
    async (taskId: string) => {
      const target = tasks.find(task => task.run_id === taskId);
      const confirmed = window.confirm(
        `删除“${target ? taskTitle(target) : taskId}”这条任务记录？已入库知识卡不会回滚。`,
      );
      if (!confirmed) {
        return;
      }

      setDeletingTaskId(taskId);
      setError("");
      try {
        await deleteAgentTask(taskId);
        const nextTasks = tasks.filter(task => task.run_id !== taskId);
        setTasks(nextTasks);
        if (selectedTaskIdRef.current === taskId) {
          selectedTaskIdRef.current = "";
          setSelectedTaskId("");
          setCurrentTask(null);
          if (nextTasks[0]) {
            await openTask(nextTasks[0].run_id);
          }
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "任务删除失败");
      } finally {
        setDeletingTaskId("");
      }
    },
    [openTask, tasks],
  );

  useEffect(() => {
    let ignore = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await listAgentTasks();
        if (ignore) {
          return;
        }
        setTasks(response.runs);
        if (response.runs[0]) {
          await openTask(response.runs[0].run_id);
        }
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
    void load();
    return () => {
      ignore = true;
    };
  }, [openTask]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void reload();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [reload]);

  useEffect(() => {
    const controller = new AbortController();
    void streamAgentTaskEvents(event => {
      if (controller.signal.aborted) {
        return;
      }
      if (event.event_type === "task_deleted") {
        setTasks(current => current.filter(task => task.run_id !== event.run_id));
        if (selectedTaskIdRef.current === event.run_id) {
          selectedTaskIdRef.current = "";
          setSelectedTaskId("");
          setCurrentTask(null);
        }
        return;
      }
      if (event.run) {
        setTasks(current => upsertSummary(current, summaryFromRun(event.run!)));
        if (
          event.event_type === "run_started" ||
          event.event_type === "task_started" ||
          !selectedTaskIdRef.current ||
          selectedTaskIdRef.current === event.run.run_id
        ) {
          selectedTaskIdRef.current = event.run.run_id;
          setSelectedTaskId(event.run.run_id);
          setCurrentTask(event.run);
        }
      }
      if (event.node) {
        setCurrentTask(current =>
          current && current.run_id === event.run_id
            ? mergeNode(current, event.node!)
            : current,
        );
      }
      if (event.llm_call) {
        setCurrentTask(current =>
          current && current.run_id === event.run_id
            ? mergeLLMCall(current, event.llm_call!)
            : current,
        );
      }
      if (event.chapter_progress) {
        setCurrentTask(current =>
          current && current.run_id === event.run_id
            ? mergeChapterProgress(current, event.chapter_progress!)
            : current,
        );
      }
    }, controller.signal).catch(caught => {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "任务监控流连接失败");
      }
    });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto grid h-full min-h-0 max-w-[1440px] grid-rows-[auto_minmax(0,1fr)] gap-4 px-4 py-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <div className="xl:col-span-2">
          <KnowledgeExtractionMonitorNav />
        </div>
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2.5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">任务监控</p>
              <h1 className="text-lg font-semibold text-[var(--tc-text-primary)]">
                知识沉淀 Agent
              </h1>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="刷新任务列表"
              onClick={() => void reload()}
            >
              <RefreshCw className="size-4" />
            </Button>
          </div>

          <Link
            href="/task-monitor"
            className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
          >
            <ChevronLeft className="size-3" />
            返回任务入口
          </Link>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {statusFilters.map(filter => (
              <button
                key={filter.value}
                type="button"
                className={cn(
                    "rounded-[var(--tc-radius-pill)] border px-2.5 py-1 text-xs",
                  statusFilter === filter.value
                    ? "border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)]",
                )}
                onClick={() => {
                  setStatusFilter(filter.value);
                  setTaskPage(1);
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div className="mt-3 min-h-0 flex-1 overflow-hidden border-t border-[var(--tc-border-subtle)] pt-3">
            {loading ? (
              <p className="py-4 text-sm text-[var(--tc-text-muted)]">正在加载任务</p>
            ) : visibleTasks.length === 0 ? (
              <p className="py-4 text-sm text-[var(--tc-text-muted)]">暂无任务记录</p>
            ) : (
              <div className="grid gap-1">
                {pagedTasks.map(task => (
                <div
                  key={task.run_id}
                  className={cn(
                    "group grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-1 rounded-[var(--tc-radius-control)] pr-1 text-sm",
                    selectedTaskId === task.run_id
                      ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                      : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)]",
                  )}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 px-3 py-2 text-left"
                    onClick={() => void openTask(task.run_id)}
                  >
                    <span className="block truncate font-medium">
                      {taskTitle(task)}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
                      {scopeLabel(task)} · {statusLabel[task.status] ?? "未知状态"}
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={deletingTaskId !== ""}
                    aria-label={`删除${taskTitle(task)}任务记录`}
                    onClick={() => void handleDeleteTask(task.run_id)}
                    className="shrink-0 text-[var(--tc-text-muted)] opacity-70 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                ))}
              </div>
            )}
          </div>
          {!loading && visibleTasks.length > 0 ? (
            <CompactPagination
              className="mt-2"
              page={currentTaskPage}
              pageSize={TASK_PAGE_SIZE}
              total={visibleTasks.length}
              onPageChange={setTaskPage}
            />
          ) : null}
        </aside>

        <main className="flex min-h-0 flex-col gap-4">
          {error ? (
            <div className="rounded-[var(--tc-radius-card)] border border-red-700/70 bg-red-950/20 px-4 py-3 text-sm text-[var(--tc-text-primary)]">
              {error}
            </div>
          ) : null}

          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3">
            {currentTask ? (
              <div className="flex min-h-0 flex-1 flex-col gap-3">
                <div className="shrink-0 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs text-[var(--tc-text-muted)]">
                      {scopeLabel(summaryFromRun(currentTask))}
                    </p>
                    <h2 className="text-lg font-semibold text-[var(--tc-text-primary)]">
                      {taskTitle(summaryFromRun(currentTask))}
                    </h2>
                    <p className="mt-0.5 text-sm text-[var(--tc-text-muted)]">
                      {statusLabel[currentTask.status]} · {currentTask.metrics.candidate_total} 个候选
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href="/agent-workbench"
                      className="inline-flex h-8 items-center gap-1.5 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm font-medium text-[var(--tc-text-primary)]"
                    >
                      <Bot className="size-4" />
                      去智能体工作台
                    </Link>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={deletingTaskId !== ""}
                      onClick={() => void handleDeleteTask(currentTask.run_id)}
                    >
                      <Trash2 className="size-4" />
                      删除任务
                    </Button>
                  </div>
                </div>
                <TaskFlowGraph run={currentTask} />
                <TaskModelSummary run={currentTask} />
              </div>
            ) : (
              <div className="py-16 text-center text-sm text-[var(--tc-text-muted)]">
                请选择一个任务查看节点流转图。
              </div>
            )}
          </section>
        </main>
      </section>
    </AppShell>
  );
}

function TaskModelSummary({ run }: { run: AgentRun }) {
  const tokenTotal = run.llm_calls.reduce(
    (sum, call) => sum + (call.total_tokens ?? 0),
    0,
  );
  const knownCost = run.llm_calls.reduce(
    (sum, call) => sum + (call.cost_amount == null ? 0 : Number(call.cost_amount)),
    0,
  );
  const hasUnknownCost = run.llm_calls.some(call => call.cost_kind === "unavailable");
  return (
    <details className="shrink-0 border-t border-[var(--tc-border-subtle)] text-xs">
      <summary className="cursor-pointer px-1 py-2 text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]">
        模型调用统计
      </summary>
      <div className="grid grid-cols-2 border-t border-[var(--tc-border-subtle)] md:grid-cols-5">
        {[
          ["模型", run.model_display_name || run.model_name || "未记录"],
          ["调用次数", `${run.llm_calls.length} 次`],
          ["总 Token", tokenTotal ? tokenTotal.toLocaleString("zh-CN") : "未返回"],
          ["费用", knownCost ? `${knownCost.toFixed(4)} 元` : "未配置价格"],
          ["费用说明", hasUnknownCost ? "部分调用不可计算" : "已完成统计"],
        ].map(([label, value]) => (
          <div key={label} className="border-r border-[var(--tc-border-subtle)] px-3 py-2 last:border-r-0">
            <p className="text-[var(--tc-text-muted)]">{label}</p>
            <p className="mt-1 text-[var(--tc-text-primary)]">{value}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function taskTitle(task: AgentRunSummary): string {
  if (task.scope_type === "chapter_batch") {
    return formatBatchRunTitle(task);
  }
  return task.chapter_title || task.chapter_id || "未命名任务";
}

function scopeLabel(task: AgentRunSummary): string {
  if (task.scope_type === "chapter_batch") {
    return `批量任务 · 完成 ${task.completed_chapter_count}/${task.total_chapter_count}`;
  }
  return "单章任务";
}

function summaryFromRun(run: AgentRun): AgentRunSummary {
  return {
    run_id: run.run_id,
    agent_name: run.agent_name,
    status: run.status,
    scope_type: run.scope.scope_type,
    chapter_id: run.scope.chapter_id,
    chapter_title: run.scope.chapter_title,
    chapter_ids: run.scope.chapter_ids,
    chapter_titles: run.scope.chapter_titles,
    candidate_count: run.metrics.candidate_total,
    pending_count: run.metrics.pending_count,
    confirmed_count: run.metrics.confirmed_count,
    rejected_count: run.metrics.rejected_count,
    total_chapter_count: run.total_chapter_count,
    completed_chapter_count: run.completed_chapter_count,
    failed_chapter_count: run.failed_chapter_count,
    started_at: run.started_at,
    finished_at: run.finished_at,
  };
}

function upsertSummary(
  tasks: AgentRunSummary[],
  task: AgentRunSummary,
): AgentRunSummary[] {
  const without = tasks.filter(item => item.run_id !== task.run_id);
  return [task, ...without].sort((left, right) =>
    right.started_at.localeCompare(left.started_at),
  );
}

function mergeNode(run: AgentRun, node: AgentRunNode): AgentRun {
  return {
    ...run,
    nodes: run.nodes.some(item => item.node_name === node.node_name)
      ? run.nodes.map(item => (item.node_name === node.node_name ? node : item))
      : [...run.nodes, node],
  };
}

function mergeLLMCall(run: AgentRun, call: AgentLLMCall): AgentRun {
  return {
    ...run,
    llm_calls: run.llm_calls.some(item => item.call_id === call.call_id)
      ? run.llm_calls.map(item => (item.call_id === call.call_id ? call : item))
      : [...run.llm_calls, call],
  };
}

function mergeChapterProgress(
  run: AgentRun,
  progress: AgentBatchChapterProgress,
): AgentRun {
  const progressItems = run.batch_chapter_progress.some(
    item => item.chapter_id === progress.chapter_id,
  )
    ? run.batch_chapter_progress.map(item =>
        item.chapter_id === progress.chapter_id ? progress : item,
      )
    : [...run.batch_chapter_progress, progress];
  return {
    ...run,
    batch_chapter_progress: progressItems,
    completed_chapter_count: progressItems.filter(item => item.status === "success")
      .length,
    failed_chapter_count: progressItems.filter(item => item.status === "failed")
      .length,
  };
}
