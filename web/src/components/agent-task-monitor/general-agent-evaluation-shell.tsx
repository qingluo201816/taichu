"use client";

import {
  Check,
  ChevronLeft,
  Clipboard,
  RefreshCw,
  Scale,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { GeneralAgentMonitorNav } from "@/components/agent-task-monitor/general-agent-monitor-nav";
import { Button } from "@/components/ui/button";
import {
  createGeneralAgentEvaluation,
  deleteGeneralAgentEvaluation,
  listGeneralAgentEvaluationDatasets,
  listGeneralAgentEvaluations,
} from "@/lib/api/general-agent-evaluation";
import { listGeneralAgentRuns } from "@/lib/api/general-agent";
import {
  evaluationOutcomeLabel,
  generalAgentEvaluationCategoryLabels,
  matchingRunsForCase,
  scoreLabel,
} from "@/lib/general-agent-evaluation-view";
import { generalCapabilityLabel } from "@/lib/general-agent-display";
import type {
  GeneralAgentEvaluationCase,
  GeneralAgentEvaluationDataset,
  GeneralAgentEvaluationRecord,
} from "@/lib/types/general-agent-evaluation";
import type { GeneralAgentRunSummary } from "@/lib/types/general-agent";
import { cn } from "@/lib/utils";

export function GeneralAgentEvaluationShell() {
  const [datasets, setDatasets] = useState<GeneralAgentEvaluationDataset[]>([]);
  const [runs, setRuns] = useState<GeneralAgentRunSummary[]>([]);
  const [evaluations, setEvaluations] = useState<GeneralAgentEvaluationRecord[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [runId, setRunId] = useState("");
  const [selectedEvaluation, setSelectedEvaluation] = useState<GeneralAgentEvaluationRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const selectedDataset = datasets.find(item => item.dataset_id === datasetId) ?? null;
  const selectedCase = selectedDataset?.cases.find(item => item.case_id === caseId) ?? null;
  const matchingRuns = selectedCase ? matchingRunsForCase(runs, selectedCase) : [];
  const effectiveRunId = matchingRuns.some(run => run.run_id === runId)
    ? runId
    : (matchingRuns[0]?.run_id ?? "");

  const load = useCallback(async () => {
    const [datasetResponse, runResponse, evaluationResponse] = await Promise.all([
      listGeneralAgentEvaluationDatasets(),
      listGeneralAgentRuns({ pageSize: 100 }),
      listGeneralAgentEvaluations(),
    ]);
    setDatasets(datasetResponse.datasets);
    setRuns(runResponse.runs);
    setEvaluations(evaluationResponse.evaluations);
    setDatasetId(current => current || datasetResponse.datasets[0]?.dataset_id || "");
    setCaseId(current => current || datasetResponse.datasets[0]?.cases[0]?.case_id || "");
    setSelectedEvaluation(current => current ?? evaluationResponse.evaluations[0] ?? null);
  }, []);

  useEffect(() => {
    let ignore = false;
    async function initialLoad() {
      try {
        await load();
        if (!ignore) setError("");
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
  }, [load]);

  function chooseDataset(nextDatasetId: string) {
    const dataset = datasets.find(item => item.dataset_id === nextDatasetId);
    setDatasetId(nextDatasetId);
    setCaseId(dataset?.cases[0]?.case_id ?? "");
    setRunId("");
    setSelectedEvaluation(null);
  }

  function chooseCase(nextCaseId: string) {
    setCaseId(nextCaseId);
    setRunId("");
    setSelectedEvaluation(null);
  }

  async function handleEvaluate() {
    if (!datasetId || !caseId || !effectiveRunId) return;
    setBusy(true);
    setError("");
    try {
      const response = await createGeneralAgentEvaluation({
        dataset_id: datasetId,
        case_id: caseId,
        run_id: effectiveRunId,
      });
      setSelectedEvaluation(response.evaluation);
      setEvaluations(current => [
        response.evaluation,
        ...current.filter(item => item.evaluation_id !== response.evaluation.evaluation_id),
      ]);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(evaluationId: string) {
    if (!window.confirm("删除这条通用写作助手评估记录？原任务不会被删除。")) return;
    setBusy(true);
    try {
      await deleteGeneralAgentEvaluation(evaluationId);
      const next = evaluations.filter(item => item.evaluation_id !== evaluationId);
      setEvaluations(next);
      if (selectedEvaluation?.evaluation_id === evaluationId) {
        setSelectedEvaluation(next[0] ?? null);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function copyQuestion() {
    if (!selectedCase) return;
    await navigator.clipboard.writeText(selectedCase.user_goal);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto grid h-full min-h-0 max-w-[1540px] grid-rows-[auto_minmax(0,1fr)] gap-4 px-4 py-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <div className="xl:col-span-2">
          <GeneralAgentMonitorNav active="evaluation" />
        </div>
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">效果评测</p>
              <h1 className="text-lg font-semibold text-[var(--tc-text-primary)]">通用写作助手</h1>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="刷新评测资料" onClick={() => void load()}>
              <RefreshCw className="size-4" />
            </Button>
          </div>
          <Link href="/task-monitor" className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]">
            <ChevronLeft className="size-3" />返回任务入口
          </Link>
          <h2 className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3 text-xs font-medium text-[var(--tc-text-primary)]">历史评估</h2>
          <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
            {loading ? (
              <p className="py-3 text-sm text-[var(--tc-text-muted)]">正在读取评测资料</p>
            ) : evaluations.length === 0 ? (
              <p className="py-3 text-sm text-[var(--tc-text-muted)]">暂无评估记录</p>
            ) : (
              <div className="grid gap-1">
                {evaluations.map(evaluation => (
                  <div key={evaluation.evaluation_id} className={cn("flex items-stretch rounded-[var(--tc-radius-control)]", selectedEvaluation?.evaluation_id === evaluation.evaluation_id ? "bg-[var(--tc-surface-muted)]" : "hover:bg-[var(--tc-surface-muted)]")}>
                    <button type="button" className="min-w-0 flex-1 px-3 py-2 text-left" onClick={() => setSelectedEvaluation(evaluation)}>
                      <span className="block truncate text-sm font-medium text-[var(--tc-text-primary)]">{evaluation.case_label}</span>
                      <span className="mt-1 flex justify-between gap-2 text-xs text-[var(--tc-text-muted)]"><span>{evaluationOutcomeLabel(evaluation)}</span><span>{scoreLabel(evaluation.overall_score)}</span></span>
                    </button>
                    <Button type="button" variant="ghost" size="icon-sm" disabled={busy} aria-label={`删除${evaluation.case_label}评估`} className="my-1 mr-1" onClick={() => void handleDelete(evaluation.evaluation_id)}>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 flex-col gap-3 overflow-hidden">
          {error ? <div className="shrink-0 rounded-[var(--tc-radius-control)] border border-red-700/70 bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">{error}</div> : null}
          <section className="shrink-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
            <div className="flex flex-wrap items-end gap-3">
              <SelectField label="评测集" value={datasetId} onChange={chooseDataset} options={datasets.map(item => ({ value: item.dataset_id, label: item.label }))} />
              <SelectField label="评测样例" value={caseId} onChange={chooseCase} options={(selectedDataset?.cases ?? []).map(item => ({ value: item.case_id, label: item.label }))} />
              <SelectField label="匹配的历史任务" value={effectiveRunId} onChange={setRunId} options={matchingRuns.map(run => ({ value: run.run_id, label: `${formatTime(run.created_at)} · ${run.status}` }))} placeholder="暂无同题任务" />
              <Button type="button" disabled={busy || !effectiveRunId} onClick={() => void handleEvaluate()}>
                <Scale className="size-4" />{busy ? "正在评估" : "开始评估"}
              </Button>
            </div>
            {selectedDataset ? <p className="mt-2 text-xs text-[var(--tc-text-muted)]">{selectedDataset.description} · 共 {selectedDataset.cases.length} 题</p> : null}
          </section>

          <section className="grid min-h-0 flex-1 gap-3 overflow-hidden 2xl:grid-cols-[minmax(0,0.92fr)_minmax(420px,1.08fr)]">
            <div className="min-h-0 overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
              {selectedCase ? <CaseBrief evaluationCase={selectedCase} copied={copied} onCopy={() => void copyQuestion()} matchingRunCount={matchingRuns.length} /> : <p className="text-sm text-[var(--tc-text-muted)]">请选择评测样例。</p>}
            </div>
            <div className="min-h-0 overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
              {selectedEvaluation ? <EvaluationDetail evaluation={selectedEvaluation} /> : <div className="flex h-full min-h-52 items-center justify-center text-sm text-[var(--tc-text-muted)]">运行同题任务后即可生成确定性评估。</div>}
            </div>
          </section>
        </main>
      </section>
    </AppShell>
  );
}

function CaseBrief({ evaluationCase, copied, onCopy, matchingRunCount }: { evaluationCase: GeneralAgentEvaluationCase; copied: boolean; onCopy: () => void; matchingRunCount: number }) {
  const required = [
    ...evaluationCase.expected.required_capabilities.map(generalCapabilityLabel),
    ...evaluationCase.expected.required_capability_groups.map(group => group.map(generalCapabilityLabel).join(" / ")),
  ];
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div><p className="text-xs text-[var(--tc-text-muted)]">{generalAgentEvaluationCategoryLabels[evaluationCase.category]}</p><h2 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">{evaluationCase.label}</h2></div>
        <Button type="button" variant="outline" size="sm" onClick={onCopy}><Clipboard className="size-4" />{copied ? "已复制" : "复制问题"}</Button>
      </div>
      <Block title="评测问题" text={evaluationCase.user_goal} />
      <Block title="参考答案" text={evaluationCase.reference_answer} />
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <Metric label="正文范围" value={scopeLabel(evaluationCase.scope_type)} />
        <Metric label="节点范围" value={`${evaluationCase.expected.min_node_count}–${evaluationCase.expected.max_node_count} 个`} />
        <Metric label="必要能力" value={required.join("、") || "直接回答"} />
        <Metric label="同题任务" value={`${matchingRunCount} 个`} />
      </div>
      {matchingRunCount === 0 ? <div className="mt-4 rounded-[var(--tc-radius-control)] border border-amber-700/50 bg-amber-950/15 p-3 text-xs text-amber-100"><p className="font-medium">还没有同题运行记录</p><p className="mt-1 text-amber-100/70">复制问题到通用写作助手运行；任务完成或进入预期人工中断后，再回到这里评估。</p></div> : null}
      {evaluationCase.assessment_mode === "deterministic_with_human_review" ? <div className="mt-4 flex gap-2 rounded-[var(--tc-radius-control)] border border-blue-700/40 bg-blue-950/15 p-3 text-xs text-blue-100"><ShieldAlert className="mt-0.5 size-4 shrink-0" /><p>自动评分只判断路径、安全和参考要点；文风、叙事张力与创作质量仍需人工复核。</p></div> : null}
    </div>
  );
}

function EvaluationDetail({ evaluation }: { evaluation: GeneralAgentEvaluationRecord }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3"><div><p className="text-xs text-[var(--tc-text-muted)]">评估结果</p><h2 className="mt-1 text-lg font-semibold text-[var(--tc-text-primary)]">{evaluationOutcomeLabel(evaluation)}</h2></div><div className={cn("rounded-[var(--tc-radius-pill)] border px-3 py-1 text-sm font-semibold", evaluation.passed ? "border-emerald-700/60 text-emerald-200" : "border-red-700/60 text-red-200")}>{scoreLabel(evaluation.overall_score)}</div></div>
      <div className="mt-4 grid gap-2">
        {evaluation.dimensions.map(dimension => (
          <details key={dimension.dimension} open={!dimension.passed} className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2">
            <summary className="cursor-pointer list-none"><span className="flex items-center justify-between gap-3 text-sm"><span className="flex items-center gap-2 text-[var(--tc-text-primary)]">{dimension.passed ? <Check className="size-4 text-emerald-300" /> : <X className="size-4 text-red-300" />}{dimension.label}</span><span className="text-[var(--tc-text-muted)]">{scoreLabel(dimension.score)} · 权重 {Math.round(dimension.weight * 100)}%</span></span></summary>
            <div className="mt-2 grid gap-1.5 border-t border-[var(--tc-border-subtle)] pt-2">
              {dimension.checks.map(check => <div key={check.check_id} className="flex gap-2 text-xs"><span className={check.passed ? "text-emerald-300" : "text-red-300"}>{check.passed ? "通过" : "未过"}</span><span className="text-[var(--tc-text-secondary)]"><strong className="font-medium text-[var(--tc-text-primary)]">{check.label}</strong> · {check.detail}{check.critical && !check.passed ? "（关键项）" : ""}</span></div>)}
            </div>
          </details>
        ))}
      </div>
      <Block title="实际答案" text={evaluation.actual_answer || "该任务停在人工授权边界，尚无最终答案。"} />
      <Block title="冻结的参考答案" text={evaluation.reference_answer} />
    </div>
  );
}

function SelectField({ label, value, onChange, options, placeholder = "请选择" }: { label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }>; placeholder?: string }) {
  return <label className="grid min-w-[210px] flex-1 gap-1 text-xs text-[var(--tc-text-muted)]"><span>{label}</span><select className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2.5 text-sm text-[var(--tc-text-primary)] outline-none" value={value} onChange={event => onChange(event.target.value)}><option value="">{placeholder}</option>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function Block({ title, text }: { title: string; text: string }) { return <div className="mt-4"><h3 className="text-xs font-medium text-[var(--tc-text-primary)]">{title}</h3><p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-secondary)]">{text}</p></div>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-2.5"><p className="text-[var(--tc-text-muted)]">{label}</p><p className="mt-1 text-[var(--tc-text-primary)]">{value}</p></div>; }
function scopeLabel(scope: GeneralAgentEvaluationCase["scope_type"]): string { return { none: "无需正文", selection: "选区", chapter: "单章", range: "多章", novel: "全文" }[scope]; }
function formatTime(value: string): string { return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function errorMessage(error: unknown): string { return error instanceof Error ? error.message : "通用写作助手评测加载失败"; }
