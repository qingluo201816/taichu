"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  Database,
  LoaderCircle,
  Network,
  Play,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { RAGMonitorNav } from "@/components/agent-task-monitor/rag-monitor-nav";
import { Button } from "@/components/ui/button";
import {
  getVectorGraphStatus,
  startVectorGraphUpdate,
} from "@/lib/api/vector-graph";
import type {
  VectorGraphBuildStage,
  VectorGraphCollectionStatus,
  VectorGraphIndexState,
  VectorGraphIndexStatus,
} from "@/lib/types/vector-graph";
import {
  vectorGraphCollectionLabels,
  vectorGraphProgressPercent,
  vectorGraphStageLabels,
  vectorGraphStateLabels,
} from "@/lib/vector-graph-status";
import { cn } from "@/lib/utils";

const buildStages: Exclude<VectorGraphBuildStage, "failed">[] = [
  "planning",
  "extracting",
  "indexing",
  "completed",
];

export function VectorGraphMonitorShell() {
  const [status, setStatus] = useState<VectorGraphIndexStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await getVectorGraphStatus();
    setStatus(response);
  }, []);

  useEffect(() => {
    if (status?.state !== "building" && !starting) return;
    const timer = window.setInterval(() => {
      void load().catch(caught => setError(errorMessage(caught)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [load, starting, status?.state]);

  useEffect(() => {
    let ignore = false;
    async function initialLoad() {
      try {
        const response = await getVectorGraphStatus();
        if (!ignore) {
          setStatus(response);
          setError("");
        }
      } catch (caught) {
        if (!ignore) setError(errorMessage(caught));
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    void initialLoad();
    return () => {
      ignore = true;
    };
  }, []);

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRefreshing(false);
    }
  }

  async function startUpdate() {
    setStarting(true);
    setError("");
    setNotice("");
    try {
      const result = await startVectorGraphUpdate();
      setConfirming(false);
      setNotice(result.message);
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setStarting(false);
    }
  }

  const plan = status?.current_plan;
  const progress = status?.progress;
  const percent = progress
    ? progress.stage === "completed"
      ? 100
      : vectorGraphProgressPercent(
          progress.processed_sources,
          progress.total_sources,
      )
    : 0;
  const hasCompletedBuild = Boolean(status?.active_build);

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto h-full w-full max-w-[1200px] overflow-y-auto px-5 py-3">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/task-monitor"
              className="inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
            >
              <ChevronLeft className="size-3" />
              返回任务入口
            </Link>
            <span className="flex items-center gap-2">
              <Network className="size-4 text-[var(--tc-monitor-rag)]" />
              <h1 className="text-base font-semibold text-[var(--tc-text-primary)]">
                RAG 索引监控
              </h1>
            </span>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading || refreshing}
            onClick={() => void refresh()}
          >
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
            刷新状态
          </Button>
        </header>

        <div className="mt-3">
          <RAGMonitorNav active="monitor" />
        </div>

        {error ? (
          <div className="mt-4 rounded-[var(--tc-radius-control)] border border-red-700/70 bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            {error}
          </div>
        ) : null}

        <div className="mt-3 grid gap-3">
          <section className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-3">
            <div className="flex items-center justify-between gap-6">
              <div className="flex min-w-0 items-center gap-3">
                <StatusIcon state={status?.state} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-medium text-[var(--tc-text-primary)]">
                      索引同步与进度
                    </h2>
                    {status ? (
                      <span
                        className={cn("text-[11px]", stateTextClass(status.state))}
                      >
                        {status.is_current ? "快照一致" : "快照未就绪"}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-[var(--tc-text-secondary)]">
                    {loading
                      ? "正在读取索引状态"
                      : status
                        ? `${vectorGraphStateLabels[status.state]}：${status.message}`
                        : "状态未知"}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                disabled={
                  loading ||
                  starting ||
                  status?.state === "building" ||
                  status?.state === "unavailable"
                }
                onClick={() => setConfirming(true)}
              >
                {starting || status?.state === "building" ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Play className="size-4" />
                )}
                {status?.state === "building"
                  ? "正在同步索引"
                  : hasCompletedBuild
                    ? "同步最新内容"
                    : "开始正式建模"}
              </Button>
            </div>

            {confirming ? (
              <div className="mt-4 rounded-[var(--tc-radius-control)] border border-orange-500/35 bg-orange-500/5 p-3">
                <p className="text-sm font-medium text-[var(--tc-text-primary)]">
                  {hasCompletedBuild
                    ? "确认同步最新内容？"
                    : "确认开始首次正式建模？"}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
                  {hasCompletedBuild
                    ? "系统会扫描当前正文章节与知识卡并按来源比较内容，只为新增或变化的章节、知识卡重新抽取和写入索引，删除已不存在的来源，未变化来源直接跳过。过程可能产生 LLM 调用费用。"
                    : "系统会扫描当前全部正文章节与知识卡，首次抽取实体与关系并建立 Milvus 三类索引。过程可能持续较长时间并产生 LLM 调用费用。"}
                  Markdown 正文和 MongoDB 知识卡不会被修改。
                </p>
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={starting}
                    onClick={() => setConfirming(false)}
                  >
                    取消
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={starting}
                    onClick={() => void startUpdate()}
                  >
                    {starting ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <Play className="size-4" />
                    )}
                    {hasCompletedBuild ? "确认并同步" : "确认并建模"}
                  </Button>
                </div>
              </div>
            ) : null}

            {notice ? (
              <p className="mt-3 text-xs text-green-400">{notice}</p>
            ) : null}

            <div className="mt-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] p-2.5">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="text-[var(--tc-text-secondary)]">
                  {progress
                    ? vectorGraphStageLabels[progress.stage]
                    : hasCompletedBuild
                      ? "等待同步最新内容"
                      : "等待首次正式建模"}
                </span>
                <span className="tc-mono-font text-[var(--tc-text-primary)]">
                  {progress?.processed_sources.toLocaleString("zh-CN") ?? "0"} / {progress?.total_sources.toLocaleString("zh-CN") ?? "0"} 个来源 · {percent}%
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/30">
                <div
                  className="h-full rounded-full bg-[var(--tc-monitor-rag)] transition-[width] duration-200 motion-reduce:transition-none"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {buildStages.map(stage => (
                  <BuildStageItem
                    key={stage}
                    stage={stage}
                    currentStage={progress?.stage}
                  />
                ))}
              </div>
              {progress?.current_source_key ? (
                <p
                  title={progress.current_source_key}
                  className="mt-2 truncate text-[11px] text-[var(--tc-text-secondary)]"
                >
                  当前来源：{formatSourceKey(progress.current_source_key)}
                </p>
              ) : null}
              {progress?.stage === "completed" && status?.active_build ? (
                <p className="mt-2 text-[11px] text-[var(--tc-text-secondary)]">
                  本次结果：更新 {status.active_build.updated_source_count.toLocaleString("zh-CN")} 个、删除 {status.active_build.deleted_source_count.toLocaleString("zh-CN")} 个、跳过 {status.active_build.unchanged_source_count.toLocaleString("zh-CN")} 个来源。
                </p>
              ) : null}
              {progress ? (
                <p className="mt-2 text-[11px] text-[var(--tc-text-muted)]">
                  最近更新：{formatTime(progress.updated_at)}；页面每 2 秒自动刷新。
                </p>
              ) : (
                <p className="mt-2 text-[11px] text-[var(--tc-text-muted)]">
                  开始后可离开此页面；索引同步期间需保持太初后端运行。
                </p>
              )}
              {progress?.error_message && status?.state === "failed" ? (
                <div className="mt-2 rounded-[var(--tc-radius-control)] bg-red-950/20 p-2 text-sm text-[var(--tc-text-secondary)]">
                  <p className="text-xs font-medium text-red-400">失败原因</p>
                  <p className="mt-1 whitespace-pre-wrap">{progress.error_message}</p>
                </div>
              ) : null}
            </div>
          </section>

          <section>
            <div className="mb-1.5 flex items-center justify-between gap-3 px-1">
              <h2 className="text-sm font-medium text-[var(--tc-text-secondary)]">
                当前同步检查范围
              </h2>
              {plan ? (
                <span
                  title={plan.snapshot_sha256}
                  className="tc-mono-font max-w-60 truncate text-[11px] text-[var(--tc-text-muted)]"
                >
                  快照 {plan.snapshot_sha256.slice(0, 12)}
                </span>
              ) : null}
            </div>
            <div className="grid grid-cols-5 gap-1.5">
              <Metric label="正文文件" value={formatCount(plan?.manuscript_count)} />
              <Metric label="正文片段" value={formatCount(plan?.manuscript_chunk_count)} />
              <Metric label="知识卡" value={formatCount(plan?.knowledge_card_count)} />
              <Metric label="检查总量" value={formatCount(plan?.document_count)} />
              <Metric label="内容字符" value={formatCount(plan?.total_content_chars)} />
            </div>
          </section>

          <section>
            <h2 className="mb-1.5 px-1 text-sm font-medium text-[var(--tc-text-secondary)]">
              Milvus 三类集合
            </h2>
            <div className="grid grid-cols-3 gap-1.5">
              {status?.collections.length ? (
                status.collections.map(collection => (
                  <CollectionRow key={collection.role} collection={collection} />
                ))
              ) : (
                <p className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-3 text-sm text-[var(--tc-text-muted)]">
                  {loading ? "正在读取集合状态" : "暂时无法读取集合状态"}
                </p>
              )}
            </div>
          </section>
        </div>
      </section>
    </AppShell>
  );
}

function BuildStageItem({
  stage,
  currentStage,
}: {
  stage: Exclude<VectorGraphBuildStage, "failed">;
  currentStage?: VectorGraphBuildStage;
}) {
  const stageIndex = buildStages.indexOf(stage);
  const currentIndex =
    currentStage && currentStage !== "failed"
      ? buildStages.indexOf(currentStage)
      : -1;
  const completed = currentStage === "completed" || stageIndex < currentIndex;
  const current = stage === currentStage;

  return (
    <div
      className={cn(
        "rounded-md border px-2 py-1.5 text-[11px]",
        completed && "border-green-500/30 bg-green-500/5 text-green-400",
        current &&
          "border-[var(--tc-monitor-rag)]/40 bg-[var(--tc-monitor-rag)]/5 text-[var(--tc-text-primary)]",
        !completed &&
          !current &&
          "border-[var(--tc-workspace-border-weak)] text-[var(--tc-text-muted)]",
      )}
    >
      <span className="tc-mono-font mr-1.5">{stageIndex + 1}</span>
      {vectorGraphStageLabels[stage]}
    </div>
  );
}

function StatusIcon({ state }: { state?: VectorGraphIndexState }) {
  if (state === "ready") {
    return (
      <span className="flex size-8 items-center justify-center rounded-full bg-green-500/10 text-green-400">
        <CheckCircle2 className="size-4" />
      </span>
    );
  }
  if (state === "failed" || state === "unavailable") {
    return (
      <span className="flex size-8 items-center justify-center rounded-full bg-red-500/10 text-red-400">
        <AlertCircle className="size-4" />
      </span>
    );
  }
  return (
    <span className="flex size-8 items-center justify-center rounded-full bg-blue-500/10 text-blue-400">
      <CircleDot className="size-4" />
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-2">
      <p className="text-[11px] text-[var(--tc-text-muted)]">{label}</p>
      <p className="tc-mono-font mt-0.5 text-base font-medium text-[var(--tc-text-primary)]">
        {value}
      </p>
    </div>
  );
}

function CollectionRow({
  collection,
}: {
  collection: VectorGraphCollectionStatus;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-2">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-cyan-500/10 text-cyan-400">
          <Database className="size-3.5" />
        </span>
        <div className="min-w-0">
          <p className="text-sm text-[var(--tc-text-primary)]">
            {vectorGraphCollectionLabels[collection.role] ?? "其他集合"}
          </p>
          <p className="tc-mono-font truncate text-[11px] text-[var(--tc-text-muted)]">
            集合标识：{collection.name}
          </p>
        </div>
      </div>
      <div className="shrink-0 text-right">
        <p className={cn("text-xs", collection.exists ? "text-green-400" : "text-[var(--tc-text-muted)]")}>
          {collection.exists ? "已创建" : "未创建"}
        </p>
        <p className="tc-mono-font mt-0.5 text-[11px] text-[var(--tc-text-muted)]">
          {collection.row_count === null
            ? "暂无数量"
            : `${collection.row_count.toLocaleString("zh-CN")} 条`}
        </p>
      </div>
    </div>
  );
}

function stateTextClass(state: VectorGraphIndexState): string {
  if (state === "ready") return "text-green-400";
  if (state === "building") return "text-blue-400";
  if (state === "failed" || state === "unavailable") return "text-red-400";
  if (state === "stale" || state === "incomplete") return "text-orange-400";
  return "text-[var(--tc-text-muted)]";
}

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : value.toLocaleString("zh-CN");
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatSourceKey(value: string): string {
  const separator = value.indexOf(":");
  if (separator < 0) return value;
  const sourceType = value.slice(0, separator);
  const sourceId = value.slice(separator + 1);
  if (sourceType === "manuscript_chunk") return `正文章节 · ${sourceId}`;
  if (sourceType === "knowledge_card") return `知识卡 · ${sourceId}`;
  return value;
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error
    ? caught.message
    : "RAG 索引状态加载失败，请确认后端服务是否可用。";
}
