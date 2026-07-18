"use client";

import {
  Activity,
  Bot,
  ChevronLeft,
  CircleDot,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { GeneralAgentFlowGraph } from "@/components/agent-task-monitor/general-agent-flow-graph";
import { GeneralAgentMonitorNav } from "@/components/agent-task-monitor/general-agent-monitor-nav";
import { Button } from "@/components/ui/button";
import {
  getGeneralAgentRun,
  listGeneralAgentRuns,
  listGeneralAgentTraces,
} from "@/lib/api/general-agent";
import {
  generalCapabilityLabel,
  generalNodeErrorMessage,
  generalNodeStatusLabel,
  generalRunProgressSummary,
  generalRunStatusLabels,
  isGeneralAgentRunActive,
} from "@/lib/general-agent-display";
import {
  generalAgentPlanRevisions,
  orchestratorTraces,
  tracesForGeneralAgentNode,
} from "@/lib/general-agent-monitor";
import type {
  GeneralAgentInvocationTrace,
  GeneralAgentNodeRun,
  GeneralAgentRun,
  GeneralAgentRunStatus,
  GeneralAgentRunSummary,
} from "@/lib/types/general-agent";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "active" | "waiting_human" | "completed" | "failed";

const filters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "active", label: "运行中" },
  { value: "waiting_human", label: "等作者" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "异常" },
];

export function GeneralAgentMonitorShell() {
  const [runs, setRuns] = useState<GeneralAgentRunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<GeneralAgentRun | null>(null);
  const [traces, setTraces] = useState<GeneralAgentInvocationTrace[]>([]);
  const [traceTotal, setTraceTotal] = useState(0);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [selectedRevision, setSelectedRevision] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const selectedRunRef = useRef("");

  const openRun = useCallback(async (runId: string) => {
    const [detail, traceResponse] = await Promise.all([
      getGeneralAgentRun(runId),
      listGeneralAgentTraces(runId),
    ]);
    setCurrentRun(detail.run);
    setTraces(traceResponse.traces);
    setTraceTotal(traceResponse.total);
    setSelectedRunId(runId);
    selectedRunRef.current = runId;
    setSelectedRevision(current =>
      generalAgentPlanRevisions(detail.run.node_runs).includes(current)
        ? current
        : detail.run.plan_revision,
    );
    setSelectedNodeId(current => {
      const currentPlanNodes = detail.run.node_runs.filter(
        node => node.plan_revision === detail.run.plan_revision,
      );
      return detail.run.node_runs.some(node => node.node_id === current)
        ? current
        : (currentPlanNodes[0]?.node_id ?? "");
    });
  }, []);

  const reload = useCallback(async () => {
    const response = await listGeneralAgentRuns({ pageSize: 100 });
    setRuns(response.runs);
    const preferred = selectedRunRef.current;
    if (preferred && response.runs.some(run => run.run_id === preferred)) {
      await openRun(preferred);
    } else if (response.runs[0]) {
      await openRun(response.runs[0].run_id);
    } else {
      setCurrentRun(null);
      setTraces([]);
      setTraceTotal(0);
      setSelectedRunId("");
      selectedRunRef.current = "";
    }
  }, [openRun]);

  useEffect(() => {
    let ignore = false;
    async function initialLoad() {
      try {
        await reload();
        if (!ignore) {
          setError("");
        }
      } catch (caught) {
        if (!ignore) {
          setError(errorMessage(caught));
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }
    void initialLoad();
    return () => {
      ignore = true;
    };
  }, [reload]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void reload().catch(caught => setError(errorMessage(caught)));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const visibleRuns = useMemo(
    () => runs.filter(run => matchesFilter(run.status, statusFilter)),
    [runs, statusFilter],
  );
  const revisions = useMemo(
    () => (currentRun ? generalAgentPlanRevisions(currentRun.node_runs) : []),
    [currentRun],
  );
  const visibleNodes = useMemo(
    () =>
      currentRun?.node_runs.filter(node => node.plan_revision === selectedRevision) ?? [],
    [currentRun, selectedRevision],
  );
  const selectedNode =
    visibleNodes.find(node => node.node_id === selectedNodeId) ?? visibleNodes[0] ?? null;
  const nodeTraces = selectedNode ? tracesForGeneralAgentNode(selectedNode, traces) : [];
  const plannerTraces = orchestratorTraces(traces);

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto grid h-full min-h-0 max-w-[1540px] grid-rows-[auto_minmax(0,1fr)] gap-4 px-4 py-4 xl:grid-cols-[286px_minmax(0,1fr)]">
        <div className="xl:col-span-2">
          <GeneralAgentMonitorNav active="monitor" />
        </div>
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">任务监控</p>
              <h1 className="text-lg font-semibold text-[var(--tc-text-primary)]">
                通用写作助手
              </h1>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="刷新通用写作助手任务"
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
            {filters.map(filter => (
              <button
                key={filter.value}
                type="button"
                className={cn(
                  "rounded-[var(--tc-radius-pill)] border px-2.5 py-1 text-xs",
                  statusFilter === filter.value
                    ? "border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                    : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)]",
                )}
                onClick={() => setStatusFilter(filter.value)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="mt-3 min-h-0 flex-1 overflow-y-auto border-t border-[var(--tc-border-subtle)] pt-3">
            {loading ? (
              <p className="py-4 text-sm text-[var(--tc-text-muted)]">正在读取任务</p>
            ) : visibleRuns.length === 0 ? (
              <p className="py-4 text-sm text-[var(--tc-text-muted)]">暂无符合条件的任务</p>
            ) : (
              <div className="grid gap-1">
                {visibleRuns.map(run => (
                  <button
                    key={run.run_id}
                    type="button"
                    className={cn(
                      "rounded-[var(--tc-radius-control)] px-3 py-2 text-left",
                      selectedRunId === run.run_id
                        ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                        : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)]",
                    )}
                    onClick={() => void openRun(run.run_id)}
                  >
                    <span className="line-clamp-2 text-sm font-medium">{run.user_goal}</span>
                    <span className="mt-1 flex items-center justify-between gap-2 text-xs text-[var(--tc-text-muted)]">
                      <span>{generalRunStatusLabels[run.status]}</span>
                      <span>
                        {isGeneralAgentRunActive(run.status)
                          ? "正在内部处理"
                          : `${run.completed_node_count}/${run.total_node_count} 节点`}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 flex-col gap-3 overflow-hidden">
          {error ? (
            <div className="shrink-0 rounded-[var(--tc-radius-control)] border border-red-700/70 bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">
              {error}
            </div>
          ) : null}
          {currentRun ? (
            <>
              <RunHeader run={currentRun} traceTotal={traceTotal} />
              <section className="grid min-h-0 flex-1 gap-3 overflow-hidden 2xl:grid-cols-[minmax(0,1fr)_370px]">
                <div className="flex min-h-0 flex-col rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1.5">
                      {revisions.length === 0 ? (
                        <span className="text-xs text-[var(--tc-text-muted)]">直接回答</span>
                      ) : (
                        revisions.map(revision => (
                          <button
                            key={revision}
                            type="button"
                            className={cn(
                              "rounded-[var(--tc-radius-pill)] border px-2.5 py-1 text-xs",
                              selectedRevision === revision
                                ? "border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                                : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)]",
                            )}
                            onClick={() => setSelectedRevision(revision)}
                          >
                            {revision === currentRun.plan_revision ? "当前计划" : "历史计划"} · 修订 {revision}
                          </button>
                        ))
                      )}
                    </div>
                    <span className="text-xs text-[var(--tc-text-muted)]">
                      重规划 {currentRun.replan_count} 次
                    </span>
                  </div>
                  <GeneralAgentFlowGraph
                    nodes={visibleNodes}
                    runStatus={currentRun.status}
                    selectedNodeId={selectedNode?.node_id ?? ""}
                    onSelectNode={setSelectedNodeId}
                  />
                </div>
                <div className="min-h-0 overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3">
                  {selectedNode ? (
                    <NodeDetail
                      node={selectedNode}
                      runStatus={currentRun.status}
                      traces={nodeTraces}
                    />
                  ) : (
                    <DirectRunDetail run={currentRun} traces={plannerTraces} />
                  )}
                </div>
              </section>
              <LifecycleStrip run={currentRun} plannerTraces={plannerTraces} />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] text-sm text-[var(--tc-text-muted)]">
              暂无通用写作助手运行记录。
            </div>
          )}
        </main>
      </section>
    </AppShell>
  );
}

function RunHeader({ run, traceTotal }: { run: GeneralAgentRun; traceTotal: number }) {
  return (
    <section className="shrink-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-xs text-[var(--tc-text-muted)]">
            <CircleDot className={cn("size-3", isGeneralAgentRunActive(run.status) && "animate-pulse text-blue-400")} />
            {generalRunStatusLabels[run.status]}
          </p>
          <h2 className="mt-1 line-clamp-2 text-lg font-semibold text-[var(--tc-text-primary)]">
            {run.user_goal}
          </h2>
          <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
            {generalRunProgressSummary(run)} · {traceTotal} 条脱敏调用记录 · 更新于 {formatTime(run.updated_at)}
          </p>
        </div>
        <Link
          href="/agent-workbench"
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm font-medium text-[var(--tc-text-primary)]"
        >
          <Bot className="size-4" />
          返回工作台
        </Link>
      </div>
    </section>
  );
}

function NodeDetail({
  node,
  runStatus,
  traces,
}: {
  node: GeneralAgentNodeRun;
  runStatus: GeneralAgentRunStatus;
  traces: GeneralAgentInvocationTrace[];
}) {
  const visibleErrorMessage = generalNodeErrorMessage(
    node.error_message,
    runStatus,
  );
  return (
    <div>
      <p className="text-xs text-[var(--tc-text-muted)]">节点详情</p>
      <h3 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">
        {generalCapabilityLabel(node.capability_name)}
      </h3>
      <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-border-subtle)] text-xs">
        <Metric label="节点类型" value={node.kind === "tool" ? "工具" : "专业智能体"} />
        <Metric
          label="节点状态"
          value={generalNodeStatusLabel(node.status, runStatus)}
        />
        <Metric label="执行耗时" value={durationLabel(node.duration_ms)} />
        <Metric label="来源数量" value={`${node.source_refs.length} 个`} />
      </div>
      <DetailBlock title="任务目标" text={node.objective} />
      <DetailBlock
        title="依赖节点"
        text={node.dependencies.length > 0 ? node.dependencies.join("、") : "无上游依赖"}
        technical
      />
      {node.authorization_approved || node.authorization_resource_scopes.length > 0 ? (
        <div className="mt-3 rounded-[var(--tc-radius-control)] border border-amber-700/50 bg-amber-950/15 p-3 text-xs text-[var(--tc-text-secondary)]">
          <p className="flex items-center gap-1.5 font-medium text-amber-200">
            <ShieldCheck className="size-4" />
            写入授权
          </p>
          <p className="mt-1">{node.authorization_approved ? "作者已授权该节点的确定输入。" : "该节点正在等待作者授权。"}</p>
        </div>
      ) : null}
      {visibleErrorMessage ? (
        <div className="mt-3 rounded-[var(--tc-radius-control)] border border-red-700/60 bg-red-950/20 p-3 text-xs text-red-100">
          <p className="font-medium">节点异常</p>
          <p className="mt-1 whitespace-pre-wrap">{visibleErrorMessage}</p>
          {node.error_type ? <p className="mt-1 text-red-200/65">技术错误类型：{node.error_type}</p> : null}
        </div>
      ) : null}
      <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3">
        <h4 className="text-sm font-medium text-[var(--tc-text-primary)]">节点内调用</h4>
        <p className="mt-0.5 text-xs text-[var(--tc-text-muted)]">
          工具和模型调用折叠在所属节点下，只展示脱敏技术记录。
        </p>
        <TraceList traces={traces} />
      </div>
    </div>
  );
}

function DirectRunDetail({
  run,
  traces,
}: {
  run: GeneralAgentRun;
  traces: GeneralAgentInvocationTrace[];
}) {
  return (
    <div>
      <p className="text-xs text-[var(--tc-text-muted)]">直接回答任务</p>
      <h3 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">没有创建能力节点</h3>
      <DetailBlock title="计划依据" text={run.plan?.rationale || "未记录计划依据"} />
      <DetailBlock title="最终结果" text={run.final_answer || "结果尚未生成"} />
      <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3">
        <h4 className="text-sm font-medium text-[var(--tc-text-primary)]">高层编排调用</h4>
        <TraceList traces={traces} />
      </div>
    </div>
  );
}

function TraceList({ traces }: { traces: GeneralAgentInvocationTrace[] }) {
  if (traces.length === 0) {
    return <p className="mt-2 text-xs text-[var(--tc-text-muted)]">暂无可展示的调用记录。</p>;
  }
  return (
    <div className="mt-2 grid gap-1.5">
      {traces.map(trace => (
        <details
          key={trace.trace_id}
          className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2.5 py-2 text-xs"
        >
          <summary className="cursor-pointer list-none text-[var(--tc-text-primary)]">
            <span className="flex items-center justify-between gap-2">
              <span className="truncate">
                {invocationTypeLabel(trace.capability_type)} · {generalCapabilityLabel(trace.capability_name)}
              </span>
              <span className={trace.status === "completed" ? "text-emerald-300" : "text-red-300"}>
                {invocationStatusLabel(trace.status)}
              </span>
            </span>
          </summary>
          <dl className="mt-2 grid gap-1 border-t border-[var(--tc-border-subtle)] pt-2 text-[var(--tc-text-muted)]">
            <div className="flex justify-between gap-2"><dt>耗时</dt><dd>{durationLabel(trace.duration_ms)}</dd></div>
            <div className="flex justify-between gap-2"><dt>输入/输出字符</dt><dd>{trace.input_char_count}/{trace.output_char_count}</dd></div>
            {trace.input_tokens != null || trace.output_tokens != null ? (
              <div className="flex justify-between gap-2"><dt>输入/输出 Token</dt><dd>{trace.input_tokens ?? 0}/{trace.output_tokens ?? 0}</dd></div>
            ) : null}
            {trace.model_role ? <div className="flex justify-between gap-2"><dt>模型角色</dt><dd>{trace.model_role}</dd></div> : null}
            {trace.model_id ? <div className="flex justify-between gap-2"><dt>模型标识</dt><dd>{trace.model_id}</dd></div> : null}
            {trace.authorization_reference ? <div className="flex justify-between gap-2"><dt>授权记录</dt><dd>已绑定</dd></div> : null}
            {trace.error_message ? <div><dt className="text-red-300">错误说明</dt><dd className="mt-0.5 whitespace-pre-wrap text-red-100">{trace.error_message}</dd></div> : null}
          </dl>
        </details>
      ))}
    </div>
  );
}

function LifecycleStrip({
  run,
  plannerTraces,
}: {
  run: GeneralAgentRun;
  plannerTraces: GeneralAgentInvocationTrace[];
}) {
  return (
    <details className="shrink-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-3 text-xs">
      <summary className="cursor-pointer py-2.5 text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]">
        生命周期与高层编排 · {run.lifecycle_events.length} 次状态变化 · {plannerTraces.length} 次模型调用
      </summary>
      <div className="grid max-h-52 gap-3 overflow-y-auto border-t border-[var(--tc-border-subtle)] py-3 lg:grid-cols-2">
        <div className="grid gap-1.5">
          {run.lifecycle_events.map((event, index) => (
            <div key={`${event.created_at}-${index}`} className="flex gap-2 text-[var(--tc-text-secondary)]">
              <Activity className="mt-0.5 size-3 shrink-0 text-[var(--tc-text-muted)]" />
              <span><strong className="font-medium text-[var(--tc-text-primary)]">{generalRunStatusLabels[event.status]}</strong> · {event.reason || "状态已更新"} · {formatTime(event.created_at)}</span>
            </div>
          ))}
        </div>
        <TraceList traces={plannerTraces} />
      </div>
    </details>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--tc-surface-muted)] px-2.5 py-2">
      <p className="text-[var(--tc-text-muted)]">{label}</p>
      <p className="mt-0.5 text-[var(--tc-text-primary)]">{value}</p>
    </div>
  );
}

function DetailBlock({
  title,
  text,
  technical = false,
}: {
  title: string;
  text: string;
  technical?: boolean;
}) {
  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-[var(--tc-text-primary)]">{title}</p>
      <p className={cn("mt-1 whitespace-pre-wrap text-xs leading-5 text-[var(--tc-text-secondary)]", technical && "font-mono")}>
        {text}
      </p>
    </div>
  );
}

function matchesFilter(status: GeneralAgentRunStatus, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "active") return isGeneralAgentRunActive(status);
  if (filter === "failed") return ["failed", "cancelled", "timeout"].includes(status);
  return status === filter;
}

function invocationTypeLabel(type: GeneralAgentInvocationTrace["capability_type"]): string {
  return { tool: "工具", subagent: "专业智能体", llm: "模型" }[type];
}

function invocationStatusLabel(status: GeneralAgentInvocationTrace["status"]): string {
  return { completed: "成功", failed: "失败", timed_out: "超时" }[status];
}

function durationLabel(durationMs: number): string {
  return durationMs < 1_000 ? `${durationMs} 毫秒` : `${(durationMs / 1_000).toFixed(1)} 秒`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "通用写作助手任务监控加载失败";
}
