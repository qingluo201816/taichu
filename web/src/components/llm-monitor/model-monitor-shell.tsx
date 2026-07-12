"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronRight,
  ListTree,
  RefreshCw,
  SearchCheck,
  Server,
  X,
} from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { CompactPagination } from "@/components/ui/compact-pagination";
import {
  getLLMCall,
  getLLMTokenTrend,
  getLLMUsageSummary,
  listLLMCalls,
  listLLMModels,
  probeLLMModel,
  type LLMUsageFilters,
} from "@/lib/api/llm";
import {
  monitoredCostLabel,
  monitoredStatusLabel,
} from "@/lib/llm/view-model";
import {
  type TokenTrendRange,
  tokenTrendRangeStart,
  tokenTrendTickIndexes,
} from "@/lib/llm/token-trend";
import type {
  LLMCallRecord,
  LLMCallStatus,
  LLMModelListResponse,
  LLMTokenTrendPoint,
  LLMUsageGroup,
  LLMUsageSummary,
} from "@/lib/types/llm";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 4;
const MODEL_PAGE_SIZE = 4;

const EMPTY_SUMMARY: LLMUsageSummary = {
  total_calls: 0,
  completed_calls: 0,
  failed_calls: 0,
  input_tokens: null,
  cached_input_tokens: null,
  output_tokens: null,
  reasoning_tokens: null,
  total_tokens: null,
  actual_cost: 0,
  estimated_cost: 0,
  unavailable_cost_calls: 0,
  average_duration_ms: 0,
  by_model: [],
  by_task_type: [],
};

type MonitorView = "trend" | "summary" | "calls" | "availability";
type TrendMetric =
  | "total_tokens"
  | "input_tokens"
  | "cached_input_tokens"
  | "output_tokens"
  | "reasoning_tokens";

type FilterState = {
  range: TokenTrendRange;
  modelId: string;
  taskType: string;
  status: "" | LLMCallStatus;
};

const EMPTY_FILTERS: FilterState = {
  range: "30d",
  modelId: "",
  taskType: "",
  status: "",
};

const VIEW_ITEMS: Array<{
  id: MonitorView;
  label: string;
  description: string;
  icon: ReactNode;
}> = [
  { id: "trend", label: "Token 趋势", description: "查看使用变化", icon: <BarChart3 className="size-4" /> },
  { id: "summary", label: "模型汇总", description: "比较模型消耗", icon: <ListTree className="size-4" /> },
  { id: "calls", label: "调用明细", description: "追踪单次调用", icon: <Activity className="size-4" /> },
  { id: "availability", label: "模型可用性", description: "检测渠道状态", icon: <Server className="size-4" /> },
];

const RANGE_ITEMS: Array<{ id: TokenTrendRange; label: string }> = [
  { id: "24h", label: "24 小时" },
  { id: "7d", label: "7 天" },
  { id: "30d", label: "30 天" },
  { id: "all", label: "全部" },
];

const METRIC_ITEMS: Array<{ id: TrendMetric; label: string }> = [
  { id: "total_tokens", label: "总 Token" },
  { id: "input_tokens", label: "输入" },
  { id: "cached_input_tokens", label: "缓存" },
  { id: "output_tokens", label: "输出" },
  { id: "reasoning_tokens", label: "推理" },
];

export function ModelMonitorShell() {
  const [view, setView] = useState<MonitorView>("trend");
  const [trendMetric, setTrendMetric] = useState<TrendMetric>("total_tokens");
  const [catalog, setCatalog] = useState<LLMModelListResponse>({
    default_model_id: "",
    models: [],
  });
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [calls, setCalls] = useState<LLMCallRecord[]>([]);
  const [trend, setTrend] = useState<LLMTokenTrendPoint[]>([]);
  const [taskTypes, setTaskTypes] = useState<LLMUsageGroup[]>([]);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [summaryPage, setSummaryPage] = useState(1);
  const [availabilityPage, setAvailabilityPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedCall, setSelectedCall] = useState<LLMCallRecord | null>(null);
  const [probingIds, setProbingIds] = useState<Set<string>>(new Set());

  const apiFilters = useMemo<LLMUsageFilters>(
    () => ({
      page,
      pageSize: PAGE_SIZE,
      startedFrom: tokenTrendRangeStart(filters.range),
      modelId: filters.modelId || undefined,
      taskType: filters.taskType || undefined,
      status: filters.status || undefined,
    }),
    [filters, page],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextCatalog, nextCalls, nextSummary, nextTrend] = await Promise.all([
        listLLMModels(),
        listLLMCalls(apiFilters),
        getLLMUsageSummary(apiFilters),
        getLLMTokenTrend(apiFilters, filters.range === "24h" ? "hour" : "day"),
      ]);
      setCatalog(nextCatalog);
      setCalls(nextCalls.items);
      setTotal(nextCalls.total);
      setSummary(nextSummary);
      setTrend(nextTrend.points);
      setTaskTypes(current => mergeTaskTypes(current, nextSummary.by_task_type));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "模型监控数据加载失败。");
    } finally {
      setLoading(false);
    }
  }, [apiFilters, filters.range]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function updateFilters(next: FilterState) {
    setFilters(next);
    setPage(1);
  }

  async function openCall(callId: string) {
    try {
      setSelectedCall(await getLLMCall(callId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "调用详情读取失败。");
    }
  }

  async function probeOne(modelId: string, confirmed = false) {
    if (
      !confirmed &&
      !window.confirm("检测会发送一次最小真实请求，并可能产生少量费用。是否继续？")
    ) {
      return;
    }
    setProbingIds(current => new Set(current).add(modelId));
    setError("");
    try {
      await probeLLMModel(modelId);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "模型检测失败。");
    } finally {
      setProbingIds(current => {
        const next = new Set(current);
        next.delete(modelId);
        return next;
      });
    }
  }

  async function probeAll() {
    if (
      !window.confirm(
        `将逐个检测 ${catalog.models.length} 个模型，每个模型都会产生一次真实请求并可能产生费用。是否继续？`,
      )
    ) {
      return;
    }
    for (const model of catalog.models) {
      await probeOne(model.id, true);
    }
  }

  function inspectModel(modelId: string) {
    updateFilters({ ...filters, modelId });
    setView("calls");
  }

  const successRate = summary.total_calls
    ? `${Math.round((summary.completed_calls / summary.total_calls) * 100)}%`
    : "—";
  const stats = [
    ["调用次数", summary.total_calls.toLocaleString("zh-CN")],
    ["成功率", successRate],
    ["总 Token", number(summary.total_tokens)],
    ["缓存 Token", number(summary.cached_input_tokens)],
    ["推理 Token", number(summary.reasoning_tokens)],
    ["实际费用", money(summary.actual_cost)],
    ["预估费用", money(summary.estimated_cost)],
    ["平均耗时", duration(summary.average_duration_ms)],
  ];

  return (
    <AppShell activePath="/model-monitor" viewportLocked>
      <section className="mx-auto flex h-full min-h-0 w-full max-w-[1440px] flex-col px-4 py-3 md:px-6">
        <header className="flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-[var(--tc-border-subtle)] pb-3">
          <div>
            <p className="text-xs text-[var(--tc-text-muted)]">跨任务模型调用遥测</p>
            <h1 className="mt-1 text-xl font-semibold text-[var(--tc-text-primary)]">模型监控</h1>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            刷新
          </Button>
        </header>

        {error ? (
          <div className="mt-3 flex items-start gap-2 border-b border-[var(--tc-border-subtle)] pb-3 text-sm text-[var(--tc-text-primary)]">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <div className="grid shrink-0 grid-cols-2 border-b border-[var(--tc-border-subtle)] md:grid-cols-4 xl:grid-cols-8">
          {stats.map(([label, value]) => (
            <div key={label} className="border-r border-[var(--tc-border-subtle)] px-3 py-2 last:border-r-0">
              <p className="text-[11px] text-[var(--tc-text-muted)]">{label}</p>
              <p className="tc-display-font mt-1 text-sm text-[var(--tc-text-primary)]">{value}</p>
            </div>
          ))}
        </div>
        {summary.unavailable_cost_calls > 0 ? (
          <p className="shrink-0 border-b border-[var(--tc-border-subtle)] px-3 py-2 text-xs text-[var(--tc-text-muted)]">
            部分模型未配置价格，共 {summary.unavailable_cost_calls} 次调用无法计算费用。
          </p>
        ) : null}

        <nav aria-label="模型监控功能入口" className="grid shrink-0 grid-cols-2 border-b border-[var(--tc-border-subtle)] md:grid-cols-4">
          {VIEW_ITEMS.map(item => (
            <button
              key={item.id}
              type="button"
              aria-pressed={view === item.id}
              onClick={() => setView(item.id)}
              className={cn(
                "flex items-center gap-3 border-r border-[var(--tc-border-subtle)] px-3 py-2 text-left transition-colors last:border-r-0",
                view === item.id
                  ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                  : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
              )}
            >
              {item.icon}
              <span className="min-w-0">
                <span className="block text-xs font-medium">{item.label}</span>
                <span className="mt-0.5 block truncate text-[11px] opacity-75">{item.description}</span>
              </span>
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-hidden">
          {view === "trend" ? (
            <TrendPanel
              points={trend}
              metric={trendMetric}
              filters={filters}
              catalog={catalog}
              loading={loading}
              onMetricChange={setTrendMetric}
              onFilterChange={updateFilters}
            />
          ) : null}
          {view === "summary" ? (
            <SummaryPanel
              summary={summary}
              catalog={catalog}
              filters={filters}
              loading={loading}
              page={summaryPage}
              onFilterChange={updateFilters}
              onPageChange={setSummaryPage}
              onInspect={inspectModel}
            />
          ) : null}
          {view === "calls" ? (
            <CallsPanel
              calls={calls}
              total={total}
              page={page}
              filters={filters}
              catalog={catalog}
              taskTypes={taskTypes}
              loading={loading}
              onFilterChange={updateFilters}
              onPageChange={setPage}
              onOpenCall={openCall}
            />
          ) : null}
          {view === "availability" ? (
            <AvailabilityPanel
              catalog={catalog}
              probingIds={probingIds}
              page={availabilityPage}
              onProbeOne={probeOne}
              onProbeAll={probeAll}
              onPageChange={setAvailabilityPage}
              onInspect={inspectModel}
            />
          ) : null}
        </div>
      </section>

      {selectedCall ? <CallDetail call={selectedCall} onClose={() => setSelectedCall(null)} /> : null}
    </AppShell>
  );
}

function TrendPanel({
  points,
  metric,
  filters,
  catalog,
  loading,
  onMetricChange,
  onFilterChange,
}: {
  points: LLMTokenTrendPoint[];
  metric: TrendMetric;
  filters: FilterState;
  catalog: LLMModelListResponse;
  loading: boolean;
  onMetricChange: (metric: TrendMetric) => void;
  onFilterChange: (filters: FilterState) => void;
}) {
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="trend-title">
      <SectionHeading id="trend-title" title="Token 使用趋势" meta={`${points.length} 个时间点`} />
      <ChipRow label="时间范围">
        {RANGE_ITEMS.map(item => (
          <FilterButton key={item.id} active={filters.range === item.id} onClick={() => onFilterChange({ ...filters, range: item.id })}>
            {item.label}
          </FilterButton>
        ))}
      </ChipRow>
      <ChipRow label="模型范围" scroll>
        <FilterButton active={!filters.modelId} onClick={() => onFilterChange({ ...filters, modelId: "" })}>全部模型</FilterButton>
        {catalog.models.map(model => (
          <FilterButton key={model.id} active={filters.modelId === model.id} onClick={() => onFilterChange({ ...filters, modelId: model.id })}>
            {model.display_name}
          </FilterButton>
        ))}
      </ChipRow>
      <ChipRow label="趋势指标">
        {METRIC_ITEMS.map(item => (
          <FilterButton key={item.id} active={metric === item.id} onClick={() => onMetricChange(item.id)}>
            {item.label}
          </FilterButton>
        ))}
      </ChipRow>
      <TokenTrendChart points={points} metric={metric} loading={loading} />
    </section>
  );
}

function TokenTrendChart({ points, metric, loading }: { points: LLMTokenTrendPoint[]; metric: TrendMetric; loading: boolean }) {
  const width = 1040;
  const height = 280;
  const padding = { top: 24, right: 24, bottom: 44, left: 68 };
  const values = points.map(point => point[metric] ?? 0);
  const maximum = Math.max(1, ...values);
  const usableWidth = width - padding.left - padding.right;
  const usableHeight = height - padding.top - padding.bottom;
  const coordinates = points.map((point, index) => ({
    point,
    value: values[index],
    x: points.length <= 1 ? padding.left + usableWidth / 2 : padding.left + (index / (points.length - 1)) * usableWidth,
    y: padding.top + usableHeight - (values[index] / maximum) * usableHeight,
  }));
  const polyline = coordinates.map(item => `${item.x},${item.y}`).join(" ");
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const xTickIndexes = tokenTrendTickIndexes(points.length);
  const metricLabel = METRIC_ITEMS.find(item => item.id === metric)?.label ?? "Token";

  if (!points.length) {
    return <div className="mt-3 grid min-h-0 flex-1 place-items-center border-y border-[var(--tc-border-subtle)] text-xs text-[var(--tc-text-muted)]">{loading ? "趋势加载中" : "当前范围内暂无 Token 记录"}</div>;
  }

  return (
    <div className="mt-3 flex min-h-0 flex-1 items-center justify-center overflow-hidden border-y border-[var(--tc-border-subtle)] py-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-full min-h-0 w-full" role="img" aria-label={`${metricLabel}使用趋势图`}>
        {yTicks.map(tick => {
          const y = padding.top + usableHeight - tick * usableHeight;
          return (
            <g key={tick}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="var(--tc-border-subtle)" strokeWidth="1" />
              <text x={padding.left - 12} y={y + 4} textAnchor="end" fill="var(--tc-text-muted)" fontSize="11">{compactNumber(Math.round(maximum * tick))}</text>
            </g>
          );
        })}
        {xTickIndexes.map(index => (
          <text key={index} x={coordinates[index].x} y={height - 14} textAnchor="middle" fill="var(--tc-text-muted)" fontSize="11">
            {trendTimeLabel(points[index].bucket_start, points.length > 31)}
          </text>
        ))}
        <polyline points={polyline} fill="none" stroke="var(--tc-text-primary)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {coordinates.map(item => (
          <circle key={item.point.bucket_start} cx={item.x} cy={item.y} r="3" fill="var(--tc-surface-page)" stroke="var(--tc-text-primary)" strokeWidth="1.5">
            <title>{`${dateTime(item.point.bucket_start)}：${number(item.value)} ${metricLabel}，${item.point.call_count} 次调用`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function SummaryPanel({ summary, catalog, filters, loading, page, onFilterChange, onPageChange, onInspect }: { summary: LLMUsageSummary; catalog: LLMModelListResponse; filters: FilterState; loading: boolean; page: number; onFilterChange: (filters: FilterState) => void; onPageChange: (page: number) => void; onInspect: (modelId: string) => void }) {
  const groups = new Map(summary.by_model.map(group => [group.key, group]));
  const rows = catalog.models.map(model => groups.get(model.id) ?? emptyGroup(model.id, model.display_name));
  const currentPage = Math.min(Math.max(1, page), Math.max(1, Math.ceil(rows.length / MODEL_PAGE_SIZE)));
  const pagedRows = rows.slice((currentPage - 1) * MODEL_PAGE_SIZE, currentPage * MODEL_PAGE_SIZE);
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="summary-title">
      <SectionHeading id="summary-title" title="模型汇总" meta={`共 ${catalog.models.length} 个模型`} />
      <ChipRow label="统计范围">
        {RANGE_ITEMS.map(item => <FilterButton key={item.id} active={filters.range === item.id} onClick={() => onFilterChange({ ...filters, range: item.id })}>{item.label}</FilterButton>)}
      </ChipRow>
      <div className="mt-3 min-h-0 flex-1 overflow-x-auto border-y border-[var(--tc-border-subtle)]">
        <table className="w-full min-w-[920px] text-left text-xs">
          <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]"><tr>{["模型", "调用数", "成功率", "输入", "缓存", "输出", "推理", "总 Token", "总费用", "平均耗时", ""].map(label => <th key={label || "action"} className="px-3 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>
            {pagedRows.map(row => (
              <tr key={row.key} className="border-t border-[var(--tc-border-subtle)] text-[var(--tc-text-secondary)]">
                <td className="px-3 py-2 text-[var(--tc-text-primary)]">{row.display_name}</td><td className="px-3 py-2">{row.total_calls}</td><td className="px-3 py-2">{row.total_calls ? `${Math.round((row.completed_calls / row.total_calls) * 100)}%` : "—"}</td><td className="px-3 py-2">{number(row.input_tokens)}</td><td className="px-3 py-2">{number(row.cached_input_tokens)}</td><td className="px-3 py-2">{number(row.output_tokens)}</td><td className="px-3 py-2">{number(row.reasoning_tokens)}</td><td className="px-3 py-2">{number(row.total_tokens)}</td><td className="px-3 py-2">{combinedCost(row.actual_cost, row.estimated_cost)}</td><td className="px-3 py-2">{duration(row.average_duration_ms)}</td><td className="px-3 py-2"><button type="button" onClick={() => onInspect(row.key)} className="whitespace-nowrap text-[var(--tc-text-primary)] hover:underline">看明细</button></td>
              </tr>
            ))}
            {!rows.length ? <EmptyRow colSpan={11} text={loading ? "统计加载中" : "暂无模型"} /> : null}
          </tbody>
        </table>
      </div>
      <CompactPagination page={currentPage} pageSize={MODEL_PAGE_SIZE} total={rows.length} onPageChange={onPageChange} />
    </section>
  );
}

function CallsPanel({ calls, total, page, filters, catalog, taskTypes, loading, onFilterChange, onPageChange, onOpenCall }: { calls: LLMCallRecord[]; total: number; page: number; filters: FilterState; catalog: LLMModelListResponse; taskTypes: LLMUsageGroup[]; loading: boolean; onFilterChange: (filters: FilterState) => void; onPageChange: (page: number | ((value: number) => number)) => void; onOpenCall: (callId: string) => void }) {
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="calls-title">
      <SectionHeading id="calls-title" title="调用明细" meta={`共 ${total} 条`} />
      <ChipRow label="时间范围">{RANGE_ITEMS.map(item => <FilterButton key={item.id} active={filters.range === item.id} onClick={() => onFilterChange({ ...filters, range: item.id })}>{item.label}</FilterButton>)}</ChipRow>
      <ChipRow label="调用状态"><FilterButton active={!filters.status} onClick={() => onFilterChange({ ...filters, status: "" })}>全部状态</FilterButton>{([['completed', '成功'], ['failed', '失败'], ['running', '运行中']] as const).map(([id, label]) => <FilterButton key={id} active={filters.status === id} onClick={() => onFilterChange({ ...filters, status: id })}>{label}</FilterButton>)}</ChipRow>
      <ChipRow label="模型" scroll><FilterButton active={!filters.modelId} onClick={() => onFilterChange({ ...filters, modelId: "" })}>全部模型</FilterButton>{catalog.models.map(model => <FilterButton key={model.id} active={filters.modelId === model.id} onClick={() => onFilterChange({ ...filters, modelId: model.id })}>{model.display_name}</FilterButton>)}</ChipRow>
      {taskTypes.length ? <ChipRow label="任务" scroll><FilterButton active={!filters.taskType} onClick={() => onFilterChange({ ...filters, taskType: "" })}>全部任务</FilterButton>{taskTypes.map(task => <FilterButton key={task.key} active={filters.taskType === task.key} onClick={() => onFilterChange({ ...filters, taskType: task.key })}>{task.display_name}</FilterButton>)}</ChipRow> : null}
      {(filters.modelId || filters.taskType || filters.status || filters.range !== EMPTY_FILTERS.range) ? <div className="flex justify-end border-b border-[var(--tc-border-subtle)] py-2"><Button type="button" variant="outline" size="sm" onClick={() => onFilterChange(EMPTY_FILTERS)}><X className="size-3.5" />清除筛选</Button></div> : null}
      <div className="mt-3 min-h-0 flex-1 overflow-x-auto border-y border-[var(--tc-border-subtle)]">
        <table className="w-full min-w-[1040px] text-left text-xs">
          <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]"><tr>{["开始时间", "任务 / 范围", "模型", "状态", "Token 明细", "费用", "耗时", ""].map(label => <th key={label || "action"} className="px-3 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>
            {calls.map(call => (
              <tr key={call.call_id} className="border-t border-[var(--tc-border-subtle)] text-[var(--tc-text-secondary)]">
                <td className="whitespace-nowrap px-3 py-2">{dateTime(call.started_at)}</td>
                <td className="max-w-64 px-3 py-2"><p className="truncate text-[var(--tc-text-primary)]">{call.task_name}</p><p className="mt-0.5 truncate text-[11px] text-[var(--tc-text-muted)]">{call.chapter_ids.join("、") || call.feature || "无章节"}</p></td>
                <td className="px-3 py-2">{call.model_display_name}</td>
                <td className="px-3 py-2">{monitoredStatusLabel(call.status)}</td>
                <td className="px-3 py-2"><p className="tc-display-font text-[var(--tc-text-primary)]">总 {number(call.total_tokens)}</p><p className="mt-0.5 whitespace-nowrap text-[11px] text-[var(--tc-text-muted)]">入 {number(call.input_tokens)} · 缓 {number(call.cached_input_tokens)} · 出 {number(call.output_tokens)} · 推 {number(call.reasoning_tokens)}</p></td>
                <td className="px-3 py-2"><p>{monitoredCostLabel(call)}</p><p className="mt-0.5 text-[11px] text-[var(--tc-text-muted)]">{costKindLabel(call.cost_kind)}</p></td>
                <td className="px-3 py-2">{duration(call.duration_ms)}</td>
                <td className="px-3 py-2"><button type="button" onClick={() => void onOpenCall(call.call_id)} className="inline-flex items-center gap-1 whitespace-nowrap text-[var(--tc-text-primary)] hover:underline">详情<ChevronRight className="size-3" /></button></td>
              </tr>
            ))}
            {!calls.length ? <EmptyRow colSpan={8} text={loading ? "调用明细加载中" : "当前范围内暂无调用"} /> : null}
          </tbody>
        </table>
      </div>
      <CompactPagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={nextPage => onPageChange(nextPage)} />
    </section>
  );
}

function AvailabilityPanel({ catalog, probingIds, page, onProbeOne, onProbeAll, onPageChange, onInspect }: { catalog: LLMModelListResponse; probingIds: Set<string>; page: number; onProbeOne: (modelId: string) => Promise<void>; onProbeAll: () => Promise<void>; onPageChange: (page: number) => void; onInspect: (modelId: string) => void }) {
  const currentPage = Math.min(Math.max(1, page), Math.max(1, Math.ceil(catalog.models.length / MODEL_PAGE_SIZE)));
  const pagedModels = catalog.models.slice((currentPage - 1) * MODEL_PAGE_SIZE, currentPage * MODEL_PAGE_SIZE);
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="availability-title">
      <div className="flex flex-wrap items-end justify-between gap-3"><SectionHeading id="availability-title" title="模型可用性" meta="页面加载不会自动检测" /><Button type="button" size="sm" onClick={() => void onProbeAll()}><SearchCheck className="size-4" />批量检测</Button></div>
      <p className="mt-2 text-xs text-[var(--tc-text-muted)]">检测会发送真实请求并可能产生少量费用，只有主动操作才会执行。</p>
      <div className="mt-3 min-h-0 flex-1 divide-y divide-[var(--tc-border-subtle)] overflow-y-auto border-y border-[var(--tc-border-subtle)]">
        {pagedModels.map(model => (
          <div key={model.id} className="grid items-center gap-2 px-3 py-2 text-xs md:grid-cols-[minmax(180px,1fr)_120px_190px_auto]">
            <div><p className="text-[var(--tc-text-primary)]">{model.display_name}{model.is_default ? "（默认）" : ""}</p><p className="mt-0.5 text-[11px] text-[var(--tc-text-muted)]">{model.upstream_verified ? "上游名称已验证" : "上游名称未验证"}</p></div>
            <span className="text-[var(--tc-text-secondary)]">{availabilityLabel(model.availability)}</span>
            <span className="text-[var(--tc-text-muted)]">{model.last_probed_at ? dateTime(model.last_probed_at) : "尚未检测"}</span>
            <div className="flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => onInspect(model.id)}>看调用</Button><Button variant="outline" size="sm" disabled={probingIds.has(model.id)} onClick={() => void onProbeOne(model.id)}>{probingIds.has(model.id) ? <Activity className="size-3.5 animate-spin" /> : <SearchCheck className="size-3.5" />}检测</Button></div>
          </div>
        ))}
      </div>
      <CompactPagination page={currentPage} pageSize={MODEL_PAGE_SIZE} total={catalog.models.length} onPageChange={onPageChange} />
    </section>
  );
}

function ChipRow({ label, children, scroll = false }: { label: string; children: ReactNode; scroll?: boolean }) {
  return <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center border-b border-[var(--tc-border-subtle)] py-2 text-xs"><span className="text-[var(--tc-text-muted)]">{label}</span><div className={cn("flex gap-1.5", scroll && "overflow-x-auto whitespace-nowrap pb-1")}>{children}</div></div>;
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={cn("shrink-0 rounded-full border px-3 py-1.5 text-xs transition-colors", active ? "border-[var(--tc-text-primary)] bg-[var(--tc-text-primary)] text-[var(--tc-surface-page)]" : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]")}>{children}</button>;
}

function SectionHeading({ id, title, meta }: { id: string; title: string; meta: string }) {
  return <div className="flex items-center justify-between gap-3"><h2 id={id} className="text-sm font-semibold text-[var(--tc-text-primary)]">{title}</h2><span className="text-xs text-[var(--tc-text-muted)]">{meta}</span></div>;
}

function CallDetail({ call, onClose }: { call: LLMCallRecord; onClose: () => void }) {
  const rows = [["调用 ID", call.call_id], ["关联运行 ID", call.run_id || "无"], ["功能来源", call.feature || "未记录"], ["模型内部 ID", call.model_id], ["上游模型名", call.upstream_model], ["协议", protocolLabel(call.wire_protocol)], ["开始时间", dateTime(call.started_at)], ["结束时间", call.finished_at ? dateTime(call.finished_at) : "未结束"], ["输入 Token", number(call.input_tokens)], ["缓存 Token", number(call.cached_input_tokens)], ["输出 Token", number(call.output_tokens)], ["推理 Token", number(call.reasoning_tokens)], ["总 Token", number(call.total_tokens)], ["费用", call.cost_amount == null ? "未配置价格" : `${call.cost_amount} ${call.cost_currency}`], ["费用类型", costKindLabel(call.cost_kind)], ["上游请求 ID", call.provider_request_id || "未返回"], ["脱敏错误", call.error_message || "无"]];
  return <div className="fixed inset-0 z-50 flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="模型调用详情"><button type="button" className="min-w-0 flex-1" aria-label="关闭详情" onClick={onClose} /><aside className="h-full w-full max-w-lg overflow-y-auto border-l border-[var(--tc-border-subtle)] bg-[var(--tc-surface-panel)] p-4"><div className="flex items-center justify-between border-b border-[var(--tc-border-subtle)] pb-3"><div><p className="text-xs text-[var(--tc-text-muted)]">模型调用</p><h2 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">调用详情</h2></div><Button variant="outline" size="icon-sm" onClick={onClose} aria-label="关闭详情"><X className="size-4" /></Button></div><dl className="divide-y divide-[var(--tc-border-subtle)]">{rows.map(([label, value]) => <div key={label} className="grid grid-cols-[120px_1fr] gap-3 py-2 text-xs"><dt className="text-[var(--tc-text-muted)]">{label}</dt><dd className="break-all text-[var(--tc-text-primary)]">{value}</dd></div>)}</dl><p className="mt-3 text-xs text-[var(--tc-text-muted)]">为保护作品内容，详情默认不展示完整提示词和模型原始输出。</p></aside></div>;
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) { return <tr><td colSpan={colSpan} className="px-3 py-8 text-center text-[var(--tc-text-muted)]">{text}</td></tr>; }
function number(value?: number | null) { return value == null ? "未返回" : value.toLocaleString("zh-CN"); }
function compactNumber(value: number) { return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value); }
function money(value: string | number) { return `${Number(value).toFixed(4)} 元`; }
function combinedCost(actual: string | number, estimated: string | number) { const total = Number(actual) + Number(estimated); return total ? `${total.toFixed(4)} 元` : "—"; }
function duration(value: number) { return value >= 1000 ? `${(value / 1000).toFixed(1)} 秒` : `${value} 毫秒`; }
function dateTime(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false }); }
function trendTimeLabel(value: string, includeYear: boolean) { const parsed = new Date(value); if (Number.isNaN(parsed.getTime())) return value; return parsed.toLocaleString("zh-CN", includeYear ? { year: "2-digit", month: "2-digit", day: "2-digit" } : { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }); }
function costKindLabel(kind: LLMCallRecord["cost_kind"]) { return kind === "actual" ? "实际" : kind === "estimated" ? "预估" : "不可计算"; }
function availabilityLabel(value: string) { return value === "available" ? "可用" : value === "unavailable" ? "不可用" : "未检测"; }
function protocolLabel(value: string) { return value === "openai_responses" ? "Responses 协议" : value === "anthropic_messages" ? "Messages 协议" : "未知协议"; }
function mergeTaskTypes(current: LLMUsageGroup[], incoming: LLMUsageGroup[]) { const merged = new Map(current.map(item => [item.key, item])); for (const item of incoming) merged.set(item.key, item); return [...merged.values()].sort((left, right) => left.display_name.localeCompare(right.display_name, "zh-CN")); }
function emptyGroup(key: string, displayName: string): LLMUsageGroup { return { key, display_name: displayName, total_calls: 0, completed_calls: 0, failed_calls: 0, input_tokens: null, cached_input_tokens: null, output_tokens: null, reasoning_tokens: null, total_tokens: null, actual_cost: 0, estimated_cost: 0, unavailable_cost_calls: 0, average_duration_ms: 0 }; }
