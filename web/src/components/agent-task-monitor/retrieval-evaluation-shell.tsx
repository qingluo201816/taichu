"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  RefreshCw,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  getRetrievalEvaluation,
  getRetrievalEvaluationDataset,
  listRetrievalEvaluations,
} from "@/lib/api/retrieval-evaluation";
import {
  formatPercent,
  metricAtK,
  retrievalCaseOutcome,
  retrievalEvaluationCategoryLabels,
  retrievalKnowledgeTypeLabels,
  retrievalStrategyLabel,
} from "@/lib/retrieval-evaluation-view";
import type {
  RetrievalEvaluationCase,
  RetrievalEvaluationCategory,
  RetrievalEvaluationDataset,
  RetrievalEvaluationFailure,
  RetrievalEvaluationListItem,
  RetrievalEvaluationRecord,
} from "@/lib/types/retrieval-evaluation";
import { cn } from "@/lib/utils";

type CategoryFilter = "all" | RetrievalEvaluationCategory;

const categoryOrder: RetrievalEvaluationCategory[] = [
  "exact_name_alias",
  "semantic_paraphrase",
  "state_relation_event_rule",
  "multi_entity_disambiguation",
  "no_answer_adversarial",
];

export function RetrievalEvaluationShell() {
  const [dataset, setDataset] = useState<RetrievalEvaluationDataset | null>(null);
  const [evaluations, setEvaluations] = useState<RetrievalEvaluationListItem[]>([]);
  const [evaluation, setEvaluation] = useState<RetrievalEvaluationRecord | null>(null);
  const [evaluationId, setEvaluationId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadPage = useCallback(async (preferredEvaluationId = "") => {
    const [datasetResponse, evaluationResponse] = await Promise.all([
      getRetrievalEvaluationDataset(),
      listRetrievalEvaluations(),
    ]);
    const nextEvaluations = evaluationResponse.evaluations;
    const targetEvaluationId = nextEvaluations.some(
      item => item.evaluation_id === preferredEvaluationId,
    )
      ? preferredEvaluationId
      : (nextEvaluations[0]?.evaluation_id ?? "");
    const detailResponse = targetEvaluationId
      ? await getRetrievalEvaluation(targetEvaluationId)
      : null;

    setDataset(datasetResponse.dataset);
    setEvaluations(nextEvaluations);
    setEvaluationId(targetEvaluationId);
    setEvaluation(detailResponse?.evaluation ?? null);
    setCaseId(current =>
      datasetResponse.dataset.cases.some(item => item.case_id === current)
        ? current
        : (datasetResponse.dataset.cases[0]?.case_id ?? ""),
    );
  }, []);

  useEffect(() => {
    let ignore = false;
    async function initialLoad() {
      try {
        await loadPage();
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
  }, [loadPage]);

  const filteredCases = useMemo(() => {
    if (!dataset) return [];
    return category === "all"
      ? dataset.cases
      : dataset.cases.filter(item => item.category === category);
  }, [category, dataset]);

  const selectedCase =
    dataset?.cases.find(item => item.case_id === caseId) ?? filteredCases[0] ?? null;
  const selectedFailure =
    evaluation?.failures.find(item => item.case_id === selectedCase?.case_id) ?? null;
  const summary = evaluation?.summary ?? null;

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      await loadPage(evaluationId);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRefreshing(false);
    }
  }

  async function chooseEvaluation(nextEvaluationId: string) {
    setEvaluationId(nextEvaluationId);
    setRefreshing(true);
    setError("");
    try {
      const response = await getRetrievalEvaluation(nextEvaluationId);
      setEvaluation(response.evaluation);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRefreshing(false);
    }
  }

  function chooseCategory(nextCategory: CategoryFilter) {
    setCategory(nextCategory);
    const nextCase =
      nextCategory === "all"
        ? dataset?.cases[0]
        : dataset?.cases.find(item => item.category === nextCategory);
    setCaseId(nextCase?.case_id ?? "");
  }

  return (
    <AppShell activePath="/task-monitor" viewportLocked>
      <section className="mx-auto flex h-full min-h-0 max-w-[1540px] flex-col gap-3 px-4 py-4">
        <header className="flex shrink-0 items-end justify-between gap-4">
          <div>
            <Link
              href="/task-monitor"
              className="inline-flex items-center gap-1 text-xs text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]"
            >
              <ChevronLeft className="size-3" />
              返回任务入口
            </Link>
            <div className="mt-2 flex items-center gap-2">
              <Search className="size-5 text-[var(--tc-agent-knowledge)]" />
              <div>
                <p className="text-xs text-[var(--tc-text-muted)]">统一知识召回</p>
                <h1 className="text-lg font-semibold text-[var(--tc-text-primary)]">
                  统一召回专项评测集
                </h1>
              </div>
            </div>
          </div>

          <div className="flex items-end gap-2">
            <label className="grid gap-1 text-xs text-[var(--tc-text-muted)]">
              基线记录
              <select
                value={evaluationId}
                disabled={loading || evaluations.length === 0 || refreshing}
                onChange={event => void chooseEvaluation(event.target.value)}
                className="h-9 min-w-72 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-text-primary)]"
              >
                {evaluations.length === 0 ? (
                  <option value="">暂无评测结果</option>
                ) : (
                  evaluations.map(item => (
                    <option key={item.evaluation_id} value={item.evaluation_id}>
                      {formatTime(item.finished_at)} · {item.failure_count} 个未通过
                    </option>
                  ))
                )}
              </select>
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={refreshing}
              onClick={() => void refresh()}
            >
              <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
              同步
            </Button>
          </div>
        </header>

        {error ? (
          <div className="shrink-0 rounded-[var(--tc-radius-control)] border border-red-700/70 bg-red-950/20 px-3 py-2 text-sm text-[var(--tc-text-primary)]">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)] gap-3">
          <aside className="flex min-h-0 flex-col overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
            <div className="shrink-0 border-b border-[var(--tc-border-subtle)] p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-medium text-[var(--tc-text-primary)]">
                    {dataset?.label ?? "正在读取评测集"}
                  </h2>
                  <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
                    {dataset ? `共 ${dataset.cases.length} 题 · 已确认` : "请稍候"}
                  </p>
                </div>
                {dataset ? (
                  <span
                    title={dataset.checksum}
                    className="tc-mono-font max-w-28 truncate text-[11px] text-[var(--tc-text-muted)]"
                  >
                    {dataset.checksum.slice(0, 12)}
                  </span>
                ) : null}
              </div>

              <div className="mt-3 grid gap-1">
                <CategoryButton
                  active={category === "all"}
                  label="全部题目"
                  count={dataset?.cases.length ?? 0}
                  onClick={() => chooseCategory("all")}
                />
                {categoryOrder.map(item => (
                  <CategoryButton
                    key={item}
                    active={category === item}
                    label={retrievalEvaluationCategoryLabels[item]}
                    count={dataset?.cases.filter(value => value.category === item).length ?? 0}
                    onClick={() => chooseCategory(item)}
                  />
                ))}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {loading ? (
                <p className="px-2 py-3 text-sm text-[var(--tc-text-muted)]">
                  正在读取 60 条评测题目
                </p>
              ) : (
                <div className="grid gap-1">
                  {filteredCases.map(item => (
                    <CaseButton
                      key={item.case_id}
                      evaluationCase={item}
                      active={selectedCase?.case_id === item.case_id}
                      outcome={retrievalCaseOutcome(item.case_id, evaluation)}
                      onClick={() => setCaseId(item.case_id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </aside>

          <main className="flex min-h-0 flex-col gap-3 overflow-hidden">
            <section className="shrink-0 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)]">
              <div className="grid grid-cols-7 divide-x divide-[var(--tc-border-subtle)]">
                <Metric label="样例" value={summary ? String(summary.case_count) : "—"} />
                <Metric label="召回率@1" value={formatPercent(metricAtK(summary, 1)?.recall)} />
                <Metric label="召回率@3" value={formatPercent(metricAtK(summary, 3)?.recall)} />
                <Metric label="召回率@10" value={formatPercent(metricAtK(summary, 10)?.recall)} />
                <Metric label="平均倒数排名" value={formatPercent(summary?.mrr)} />
                <Metric label="空结果准确率" value={formatPercent(summary?.empty_result_accuracy)} />
                <Metric label="禁止卡命中率" value={formatPercent(summary?.forbidden_hit_rate)} />
              </div>
              {evaluation ? (
                <div className="flex items-center justify-between gap-4 border-t border-[var(--tc-border-subtle)] px-3 py-2 text-xs text-[var(--tc-text-muted)]">
                  <span>
                    {retrievalStrategyLabel(evaluation.requested_strategy)} · 已确认知识卡 {evaluation.confirmed_card_count} 张 · 平均 {evaluation.summary.average_latency_ms.toFixed(3)} ms · p95 {evaluation.summary.p95_latency_ms.toFixed(0)} ms
                  </span>
                  <span
                    title={evaluation.index_snapshot_id}
                    className="tc-mono-font max-w-80 truncate"
                  >
                    快照 {evaluation.index_snapshot_id}
                  </span>
                </div>
              ) : null}
            </section>

            <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.18fr)_minmax(380px,0.82fr)] gap-3 overflow-hidden">
              <section className="min-h-0 overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
                {selectedCase ? (
                  <CaseDetail
                    evaluationCase={selectedCase}
                    evaluation={evaluation}
                    failure={selectedFailure}
                  />
                ) : (
                  <p className="text-sm text-[var(--tc-text-muted)]">请选择评测题目。</p>
                )}
              </section>

              <section className="min-h-0 overflow-y-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
                <GroupSummary evaluation={evaluation} />
                <FailureList
                  evaluation={evaluation}
                  dataset={dataset}
                  selectedCaseId={selectedCase?.case_id ?? ""}
                  onSelect={setCaseId}
                />
              </section>
            </div>
          </main>
        </div>
      </section>
    </AppShell>
  );
}

function CategoryButton({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex items-center justify-between rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-xs",
        active
          ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
          : "text-[var(--tc-text-muted)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
      )}
    >
      <span>{label}</span>
      <span className="tc-mono-font">{count}</span>
    </button>
  );
}

function CaseButton({
  evaluationCase,
  active,
  outcome,
  onClick,
}: {
  evaluationCase: RetrievalEvaluationCase;
  active: boolean;
  outcome: "通过" | "未通过" | "未评测";
  onClick: () => void;
}) {
  const OutcomeIcon =
    outcome === "通过"
      ? CheckCircle2
      : outcome === "未通过"
        ? AlertCircle
        : CircleDot;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-2 rounded-[var(--tc-radius-control)] px-2 py-2 text-left",
        active ? "bg-[var(--tc-surface-muted)]" : "hover:bg-[var(--tc-surface-muted)]",
      )}
    >
      <OutcomeIcon className="mt-0.5 size-3.5 shrink-0 text-[var(--tc-text-muted)]" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-[var(--tc-text-primary)]">
          {evaluationCase.label}
        </span>
        <span className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-[var(--tc-text-muted)]">
          <span>{retrievalEvaluationCategoryLabels[evaluationCase.category]}</span>
          <span>{outcome}</span>
        </span>
      </span>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-3">
      <p className="text-[11px] text-[var(--tc-text-muted)]">{label}</p>
      <p className="tc-mono-font mt-1 text-base font-medium text-[var(--tc-text-primary)]">
        {value}
      </p>
    </div>
  );
}

function CaseDetail({
  evaluationCase,
  evaluation,
  failure,
}: {
  evaluationCase: RetrievalEvaluationCase;
  evaluation: RetrievalEvaluationRecord | null;
  failure: RetrievalEvaluationFailure | null;
}) {
  const result = evaluation?.cases.find(item => item.case_id === evaluationCase.case_id) ?? null;
  const outcome = retrievalCaseOutcome(evaluationCase.case_id, evaluation);
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-[var(--tc-text-muted)]">
            {retrievalEvaluationCategoryLabels[evaluationCase.category]}
          </p>
          <h2 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">
            {evaluationCase.label}
          </h2>
          <p className="tc-mono-font mt-1 text-[11px] text-[var(--tc-text-muted)]">
            {evaluationCase.case_id}
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tc-border-subtle)] px-2 py-1 text-xs text-[var(--tc-text-secondary)]">
          {outcome === "通过" ? (
            <CheckCircle2 className="size-3.5" />
          ) : (
            <AlertCircle className="size-3.5" />
          )}
          {outcome}
        </span>
      </div>

      <DetailBlock title="评测问题">
        <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-primary)]">
          {evaluationCase.query_text}
        </p>
      </DetailBlock>

      {evaluationCase.context_text ? (
        <DetailBlock title="辅助上下文">
          <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-secondary)]">
            {evaluationCase.context_text}
          </p>
        </DetailBlock>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-[var(--tc-border-subtle)] pt-4">
        <IdSection
          title="期望相关知识卡"
          values={evaluationCase.relevant_card_ids}
          emptyLabel={evaluationCase.should_be_empty ? "本题期望空结果" : "未设置"}
        />
        <IdSection
          title="禁止返回知识卡"
          values={evaluationCase.must_not_return_card_ids}
          emptyLabel="无禁止卡约束"
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-[var(--tc-border-subtle)] pt-3 text-xs text-[var(--tc-text-muted)]">
        <span>期望前 {evaluationCase.expected_top_k} 条</span>
        <span>
          知识类型：
          {evaluationCase.knowledge_types.length > 0
            ? evaluationCase.knowledge_types
                .map(item => retrievalKnowledgeTypeLabels[item] ?? `其他类型（${item}）`)
                .join("、")
            : "不限"}
        </span>
        <span>{evaluationCase.should_be_empty ? "应返回空结果" : "应召回相关卡"}</span>
      </div>

      {failure ? (
        <div className="mt-4 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-3">
          <p className="flex items-center gap-1 text-xs font-medium text-[var(--tc-text-primary)]">
            <AlertCircle className="size-3.5" />未通过原因
          </p>
          <ul className="mt-2 grid gap-1 text-sm text-[var(--tc-text-secondary)]">
            {failure.reasons.map(reason => (
              <li key={reason}>· {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <DetailBlock title="实际召回结果">
        {result ? (
          <div>
            <div className="grid grid-cols-5 gap-2 text-xs">
              <ResultStat label="返回" value={`${result.hit_count} 张`} />
              <ResultStat label="候选" value={`${result.candidate_count} 张`} />
              <ResultStat label="耗时" value={`${result.latency_ms} ms`} />
              <ResultStat label="倒数排名" value={formatPercent(result.reciprocal_rank)} />
              <ResultStat label="截断" value={result.truncated ? "是" : "否"} />
            </div>
            <IdSection
              title="返回知识卡顺序"
              values={result.returned_card_ids}
              emptyLabel="本次没有返回知识卡"
              className="mt-3"
            />
            <div className="mt-3 overflow-hidden rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)]">
              <table className="w-full text-left text-xs">
                <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">位置</th>
                    <th className="px-3 py-2 font-medium">召回率</th>
                    <th className="px-3 py-2 font-medium">准确率</th>
                    <th className="px-3 py-2 font-medium">排序质量</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--tc-border-subtle)] text-[var(--tc-text-secondary)]">
                  {result.at_k.map(metric => (
                    <tr key={metric.k}>
                      <td className="px-3 py-2">前 {metric.k} 条</td>
                      <td className="tc-mono-font px-3 py-2">{formatPercent(metric.recall)}</td>
                      <td className="tc-mono-font px-3 py-2">{formatPercent(metric.precision)}</td>
                      <td className="tc-mono-font px-3 py-2">{formatPercent(metric.ndcg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-sm text-[var(--tc-text-muted)]">当前没有可对应的评测结果。</p>
        )}
      </DetailBlock>
    </div>
  );
}

function GroupSummary({ evaluation }: { evaluation: RetrievalEvaluationRecord | null }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-[var(--tc-text-primary)]">分组表现</h2>
        <span className="text-xs text-[var(--tc-text-muted)]">
          {evaluation ? `${evaluation.groups.length} 个类别` : "暂无结果"}
        </span>
      </div>
      {evaluation ? (
        <div className="mt-3 overflow-hidden rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)]">
          <table className="w-full text-left text-xs">
            <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]">
              <tr>
                <th className="px-2 py-2 font-medium">类别</th>
                <th className="px-2 py-2 font-medium">@1</th>
                <th className="px-2 py-2 font-medium">@3</th>
                <th className="px-2 py-2 font-medium">倒数排名</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--tc-border-subtle)] text-[var(--tc-text-secondary)]">
              {evaluation.groups.map(group => (
                <tr key={group.category}>
                  <td className="px-2 py-2">
                    {retrievalEvaluationCategoryLabels[group.category]}
                  </td>
                  <td className="tc-mono-font px-2 py-2">
                    {formatPercent(metricAtK(group.summary, 1)?.recall)}
                  </td>
                  <td className="tc-mono-font px-2 py-2">
                    {formatPercent(metricAtK(group.summary, 3)?.recall)}
                  </td>
                  <td className="tc-mono-font px-2 py-2">
                    {group.summary.relevance_case_count > 0
                      ? formatPercent(group.summary.mrr)
                      : `空结果 ${formatPercent(group.summary.empty_result_accuracy)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-[var(--tc-text-muted)]">暂无可展示的分组指标。</p>
      )}
    </div>
  );
}

function FailureList({
  evaluation,
  dataset,
  selectedCaseId,
  onSelect,
}: {
  evaluation: RetrievalEvaluationRecord | null;
  dataset: RetrievalEvaluationDataset | null;
  selectedCaseId: string;
  onSelect: (caseId: string) => void;
}) {
  return (
    <div className="mt-5 border-t border-[var(--tc-border-subtle)] pt-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-[var(--tc-text-primary)]">未通过样例</h2>
        <span className="tc-mono-font text-xs text-[var(--tc-text-muted)]">
          {evaluation?.failures.length ?? 0}
        </span>
      </div>
      {evaluation?.failures.length ? (
        <div className="mt-2 grid gap-1">
          {evaluation.failures.map(failure => {
            const evaluationCase = dataset?.cases.find(
              item => item.case_id === failure.case_id,
            );
            return (
              <button
                key={failure.case_id}
                type="button"
                onClick={() => onSelect(failure.case_id)}
                className={cn(
                  "rounded-[var(--tc-radius-control)] px-2 py-2 text-left",
                  selectedCaseId === failure.case_id
                    ? "bg-[var(--tc-surface-muted)]"
                    : "hover:bg-[var(--tc-surface-muted)]",
                )}
              >
                <span className="block text-sm text-[var(--tc-text-primary)]">
                  {evaluationCase?.label ?? failure.case_id}
                </span>
                <span className="mt-0.5 block line-clamp-1 text-xs text-[var(--tc-text-muted)]">
                  {failure.reasons.join("；")}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-sm text-[var(--tc-text-muted)]">当前记录没有未通过样例。</p>
      )}
    </div>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-4">
      <h3 className="mb-2 text-xs font-medium text-[var(--tc-text-muted)]">{title}</h3>
      {children}
    </div>
  );
}

function IdSection({
  title,
  values,
  emptyLabel,
  className,
}: {
  title: string;
  values: string[];
  emptyLabel: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <h3 className="text-xs font-medium text-[var(--tc-text-muted)]">{title}</h3>
      {values.length > 0 ? (
        <ol className="mt-2 grid gap-1">
          {values.map((value, index) => (
            <li
              key={`${value}-${index}`}
              title={value}
              className="tc-mono-font truncate text-[11px] text-[var(--tc-text-secondary)]"
            >
              {index + 1}. {value}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-2 text-xs text-[var(--tc-text-muted)]">{emptyLabel}</p>
      )}
    </div>
  );
}

function ResultStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-[var(--tc-text-muted)]">{label}</p>
      <p className="tc-mono-font mt-1 text-[var(--tc-text-primary)]">{value}</p>
    </div>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error
    ? caught.message
    : "统一召回评测资料加载失败，请确认后端服务是否可用。";
}
