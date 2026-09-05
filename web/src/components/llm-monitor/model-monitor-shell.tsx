"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronRight,
  Download,
  ListTree,
  Network,
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
  useRef,
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
  listLLMProviders,
  probeLLMModel,
  switchLLMProvider,
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
  customTrendWindow,
  trendBucketWindow,
  trendCsv,
  type TrendWindow,
} from "@/lib/llm/token-trend";
import type {
  LLMCallRecord,
  LLMCallStatus,
  LLMModelListResponse,
  LLMProviderListResponse,
  LLMTokenTrendPoint,
  LLMUsageGroup,
  LLMUsageSummary,
} from "@/lib/types/llm";
import { cn } from "@/lib/utils";
import { knownGeneralCapabilityLabel } from "@/lib/general-agent-display";

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

type MonitorView = "trend" | "summary" | "calls" | "availability" | "providers";
type TrendMetric =
  | "total_tokens"
  | "input_tokens"
  | "cached_input_tokens"
  | "output_tokens"
  | "reasoning_tokens";

type FilterState = {
  range: TokenTrendRange | "custom";
  window?: TrendWindow;
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
  { id: "providers", label: "供应商切换", description: "限定模型来源", icon: <Network className="size-4" /> },
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
  const [providers, setProviders] = useState<LLMProviderListResponse>({
    active_provider_id: "rightcode",
    providers: [],
  });
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
  const [switchingProvider, setSwitchingProvider] = useState(false);
  const requestVersion = useRef(0);
  const [drillWindow, setDrillWindow] = useState<TrendWindow | null>(null);

  const apiFilters = useMemo<LLMUsageFilters>(
    () => ({
      page,
      pageSize: PAGE_SIZE,
      startedFrom: filters.range === "custom" ? filters.window?.startedFrom : tokenTrendRangeStart(filters.range),
      startedTo: filters.range === "custom" ? filters.window?.startedTo : undefined,
      modelId: filters.modelId || undefined,
      taskType: filters.taskType || undefined,
      status: filters.status || undefined,
    }),
    [filters, page],
  );

  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    try {
      const [nextCatalog, nextProviders, nextCalls, nextSummary, nextTrend] = await Promise.all([
        listLLMModels(),
        listLLMProviders(),
        listLLMCalls({ ...apiFilters, ...(drillWindow ?? {}) }),
        getLLMUsageSummary(apiFilters),
        getLLMTokenTrend(apiFilters, filters.range === "24h" ? "hour" : "day"),
      ]);
      if (version !== requestVersion.current) return;
      setCatalog(nextCatalog);
      setProviders(nextProviders);
      setCalls(nextCalls.items);
      setTotal(nextCalls.total);
      setSummary(nextSummary);
      setTrend(nextTrend.points);
      setTaskTypes(current => mergeTaskTypes(current, nextSummary.by_task_type));
    } catch (caught) {
      if (version !== requestVersion.current) return;
      setSummary(EMPTY_SUMMARY);
      setTrend([]);
      setCalls([]);
      setTotal(0);
      setError(caught instanceof Error ? caught.message : "模型监控数据加载失败。");
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [apiFilters, filters.range, drillWindow]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(timer); requestVersion.current += 1; };
  }, [load]);

  function updateFilters(next: FilterState) {
    setFilters(next);
    setPage(1);
    setSummaryPage(1);
    setDrillWindow(null);
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

  async function changeProvider(providerId: LLMProviderListResponse["active_provider_id"]) {
    const target = providers.providers.find(item => item.id === providerId);
    if (!target || providerId === providers.active_provider_id) return;
    if (!window.confirm(`切换到“${target.display_name}”后，只能使用该供应商支持的模型。是否继续？`)) return;
    setSwitchingProvider(true);
    setError("");
    try {
      await switchLLMProvider(providerId);
      setFilters(EMPTY_FILTERS);
      setPage(1);
      setAvailabilityPage(1);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "模型供应商切换失败。");
    } finally {
      setSwitchingProvider(false);
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
    ["总 Token", number(summary.total_tokens), `缓存 ${number(summary.cached_input_tokens)} · 推理 ${number(summary.reasoning_tokens)}`],
    ["调用次数", summary.total_calls.toLocaleString("zh-CN"), `成功率 ${successRate} · 平均 ${duration(summary.average_duration_ms)}`],
    ["实际费用", money(summary.actual_cost), "仅统计供应商已返回的费用"],
    ["预估费用", money(summary.estimated_cost), "仅统计按配置单价估算的调用"],
  ];

  return (
    <AppShell activePath="/model-monitor" viewportLocked>
      <section className="mx-auto flex h-full min-h-0 w-full max-w-[1440px] flex-col px-6 py-4">
        <header className="flex shrink-0 items-end justify-between gap-3 pb-4">
          <div>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">Token 用量与计费</h1>
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">查看消耗变化，追溯每一次模型调用</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className={cn("size-4", loading && "animate-spin motion-reduce:animate-none")} />
            刷新
          </Button>
        </header>

        {error ? (
          <div className="mt-3 flex items-start gap-2 pb-3 text-sm text-[var(--tc-text-primary)]">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <div className="grid shrink-0 grid-cols-4 gap-4 rounded-xl bg-[var(--tc-surface-muted)] px-4 py-3" aria-busy={loading}>
          {stats.map(([label, value, detail]) => (
            <div key={label}>
              <p className="text-xs text-[var(--tc-text-muted)]">{label}</p>
              <p className="tc-display-font mt-1 text-2xl text-[var(--tc-text-primary)]">{loading ? "—" : value}</p>
              <p className="mt-1 text-[11px] text-[var(--tc-text-muted)]">{loading ? "正在更新统计" : detail}</p>
            </div>
          ))}
        </div>
        {summary.unavailable_cost_calls > 0 ? (
          <p className="shrink-0 px-3 py-2 text-xs text-[var(--tc-text-muted)]">
            部分模型未配置价格，共 {summary.unavailable_cost_calls} 次调用无法计算费用。
          </p>
        ) : null}

        <nav aria-label="模型监控功能入口" className="mt-4 flex shrink-0 gap-2">
          {VIEW_ITEMS.map(item => (
            <button
              key={item.id}
              type="button"
              aria-pressed={view === item.id}
              onClick={() => { setView(item.id); setDrillWindow(null); setPage(1); }}
              className={cn(
                "flex items-center gap-2 rounded-full px-4 py-2 text-left transition-colors",
                view === item.id
                  ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                  : "text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]",
              )}
            >
              {item.icon}
              <span className="min-w-0">
                <span className="block text-xs font-medium">{item.label}</span>
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
              onInspect={point => { setDrillWindow(trendBucketWindow(point.bucket_start, filters.range === "24h" ? "hour" : "day", apiFilters)); setPage(1); setView("calls"); }}
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
            <div className="flex h-full min-h-0 flex-col">
            {drillWindow ? <div className="flex items-center justify-between rounded-lg bg-[var(--tc-surface-muted)] px-3 py-2 text-xs"><span>已定位时段（本地时间）：{dateTime(drillWindow.startedFrom!)} 至 {dateTime(drillWindow.startedTo!)}</span><Button size="sm" variant="ghost" onClick={() => { setDrillWindow(null); setPage(1); setView("trend"); }}>返回趋势</Button></div> : null}
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
            </div>
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
          {view === "providers" ? (
            <ProviderPanel
              providers={providers}
              switching={switchingProvider}
              onSwitch={changeProvider}
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
  onInspect,
}: {
  points: LLMTokenTrendPoint[];
  metric: TrendMetric;
  filters: FilterState;
  catalog: LLMModelListResponse;
  loading: boolean;
  onMetricChange: (metric: TrendMetric) => void;
  onFilterChange: (filters: FilterState) => void;
  onInspect: (point: LLMTokenTrendPoint) => void;
}) {
  return (
    <section className="flex h-full min-h-0 flex-col overflow-y-auto pt-3" aria-labelledby="trend-title">
      <div className="flex items-center justify-between"><SectionHeading id="trend-title" title="Token 使用趋势" meta={filters.range === "24h" ? "按小时聚合" : "按天聚合"} /><Button variant="ghost" size="sm" disabled={loading || !points.length} onClick={() => { const url = URL.createObjectURL(new Blob([trendCsv(points)], { type: "text/csv;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `Token用量趋势-${filters.range}-${new Date().toISOString().slice(0, 10)}.csv`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }}><Download className="size-3.5" />导出趋势</Button></div>
      <RangeFilter filters={filters} onChange={onFilterChange} />
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
      <TokenTrendChart key={`${metric}-${JSON.stringify(filters)}-${loading}`} points={points} metric={metric} loading={loading} bucket={filters.range === "24h" ? "hour" : "day"} onInspect={onInspect} />
    </section>
  );
}

function RangeFilter({ filters, onChange }: { filters: FilterState; onChange: (filters: FilterState) => void }) {
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState(() => filters.window?.startedFrom?.slice(0, 10) ?? new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10));
  const [end, setEnd] = useState(() => filters.window?.startedTo?.slice(0, 10) ?? new Date().toISOString().slice(0, 10));
  const window = customTrendWindow(start, end);
  return <div>
    <ChipRow label="时间范围">
      {RANGE_ITEMS.map(item => <FilterButton key={item.id} active={filters.range === item.id} onClick={() => { setEditing(false); onChange({ ...filters, range: item.id, window: undefined }); }}>{item.label}</FilterButton>)}
      <FilterButton active={filters.range === "custom" || editing} onClick={() => setEditing(!editing)}>自定义日期</FilterButton>
      {filters.range === "custom" && !editing ? <span className="self-center text-[var(--tc-text-muted)]">{filters.window?.startedFrom?.slice(0, 10)} 至 {filters.window?.startedTo?.slice(0, 10)}</span> : null}
    </ChipRow>
    {editing ? <form className="flex items-center gap-2 py-2 text-xs" onSubmit={event => { event.preventDefault(); if (window) { onChange({ ...filters, range: "custom", window }); setEditing(false); } }}>
      <label>开始日期 <input aria-label="开始日期" type="date" value={start} onChange={event => setStart(event.target.value)} className="rounded border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-1.5" /></label>
      <label>结束日期 <input aria-label="结束日期" type="date" value={end} onChange={event => setEnd(event.target.value)} className="rounded border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-1.5" /></label>
      <Button size="sm" type="submit" disabled={!window}>应用</Button>
      <span className="text-[var(--tc-text-muted)]">{window ? "按协调世界时的自然日统计" : "请选择有效日期，结束日期不能早于开始日期"}</span>
    </form> : null}
  </div>;
}

function TokenTrendChart({ points, metric, loading, bucket, onInspect }: { points: LLMTokenTrendPoint[]; metric: TrendMetric; loading: boolean; bucket: "hour" | "day"; onInspect: (point: LLMTokenTrendPoint) => void }) {
  const [active, setActive] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const [{ width, height }, setSize] = useState({ width: 1040, height: 200 });
  useEffect(() => {
    if (!plotRef.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: Math.max(320, entry.contentRect.width), height: Math.max(160, entry.contentRect.height) }));
    observer.observe(plotRef.current);
    return () => observer.disconnect();
  }, []);
  const padding = { top: 24, right: 30, bottom: 36, left: 68 };
  const maximum = Math.max(1, ...points.map(point => point[metric] ?? 0));
  const usableWidth = width - padding.left - padding.right;
  const usableHeight = height - padding.top - padding.bottom;
  const first = points.length ? Date.parse(points[0].bucket_start) : 0;
  const last = points.length ? Date.parse(points[points.length - 1].bucket_start) : 0;
  const step = bucket === "hour" ? 3600000 : 86400000;
  const coordinates = points.map(point => ({
    point, value: point[metric],
    x: first === last ? padding.left + usableWidth / 2 : padding.left + (Date.parse(point.bucket_start) - first) / (last - first) * usableWidth,
    y: padding.top + usableHeight - ((point[metric] ?? 0) / maximum) * usableHeight,
  }));
  // Missing measurements and absent buckets must not become zero or continuous usage.
  const segments: typeof coordinates[] = [];
  coordinates.forEach((item, index) => {
    if (item.value == null) return;
    const previous = coordinates[index - 1];
    if (!previous || previous.value == null || Date.parse(item.point.bucket_start) - Date.parse(previous.point.bucket_start) > step) segments.push([]);
    segments[segments.length - 1].push(item);
  });
  const metricLabel = METRIC_ITEMS.find(item => item.id === metric)?.label ?? "Token";
  const selected = active == null ? null : coordinates[active];
  const tickIndexes = tokenTrendTickIndexes(points.length).filter((index, position, indexes) => position === indexes.length - 1 || !indexes.slice(position + 1).some(next => coordinates[next].x - coordinates[index].x < 115));
  const known = points.map(point => point[metric]).filter((value): value is number => value != null);
  const utcLabel = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit", ...(bucket === "hour" ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}) });

  if (loading || !points.length) return <div className="mt-3 grid min-h-40 flex-1 place-items-center rounded-xl bg-[var(--tc-surface-muted)] text-xs text-[var(--tc-text-muted)]">{loading ? "趋势加载中" : "当前筛选范围内暂无调用记录"}</div>;

  return <div className="mt-2 flex min-h-[260px] flex-1 flex-col rounded-xl bg-[var(--tc-surface-muted)] px-4 py-3">
    <div className="flex items-center justify-between text-xs text-[var(--tc-text-muted)]">
      <span>{metricLabel} · 协调世界时（UTC）</span>
      <span>峰值 {known.length ? compactNumber(Math.max(...known)) : "未返回"} · {points.length} 个有调用时段</span>
    </div>
    <div ref={plotRef} className="min-h-40 flex-1">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full" role="group" aria-label={`${metricLabel}使用趋势图，选择时间点查看调用明细`}>
        {[0, 0.5, 1].map(tick => <text key={tick} x={padding.left - 12} y={padding.top + usableHeight - tick * usableHeight + 4} textAnchor="end" fill="var(--tc-text-muted)" fontSize="11">{compactNumber(Math.round(maximum * tick))}</text>)}
        {tickIndexes.map(index => <text key={index} x={coordinates[index].x} y={height - 10} textAnchor={index === points.length - 1 ? "end" : "middle"} fill="var(--tc-text-muted)" fontSize="11">{utcLabel(points[index].bucket_start)}</text>)}
        {segments.map((segment, index) => <g key={index}>
          <polygon points={`${segment[0].x},${padding.top + usableHeight} ${segment.map(item => `${item.x},${item.y}`).join(" ")} ${segment[segment.length - 1].x},${padding.top + usableHeight}`} fill="var(--tc-text-primary)" opacity="0.035" />
          <polyline points={segment.map(item => `${item.x},${item.y}`).join(" ")} fill="none" stroke="var(--tc-text-primary)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </g>)}
        {coordinates.map((item, index) => <g key={item.point.bucket_start} role="button" tabIndex={0} aria-label={`${utcLabel(item.point.bucket_start)}，${metricLabel} ${number(item.value)}，${item.point.call_count} 次调用，查看明细`} className="cursor-pointer outline-none" onMouseEnter={() => setActive(index)} onFocus={() => setActive(index)} onClick={() => onInspect(item.point)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onInspect(item.point); } }}>
          <circle cx={item.x} cy={item.y} r="12" fill="transparent" />
          <circle cx={item.x} cy={item.y} r={active === index ? 5 : 3} fill={item.value == null ? "var(--tc-surface-muted)" : "var(--tc-text-primary)"} stroke="var(--tc-text-primary)" strokeDasharray={item.value == null ? "2 2" : undefined} />
        </g>)}
      </svg>
    </div>
    <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 text-xs" aria-live="polite">
      {selected ? <><div><p className="text-[var(--tc-text-primary)]">{utcLabel(selected.point.bucket_start)} · {metricLabel} {number(selected.value)} · {selected.point.call_count} 次调用</p><p className="mt-1 text-[var(--tc-text-muted)]">输入 {number(selected.point.input_tokens)} · 输出 {number(selected.point.output_tokens)} · 缓存 {number(selected.point.cached_input_tokens)} · 推理 {number(selected.point.reasoning_tokens)}</p></div><Button size="sm" variant="outline" onClick={() => onInspect(selected.point)}>查看该时段明细<ChevronRight className="size-3.5" /></Button></> : <span className="text-[var(--tc-text-muted)]">悬停查看用量，点击时间点追溯调用与费用。无调用时段断开，空心点表示未返回用量。</span>}
    </div>
  </div>;
}
function SummaryPanel({ summary, catalog, filters, loading, page, onFilterChange, onPageChange, onInspect }: { summary: LLMUsageSummary; catalog: LLMModelListResponse; filters: FilterState; loading: boolean; page: number; onFilterChange: (filters: FilterState) => void; onPageChange: (page: number) => void; onInspect: (modelId: string) => void }) {
  const groups = new Map(summary.by_model.map(group => [group.key, group]));
  for (const model of catalog.models) if (!groups.has(model.id)) groups.set(model.id, emptyGroup(model.id, model.display_name));
  const rows = [...groups.values()].filter(row => !filters.modelId || row.key === filters.modelId);
  const currentPage = Math.min(Math.max(1, page), Math.max(1, Math.ceil(rows.length / MODEL_PAGE_SIZE)));
  const pagedRows = rows.slice((currentPage - 1) * MODEL_PAGE_SIZE, currentPage * MODEL_PAGE_SIZE);
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="summary-title">
      <SectionHeading id="summary-title" title="模型汇总" meta={`共 ${rows.length} 个模型`} />
      <RangeFilter filters={filters} onChange={onFilterChange} />
      <div className="mt-3 min-h-0 flex-1 overflow-x-auto ">
        <table className="w-full min-w-[920px] text-left text-xs">
          <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]"><tr>{["模型", "调用数", "成功率", "输入", "缓存", "输出", "推理", "总 Token", "总费用", "平均耗时", ""].map(label => <th key={label || "action"} className="px-3 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>
            {pagedRows.map(row => (
              <tr key={row.key} className="text-[var(--tc-text-secondary)]">
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
      <RangeFilter filters={filters} onChange={onFilterChange} />
      <ChipRow label="调用状态"><FilterButton active={!filters.status} onClick={() => onFilterChange({ ...filters, status: "" })}>全部状态</FilterButton>{([['completed', '成功'], ['failed', '失败'], ['running', '运行中']] as const).map(([id, label]) => <FilterButton key={id} active={filters.status === id} onClick={() => onFilterChange({ ...filters, status: id })}>{label}</FilterButton>)}</ChipRow>
      <ChipRow label="模型" scroll><FilterButton active={!filters.modelId} onClick={() => onFilterChange({ ...filters, modelId: "" })}>全部模型</FilterButton>{catalog.models.map(model => <FilterButton key={model.id} active={filters.modelId === model.id} onClick={() => onFilterChange({ ...filters, modelId: model.id })}>{model.display_name}</FilterButton>)}</ChipRow>
      {taskTypes.length ? <ChipRow label="任务" scroll><FilterButton active={!filters.taskType} onClick={() => onFilterChange({ ...filters, taskType: "" })}>全部任务</FilterButton>{taskTypes.map(task => <FilterButton key={task.key} active={filters.taskType === task.key} onClick={() => onFilterChange({ ...filters, taskType: task.key })}>{taskLabel(task.display_name)}</FilterButton>)}</ChipRow> : null}
      {(filters.modelId || filters.taskType || filters.status || filters.range !== EMPTY_FILTERS.range) ? <div className="flex justify-end py-2"><Button type="button" variant="outline" size="sm" onClick={() => onFilterChange(EMPTY_FILTERS)}><X className="size-3.5" />清除筛选</Button></div> : null}
      <div className="mt-3 min-h-0 flex-1 overflow-x-auto ">
        <table className="w-full min-w-[1040px] text-left text-xs">
          <thead className="bg-[var(--tc-surface-muted)] text-[var(--tc-text-muted)]"><tr>{["开始时间", "任务 / 范围", "模型", "状态", "Token 明细", "费用", "耗时", ""].map(label => <th key={label || "action"} className="px-3 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>
            {(loading ? [] : calls).map(call => (
              <tr key={call.call_id} className="text-[var(--tc-text-secondary)]">
                <td className="whitespace-nowrap px-3 py-2">{dateTime(call.started_at)}</td>
                <td className="max-w-64 px-3 py-2"><p className="truncate text-[var(--tc-text-primary)]">{taskLabel(call.task_name)}</p><p className="mt-0.5 truncate text-[11px] text-[var(--tc-text-muted)]">{call.chapter_ids.join("、") || (call.feature ? taskLabel(call.feature) : "无章节")}</p></td>
                <td className="px-3 py-2">{call.model_display_name}</td>
                <td className="px-3 py-2">{monitoredStatusLabel(call.status)}</td>
                <td className="px-3 py-2"><p className="tc-display-font text-[var(--tc-text-primary)]">总 {number(call.total_tokens)}</p><p className="mt-0.5 whitespace-nowrap text-[11px] text-[var(--tc-text-muted)]">入 {number(call.input_tokens)} · 缓 {number(call.cached_input_tokens)} · 出 {number(call.output_tokens)} · 推 {number(call.reasoning_tokens)}</p></td>
                <td className="px-3 py-2"><p>{monitoredCostLabel(call).replace(" CNY", " 元")}</p><p className="mt-0.5 text-[11px] text-[var(--tc-text-muted)]">{costKindLabel(call.cost_kind)}</p></td>
                <td className="px-3 py-2">{duration(call.duration_ms)}</td>
                <td className="px-3 py-2"><button type="button" onClick={() => void onOpenCall(call.call_id)} className="inline-flex items-center gap-1 whitespace-nowrap text-[var(--tc-text-primary)] hover:underline">详情<ChevronRight className="size-3" /></button></td>
              </tr>
            ))}
            {loading || !calls.length ? <EmptyRow colSpan={8} text={loading ? "调用明细加载中" : "当前范围内暂无调用"} /> : null}
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
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto ">
        {pagedModels.map(model => (
          <div key={model.id} className="grid items-center gap-2 px-3 py-2 text-xs grid-cols-[minmax(180px,1fr)_120px_190px_auto]">
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

function ProviderPanel({ providers, switching, onSwitch }: { providers: LLMProviderListResponse; switching: boolean; onSwitch: (providerId: LLMProviderListResponse["active_provider_id"]) => Promise<void> }) {
  const current = providers.providers.find(item => item.id === providers.active_provider_id);
  return (
    <section className="flex h-full min-h-0 flex-col pt-3" aria-labelledby="providers-title">
      <SectionHeading id="providers-title" title="模型供应商" meta={`当前：${current?.display_name ?? "未读取"}`} />
      <p className="mt-2 text-xs text-[var(--tc-text-muted)]">切换后，所有新调用只能选择并使用当前供应商支持的模型，不会跨供应商自动降级。</p>
      <div className="mt-4 grid gap-3 grid-cols-2">
        {providers.providers.map(provider => {
          const active = provider.id === providers.active_provider_id;
          return (
            <article key={provider.id} className={cn("border p-4", active ? "border-[var(--tc-text-primary)] bg-[var(--tc-surface-muted)]" : "border-[var(--tc-border-subtle)]")}>
              <div className="flex items-start justify-between gap-3">
                <div><h3 className="text-sm font-semibold text-[var(--tc-text-primary)]">{provider.display_name}</h3><p className="mt-1 text-xs leading-5 text-[var(--tc-text-muted)]">{provider.description}</p></div>
                <span className="shrink-0 text-xs text-[var(--tc-text-secondary)]">{provider.configured ? "已配置" : "未配置"}</span>
              </div>
              <div className="mt-4 py-3 text-xs">
                <p className="text-[var(--tc-text-muted)]">支持 {provider.model_count} 个模型</p>
                <p className="mt-2 leading-5 text-[var(--tc-text-secondary)]">{provider.model_names.join("、") || "暂无可用模型"}</p>
              </div>
              <Button className="mt-4 w-full" variant={active ? "outline" : "default"} disabled={active || !provider.configured || switching} onClick={() => void onSwitch(provider.id)}>
                {active ? "当前供应商" : provider.configured ? "切换到此供应商" : "尚未配置密钥"}
              </Button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ChipRow({ label, children, scroll = false }: { label: string; children: ReactNode; scroll?: boolean }) {
  return <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center py-1.5 text-xs"><span className="text-[var(--tc-text-muted)]">{label}</span><div className={cn("flex gap-1.5", scroll && "overflow-x-auto whitespace-nowrap pb-1")}>{children}</div></div>;
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={cn("shrink-0 rounded-full border px-3 py-1.5 text-xs transition-colors", active ? "border-[var(--tc-text-primary)] bg-[var(--tc-text-primary)] text-[var(--tc-surface-page)]" : "border-[var(--tc-border-subtle)] text-[var(--tc-text-muted)] hover:text-[var(--tc-text-primary)]")}>{children}</button>;
}

function SectionHeading({ id, title, meta }: { id: string; title: string; meta: string }) {
  return <div className="flex items-center justify-between gap-3"><h2 id={id} className="text-sm font-semibold text-[var(--tc-text-primary)]">{title}</h2><span className="text-xs text-[var(--tc-text-muted)]">{meta}</span></div>;
}

function CallDetail({ call, onClose }: { call: LLMCallRecord; onClose: () => void }) {
  const rows = [["调用 ID", call.call_id], ["关联运行 ID", call.run_id || "无"], ["功能来源", call.feature ? taskLabel(call.feature) : "未记录"], ["模型内部 ID", call.model_id], ["上游模型名", call.upstream_model], ["协议", protocolLabel(call.wire_protocol)], ["开始时间", dateTime(call.started_at)], ["结束时间", call.finished_at ? dateTime(call.finished_at) : "未结束"], ["输入 Token", number(call.input_tokens)], ["缓存 Token", number(call.cached_input_tokens)], ["输出 Token", number(call.output_tokens)], ["推理 Token", number(call.reasoning_tokens)], ["总 Token", number(call.total_tokens)], ["费用", call.cost_amount == null ? "未配置价格" : `${call.cost_amount} ${call.cost_currency}`], ["费用类型", costKindLabel(call.cost_kind)], ["上游请求 ID", call.provider_request_id || "未返回"], ["脱敏错误", call.error_message || "无"]];
  return <div className="fixed inset-0 z-50 flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="模型调用详情"><button type="button" className="min-w-0 flex-1" aria-label="关闭详情" onClick={onClose} /><aside className="h-full w-full max-w-lg overflow-y-auto bg-[var(--tc-surface-panel)] p-4"><div className="flex items-center justify-between pb-3"><div><p className="text-xs text-[var(--tc-text-muted)]">模型调用</p><h2 className="mt-1 text-base font-semibold text-[var(--tc-text-primary)]">调用详情</h2></div><Button variant="outline" size="icon-sm" onClick={onClose} aria-label="关闭详情"><X className="size-4" /></Button></div><dl className="">{rows.map(([label, value]) => <div key={label} className="grid grid-cols-[120px_1fr] gap-3 py-2 text-xs"><dt className="text-[var(--tc-text-muted)]">{label}</dt><dd className="break-all text-[var(--tc-text-primary)]">{value}</dd></div>)}</dl><p className="mt-3 text-xs text-[var(--tc-text-muted)]">为保护作品内容，详情默认不展示完整提示词和模型原始输出。</p></aside></div>;
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) { return <tr><td colSpan={colSpan} className="px-3 py-8 text-center text-[var(--tc-text-muted)]">{text}</td></tr>; }
function number(value?: number | null) { return value == null ? "未返回" : value.toLocaleString("zh-CN"); }
function compactNumber(value: number) { return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value); }
function money(value: string | number) { return `${Number(value).toFixed(4)} 元`; }
function combinedCost(actual: string | number, estimated: string | number) { const total = Number(actual) + Number(estimated); return total ? `${total.toFixed(4)} 元` : "—"; }
function duration(value: number) { return value >= 1000 ? `${(value / 1000).toFixed(1)} 秒` : `${value} 毫秒`; }
function dateTime(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false }); }
function costKindLabel(kind: LLMCallRecord["cost_kind"]) { return kind === "actual" ? "实际" : kind === "estimated" ? "预估" : "不可计算"; }
function availabilityLabel(value: string) { return value === "available" ? "可用" : value === "unavailable" ? "不可用" : "未检测"; }
function protocolLabel(value: string) { return value === "openai_responses" ? "Responses 协议" : value === "anthropic_messages" ? "Messages 协议" : "未知协议"; }
function mergeTaskTypes(current: LLMUsageGroup[], incoming: LLMUsageGroup[]) { const merged = new Map(current.map(item => [item.key, item])); for (const item of incoming) merged.set(item.key, item); return [...merged.values()].sort((left, right) => left.display_name.localeCompare(right.display_name, "zh-CN")); }
function emptyGroup(key: string, displayName: string): LLMUsageGroup { return { key, display_name: displayName, total_calls: 0, completed_calls: 0, failed_calls: 0, input_tokens: null, cached_input_tokens: null, output_tokens: null, reasoning_tokens: null, total_tokens: null, actual_cost: 0, estimated_cost: 0, unavailable_cost_calls: 0, average_duration_ms: 0 }; }
function taskLabel(value: string) { return knownGeneralCapabilityLabel(value) ?? ({ general_writing_assistant: "通用写作助手", "vector_graph.extract_triplets": "知识关系抽取" } as Record<string, string>)[value] ?? (/[\u4e00-\u9fff]/.test(value) ? value : "模型任务"); }
