"use client";

import Link from "next/link";
import {
  AlertCircle,
  ArchiveX,
  Check,
  CheckCircle2,
  ChevronLeft,
  CircleDashed,
  Clock3,
  Copy,
  FileDiff,
  LoaderCircle,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Scale,
  ShieldAlert,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";

import { AppShell } from "@/components/app-shell";
import { KnowledgeExtractionMonitorNav } from "@/components/agent-task-monitor/knowledge-extraction-monitor-nav";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CompactPagination } from "@/components/ui/compact-pagination";
import {
  confirmKnowledgeEvaluation,
  createKnowledgeEvaluation,
  getKnowledgeEvaluation,
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
  buildKnowledgeEvaluationCodexAnalysisRequest,
  evaluationErrorMessage,
  evaluationFieldLabel,
  evaluationIndependenceLabel,
  evaluationMatchBasisLabel,
  evaluationModelLabel,
  evaluationProgressText,
  evaluationStatusLabels,
  evaluationTaskTitle,
  formatEvaluationScore,
  isTerminalEvaluation,
  issueTypeLabels,
  knowledgeTypeLabels,
  metricValue,
  modelIdentityLabel,
  noticeMessage,
  previewIndependenceLabel,
  qualityStateLabel,
  selectableEvaluationRun,
  shouldPollEvaluation,
  toggleEvaluationRunSelection,
  visibleEvaluationRuns,
} from "@/lib/agent-evaluation/evaluation-view-model";
import type {
  CreateKnowledgeEvaluationRequest,
  EligibleEvaluationRun,
  EvaluationDatasetSummary,
  EvaluationIssueType,
  EvaluationQualityState,
  KnowledgeEvaluation,
  KnowledgeEvaluationComparison,
  KnowledgeEvaluationPreview,
} from "@/lib/types/agent-evaluation";
import { cn } from "@/lib/utils";

const METRIC_PROFILE_ID = "knowledge_extraction_balanced";
const EVALUATION_HISTORY_PAGE_SIZE = 6;
const COMPARISON_PAGE_SIZE = 12;

type EvaluationSection = "runs" | "report" | "comparisons";

const issueFilters: Array<{
  value: EvaluationIssueType | "all";
  label: string;
}> = [
  { value: "all", label: "全部" },
  { value: "missing_candidate", label: "漏提取" },
  { value: "extra_candidate", label: "多提取" },
  { value: "ambiguous_match", label: "匹配待复核" },
  { value: "field_difference", label: "字段不同" },
  { value: "semantic_issue", label: "语义问题" },
  { value: "evidence_issue", label: "证据问题" },
  { value: "judge_disagreement", label: "裁判评分分歧" },
  { value: "judge_inconclusive", label: "裁判结果不足" },
  { value: "judge_failed", label: "裁判调用失败" },
];

export function KnowledgeEvaluationShell() {
  const [activeSection, setActiveSection] =
    useState<EvaluationSection>("runs");
  const [historyPage, setHistoryPage] = useState(1);
  const [datasets, setDatasets] = useState<EvaluationDatasetSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [eligibleRuns, setEligibleRuns] = useState<EligibleEvaluationRun[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [showDiagnostic, setShowDiagnostic] = useState(false);
  const [judgeEnabled, setJudgeEnabled] = useState(true);
  const [preview, setPreview] = useState<KnowledgeEvaluationPreview | null>(null);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
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

  const [initialLoading, setInitialLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [copiedEvaluationId, setCopiedEvaluationId] = useState("");

  const [loadError, setLoadError] = useState("");
  const [runsError, setRunsError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [actionError, setActionError] = useState("");
  const [comparisonError, setComparisonError] = useState("");
  const [pollError, setPollError] = useState("");

  const loadComparisons = useCallback(
    async (
      evaluationId: string,
      page = 1,
      filter: EvaluationIssueType | "all" = "all",
    ) => {
      setComparisonLoading(true);
      setComparisonError("");
      try {
        const response = await listKnowledgeEvaluationComparisons(evaluationId, {
          page,
          pageSize: COMPARISON_PAGE_SIZE,
          issueType: filter,
        });
        setComparisons(response.comparisons);
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
      setHistoryPage(1);
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

  const selectedDataset = datasets.find(
    item => item.dataset_id === selectedDatasetId,
  );
  const historyTotalPages = Math.max(
    1,
    Math.ceil(evaluations.length / EVALUATION_HISTORY_PAGE_SIZE),
  );
  const visibleHistoryPage = Math.min(historyPage, historyTotalPages);
  const visibleEvaluations = evaluations.slice(
    (visibleHistoryPage - 1) * EVALUATION_HISTORY_PAGE_SIZE,
    visibleHistoryPage * EVALUATION_HISTORY_PAGE_SIZE,
  );

  function resetPreview() {
    setPreview(null);
    setPreviewDialogOpen(false);
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
      setPreviewDialogOpen(true);
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
      setPreview(null);
      setPreviewDialogOpen(false);
      setActiveSection("report");
      setHistoryPage(1);
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
    setIssueFilter("all");
    setComparisons([]);
    setComparisonTotal(0);
    try {
      const response = await getKnowledgeEvaluation(evaluationId);
      setCurrentEvaluation(response.evaluation);
      setActiveSection("report");
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
      setActiveSection("report");
      setHistoryPage(1);
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

  async function handleCopyForCodex(evaluation: KnowledgeEvaluation) {
    setActionError("");
    try {
      await copyTextToClipboard(
        buildKnowledgeEvaluationCodexAnalysisRequest(evaluation),
      );
      setCopiedEvaluationId(evaluation.evaluation_id);
    } catch {
      setActionError(
        "复制失败，请检查浏览器的剪贴板权限后重试。评估结果仍已保存在本地。",
      );
    }
  }

  if (initialLoading) {
    return (
      <AppShell activePath="/task-monitor" viewportLocked>
        <div className="mx-auto flex min-h-[52vh] max-w-[1200px] items-center justify-center px-5 text-sm text-[var(--tc-text-muted)]">
          <LoaderCircle className="mr-2 size-4 animate-spin motion-reduce:animate-none" />
          正在加载评测集与历史任务
        </div>
      </AppShell>
    );
  }

  if (loadError) {
    return (
      <AppShell activePath="/task-monitor" viewportLocked>
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
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto grid h-full min-h-0 w-full max-w-[1440px] grid-rows-[auto_minmax(0,1fr)] gap-4 overflow-hidden px-4 py-4 xl:grid-cols-[270px_minmax(0,1fr)_148px]">
        <div className="flex flex-wrap items-center justify-between gap-3 xl:col-span-3">
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
        </div>

        <aside className="flex min-h-0 flex-col rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3 xl:col-start-1 xl:row-start-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">效果评估</p>
              <h1 className="text-base font-semibold text-[var(--tc-text-primary)]">
                最近运行
              </h1>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="刷新评测记录"
              onClick={() => void loadWorkspace()}
            >
              <RefreshCw className="size-4" />
            </Button>
          </div>

          {evaluations.length === 0 ? (
            <p className="mt-6 text-sm text-[var(--tc-text-muted)]">
              暂无评测记录
            </p>
          ) : (
            <>
              <div className="mt-3 min-h-0 flex-1 overflow-y-auto border-y border-[var(--tc-border-subtle)] py-1">
                {visibleEvaluations.map(evaluation => {
                  const selected =
                    evaluation.evaluation_id === currentEvaluation?.evaluation_id;
                  return (
                    <button
                      key={evaluation.evaluation_id}
                      type="button"
                      onClick={() => void handleOpenEvaluation(evaluation.evaluation_id)}
                      className={cn(
                        "block w-full rounded-[var(--tc-radius-control)] px-2 py-2 text-left transition-colors",
                        selected
                          ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                          : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
                      )}
                    >
                      <span className="block truncate text-sm font-medium">
                        {evaluation.subject_title || "未命名章节"}
                      </span>
                      <span className="mt-1 flex items-center justify-between gap-2 text-xs text-[var(--tc-text-muted)]">
                        <span className="truncate">{formatDateTime(evaluation.created_at)}</span>
                        <span className="shrink-0">
                          {evaluationStatusLabels[evaluation.status]}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
              <CompactPagination
                page={visibleHistoryPage}
                pageSize={EVALUATION_HISTORY_PAGE_SIZE}
                total={evaluations.length}
                onPageChange={setHistoryPage}
                className="mt-2"
              />
            </>
          )}
        </aside>

        <aside
          className={cn(
            "min-h-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3 xl:col-start-2 xl:row-start-2 xl:overflow-y-auto",
            activeSection === "runs" ? "" : "hidden",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">效果评估</p>
              <h1 className="text-base font-semibold text-[var(--tc-text-primary)]">
                待评估任务
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
                  评测集需通过结构、来源证据与一致性检查，并由维护者确认为可用状态。
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

              <div className="mt-2 text-xs text-[var(--tc-text-muted)]">
                <span>
                  {selectedDataset?.case_count != null
                    ? `${selectedDataset.case_count} 个已标注样本`
                    : "已确认评测集"}
                </span>
              </div>

              <div className="mt-3 border-t border-[var(--tc-border-subtle)] pt-3">
                <span className="text-xs text-[var(--tc-text-muted)]">
                  选择一个历史任务进行评估
                </span>
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
                          disabled={!selectable}
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

        <main
          className={cn(
            "min-h-0 min-w-0 space-y-4 overflow-y-auto pr-1 xl:col-start-2 xl:row-start-2",
            activeSection === "report" || activeSection === "comparisons"
              ? ""
              : "hidden",
          )}
        >
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

          {activeSection === "report" ? (
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
                      {evaluation.subject_title || "未命名章节"} · {formatDateTime(evaluation.created_at)} · {evaluationStatusLabels[evaluation.status]}
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
                copiedForCodex={
                  copiedEvaluationId === currentEvaluation.evaluation_id
                }
                onCopyForCodex={() =>
                  void handleCopyForCodex(currentEvaluation)
                }
                onRetry={() => void handleRetry()}
              />
            ) : (
              <div className="px-4 py-14 text-center text-sm text-[var(--tc-text-muted)]">
                选择历史任务并完成预检后，可开始效果评估。
              </div>
            )}
            </section>
          ) : null}

          {activeSection === "comparisons" &&
          currentEvaluation &&
          isTerminalEvaluation(currentEvaluation.status) ? (
            <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tc-border-subtle)] px-3 py-2.5">
                <div>
                  <h2 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                    卡片差异
                  </h2>
                  <p className="mt-0.5 text-xs text-[var(--tc-text-muted)]">
                    当前筛选共 {comparisonTotal} 条，每项优先显示可读总结
                  </p>
                </div>
                <div className="flex max-w-full flex-wrap justify-end gap-1">
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
                      onClick={() => {
                        setIssueFilter(filter.value);
                        if (currentEvaluation) {
                          void loadComparisons(
                            currentEvaluation.evaluation_id,
                            1,
                            filter.value,
                          );
                        }
                      }}
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
              ) : comparisons.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-[var(--tc-text-muted)]">
                  {issueFilter === "all"
                    ? "本次评估未发现可展示的卡片差异"
                    : "当前筛选下没有差异"}
                </p>
              ) : (
                <div className="divide-y divide-[var(--tc-border-subtle)]">
                  {comparisons.map(comparison => (
                    <ComparisonRow
                      key={comparison.comparison_id}
                      comparison={comparison}
                    />
                  ))}
                </div>
              )}

              {comparisonTotal > 0 ? (
                <CompactPagination
                  page={comparisonPage}
                  pageSize={COMPARISON_PAGE_SIZE}
                  total={comparisonTotal}
                  onPageChange={page =>
                    currentEvaluation &&
                    void loadComparisons(
                      currentEvaluation.evaluation_id,
                      page,
                      issueFilter,
                    )
                  }
                  className="m-3"
                />
              ) : null}
            </section>
          ) : activeSection === "comparisons" ? (
            <StatePanel
              icon={FileDiff}
              title="暂无可查看的卡片差异"
              description="请先从左侧打开一份已完成的评测报告。"
              actionLabel="查看评估报告"
              onAction={() => setActiveSection("report")}
            />
          ) : null}
        </main>
        <EvaluationSectionRail
          activeSection={activeSection}
          pendingCount={selectedRunIds.length}
          onSectionChange={setActiveSection}
        />
      </section>
      <PreviewDialog
        preview={preview}
        open={previewDialogOpen}
        creating={creating}
        onOpenChange={open => {
          setPreviewDialogOpen(open);
          if (!open) {
            setPreview(null);
          }
        }}
        onCreate={() => void handleCreate()}
      />
    </AppShell>
  );
}

function EvaluationSectionRail({
  activeSection,
  pendingCount,
  onSectionChange,
}: {
  activeSection: EvaluationSection;
  pendingCount: number;
  onSectionChange: (section: EvaluationSection) => void;
}) {
  const sections: Array<{
    key: EvaluationSection;
    label: string;
    icon: typeof Scale;
  }> = [
    {
      key: "runs",
      label: pendingCount > 0 ? `待评估任务 ${pendingCount}` : "待评估任务",
      icon: CircleDashed,
    },
    { key: "report", label: "评估报告", icon: CheckCircle2 },
    { key: "comparisons", label: "评估详情", icon: FileDiff },
  ];

  return (
    <nav
      aria-label="效果评估功能"
      className="grid h-max gap-2 self-start xl:col-start-3 xl:row-start-2"
    >
      {sections.map(section => {
        const Icon = section.icon;
        const selected = activeSection === section.key;
        return (
          <Button
            key={section.key}
            type="button"
            variant={selected ? "default" : "outline"}
            size="sm"
            aria-pressed={selected}
            onClick={() => onSectionChange(section.key)}
            className="h-9 w-full justify-start px-3"
          >
            <Icon className="size-4" />
            {section.label}
          </Button>
        );
      })}
    </nav>
  );
}

function PreviewDialog({
  preview,
  open,
  creating,
  onOpenChange,
  onCreate,
}: {
  preview: KnowledgeEvaluationPreview | null;
  open: boolean;
  creating: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: () => void;
}) {
  if (!preview) return null;
  const selectedRun = preview.runs[0];
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/60 data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 motion-reduce:transition-none" />
        <Dialog.Viewport className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4">
          <Dialog.Popup className="w-full max-w-[720px] rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] text-[var(--tc-text-primary)] outline-none data-[starting-style]:scale-[0.98] data-[starting-style]:opacity-0 data-[ending-style]:scale-[0.98] data-[ending-style]:opacity-0 motion-safe:transition-[opacity,transform] motion-safe:duration-150">
            <div className="flex items-start justify-between gap-3 border-b border-[var(--tc-border-subtle)] px-4 py-3">
              <div>
                <Dialog.Title className="text-base font-semibold">预检结果</Dialog.Title>
                <Dialog.Description className="mt-0.5 text-xs text-[var(--tc-text-muted)]">
                  {preview.can_create
                    ? "确认后将冻结当前输入并开始效果评估。"
                    : "当前选择暂不能创建效果评估。"}
                </Dialog.Description>
              </div>
              <Dialog.Close
                type="button"
                aria-label="关闭预检结果"
                className="flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)] disabled:opacity-50"
                disabled={creating}
              >
                <X className="size-4" />
              </Dialog.Close>
            </div>
            <div className="px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                {selectedRun ? (
                  <p className="text-sm text-[var(--tc-text-primary)]">
                    评估对象：{selectedRun.display_title}
                  </p>
                ) : null}
                <span className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-2 py-1 text-xs text-[var(--tc-text-secondary)]">
                  {preview.evaluation_mode === "deterministic_only"
                    ? "仅确定性比对"
                    : "确定性比对与语义裁判"}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 divide-x divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)] text-xs sm:grid-cols-3 xl:grid-cols-5 xl:divide-y-0">
                <PreviewReadout label="期望卡" value={`${preview.estimate.expected_card_count}`} />
                <PreviewReadout label="预计匹配" value={`${preview.estimate.matched_card_count}`} />
                <PreviewReadout label="预计裁判" value={`${preview.estimate.judge_card_count}`} />
                <PreviewReadout label="裁判批次" value={`${preview.estimate.judge_batch_count}`} />
                <PreviewReadout
                  label="模型独立性"
                  value={preview.judge.requested ? previewIndependenceLabel(preview.runs) : "未启用裁判"}
                />
              </div>
              <p className="mt-2 text-xs text-[var(--tc-text-muted)]">
                裁判模型：{preview.judge.requested ? modelIdentityLabel(preview.judge.model_identity) : "未启用"}
              </p>
              {preview.judge.requested && preview.judge.available === false ? (
                <p className="mt-2 flex items-start gap-2 text-sm text-[var(--tc-text-primary)]">
                  <ShieldAlert className="mt-0.5 size-4 shrink-0" />
                  {preview.judge.unavailable_reason || "语义裁判当前不可用"}
                </p>
              ) : null}
              {[...preview.blocking_errors, ...preview.warnings].length > 0 ? (
                <ul className="mt-3 space-y-1 text-xs text-[var(--tc-text-secondary)]">
                  {[...preview.blocking_errors, ...preview.warnings].map((message, index) => (
                    <li key={`${message}-${index}`}>· {message}</li>
                  ))}
                </ul>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 border-t border-[var(--tc-border-subtle)] px-4 py-3">
              <Dialog.Close render={<Button type="button" variant="outline" disabled={creating} />}>
                取消
              </Dialog.Close>
              <Button
                type="button"
                disabled={!preview.can_create || creating}
                onClick={onCreate}
              >
                {creating ? (
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Scale className="size-4" />
                )}
                开始效果评估
              </Button>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
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
  copiedForCodex,
  onCopyForCodex,
  onRetry,
}: {
  evaluation: KnowledgeEvaluation;
  actionLoading: boolean;
  copiedForCodex: boolean;
  onCopyForCodex: () => void;
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
  const diagnosticMessages = Array.from(
    new Set((evaluation.warnings ?? []).map(noticeMessage).filter(Boolean)),
  );
  const hasLegacyJudgeWarning = diagnosticMessages.some(message =>
    message.includes("语义裁判返回内容无法校验"),
  );

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
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
              评估对象：{evaluation.subject_title || "未命名章节"}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {terminal ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onCopyForCodex}
              >
                {copiedForCodex ? (
                  <Check className="size-3.5" />
                ) : (
                  <Copy className="size-3.5" />
                )}
                {copiedForCodex ? "已复制分析请求" : "复制给 Codex 分析"}
              </Button>
            ) : null}
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
        </div>

        {!terminal ? (
          <EvaluationProgressBar evaluation={evaluation} />
        ) : evaluation.status === "failed" ? (
          <div className="mt-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-strong)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            <p>{evaluationErrorMessage(evaluation)}</p>
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
              {evaluationIndependenceLabel(evaluation)}
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
            <span>关键风险 {criticalRiskCount} 项</span>
          </div>

          {diagnosticMessages.length ? (
            <section className="border-t border-[var(--tc-border-subtle)] px-3 py-2">
              <h3 className="text-xs font-medium text-[var(--tc-text-primary)]">
                评估诊断
              </h3>
              <ul className="mt-1 space-y-1 text-xs text-[var(--tc-text-secondary)]">
                {diagnosticMessages.map(message => (
                  <li key={message}>· {message}</li>
                ))}
                {hasLegacyJudgeWarning ? (
                  <li>
                    · 此历史报告仅保存了泛化错误；基于原快照重试后会展示具体协议诊断。
                  </li>
                ) : null}
              </ul>
            </section>
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
        {run.display_title || "未命名章节"}
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

function ComparisonRow({ comparison }: {
  comparison: KnowledgeEvaluationComparison;
}) {
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
            <span>{comparison.task_title || "未命名章节"}</span>
          </span>
          {comparison.explanation?.summary ? (
            <span className="mt-1.5 line-clamp-2 block text-xs leading-5 text-[var(--tc-text-secondary)]">
              <span className="text-[var(--tc-text-muted)]">
                {comparison.explanation.source === "model"
                  ? "模型总结："
                  : "规则说明："}
              </span>
              {comparison.explanation.summary}
            </span>
          ) : null}
        </span>
        <FileDiff className="mt-0.5 size-4 shrink-0 text-[var(--tc-text-muted)]" />
      </summary>
      <div className="border-t border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-3 text-sm">
        {comparison.explanation?.summary ? (
          <div>
            <p className="text-xs text-[var(--tc-text-muted)]">
              {comparison.explanation.source === "model"
                ? "模型总结"
                : "规则说明"}
            </p>
            <p className="mt-1 leading-6 text-[var(--tc-text-primary)]">
              {comparison.explanation.summary}
            </p>
          </div>
        ) : null}

        <details className="mt-3 border-t border-[var(--tc-border-subtle)] pt-2">
          <summary className="cursor-pointer text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-secondary)]">
            查看原始对比依据
          </summary>
          <div className="pt-3">
            <p className="text-xs text-[var(--tc-text-muted)]">匹配依据</p>
            <p className="mt-1 text-[var(--tc-text-secondary)]">
              {evaluationMatchBasisLabel(comparison.match_basis)}
            </p>

            {comparison.field_diffs?.length ? (
              <div className="mt-3">
                <p className="text-xs text-[var(--tc-text-muted)]">
                  精确字段差异
                </p>
                <div className="mt-1 divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
                  {comparison.field_diffs.map((diff, index) => (
                    <div
                      key={`${diff.field}-${index}`}
                      className="grid gap-1 py-2 text-xs sm:grid-cols-[120px_1fr_1fr] sm:gap-3"
                    >
                      <span className="font-medium text-[var(--tc-text-primary)]">
                        {evaluationFieldLabel(diff.label, diff.field)}
                      </span>
                      <span>
                        <span className="text-[var(--tc-text-muted)]">
                          评测标准：
                        </span>
                        {displayValue(diff.expected, diff.field)}
                      </span>
                      <span>
                        <span className="text-[var(--tc-text-muted)]">
                          本次提取：
                        </span>
                        {displayValue(diff.actual, diff.field)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <IssueList
              label="缺失关键事实"
              items={comparison.missing_critical_claims}
            />
            <IssueList
              label="无依据断言"
              items={comparison.unsupported_claims}
            />
            <IssueList label="矛盾项" items={comparison.contradictions} />

            {comparison.evidence_diffs?.length ? (
              <div className="mt-3">
                <p className="text-xs text-[var(--tc-text-muted)]">
                  证据与章节定位
                </p>
                <div className="mt-1 space-y-2">
                  {comparison.evidence_diffs.map((evidence, index) => (
                    <div
                      key={`${evidence.quote_id ?? "evidence"}-${index}`}
                      className="border-l border-[var(--tc-border-strong)] pl-2 text-xs leading-5 text-[var(--tc-text-secondary)]"
                    >
                      <p>
                        {evidence.chapter_title || "章节未知"}
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
          </div>
        </details>
      </div>
    </details>
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

function displayValue(value: unknown, field?: string): string {
  if (value == null) return "未填写";
  if (typeof value === "string") {
    const enumLabels: Record<string, string> = {
      protagonist: "主角",
      supporting: "配角",
      antagonist: "反派",
      passerby: "路人",
      faction_representative: "势力代表",
      cultivation_method: "功法",
      spell: "术法",
      divine_ability: "神通",
      sword_art: "剑诀",
      forbidden_art: "禁术",
      alchemy: "炼丹",
      formation: "阵法",
      sect: "宗门",
      family: "家族",
      dynasty: "王朝",
      guild: "商会",
      demonic: "魔道",
      alliance: "联盟",
      academy: "学院",
      magic_treasure: "法宝",
      pill: "丹药",
      material: "材料",
      other: "其他",
      draft: "草稿",
      confirmed: "已确认",
      rejected: "已拒绝",
      inbox_fact: "收件箱事实转化",
      agent_extract: "正文自动提取",
      manual: "人工添加",
      character: "角色",
      realm: "境界",
      technique: "功法",
      location: "地点",
      faction: "势力",
      item: "物品",
      rule: "规则",
      event: "事件",
      create_card: "新建卡片",
      update_card: "更新卡片",
    };
    if (enumLabels[value]) return enumLabels[value];
    if (field?.endsWith("chapter_id")) return "已填写章节引用";
    if (field?.endsWith("_id")) return "已填写知识引用";
    return value || "空字符串";
  }
  if (Array.isArray(value)) {
    return value
      .filter(item => typeof item === "string" || typeof item === "number")
      .join("、") || "无";
  }
  return "内容不同";
}

async function copyTextToClipboard(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // 浏览器拒绝现代剪贴板接口时，继续尝试本地同步回退。
    }
  }

  const textArea = document.createElement("textarea");
  textArea.value = value;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.appendChild(textArea);
  textArea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textArea);
  if (!copied) {
    throw new Error("clipboard unavailable");
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
