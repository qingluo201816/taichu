"use client";

import Link from "next/link";
import {
  AlertCircle,
  ArchiveX,
  CheckCircle2,
  ChevronLeft,
  CircleDashed,
  Clock3,
  FileDiff,
  LoaderCircle,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { KnowledgeExtractionMonitorNav } from "@/components/agent-task-monitor/knowledge-extraction-monitor-nav";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  confirmKnowledgeEvaluation,
  createKnowledgeEvaluation,
  getKnowledgeEvaluation,
  getKnowledgeEvaluationJudgeCall,
  listEligibleEvaluationRuns,
  listEvaluationDatasets,
  listKnowledgeEvaluationComparisons,
  listKnowledgeEvaluations,
  previewKnowledgeEvaluation,
  rejectKnowledgeEvaluation,
  retryKnowledgeEvaluation,
} from "@/lib/api/agent-evaluation";
import {
  canRetryEvaluation,
  comparisonMatchesIssue,
  evaluationErrorMessage,
  evaluationModelLabel,
  evaluationProgressText,
  evaluationStatusLabels,
  evaluationTaskTitle,
  formatEvaluationScore,
  isTerminalEvaluation,
  issueTypeLabels,
  knowledgeTypeLabels,
  metricValue,
  noticeMessage,
  previewIndependenceLabel,
  qualityStateLabel,
  selectableEvaluationRun,
  shortChecksum,
  shouldPollEvaluation,
  toggleEvaluationRunSelection,
  visibleEvaluationRuns,
} from "@/lib/agent-evaluation/evaluation-view-model";
import type {
  CreateKnowledgeEvaluationRequest,
  EligibleEvaluationRun,
  EvaluationDatasetSummary,
  EvaluationIssueType,
  EvaluationJudgeCall,
  EvaluationQualityState,
  KnowledgeEvaluation,
  KnowledgeEvaluationComparison,
  KnowledgeEvaluationPreview,
} from "@/lib/types/agent-evaluation";
import { cn } from "@/lib/utils";

const METRIC_PROFILE_ID = "knowledge_extraction_balanced";

const issueFilters: Array<{
  value: EvaluationIssueType | "all";
  label: string;
}> = [
  { value: "all", label: "全部" },
  { value: "missing_candidate", label: "漏提取" },
  { value: "extra_candidate", label: "多提取" },
  { value: "field_difference", label: "字段不同" },
  { value: "semantic_issue", label: "语义问题" },
  { value: "evidence_issue", label: "证据问题" },
  { value: "judge_disagreement", label: "裁判意见不一致" },
];

export function KnowledgeEvaluationShell() {
  const [datasets, setDatasets] = useState<EvaluationDatasetSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [eligibleRuns, setEligibleRuns] = useState<EligibleEvaluationRun[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [showDiagnostic, setShowDiagnostic] = useState(false);
  const [judgeEnabled, setJudgeEnabled] = useState(true);
  const [preview, setPreview] = useState<KnowledgeEvaluationPreview | null>(null);
  const [evaluations, setEvaluations] = useState<KnowledgeEvaluation[]>([]);
  const [currentEvaluation, setCurrentEvaluation] =
    useState<KnowledgeEvaluation | null>(null);
  const [comparisons, setComparisons] = useState<
    KnowledgeEvaluationComparison[]
  >([]);
  const [comparisonTotal, setComparisonTotal] = useState(0);
  const [comparisonPage, setComparisonPage] = useState(1);
  const [issueFilter, setIssueFilter] = useState<EvaluationIssueType | "all">(
    "all",
  );
  const [judgeCalls, setJudgeCalls] = useState<
    Record<string, EvaluationJudgeCall>
  >({});

  const [initialLoading, setInitialLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [judgeCallLoadingId, setJudgeCallLoadingId] = useState("");

  const [loadError, setLoadError] = useState("");
  const [runsError, setRunsError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [actionError, setActionError] = useState("");
  const [comparisonError, setComparisonError] = useState("");
  const [pollError, setPollError] = useState("");

  const loadComparisons = useCallback(
    async (evaluationId: string, page = 1, append = false) => {
      setComparisonLoading(true);
      setComparisonError("");
      try {
        const response = await listKnowledgeEvaluationComparisons(evaluationId, {
          page,
          pageSize: 50,
        });
        setComparisons(current =>
          append ? [...current, ...response.comparisons] : response.comparisons,
        );
        setComparisonTotal(response.total);
        setComparisonPage(response.page);
      } catch (caught) {
        setComparisonError(
          caught instanceof Error ? caught.message : "差异明细加载失败，请重试",
        );
      } finally {
        setComparisonLoading(false);
      }
    },
    [],
  );

  const loadWorkspace = useCallback(async () => {
    setInitialLoading(true);
    setLoadError("");
    setPreview(null);
    setPreviewError("");
    try {
      const [datasetResponse, historyResponse] = await Promise.all([
        listEvaluationDatasets(),
        listKnowledgeEvaluations(),
      ]);
      setDatasets(datasetResponse.datasets);
      setSelectedDatasetId(current =>
        datasetResponse.datasets.some(item => item.dataset_id === current)
          ? current
          : datasetResponse.datasets[0]?.dataset_id ?? "",
      );
      setEvaluations(historyResponse.evaluations);
      const latest = historyResponse.evaluations[0];
      if (latest) {
        const detail = await getKnowledgeEvaluation(latest.evaluation_id);
        setCurrentEvaluation(detail.evaluation);
        if (isTerminalEvaluation(detail.evaluation.status)) {
          await loadComparisons(detail.evaluation.evaluation_id);
        }
      } else {
        setCurrentEvaluation(null);
        setComparisons([]);
        setComparisonTotal(0);
      }
    } catch (caught) {
      setLoadError(
        caught instanceof Error
          ? caught.message
          : "评估资料加载失败，请重试",
      );
    } finally {
      setInitialLoading(false);
    }
  }, [loadComparisons]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadWorkspace();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadWorkspace]);

  useEffect(() => {
    if (!selectedDatasetId) {
      return;
    }
    let ignore = false;
    async function loadRuns() {
      setRunsLoading(true);
      setRunsError("");
      try {
        const response = await listEligibleEvaluationRuns(selectedDatasetId);
        if (!ignore) {
          setEligibleRuns(response.runs);
          setPreview(null);
          setSelectedRunIds(current =>
            current.filter(runId =>
              response.runs.some(
                run => run.run_id === runId && selectableEvaluationRun(run),
              ),
            ),
          );
        }
      } catch (caught) {
        if (!ignore) {
          setRunsError(
            caught instanceof Error
              ? caught.message
              : "历史任务加载失败，请重试",
          );
          setEligibleRuns([]);
        }
      } finally {
        if (!ignore) setRunsLoading(false);
      }
    }
    void loadRuns();
    return () => {
      ignore = true;
    };
  }, [selectedDatasetId]);

  const polling = shouldPollEvaluation(currentEvaluation);
  const currentEvaluationId = currentEvaluation?.evaluation_id ?? "";

  const refreshEvaluation = useCallback(
    async (evaluationId: string, showConnectionError = true) => {
      try {
        const response = await getKnowledgeEvaluation(evaluationId);
        setCurrentEvaluation(response.evaluation);
        setPollError("");
        if (isTerminalEvaluation(response.evaluation.status)) {
          await loadComparisons(evaluationId);
          const history = await listKnowledgeEvaluations();
          setEvaluations(history.evaluations);
        }
      } catch (caught) {
        if (showConnectionError) {
          setPollError(
            caught instanceof Error
              ? caught.message
              : "进度暂时无法更新",
          );
        }
      }
    },
    [loadComparisons],
  );

  useEffect(() => {
    if (!polling || !currentEvaluationId) return;
    const timer = window.setInterval(() => {
      void refreshEvaluation(currentEvaluationId);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [currentEvaluationId, polling, refreshEvaluation]);

  const visibleRuns = useMemo(
    () => visibleEvaluationRuns(eligibleRuns, showDiagnostic),
    [eligibleRuns, showDiagnostic],
  );

  const filteredComparisons = useMemo(
    () =>
      comparisons.filter(item => comparisonMatchesIssue(item, issueFilter)),
    [comparisons, issueFilter],
  );

  const selectedDataset = datasets.find(
    item => item.dataset_id === selectedDatasetId,
  );

  function resetPreview() {
    setPreview(null);
    setPreviewError("");
  }

  function requestPayload(): CreateKnowledgeEvaluationRequest {
    return {
      dataset_id: selectedDatasetId,
      run_ids: selectedRunIds,
      judge_enabled: judgeEnabled,
      metric_profile_id: METRIC_PROFILE_ID,
    };
  }

  async function handlePreview() {
    if (!selectedDatasetId || selectedRunIds.length === 0) return;
    setPreviewLoading(true);
    setPreviewError("");
    setActionError("");
    try {
      setPreview(await previewKnowledgeEvaluation(requestPayload()));
    } catch (caught) {
      setPreview(null);
      setPreviewError(
        caught instanceof Error ? caught.message : "评估预检失败，请重试",
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleCreate() {
    if (!preview?.can_create) return;
    setCreating(true);
    setActionError("");
    try {
      const evaluation = await createKnowledgeEvaluation(requestPayload());
      setCurrentEvaluation(evaluation);
      setEvaluations(current => [
        evaluation,
        ...current.filter(
          item => item.evaluation_id !== evaluation.evaluation_id,
        ),
      ]);
      setComparisons([]);
      setComparisonTotal(0);
      setPollError("");
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "效果评估创建失败",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleOpenEvaluation(evaluationId: string) {
    if (!evaluationId) return;
    setDetailLoading(true);
    setActionError("");
    setPollError("");
    setComparisons([]);
    setComparisonTotal(0);
    try {
      const response = await getKnowledgeEvaluation(evaluationId);
      setCurrentEvaluation(response.evaluation);
      if (isTerminalEvaluation(response.evaluation.status)) {
        await loadComparisons(evaluationId);
      }
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "评估详情加载失败，请重试",
      );
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRetry() {
    if (!currentEvaluation || !canRetryEvaluation(currentEvaluation)) return;
    setActionLoading(true);
    setActionError("");
    try {
      const evaluation = await retryKnowledgeEvaluation(
        currentEvaluation.evaluation_id,
      );
      setCurrentEvaluation(evaluation);
      setEvaluations(current => [evaluation, ...current]);
      setComparisons([]);
      setComparisonTotal(0);
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "基于原快照重试失败",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleConfirm() {
    if (!currentEvaluation) return;
    setActionLoading(true);
    setActionError("");
    try {
      const evaluation = await confirmKnowledgeEvaluation(
        currentEvaluation.evaluation_id,
      );
      setCurrentEvaluation(evaluation);
      setEvaluations(current =>
        current.map(item =>
          item.evaluation_id === evaluation.evaluation_id ? evaluation : item,
        ),
      );
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "评估报告确认失败",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    if (!currentEvaluation) return;
    const confirmed = window.confirm(
      "废弃这份评估报告？废弃后不会继续出现在普通历史列表中。",
    );
    if (!confirmed) return;
    setActionLoading(true);
    setActionError("");
    try {
      await rejectKnowledgeEvaluation(currentEvaluation.evaluation_id);
      const history = await listKnowledgeEvaluations();
      setEvaluations(history.evaluations);
      if (history.evaluations[0]) {
        await handleOpenEvaluation(history.evaluations[0].evaluation_id);
      } else {
        setCurrentEvaluation(null);
        setComparisons([]);
        setComparisonTotal(0);
      }
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "评估报告废弃失败",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleLoadJudgeCall(callId: string) {
    if (!currentEvaluation || judgeCalls[callId]) return;
    setJudgeCallLoadingId(callId);
    setActionError("");
    try {
      const response = await getKnowledgeEvaluationJudgeCall(
        currentEvaluation.evaluation_id,
        callId,
      );
      setJudgeCalls(current => ({
        ...current,
        [callId]: response.judge_call,
      }));
    } catch (caught) {
      setActionError(
        caught instanceof Error ? caught.message : "裁判审计记录加载失败",
      );
    } finally {
      setJudgeCallLoadingId("");
    }
  }

  if (initialLoading) {
    return (
      <AppShell activePath="/task-monitor">
        <div className="mx-auto flex min-h-[52vh] max-w-[1200px] items-center justify-center px-5 text-sm text-[var(--tc-text-muted)]">
          <LoaderCircle className="mr-2 size-4 animate-spin motion-reduce:animate-none" />
          正在加载评测集与历史任务
        </div>
      </AppShell>
    );
  }

  if (loadError) {
    return (
      <AppShell activePath="/task-monitor">
        <div className="mx-auto max-w-[760px] px-5 py-8">
          <StatePanel
            icon={AlertCircle}
            title="评估资料加载失败，请重试"
            description={loadError}
            actionLabel="重新加载"
            onAction={() => void loadWorkspace()}
          />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell activePath="/task-monitor">
      <section className="mx-auto grid max-w-[1440px] gap-4 px-4 py-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <div className="flex flex-wrap items-center justify-between gap-3 xl:col-span-2">
          <div className="flex flex-wrap items-center gap-3">
            <KnowledgeExtractionMonitorNav />
            <Link
              href="/task-monitor"
              className="inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
            >
              <ChevronLeft className="size-3" />
              返回任务入口
            </Link>
          </div>
          <Button
            type="button"
            disabled={!preview?.can_create || creating}
            onClick={() => void handleCreate()}
          >
            {creating ? (
              <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
            ) : (
              <Scale className="size-4" />
            )}
            开始效果评估
          </Button>
        </div>

        <aside className="self-start rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3 xl:sticky xl:top-24">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">效果评估</p>
              <h1 className="text-base font-semibold text-[var(--tc-text-primary)]">
                选择历史任务
              </h1>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="刷新评估资料"
              onClick={() => void loadWorkspace()}
            >
              <RefreshCw className="size-4" />
            </Button>
          </div>

          {datasets.length === 0 ? (
            <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-4">
              <p className="text-sm text-[var(--tc-text-primary)]">
                暂无可用评测集，请先完成评测集校验
              </p>
              <details className="mt-2 text-xs text-[var(--tc-text-muted)]">
                <summary className="cursor-pointer">查看校验说明</summary>
                <p className="mt-2 leading-5">
                  评测集需通过结构、来源证据与校验摘要检查，并由维护者确认为可用状态。
                </p>
              </details>
            </div>
          ) : (
            <>
              <label className="mt-3 block text-xs text-[var(--tc-text-muted)]">
                评测集
                <select
                  value={selectedDatasetId}
                  onChange={event => {
                    setSelectedDatasetId(event.target.value);
                    setSelectedRunIds([]);
                    resetPreview();
                  }}
                  className="mt-1 h-8 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-sm text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-border-strong)]"
                >
                  {datasets.map(dataset => (
                    <option key={dataset.dataset_id} value={dataset.dataset_id}>
                      {dataset.display_name ||
                        dataset.name ||
                        dataset.label ||
                        `评测集 ${dataset.dataset_id}`}
                    </option>
                  ))}
                </select>
              </label>

              <div className="mt-2 flex items-center justify-between gap-2 text-xs text-[var(--tc-text-muted)]">
                <span>
                  {selectedDataset?.case_count != null
                    ? `${selectedDataset.case_count} 个评测样例`
                    : "已确认评测集"}
                </span>
                <span className="font-mono">
                  {shortChecksum(selectedDataset?.checksum)}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between border-t border-[var(--tc-border-subtle)] pt-3">
                <span className="text-xs text-[var(--tc-text-muted)]">
                  已选 {selectedRunIds.length}/10
                </span>
                <div className="flex gap-2 text-xs">
                  <button
                    type="button"
                    className="text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
                    onClick={() => {
                      setSelectedRunIds(
                        visibleRuns
                          .filter(selectableEvaluationRun)
                          .slice(0, 10)
                          .map(run => run.run_id),
                      );
                      resetPreview();
                    }}
                  >
                    全选可评估
                  </button>
                  <button
                    type="button"
                    className="text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
                    onClick={() => {
                      setSelectedRunIds([]);
                      resetPreview();
                    }}
                  >
                    清空
                  </button>
                </div>
              </div>

              <div className="mt-2 flex max-h-[42vh] min-h-24 flex-col overflow-y-auto border-y border-[var(--tc-border-subtle)]">
                {runsLoading ? (
                  <p className="px-2 py-5 text-sm text-[var(--tc-text-muted)]">
                    正在读取匹配任务
                  </p>
                ) : runsError ? (
                  <div className="px-2 py-4 text-sm text-[var(--tc-text-primary)]">
                    <p>历史任务加载失败，请重试</p>
                    <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
                      {runsError}
                    </p>
                  </div>
                ) : visibleRuns.length === 0 ? (
                  <div className="px-2 py-5 text-sm">
                    <p className="text-[var(--tc-text-primary)]">
                      暂无与当前评测集匹配的历史任务
                    </p>
                    <button
                      type="button"
                      className="mt-2 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
                      onClick={() => setShowDiagnostic(true)}
                    >
                      显示降级任务
                    </button>
                  </div>
                ) : (
                  visibleRuns.map(run => {
                    const selectable = selectableEvaluationRun(run);
                    const checked = selectedRunIds.includes(run.run_id);
                    const maxReached = selectedRunIds.length >= 10 && !checked;
                    return (
                      <label
                        key={run.run_id}
                        className={cn(
                          "flex gap-2 border-b border-[var(--tc-border-subtle)] px-2 py-2 last:border-b-0",
                          selectable
                            ? "cursor-pointer hover:bg-[var(--tc-surface-muted)]"
                            : "cursor-not-allowed opacity-60",
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          disabled={!selectable || maxReached}
                          aria-label={`选择${evaluationTaskTitle(run)}`}
                          onCheckedChange={() => {
                            setSelectedRunIds(current =>
                              toggleEvaluationRunSelection(current, run.run_id),
                            );
                            resetPreview();
                          }}
                          className="mt-0.5"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-start justify-between gap-2">
                            <span className="truncate text-sm font-medium text-[var(--tc-text-primary)]">
                              {evaluationTaskTitle(run)}
                            </span>
                            <EligibilityLabel level={run.eligibility_level} />
                          </span>
                          <span className="mt-1 block truncate text-xs text-[var(--tc-text-muted)]">
                            {formatDateTime(run.started_at)} · {evaluationModelLabel(run)}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-[var(--tc-text-muted)]">
                            提示词 {run.prompt_version || "未知"}
                            {run.latest_evaluation
                              ? ` · 最近 ${formatEvaluationScore(run.latest_evaluation.overall_quality_score)}`
                              : " · 尚未评估"}
                          </span>
                          {run.reason ? (
                            <span className="mt-1 block text-xs leading-4 text-[var(--tc-text-secondary)]">
                              {run.reason}
                            </span>
                          ) : null}
                        </span>
                      </label>
                    );
                  })
                )}
              </div>

              <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs text-[var(--tc-text-secondary)]">
                <Checkbox
                  checked={showDiagnostic}
                  onCheckedChange={checked => setShowDiagnostic(checked)}
                  aria-label="显示降级与不可评估任务"
                />
                显示降级与不可评估任务
              </label>

              <label className="mt-3 flex cursor-pointer items-start gap-2 border-t border-[var(--tc-border-subtle)] pt-3 text-sm text-[var(--tc-text-primary)]">
                <Checkbox
                  checked={judgeEnabled}
                  onCheckedChange={checked => {
                    setJudgeEnabled(checked);
                    resetPreview();
                  }}
                  aria-label="启用语义裁判"
                  className="mt-0.5"
                />
                <span>
                  启用语义裁判
                  <span className="mt-0.5 block text-xs text-[var(--tc-text-muted)]">
                    评估口径：均衡评估
                  </span>
                </span>
              </label>

              <Button
                type="button"
                variant="outline"
                className="mt-3 w-full"
                disabled={
                  selectedRunIds.length === 0 || previewLoading || runsLoading
                }
                onClick={() => void handlePreview()}
              >
                {previewLoading ? (
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
                ) : (
                  <CircleDashed className="size-4" />
                )}
                {preview ? "重新预检" : "预检所选任务"}
              </Button>
            </>
          )}
        </aside>

        <main className="min-w-0 space-y-4">
          {actionError ? <ErrorBanner message={actionError} /> : null}
          {previewError ? <ErrorBanner message={previewError} /> : null}
          {pollError && currentEvaluation ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
              <span>进度暂时无法更新，已保留最后一次成功结果。</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  void refreshEvaluation(currentEvaluation.evaluation_id)
                }
              >
                <RefreshCw className="size-3.5" />
                立即重试
              </Button>
            </div>
          ) : null}

          <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tc-border-subtle)] px-3 py-2.5">
              <div>
                <p className="text-xs text-[var(--tc-text-muted)]">知识沉淀智能体</p>
                <h2 className="text-base font-semibold text-[var(--tc-text-primary)]">
                  效果评估报告
                </h2>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <label className="sr-only" htmlFor="evaluation-history">
                  评估历史
                </label>
                <select
                  id="evaluation-history"
                  value={currentEvaluation?.evaluation_id ?? ""}
                  disabled={detailLoading || evaluations.length === 0}
                  onChange={event =>
                    void handleOpenEvaluation(event.target.value)
                  }
                  className="h-8 max-w-[260px] rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-xs text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-border-strong)]"
                >
                  {evaluations.length === 0 ? (
                    <option value="">暂无评估历史</option>
                  ) : null}
                  {evaluations.map(evaluation => (
                    <option
                      key={evaluation.evaluation_id}
                      value={evaluation.evaluation_id}
                    >
                      {formatDateTime(evaluation.created_at)} · {evaluationStatusLabels[evaluation.status]}
                    </option>
                  ))}
                </select>
                {currentEvaluation &&
                isTerminalEvaluation(currentEvaluation.status) ? (
                  <details className="relative">
                    <summary
                      aria-label="评估报告更多操作"
                      className="flex size-8 cursor-pointer list-none items-center justify-center rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
                    >
                      <MoreHorizontal className="size-4" />
                    </summary>
                    <div className="absolute right-0 z-20 mt-1 w-44 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-panel)] p-1 shadow-none">
                      {currentEvaluation.lifecycle === "draft" &&
                      currentEvaluation.status !== "failed" ? (
                        <button
                          type="button"
                          disabled={actionLoading}
                          className="flex w-full items-center gap-2 rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-xs text-[var(--tc-text-primary)] hover:bg-[var(--tc-surface-muted)] disabled:opacity-50"
                          onClick={() => void handleConfirm()}
                        >
                          <CheckCircle2 className="size-3.5" />
                          确认评估报告
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={actionLoading}
                        className="flex w-full items-center gap-2 rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-xs text-[var(--tc-text-primary)] hover:bg-[var(--tc-surface-muted)] disabled:opacity-50"
                        onClick={() => void handleReject()}
                      >
                        <ArchiveX className="size-3.5" />
                        废弃评估报告
                      </button>
                    </div>
                  </details>
                ) : null}
              </div>
            </div>

            {detailLoading ? (
              <div className="flex items-center justify-center py-16 text-sm text-[var(--tc-text-muted)]">
                <LoaderCircle className="mr-2 size-4 animate-spin motion-reduce:animate-none" />
                正在加载评估详情
              </div>
            ) : currentEvaluation ? (
              <EvaluationResult
                evaluation={currentEvaluation}
                actionLoading={actionLoading}
                onRetry={() => void handleRetry()}
              />
            ) : preview ? (
              <PreviewPanel preview={preview} />
            ) : (
              <div className="px-4 py-14 text-center text-sm text-[var(--tc-text-muted)]">
                选择历史任务并完成预检后，可开始效果评估。
              </div>
            )}
          </section>

          {preview && currentEvaluation ? <PreviewPanel preview={preview} /> : null}

          {currentEvaluation && isTerminalEvaluation(currentEvaluation.status) ? (
            <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tc-border-subtle)] px-3 py-2.5">
                <div>
                  <h2 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                    卡片差异
                  </h2>
                  <p className="mt-0.5 text-xs text-[var(--tc-text-muted)]">
                    共 {comparisonTotal} 条，完整卡片与裁判原文按需展开
                  </p>
                </div>
                <div className="flex max-w-full gap-1 overflow-x-auto">
                  {issueFilters.map(filter => (
                    <button
                      key={filter.value}
                      type="button"
                      className={cn(
                        "shrink-0 rounded-[var(--tc-radius-pill)] border px-2.5 py-1 text-xs",
                        issueFilter === filter.value
                          ? "border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                          : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)]",
                      )}
                      onClick={() => setIssueFilter(filter.value)}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>

              {comparisonError ? (
                <div className="p-3">
                  <ErrorBanner message={comparisonError} />
                </div>
              ) : comparisonLoading && comparisons.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-[var(--tc-text-muted)]">
                  正在加载差异明细
                </p>
              ) : filteredComparisons.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-[var(--tc-text-muted)]">
                  {comparisons.length === 0
                    ? "本次评估未发现可展示的卡片差异"
                    : "当前筛选下没有差异"}
                </p>
              ) : (
                <div className="divide-y divide-[var(--tc-border-subtle)]">
                  {filteredComparisons.map(comparison => (
                    <ComparisonRow
                      key={comparison.comparison_id}
                      comparison={comparison}
                      judgeCalls={judgeCalls}
                      judgeCallLoadingId={judgeCallLoadingId}
                      onLoadJudgeCall={callId =>
                        void handleLoadJudgeCall(callId)
                      }
                    />
                  ))}
                </div>
              )}

              {comparisons.length < comparisonTotal ? (
                <div className="border-t border-[var(--tc-border-subtle)] p-2 text-center">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={comparisonLoading}
                    onClick={() =>
                      currentEvaluation &&
                      void loadComparisons(
                        currentEvaluation.evaluation_id,
                        comparisonPage + 1,
                        true,
                      )
                    }
                  >
                    {comparisonLoading ? (
                      <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" />
                    ) : null}
                    加载更多差异
                  </Button>
                </div>
              ) : null}
            </section>
          ) : null}
        </main>
      </section>
    </AppShell>
  );
}

function PreviewPanel({ preview }: { preview: KnowledgeEvaluationPreview }) {
  const model = preview.judge.model_identity;
  return (
    <section className="border-b border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-3 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--tc-text-primary)]">
            预检结果
          </h3>
          <p className="mt-0.5 text-xs text-[var(--tc-text-muted)]">
            {preview.can_create ? "输入可以冻结并开始评估" : "当前选择暂不能创建评估"}
          </p>
        </div>
        <span className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-2 py-1 text-xs text-[var(--tc-text-secondary)]">
          {preview.evaluation_mode === "deterministic_only"
            ? "仅确定性比对"
            : "确定性比对与语义裁判"}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 divide-x divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)] text-xs sm:grid-cols-3 xl:grid-cols-6 xl:divide-y-0">
        <PreviewReadout label="任务" value={`${preview.estimate.run_count}`} />
        <PreviewReadout
          label="期望卡"
          value={`${preview.estimate.expected_card_count}`}
        />
        <PreviewReadout
          label="预计匹配"
          value={`${preview.estimate.matched_card_count}`}
        />
        <PreviewReadout
          label="预计裁判"
          value={`${preview.estimate.judge_card_count}`}
        />
        <PreviewReadout
          label="裁判批次"
          value={`${preview.estimate.judge_batch_count}`}
        />
        <PreviewReadout
          label="模型独立性"
          value={
            preview.judge.requested
              ? previewIndependenceLabel(preview.runs)
              : "未启用裁判"
          }
        />
      </div>
      <p className="mt-2 text-xs text-[var(--tc-text-muted)]">
        真实裁判模型：
        {preview.judge.requested
          ? model?.known
            ? `${model.provider ?? "未知提供方"} / ${model.model_id ?? "未登记模型"}`
            : preview.judge.unavailable_reason || "裁判模型身份未知"
          : "未启用"}
      </p>
      {preview.judge.requested && preview.judge.available === false ? (
        <p className="mt-2 flex items-start gap-2 text-sm text-[var(--tc-text-primary)]">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          {preview.judge.unavailable_reason || "语义裁判当前不可用"}
        </p>
      ) : null}
      {[...preview.blocking_errors, ...preview.warnings].length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-[var(--tc-text-secondary)]">
          {[...preview.blocking_errors, ...preview.warnings].map((message, index) => (
            <li key={`${message}-${index}`}>· {message}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function PreviewReadout({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-2 py-2">
      <p className="text-[var(--tc-text-muted)]">{label}</p>
      <p className="mt-0.5 truncate font-mono text-sm text-[var(--tc-text-primary)]">
        {value}
      </p>
    </div>
  );
}

function EvaluationResult({
  evaluation,
  actionLoading,
  onRetry,
}: {
  evaluation: KnowledgeEvaluation;
  actionLoading: boolean;
  onRetry: () => void;
}) {
  const metrics = evaluation.aggregate_metrics ?? {};
  const terminal = isTerminalEvaluation(evaluation.status);
  const criticalRiskCount =
    metricValue(metrics, "critical_risk_count", "critical_flag_count") ?? 0;
  const qualityState: EvaluationQualityState | null =
    typeof metrics.final_quality_state === "string"
      ? (metrics.final_quality_state as EvaluationQualityState)
      : null;

  return (
    <div>
      <div className="px-3 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusLabel status={evaluation.status} />
              <span className="text-xs text-[var(--tc-text-muted)]">
                {evaluation.lifecycle === "draft"
                  ? "报告待确认"
                  : evaluation.lifecycle === "confirmed"
                    ? "报告已确认"
                    : "报告已废弃"}
              </span>
            </div>
            <p className="mt-2 text-sm font-medium text-[var(--tc-text-primary)]">
              {evaluationProgressText(evaluation)}
            </p>
            <p className="mt-1 truncate font-mono text-xs text-[var(--tc-text-muted)]">
              评估标识 {evaluation.evaluation_id}
            </p>
          </div>
          {canRetryEvaluation(evaluation) ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={actionLoading}
              onClick={onRetry}
            >
              <RotateCcw className="size-3.5" />
              基于原快照重试
            </Button>
          ) : null}
        </div>

        {!terminal ? (
          <EvaluationProgressBar evaluation={evaluation} />
        ) : evaluation.status === "failed" ? (
          <div className="mt-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            <p>{evaluationErrorMessage(evaluation)}</p>
            {evaluation.error_code ? (
              <details className="mt-1 text-xs text-[var(--tc-text-muted)]">
                <summary className="cursor-pointer">查看内部错误码</summary>
                <code className="mt-1 block font-mono">
                  {evaluation.error_code}
                </code>
              </details>
            ) : null}
          </div>
        ) : null}
      </div>

      {terminal && evaluation.status !== "failed" ? (
        <>
          <div className="grid grid-cols-2 border-y border-[var(--tc-border-subtle)] sm:grid-cols-3 xl:grid-cols-6">
            <MetricReadout
              label="综合参考分"
              value={metricValue(metrics, "overall_quality_score")}
              emphasized
            />
            <MetricReadout
              label="候选 F1"
              value={metricValue(metrics, "candidate_f1_micro")}
            />
            <MetricReadout
              label="结构字段分"
              value={metricValue(metrics, "structured_field_score")}
            />
            <MetricReadout
              label="语义正确性"
              value={metricValue(metrics, "semantic_score", "semantic_correctness")}
            />
            <MetricReadout
              label="证据质量"
              value={metricValue(metrics, "evidence_score")}
            />
            <MetricReadout
              label="裁判覆盖率"
              value={metricValue(metrics, "judge_coverage")}
            />
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-2 text-xs text-[var(--tc-text-muted)]">
            <span>质量结论：{qualityStateLabel(qualityState)}</span>
            <span>
              {evaluation.judge?.self_judge == null
                ? "模型独立性未确认"
                : evaluation.judge.self_judge
                  ? "同模型自评"
                  : "非同模型自评"}
            </span>
            <span>
              {metricValue(metrics, "execution_coverage") === 1
                ? "完整评估"
                : "评估范围不完整"}
            </span>
            <span>
              评测集：
              {evaluation.dataset.display_name ||
                evaluation.dataset.name ||
                evaluation.dataset.dataset_id}
            </span>
            <span className="font-mono">
              校验摘要 {shortChecksum(evaluation.dataset.checksum)}
            </span>
            <span>关键风险 {criticalRiskCount} 项</span>
          </div>

          {evaluation.warnings?.length ? (
            <ul className="border-t border-[var(--tc-border-subtle)] px-3 py-2 text-xs text-[var(--tc-text-secondary)]">
              {evaluation.warnings.map((warning, index) => (
                <li key={`${noticeMessage(warning)}-${index}`}>
                  · {noticeMessage(warning)}
                </li>
              ))}
            </ul>
          ) : null}

          <details className="border-t border-[var(--tc-border-subtle)]">
            <summary className="cursor-pointer px-3 py-2 text-xs text-[var(--tc-text-muted)]">
              综合参考分计算说明
            </summary>
            <p className="px-3 pb-3 text-xs leading-5 text-[var(--tc-text-secondary)]">
              综合参考分由候选 F1、结构字段分、语义正确性、证据质量与负样本抑制按当前评估口径加权得到，仅用于同一评测口径下的趋势和排序；任一必需指标不适用时不生成综合分。
            </p>
          </details>

          {evaluation.run_results?.length ? (
            <div className="border-t border-[var(--tc-border-subtle)]">
              <div className="grid grid-cols-[minmax(0,1fr)_repeat(4,minmax(64px,0.35fr))] gap-2 px-3 py-2 text-xs text-[var(--tc-text-muted)]">
                <span>单任务结果</span>
                <span>候选 F1</span>
                <span>结构</span>
                <span>语义</span>
                <span>证据</span>
              </div>
              {evaluation.run_results.map(run => (
                <RunResultRow key={run.run_id} run={run} />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function RunResultRow({
  run,
}: {
  run: KnowledgeEvaluation["run_results"][number];
}) {
  const metrics = {
    ...(run.metrics ?? {}),
    semantic_score:
      run.semantic_score ?? run.metrics?.semantic_score ?? null,
    judge_coverage:
      run.judge_coverage ?? run.metrics?.judge_coverage ?? null,
    overall_quality_score:
      run.overall_quality_score ??
      run.metrics?.overall_quality_score ??
      null,
  };
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_repeat(4,minmax(64px,0.35fr))] gap-2 border-t border-[var(--tc-border-subtle)] px-3 py-2 text-xs text-[var(--tc-text-secondary)]">
      <span className="truncate text-[var(--tc-text-primary)]">
        {run.chapter_title ||
          (run.case_id ? `评测样例 ${run.case_id}` : `任务 ${run.run_id}`)}
      </span>
      <span>{formatEvaluationScore(metricValue(metrics, "candidate_f1_micro"))}</span>
      <span>
        {formatEvaluationScore(metricValue(metrics, "structured_field_score"))}
      </span>
      <span>
        {formatEvaluationScore(
          metricValue(metrics, "semantic_score", "semantic_correctness"),
        )}
      </span>
      <span>{formatEvaluationScore(metricValue(metrics, "evidence_score"))}</span>
    </div>
  );
}

function EvaluationProgressBar({
  evaluation,
}: {
  evaluation: KnowledgeEvaluation;
}) {
  const judging = evaluation.phase === "judging";
  const current = judging
    ? evaluation.progress.judge_card_completed
    : evaluation.progress.run_completed;
  const total = judging
    ? evaluation.progress.judge_card_total
    : evaluation.progress.run_total;
  const percentage = total > 0 ? Math.min(100, (current / total) * 100) : 0;
  return (
    <div className="mt-3" aria-label={`评估进度 ${Math.round(percentage)}%`}>
      <div className="h-1 overflow-hidden rounded-[var(--tc-radius-pill)] bg-[var(--tc-surface-muted)]">
        <div
          className="h-full bg-[var(--tc-text-primary)] transition-[width] duration-200 motion-reduce:transition-none"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function MetricReadout({
  label,
  value,
  emphasized = false,
}: {
  label: string;
  value: number | null;
  emphasized?: boolean;
}) {
  return (
    <div className="min-w-0 border-r border-b border-[var(--tc-border-subtle)] px-3 py-2.5 last:border-r-0 xl:border-b-0">
      <p className="text-xs text-[var(--tc-text-muted)]">{label}</p>
      <p
        className={cn(
          "mt-1 truncate font-mono text-[var(--tc-text-primary)]",
          emphasized ? "text-xl font-semibold" : "text-base font-medium",
        )}
      >
        {formatEvaluationScore(value)}
      </p>
    </div>
  );
}

function ComparisonRow({
  comparison,
  judgeCalls,
  judgeCallLoadingId,
  onLoadJudgeCall,
}: {
  comparison: KnowledgeEvaluationComparison;
  judgeCalls: Record<string, EvaluationJudgeCall>;
  judgeCallLoadingId: string;
  onLoadJudgeCall: (callId: string) => void;
}) {
  const callIds = comparison.judge_call_ids ?? [];
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-3 py-2.5 hover:bg-[var(--tc-surface-muted)]">
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-[var(--tc-text-primary)]">
            {comparison.display_title || "未命名知识卡"}
          </span>
          <span className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-[var(--tc-text-muted)]">
            <span>{knowledgeTypeLabels[comparison.knowledge_type]}</span>
            <span>{issueTypeLabels[comparison.issue_type]}</span>
            <span className="font-mono">任务标识 {comparison.run_id}</span>
          </span>
        </span>
        <FileDiff className="mt-0.5 size-4 shrink-0 text-[var(--tc-text-muted)]" />
      </summary>
      <div className="border-t border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-3 text-sm">
        <p className="text-xs text-[var(--tc-text-muted)]">匹配依据</p>
        <p className="mt-1 text-[var(--tc-text-secondary)]">
          {comparison.match_basis || "未形成一对一匹配"}
        </p>

        {comparison.field_diffs?.length ? (
          <div className="mt-3">
            <p className="text-xs text-[var(--tc-text-muted)]">精确字段差异</p>
            <div className="mt-1 divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
              {comparison.field_diffs.map((diff, index) => (
                <div
                  key={`${diff.field}-${index}`}
                  className="grid gap-1 py-2 text-xs sm:grid-cols-[120px_1fr_1fr] sm:gap-3"
                >
                  <span className="font-medium text-[var(--tc-text-primary)]">
                    {diff.label || diff.field}
                  </span>
                  <span>
                    <span className="text-[var(--tc-text-muted)]">期望：</span>
                    {displayValue(diff.expected)}
                  </span>
                  <span>
                    <span className="text-[var(--tc-text-muted)]">实际：</span>
                    {displayValue(diff.actual)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <IssueList label="缺失关键事实" items={comparison.missing_critical_claims} />
        <IssueList label="无依据断言" items={comparison.unsupported_claims} />
        <IssueList label="矛盾项" items={comparison.contradictions} />

        {comparison.evidence_diffs?.length ? (
          <div className="mt-3">
            <p className="text-xs text-[var(--tc-text-muted)]">证据与章节定位</p>
            <div className="mt-1 space-y-2">
              {comparison.evidence_diffs.map((evidence, index) => (
                <div
                  key={`${evidence.quote_id ?? "evidence"}-${index}`}
                  className="border-l border-[var(--tc-border-strong)] pl-2 text-xs leading-5 text-[var(--tc-text-secondary)]"
                >
                  <p>
                    {evidence.chapter_title || evidence.chapter_id || "章节未知"}
                    {evidence.located === false ? " · 无法定位" : ""}
                  </p>
                  {evidence.expected_quote ? (
                    <p>期望证据：{evidence.expected_quote}</p>
                  ) : null}
                  {evidence.actual_quote ? (
                    <p>实际证据：{evidence.actual_quote}</p>
                  ) : null}
                  {evidence.reason ? <p>{evidence.reason}</p> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {comparison.judge_reason ? (
          <div className="mt-3">
            <p className="text-xs text-[var(--tc-text-muted)]">裁判理由</p>
            <p className="mt-1 leading-5 text-[var(--tc-text-secondary)]">
              {comparison.judge_reason}
              {comparison.judge_confidence != null
                ? ` · 置信度 ${formatEvaluationScore(comparison.judge_confidence)}`
                : ""}
            </p>
          </div>
        ) : null}

        <div className="mt-3 grid gap-2 lg:grid-cols-2">
          <JsonDisclosure
            label="期望卡完整数据（JSON）"
            value={comparison.expected_card}
          />
          <JsonDisclosure
            label="实际卡完整数据（JSON）"
            value={comparison.actual_card}
          />
        </div>

        {callIds.length ? (
          <details className="mt-3 border-t border-[var(--tc-border-subtle)] pt-2">
            <summary className="cursor-pointer text-xs text-[var(--tc-text-muted)]">
              裁判提示词与原始响应
            </summary>
            <div className="mt-2 space-y-2">
              {callIds.map(callId => {
                const call = judgeCalls[callId];
                return (
                  <div key={callId} className="text-xs">
                    {call ? (
                      <JudgeCallDisclosure call={call} />
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        disabled={judgeCallLoadingId !== ""}
                        onClick={() => onLoadJudgeCall(callId)}
                      >
                        {judgeCallLoadingId === callId ? (
                          <LoaderCircle className="size-3 animate-spin motion-reduce:animate-none" />
                        ) : null}
                        加载裁判审计 {callId}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          </details>
        ) : null}
      </div>
    </details>
  );
}

function JudgeCallDisclosure({ call }: { call: EvaluationJudgeCall }) {
  return (
    <details className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
      <summary className="cursor-pointer px-2 py-1.5 font-mono text-[var(--tc-text-muted)]">
        {call.call_id}
      </summary>
      <div className="grid gap-2 border-t border-[var(--tc-border-subtle)] p-2 lg:grid-cols-2">
        <JsonText label="裁判提示词" value={call.input_prompt || "无"} />
        <JsonText label="原始响应" value={call.raw_response || "无"} />
      </div>
    </details>
  );
}

function JsonDisclosure({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
      <summary className="cursor-pointer px-2 py-1.5 text-xs text-[var(--tc-text-muted)]">
        {label}
      </summary>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words border-t border-[var(--tc-border-subtle)] p-2 font-mono text-xs leading-5 text-[var(--tc-text-secondary)]">
        {formatJson(value)}
      </pre>
    </details>
  );
}

function JsonText({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1 text-[var(--tc-text-muted)]">{label}</p>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono leading-5 text-[var(--tc-text-secondary)]">
        {value}
      </pre>
    </div>
  );
}

function IssueList({ label, items }: { label: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-3">
      <p className="text-xs text-[var(--tc-text-muted)]">{label}</p>
      <ul className="mt-1 space-y-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>· {item}</li>
        ))}
      </ul>
    </div>
  );
}

function EligibilityLabel({
  level,
}: {
  level: EligibleEvaluationRun["eligibility_level"];
}) {
  const label =
    level === "full"
      ? "完整可评估"
      : level === "diagnostic"
        ? "降级可诊断"
        : "不可评估";
  return (
    <span className="shrink-0 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--tc-text-muted)]">
      {label}
    </span>
  );
}

function StatusLabel({ status }: { status: KnowledgeEvaluation["status"] }) {
  const Icon =
    status === "pending" || status === "running"
      ? Clock3
      : status === "failed"
        ? AlertCircle
        : CheckCircle2;
  return (
    <span className="inline-flex items-center gap-1 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-1.5 py-0.5 text-xs text-[var(--tc-text-secondary)]">
      <Icon className="size-3" />
      {evaluationStatusLabels[status]}
    </span>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function StatePanel({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}: {
  icon: typeof AlertCircle;
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-4 py-5">
      <Icon className="size-5 text-[var(--tc-text-muted)]" />
      <h1 className="mt-3 text-base font-semibold text-[var(--tc-text-primary)]">
        {title}
      </h1>
      <p className="mt-1 text-sm text-[var(--tc-text-muted)]">{description}</p>
      <Button type="button" variant="outline" className="mt-4" onClick={onAction}>
        <RefreshCw className="size-4" />
        {actionLabel}
      </Button>
    </div>
  );
}

function displayValue(value: unknown): string {
  if (value == null) return "无";
  if (typeof value === "string") return value || "空字符串";
  return formatJson(value);
}

function formatJson(value: unknown): string {
  if (value == null) return "无";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
