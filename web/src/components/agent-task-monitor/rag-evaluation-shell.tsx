"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  Database,
  FlaskConical,
  GitCompareArrows,
  Info,
  Network,
  RefreshCw,
  Route,
  Settings2,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RAGMonitorNav } from "@/components/agent-task-monitor/rag-monitor-nav";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  getCurrentRAGEvaluationSuite,
  getRAGEvaluationConfiguration,
  getRAGEvaluationResult,
  listRAGEvaluationResults,
} from "@/lib/api/rag-evaluation";
import type {
  RAGCaseScore,
  RAGEvaluationConfiguration,
  RAGEvaluationResultDetail,
  RAGEvaluationResultSummary,
  RAGGoldenCase,
  RAGGoldenCategory,
  RAGGoldenSuite,
  RAGRunReport,
  RAGSemanticCaseFailure,
  RAGSemanticCaseResult,
  RAGSemanticCaseScore,
} from "@/lib/types/rag-evaluation";
import { cn } from "@/lib/utils";

type ViewName = "results" | "dataset";

const categories: Array<{ value: RAGGoldenCategory | "all"; label: string }> = [
  { value: "all", label: "全部" },
  { value: "single_fact", label: "单事实" },
  { value: "cross_source", label: "跨来源" },
  { value: "graph_multi_hop", label: "图多跳" },
  { value: "hard_negative", label: "困难负例" },
];

const categoryLabels: Record<RAGGoldenCategory, string> = {
  single_fact: "单事实",
  cross_source: "跨来源",
  graph_multi_hop: "图多跳",
  hard_negative: "困难负例",
};

export function RAGEvaluationShell() {
  const [suite, setSuite] = useState<RAGGoldenSuite | null>(null);
  const [results, setResults] = useState<RAGEvaluationResultSummary[]>([]);
  const [configuration, setConfiguration] = useState<RAGEvaluationConfiguration | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<RAGEvaluationResultDetail | null>(null);
  const [view, setView] = useState<ViewName>("results");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [nextSuite, nextResults, nextConfiguration] = await Promise.all([
      getCurrentRAGEvaluationSuite(),
      listRAGEvaluationResults(20),
      getRAGEvaluationConfiguration(),
    ]);
    setSuite(nextSuite);
    setResults(nextResults);
    setConfiguration(nextConfiguration);
    if (!nextResults.length) setDetail(null);
    setSelectedRunId(current =>
      nextResults.some(item => item.run_id === current)
        ? current
        : nextResults[0]?.run_id ?? "",
    );
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
    return () => { ignore = true; };
  }, [load]);

  useEffect(() => {
    if (!selectedRunId) return;
    let ignore = false;
    getRAGEvaluationResult(selectedRunId)
      .then(next => {
        if (!ignore) {
          setDetail(next);
          setError("");
        }
      })
      .catch(caught => {
        if (!ignore) setError(errorMessage(caught));
      })
      .finally(() => {
        if (!ignore) setDetailLoading(false);
      });
    return () => { ignore = true; };
  }, [selectedRunId]);

  async function refresh() {
    setRefreshing(true);
    try {
      await load();
      setError("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto h-full w-full max-w-[1200px] overflow-y-auto px-5 py-3">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href="/task-monitor" className="inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]">
              <ChevronLeft className="size-3" />返回任务入口
            </Link>
            <span className="flex items-center gap-2">
              <FlaskConical className="size-4 text-[var(--tc-monitor-rag)]" />
              <h1 className="text-base font-semibold text-[var(--tc-text-primary)]">RAG 质量评测</h1>
            </span>
          </div>
          <Button type="button" variant="outline" size="sm" disabled={loading || refreshing} onClick={() => void refresh()}>
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />刷新结果
          </Button>
        </header>

        <div className="mt-3"><RAGMonitorNav active="evaluation" /></div>
        <div className="mt-3 flex gap-1 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] p-1">
          <ViewButton active={view === "results"} onClick={() => setView("results")}>评测结果</ViewButton>
          <ViewButton active={view === "dataset"} onClick={() => setView("dataset")}>当前评测集</ViewButton>
        </div>

        {error ? (
          <div className="mt-3 flex items-center gap-2 rounded-[var(--tc-radius-control)] bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            <AlertCircle className="size-4 text-red-400" />{error}
          </div>
        ) : null}

        {view === "results" ? (
          <ResultsView
            results={results}
            selectedRunId={selectedRunId}
            onSelect={runId => {
              setDetail(null);
              setDetailLoading(true);
              setSelectedRunId(runId);
            }}
            detail={detail}
            detailLoading={detailLoading || loading}
            configuration={configuration}
            suite={suite}
          />
        ) : <DatasetView suite={suite} loading={loading} />}
      </section>
    </AppShell>
  );
}

function ViewButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cn(
      "rounded-[var(--tc-radius-control)] px-3 py-1.5 text-xs transition-colors duration-150 motion-reduce:transition-none",
      active ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]" : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
    )}>{children}</button>
  );
}

function ResultsView({ results, selectedRunId, onSelect, detail, detailLoading, configuration, suite }: {
  results: RAGEvaluationResultSummary[];
  selectedRunId: string;
  onSelect: (runId: string) => void;
  detail: RAGEvaluationResultDetail | null;
  detailLoading: boolean;
  configuration: RAGEvaluationConfiguration | null;
  suite: RAGGoldenSuite | null;
}) {
  const report = isCompletedReport(detail) ? detail : null;
  const summary = report?.deterministic.summary;
  return (
    <>
      <section className="mt-3 grid grid-cols-5 gap-1.5">
        <Metric label="自动门禁" description="所有预设质量门槛均满足时通过；未通过不会修改评测数据。" value={gateLabel(detail)} />
        <Metric label="Recall@10" description="前 10 条检索结果中，找回预期知识来源的比例。" value={formatScore(summary?.mean_recall_at_k)} />
        <Metric label="MRR@10" description="正确结果在前 10 条中的排序质量；越靠前分数越高，第一名为 100%。" value={formatScore(summary?.mean_mrr_at_k)} />
        <Metric label="Relation Recall@10" description="前 10 条结果关联出的关系中，找回预期关系边的比例；仅图关系用例适用。" value={formatScore(summary?.mean_relation_recall_at_k)} />
        <Metric label="Complete Path Recall" description="预期多跳关系链是否完整命中；路径中的关系均找回才计为成功。" value={formatScore(summary?.complete_path_pass_rate)} />
      </section>
      <section className="mt-3 grid min-h-[390px] grid-cols-[300px_minmax(0,1fr)] gap-3">
        <ResultHistory results={results} selectedRunId={selectedRunId} onSelect={onSelect} />
        <ResultDetail detail={detail} loading={detailLoading} suite={suite} />
      </section>
      <EvaluationArchitecture configuration={configuration} />
    </>
  );
}

function ResultHistory({ results, selectedRunId, onSelect }: {
  results: RAGEvaluationResultSummary[];
  selectedRunId: string;
  onSelect: (runId: string) => void;
}) {
  return (
    <section className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-3">
      <div className="px-1"><h2 className="text-sm font-medium text-[var(--tc-text-primary)]">运行记录</h2><p className="mt-0.5 text-xs text-[var(--tc-text-muted)]">最近二十次自动回归</p></div>
      <div className="mt-2 grid max-h-[340px] gap-1 overflow-y-auto pr-1">
        {results.map(result => (
          <button key={result.run_id} type="button" onClick={() => onSelect(result.run_id)} className={cn(
            "flex w-full items-center gap-2 rounded-[var(--tc-radius-control)] px-2.5 py-2 text-left transition-colors duration-150 motion-reduce:transition-none",
            selectedRunId === result.run_id ? "bg-[var(--tc-surface-muted)]" : "hover:bg-[color-mix(in_srgb,var(--tc-surface-muted),transparent_45%)]",
          )}>
            <Database className="size-4 shrink-0 text-[var(--tc-monitor-rag)]" />
            <span className="min-w-0 flex-1">
              <span className="tc-mono-font block truncate text-[11px] text-[var(--tc-text-primary)]">{result.run_id}</span>
              <span className="mt-0.5 block truncate text-[10px] text-[var(--tc-text-muted)]">{modeLabel(result.mode)} · {formatTime(result.created_at)}</span>
            </span>
            <span className={cn("shrink-0 text-[11px]", resultStatusClass(result))}>{resultStatusLabel(result)}</span>
          </button>
        ))}
        {!results.length ? <p className="px-3 py-8 text-center text-sm text-[var(--tc-text-muted)]">暂无评测结果</p> : null}
      </div>
    </section>
  );
}

function ResultDetail({ detail, loading, suite }: { detail: RAGEvaluationResultDetail | null; loading: boolean; suite: RAGGoldenSuite | null }) {
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  if (loading && !detail) return <EmptyPanel text="正在读取评测结果" />;
  if (!detail) return <EmptyPanel text="选择一条运行记录查看完整结果" />;
  if (!isCompletedReport(detail)) {
    return (
      <section className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-5">
        <div className="flex items-center gap-2 text-red-400"><XCircle className="size-4" /><h2 className="text-sm font-medium">基础设施失败</h2></div>
        <p className="mt-3 text-sm leading-6 text-[var(--tc-text-secondary)]">{detail.error_message}</p>
        <p className="tc-mono-font mt-2 text-xs text-[var(--tc-text-muted)]">{detail.error_type} · {formatTime(detail.created_at)}</p>
      </section>
    );
  }

  const semanticFailureGroups = summarizeSemanticFailureGroups(detail);

  return (
    <section className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            {detail.gate.passed ? <ShieldCheck className="size-4 text-green-400" /> : <AlertCircle className="size-4 text-red-400" />}
            <h2 className="text-sm font-medium text-[var(--tc-text-primary)]">{detail.gate.passed ? "自动门禁通过" : "自动门禁未通过"}</h2>
          </div>
          <p className="mt-1 text-xs text-[var(--tc-text-muted)]">{modeLabel(detail.deterministic.mode)} · {detail.deterministic.summary.case_count} 条用例 · Top {detail.deterministic.top_k}</p>
        </div>
        <span className="tc-mono-font text-[11px] text-[var(--tc-text-muted)]">{formatTime(detail.deterministic.created_at)}</span>
      </div>

      {detail.gate.failures.length ? (
        <div className="mt-3 rounded-[var(--tc-radius-control)] bg-red-950/20 px-3 py-2">
          <p className="text-xs font-medium text-red-300">门禁诊断</p>
          <ul className="mt-1 grid gap-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
            {detail.gate.failures.map(failure => <li key={failure}>· {failure}</li>)}
          </ul>
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-3 gap-1.5">
        <CompactFact label="权威回源" value={formatScore(detail.deterministic.summary.authority_pass_rate)} />
        <CompactFact label="图关系用例" value={`${detail.deterministic.summary.graph_case_count} 条`} />
        <CompactFact label="语义评测" value={summarizeSemantic(detail)} />
      </div>

      {semanticFailureGroups.length ? (
        <div className="mt-3 rounded-[var(--tc-radius-control)] bg-red-950/20 px-3 py-2">
          <p className="text-xs font-medium text-red-300">语义评测执行异常</p>
          <ul className="mt-1 grid gap-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
            {semanticFailureGroups.map(group => (
              <li key={group.message}>· {group.count} 条未完成：{group.message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-3 flex items-center gap-2 px-1"><CircleGauge className="size-3.5 text-[var(--tc-monitor-rag)]" /><h3 className="text-xs font-medium text-[var(--tc-text-primary)]">逐案结果</h3><span className="text-[10px] text-[var(--tc-text-muted)]">点击用例查看预期与实际结果</span></div>
      <div className="mt-1.5 max-h-[390px] overflow-y-auto rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] p-1">
        <div className="grid grid-cols-[18px_82px_1fr_1fr_1fr_1fr_56px] gap-2 px-2 py-1 text-[10px] text-[var(--tc-text-muted)]">
          <span /><MetricTableHeading label="用例" /><MetricTableHeading label="Recall@10" description="前 10 条检索结果中找回预期来源的比例。" /><MetricTableHeading label="MRR@10" description="正确结果在前 10 条中的排序质量。" /><MetricTableHeading label="Relation Recall@10" description="前 10 条中找回预期关系边的比例。" /><MetricTableHeading label="Complete Path Recall" description="预期多跳关系链完整命中的比例。" /><span>回源</span>
        </div>
        {detail.deterministic.case_scores.map(score => {
          const goldenCase = suite?.cases.find(item => item.case_id === score.case_id) ?? null;
          return <CaseScoreRow key={score.case_id} score={score} goldenCase={goldenCase} expanded={expandedCaseId === score.case_id} onToggle={() => setExpandedCaseId(current => current === score.case_id ? null : score.case_id)} />;
        })}
      </div>
    </section>
  );
}

function CaseScoreRow({ score, goldenCase, expanded, onToggle }: { score: RAGCaseScore; goldenCase: RAGGoldenCase | null; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="rounded-[var(--tc-radius-control)]">
      <button type="button" aria-expanded={expanded} aria-controls={`rag-case-${score.case_id}`} onClick={onToggle} className="grid w-full grid-cols-[18px_82px_1fr_1fr_1fr_1fr_56px] gap-2 rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-[11px] text-[var(--tc-text-secondary)] transition-colors duration-150 hover:bg-[var(--tc-surface-card)] motion-reduce:transition-none">
        <ChevronRight className={cn("mt-0.5 size-3 text-[var(--tc-text-muted)] transition-transform duration-150 motion-reduce:transition-none", expanded && "rotate-90")} />
        <span className="tc-mono-font text-[var(--tc-text-primary)]">{score.case_id}</span>
        <span>{formatScore(score.recall_at_k)}</span><span>{formatScore(score.mrr_at_k)}</span><span>{formatScore(score.relation_recall_at_k)}</span><span>{formatScore(score.complete_path_recall)}</span>
        <span className={score.authority_verified ? "text-green-400" : "text-red-400"}>{score.authority_verified ? "通过" : "失败"}</span>
      </button>
      {expanded ? <CaseScoreDetail id={`rag-case-${score.case_id}`} score={score} goldenCase={goldenCase} /> : null}
    </div>
  );
}

function CaseScoreDetail({ id, score, goldenCase }: { id: string; score: RAGCaseScore; goldenCase: RAGGoldenCase | null }) {
  return (
    <div id={id} className="mx-1 mb-1 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] p-3 text-xs leading-5 text-[var(--tc-text-secondary)]">
      <p className="text-[var(--tc-text-primary)]"><span className="text-[var(--tc-text-muted)]">检索问题：</span>{goldenCase?.query ?? "当前评测集已更新，未找到该用例定义。"}</p>
      <div className="mt-2 grid grid-cols-2 gap-3">
        <ScoreDetailGroup title="预期来源" values={goldenCase?.expected_source_ids ?? []} emptyText="该用例不要求命中指定来源。" />
        <ScoreDetailGroup title="实际召回来源" values={score.retrieved_source_ids} emptyText="未召回来源。" />
        <ScoreDetailGroup title="预期关系" values={goldenCase?.expected_relations.map(relation => relation.text || `${relation.subject} → ${relation.predicate} → ${relation.object}`) ?? []} emptyText="该用例不验证关系。" />
        <ScoreDetailGroup title="实际召回关系" values={score.retrieved_relation_ids} emptyText="未召回关系。" />
      </div>
      {goldenCase?.expected_path.length ? <p className="mt-2"><span className="text-[var(--tc-text-muted)]">预期路径：</span>{goldenCase.expected_path.join(" → ")}</p> : null}
    </div>
  );
}

function ScoreDetailGroup({ title, values, emptyText }: { title: string; values: string[]; emptyText: string }) {
  return <div><p className="text-[10px] text-[var(--tc-text-muted)]">{title}</p>{values.length ? <div className="mt-1 flex flex-wrap gap-1">{values.map(value => <span key={value} className="tc-mono-font rounded bg-[var(--tc-surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--tc-text-secondary)]">{value}</span>)}</div> : <p className="mt-1 text-[11px] text-[var(--tc-text-muted)]">{emptyText}</p>}</div>;
}

function EvaluationArchitecture({ configuration }: { configuration: RAGEvaluationConfiguration | null }) {
  return (
    <section className="mt-3 grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-3 pb-4">
      <div className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-4">
        <div className="flex items-center gap-2"><Workflow className="size-4 text-[var(--tc-monitor-rag)]" /><h2 className="text-sm font-medium text-[var(--tc-text-primary)]">评测链路</h2></div>
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          {configuration?.pipeline.map(stage => (
            <div key={stage.key} className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2">
              <p className="tc-mono-font text-[10px] text-[var(--tc-monitor-rag)]">{String(stage.order).padStart(2, "0")}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--tc-text-primary)]">{stage.name}</p>
              <p className="mt-1 text-[11px] leading-4 text-[var(--tc-text-muted)]">{stage.description}</p>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2 px-1"><GitCompareArrows className="size-3.5 text-[var(--tc-monitor-rag)]" /><h3 className="text-xs font-medium text-[var(--tc-text-primary)]">CI 触发策略</h3></div>
        <div className="mt-1.5 grid gap-1">
          {configuration?.ci_policies.map(policy => (
            <div key={policy.name} className="grid grid-cols-[120px_170px_1fr] gap-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2 text-[11px]">
              <span className="text-[var(--tc-text-primary)]">{policy.name}</span><span className="text-[var(--tc-text-muted)]">{policy.trigger}</span><span className="text-[var(--tc-text-secondary)]">{policy.scope}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-4">
        <div className="flex items-center gap-2"><Settings2 className="size-4 text-[var(--tc-monitor-rag)]" /><h2 className="text-sm font-medium text-[var(--tc-text-primary)]">重要参数</h2></div>
        <div className="mt-3 grid grid-cols-2 gap-1.5">
          {configuration?.parameters.map(parameter => (
            <div key={parameter.key} title={parameter.description} className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2">
              <p className="text-[10px] text-[var(--tc-text-muted)]">{parameter.name}</p><p className="tc-mono-font mt-0.5 text-sm font-medium text-[var(--tc-text-primary)]">{parameter.value}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function DatasetView({ suite, loading }: { suite: RAGGoldenSuite | null; loading: boolean }) {
  const [selectedId, setSelectedId] = useState("");
  const [category, setCategory] = useState<RAGGoldenCategory | "all">("all");
  const filteredCases = useMemo(() => suite?.cases.filter(item => category === "all" || item.category === category) ?? [], [category, suite]);
  const selected = filteredCases.find(item => item.case_id === selectedId) ?? filteredCases[0] ?? null;
  const graphCount = suite?.cases.filter(item => item.graph_required).length ?? 0;
  const smokeCount = suite?.cases.filter(item => item.smoke).length ?? 0;

  function selectCategory(next: RAGGoldenCategory | "all") {
    setCategory(next);
    const first = suite?.cases.find(item => next === "all" || item.category === next);
    setSelectedId(first?.case_id ?? "");
  }

  return (
    <>
      <section className="mt-3 grid grid-cols-4 gap-1.5">
        <Metric label="当前评测集" value={suite?.suite_id ?? "正在读取"} compact />
        <Metric label="Golden 用例" value={formatCount(suite?.cases.length)} />
        <Metric label="Graph 多跳" value={formatCount(graphCount)} />
        <Metric label="PR 冒烟" value={formatCount(smokeCount)} />
      </section>
      <section className="mt-3 grid min-h-[520px] grid-cols-[380px_minmax(0,1fr)] gap-3 pb-4">
        <div className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-3">
          <div className="flex flex-wrap gap-1">
            {categories.map(item => (
              <button key={item.value} type="button" aria-pressed={category === item.value} onClick={() => selectCategory(item.value)} className={cn(
                "rounded-[var(--tc-radius-control)] px-2 py-1 text-xs transition-colors duration-150 motion-reduce:transition-none",
                category === item.value ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]" : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
              )}>{item.label}</button>
            ))}
          </div>
          <div className="mt-2 grid max-h-[450px] gap-1 overflow-y-auto pr-1">
            {filteredCases.map(item => <CaseRow key={item.case_id} item={item} selected={item.case_id === selected?.case_id} onSelect={() => setSelectedId(item.case_id)} />)}
            {!filteredCases.length ? <p className="px-2 py-8 text-center text-sm text-[var(--tc-text-muted)]">{loading ? "正在读取评测集" : "当前分类没有用例"}</p> : null}
          </div>
        </div>
        <CaseDetail item={selected} loading={loading} />
      </section>
    </>
  );
}

function CaseRow({ item, selected, onSelect }: { item: RAGGoldenCase; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} className={cn(
      "flex w-full min-w-0 items-center gap-2 overflow-hidden rounded-[var(--tc-radius-control)] px-2.5 py-2 text-left transition-colors duration-150 motion-reduce:transition-none",
      selected ? "bg-[var(--tc-surface-muted)]" : "hover:bg-[color-mix(in_srgb,var(--tc-surface-muted),transparent_45%)]",
    )}>
      <span className="tc-mono-font w-20 shrink-0 text-[11px] text-[var(--tc-text-muted)]">{item.case_id}</span><span className="min-w-0 flex-1 truncate text-sm text-[var(--tc-text-primary)]">{item.query}</span>
      {item.smoke ? <span className="shrink-0 text-[10px] text-[var(--tc-monitor-rag)]">冒烟</span> : null}
    </button>
  );
}

function CaseDetail({ item, loading }: { item: RAGGoldenCase | null; loading: boolean }) {
  if (!item) return <EmptyPanel text={loading ? "正在读取用例详情" : "请选择一条评测用例"} />;
  return (
    <article className="rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] p-5">
      <div className="flex items-center gap-2 text-xs text-[var(--tc-text-muted)]"><span className="tc-mono-font">{item.case_id}</span><span>{categoryLabels[item.category]}</span>{item.graph_required ? <span className="inline-flex items-center gap-1 text-[var(--tc-monitor-rag)]"><Route className="size-3" />需要图关系</span> : null}</div>
      <h2 className="mt-2 text-xl font-semibold leading-8 text-[var(--tc-text-primary)]">{item.query}</h2>
      <DetailBlock title="参考答案"><p>{item.reference_answer}</p></DetailBlock>
      <DetailBlock title="期望事实"><ul className="grid gap-1">{item.expected_claims.map(claim => <li key={claim} className="flex gap-2"><CheckCircle2 className="mt-1 size-3.5 shrink-0 text-[var(--tc-monitor-rag)]" /><span>{claim}</span></li>)}</ul></DetailBlock>
      <DetailBlock title="期望来源">{item.expected_source_ids.length ? <div className="flex flex-wrap gap-1.5">{item.expected_source_ids.map(sourceId => <span key={sourceId} className="tc-mono-font rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-2 py-1 text-[11px] text-[var(--tc-text-secondary)]">{sourceId}</span>)}</div> : <p className="text-[var(--tc-text-muted)]">困难负例不指定命中来源，重点检查正确拒答。</p>}</DetailBlock>
      {item.expected_relations.length ? <DetailBlock title="完整关系链"><div className="grid gap-1.5">{item.expected_relations.map((relation, index) => <div key={relation.relation_id} className="flex items-center gap-2 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-2.5 py-2 text-xs"><span className="tc-mono-font text-[var(--tc-text-muted)]">{String(index + 1).padStart(2, "0")}</span><Network className="size-3.5 text-[var(--tc-monitor-rag)]" /><span className="text-[var(--tc-text-primary)]">{relation.subject} → {relation.predicate} → {relation.object}</span></div>)}</div></DetailBlock> : null}
    </article>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="mt-5 text-sm leading-6 text-[var(--tc-text-secondary)]"><h3 className="mb-1 text-xs text-[var(--tc-text-muted)]">{title}</h3>{children}</section>;
}

function Metric({ label, value, description, compact = false }: { label: string; value: string; description?: string; compact?: boolean }) {
  return <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-2"><MetricLabel label={label} description={description} /><p className={cn("tc-mono-font mt-0.5 truncate font-medium text-[var(--tc-text-primary)]", compact ? "text-sm" : "text-base")} title={value}>{value}</p></div>;
}

function MetricTableHeading({ label, description }: { label: string; description?: string }) {
  return <MetricLabel label={label} description={description} className="text-[10px]" />;
}

function MetricLabel({ label, description, className }: { label: string; description?: string; className?: string }) {
  if (!description) return <span className={cn("text-[11px] text-[var(--tc-text-muted)]", className)}>{label}</span>;
  return (
    <span
      title={description}
      tabIndex={0}
      className={cn("group relative inline-flex w-fit items-center gap-1 text-[11px] text-[var(--tc-text-muted)]", className)}
    >
      {label}<Info className="size-3" aria-hidden="true" />
      <span role="tooltip" className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 hidden w-56 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-2 py-1.5 text-[11px] leading-4 text-[var(--tc-text-secondary)] shadow-[var(--tc-shadow-soft)] group-hover:block group-focus-within:block">{description}</span>
    </span>
  );
}

function CompactFact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2"><p className="text-[10px] text-[var(--tc-text-muted)]">{label}</p><p className="tc-mono-font mt-0.5 text-xs text-[var(--tc-text-primary)]">{value}</p></div>;
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="flex items-center justify-center rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] text-sm text-[var(--tc-text-muted)]">{text}</div>;
}

function isCompletedReport(detail: RAGEvaluationResultDetail | null): detail is RAGRunReport {
  return detail !== null && "deterministic" in detail;
}

function gateLabel(detail: RAGEvaluationResultDetail | null): string {
  if (!detail) return "—";
  if (!isCompletedReport(detail)) return "基础设施失败";
  return detail.gate.passed ? "通过" : "未通过";
}

function summarizeSemantic(report: RAGRunReport): string {
  const metrics = report.semantic_scores
    .filter(isSemanticCaseScore)
    .flatMap(item => item.metrics);
  const failureCount = report.semantic_scores.filter(isSemanticCaseFailure).length;
  const metricSummary = metrics.length
    ? `${metrics.filter(metric => metric.passed).length}/${metrics.length} 项通过`
    : "";
  const failureSummary = failureCount ? `${failureCount} 条执行失败` : "";
  return [metricSummary, failureSummary].filter(Boolean).join("，") || "本次未运行";
}

function isSemanticCaseScore(
  item: RAGSemanticCaseResult,
): item is RAGSemanticCaseScore {
  return "metrics" in item && Array.isArray(item.metrics);
}

function isSemanticCaseFailure(
  item: RAGSemanticCaseResult,
): item is RAGSemanticCaseFailure {
  return "status" in item && item.status === "failed";
}

function summarizeSemanticFailureGroups(
  report: RAGRunReport,
): Array<{ message: string; count: number }> {
  const counts = new Map<string, number>();
  for (const failure of report.semantic_scores.filter(isSemanticCaseFailure)) {
    const message = failure.error_message?.trim() || "模型未返回可用的评测结果。";
    counts.set(message, (counts.get(message) ?? 0) + 1);
  }
  return [...counts.entries()].map(([message, count]) => ({ message, count }));
}

function modeLabel(mode: string): string {
  if (mode === "smoke") return "五条冒烟";
  if (mode === "rag-pr") return "RAG 变更回归";
  if (mode === "full") return "发布前完整评测";
  if (mode === "deterministic") return "确定性回归";
  return "评测运行";
}

function resultStatusLabel(result: RAGEvaluationResultSummary): string {
  if (result.status === "infrastructure_failed") return "基础设施失败";
  if (result.passed === true) return "通过";
  if (result.passed === false) return "未通过";
  return "已完成";
}

function resultStatusClass(result: RAGEvaluationResultSummary): string {
  if (result.status === "infrastructure_failed" || result.passed === false) return "text-red-400";
  if (result.passed === true) return "text-green-400";
  return "text-[var(--tc-text-muted)]";
}

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : value.toLocaleString("zh-CN");
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "RAG 评测数据加载失败，请确认后端服务是否可用。";
}
