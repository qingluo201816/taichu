"use client";

import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  CircleAlert,
  CircleCheck,
  ChevronDown,
  Database,
  ExternalLink,
  FileQuestion,
  RefreshCcw,
  ShieldCheck,
  Timer,
  UserRound,
  Wrench,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from "react";

import { GeneralAgentMonitorNav } from "@/components/agent-task-monitor/general-agent-monitor-nav";
import { AppShell } from "@/components/app-shell";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  getBenchmarkOpikSummary,
  getBenchmarkSuite,
  getBenchmarkSuiteArtifact,
  listBenchmarkRuns,
  listBenchmarkSuites,
} from "@/lib/api/general-agent-benchmark";
import {
  generalCapabilityLabel,
  knownGeneralCapabilityLabel,
} from "@/lib/general-agent-display";
import {
  normalizeBenchmarkRequestError,
  RequestCoordinator,
} from "@/lib/general-agent-benchmark-state";
import { suiteRunLifecycleLabel } from "@/lib/general-agent-benchmark-view";
import {
  SuiteRunLifecycle,
  type BenchmarkCaseExpectation,
  type BenchmarkCaseResult,
  type BenchmarkEntryId,
  type BenchmarkObservabilityEntry,
  type BenchmarkObservabilitySnapshot,
  type BenchmarkPortfolioEntry,
  type BenchmarkScenarioCategory,
  type BenchmarkSuiteArtifact,
  type BenchmarkSuiteDetail,
  type BenchmarkSuiteRun,
} from "@/lib/types/general-agent-benchmark";
import { cn } from "@/lib/utils";

type EvidenceBundle = BenchmarkSuiteArtifact["evidence_bundles"][number];
type EvidenceDetails = NonNullable<EvidenceBundle["details"]>;
type EvidenceGate = EvidenceDetails["gates"][number];
type EvidenceAction = EvidenceDetails["normalization_actions"][number];
type EvidenceGateKind = EvidenceGate["gate_kind"];

const proofGroups: ReadonlyArray<{
  id: string;
  title: string;
  summary: string;
  gateKinds: readonly EvidenceGateKind[];
}> = [
  {
    id: "behavior",
    title: "执行路径符合要求",
    summary: "核对调用次数、先后关系、数据交接和最终回答。",
    gateKinds: ["verifier"],
  },
  {
    id: "result",
    title: "结果与结束状态正确",
    summary: "核对所需产物确实形成，并在合同规定的状态结束。",
    gateKinds: ["artifact", "stop_reason"],
  },
  {
    id: "boundary",
    title: "资源与安全边界受控",
    summary: "核对预算、授权，以及正文、结构、知识库等资源是否被意外修改。",
    gateKinds: ["budget", "security"],
  },
  {
    id: "evidence",
    title: "结论具有完整证据",
    summary: "核对每项结论都来自同一次运行的有效证据。",
    gateKinds: ["evidence"],
  },
];

export function GeneralAgentEvaluationShell({
  entryId,
}: {
  entryId: BenchmarkEntryId;
}) {
  const [suite, setSuite] = useState<BenchmarkSuiteDetail | null>(null);
  const [latestRun, setLatestRun] = useState<BenchmarkSuiteRun | null>(null);
  const [artifact, setArtifact] = useState<BenchmarkSuiteArtifact | null>(null);
  const [opikSnapshot, setOpikSnapshot] = useState<
    BenchmarkObservabilitySnapshot | null | undefined
  >(undefined);
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [selectedContractId, setSelectedContractId] = useState("");
  const [error, setError] = useState("");
  const coordinator = useRef(new RequestCoordinator());

  const loadLatest = useCallback(async () => {
    const request = coordinator.current.begin();
    try {
      const [suitePage, runPage, opikSummary] = await Promise.all([
        listBenchmarkSuites({ page: 1, pageSize: 1 }, request.signal),
        listBenchmarkRuns({ page: 1, pageSize: 1 }, request.signal),
        getBenchmarkOpikSummary(request.signal).catch(() => null),
      ]);
      const suiteSummary = suitePage.items[0];
      if (!suiteSummary) {
        throw new Error("尚未配置固定评测基准。");
      }
      const detail = await getBenchmarkSuite(
        suiteSummary.suite_id,
        request.signal,
      );
      const run =
        runPage.items.find(
          item => item.suite_content_hash === detail.content_hash,
        ) ?? null;
      const latestArtifact =
        run?.terminal_artifact_ref &&
        run.lifecycle === SuiteRunLifecycle.COMPLETED
          ? await getBenchmarkSuiteArtifact(run.run_id, request.signal)
          : null;
      coordinator.current.apply(
        request,
        Math.max(suitePage.index_revision, runPage.index_revision),
        () => {
          const entry =
            detail.benchmark_entries.find(item => item.entry_id === entryId) ??
            detail.benchmark_entries[0];
          const firstCategory = entry?.categories[0];
          setSuite(detail);
          setLatestRun(run);
          setArtifact(latestArtifact);
          setOpikSnapshot(opikSummary);
          setSelectedCategoryId(current =>
            entry?.categories.some(
              category => category.category_id === current,
            )
              ? current
              : firstCategory?.category_id ?? "",
          );
          setSelectedContractId(current =>
            entry?.case_ids.includes(current)
              ? current
              : "",
          );
          setError("");
        },
      );
    } catch (caught) {
      const message = normalizeBenchmarkRequestError(caught);
      if (message) {
        setError(message);
      }
    }
  }, [entryId]);

  useEffect(() => {
    const activeCoordinator = coordinator.current;
    void Promise.resolve().then(loadLatest);
    return () => activeCoordinator.cancel();
  }, [loadLatest]);

  const selectedEntry = useMemo(
    () =>
      suite?.benchmark_entries.find(entry => entry.entry_id === entryId) ?? null,
    [entryId, suite],
  );
  const selectedCategory = useMemo(
    () =>
      selectedEntry?.categories.find(
        category => category.category_id === selectedCategoryId,
      ) ??
      selectedEntry?.categories[0] ??
      null,
    [selectedCategoryId, selectedEntry],
  );
  const contractsById = useMemo(
    () => new Map((suite?.cases ?? []).map(item => [item.case_id, item])),
    [suite],
  );
  const categoryContracts = useMemo(
    () =>
      (selectedCategory?.case_ids ?? [])
        .map(caseId => contractsById.get(caseId))
        .filter(
          (contract): contract is BenchmarkCaseExpectation =>
            contract !== undefined,
        ),
    [contractsById, selectedCategory],
  );
  const selectedContract = selectedEntry?.case_ids.includes(selectedContractId)
    ? (contractsById.get(selectedContractId) ?? null)
    : null;
  const selectedRow =
    artifact?.case_rows.find(
      row => row.case_id === selectedContract?.case_id,
    ) ?? null;
  const selectedEvidence =
    artifact?.evidence_bundles.find(
      bundle => bundle.identity.case_id === selectedContract?.case_id,
    ) ?? null;

  function selectCategory(category: BenchmarkScenarioCategory) {
    setSelectedCategoryId(category.category_id);
    setSelectedContractId("");
  }

  return (
    <AppShell activePath="/task-monitor">
      <section className="mx-auto min-h-full w-full max-w-[1200px] px-6 py-5">
        <GeneralAgentMonitorNav active="evaluation" />
        <BenchmarkEntryNav
          entries={suite?.benchmark_entries ?? []}
          activeEntryId={entryId}
        />
        <BenchmarkHeader
          entry={selectedEntry}
          artifact={artifact}
        />
        <OpikResultsPanel
          snapshot={opikSnapshot}
          entryId={entryId}
        />

        {error ? (
          <section className="mt-5 flex items-center justify-between gap-4 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] px-4 py-3 text-sm text-[var(--tc-text-primary)]">
            <span className="flex items-center gap-2">
              <CircleAlert className="size-4 text-amber-200" />
              {error}
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => void loadLatest()}
            >
              重新读取
            </Button>
          </section>
        ) : (
          <main className="mt-5">
            <ContractPicker
              categories={selectedEntry?.categories ?? []}
              category={selectedCategory}
              contracts={categoryContracts}
              contract={selectedContract}
              artifact={artifact}
              onCategoryChange={categoryId => {
                const category = selectedEntry?.categories.find(
                  item => item.category_id === categoryId,
                );
                if (category) selectCategory(category);
              }}
              onContractChange={setSelectedContractId}
              onShowIntroduction={() => setSelectedContractId("")}
            />
            {selectedContract ? (
              <ContractProof
                contract={selectedContract}
                row={selectedRow}
                evidence={selectedEvidence}
                run={latestRun}
              />
            ) : (
              <EvaluationIntroduction entry={selectedEntry} />
            )}
          </main>
        )}
      </section>
    </AppShell>
  );
}

function BenchmarkEntryNav({
  entries,
  activeEntryId,
}: {
  entries: BenchmarkPortfolioEntry[];
  activeEntryId: BenchmarkEntryId;
}) {
  const entryById = new Map(entries.map(entry => [entry.entry_id, entry]));
  const items: ReadonlyArray<{
    id: BenchmarkEntryId;
    href: string;
    fallbackName: string;
    fallbackCount: number;
    icon: ComponentType<{ className?: string }>;
  }> = [
    {
      id: "multi_step",
      href: "/task-monitor/general-agent/evaluation/multi-step",
      fallbackName: "多步骤组合任务",
      fallbackCount: 18,
      icon: Workflow,
    },
    {
      id: "recovery",
      href: "/task-monitor/general-agent/evaluation/recovery",
      fallbackName: "异常中断恢复",
      fallbackCount: 8,
      icon: RefreshCcw,
    },
  ];

  return (
    <nav
      aria-label="通用写作智能体评测入口"
      className="mt-4 grid grid-cols-2 gap-3"
    >
      {items.map(item => {
        const entry = entryById.get(item.id);
        const Icon = item.icon;
        const isActive = item.id === activeEntryId;
        return (
          <Link
            key={item.id}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-[var(--tc-radius-card)] px-4 py-3 transition-colors duration-150 motion-reduce:transition-none",
              isActive
                ? "bg-[var(--tc-surface-card)] text-[var(--tc-text-primary)] ring-1 ring-inset ring-white/10"
                : "bg-[var(--tc-surface-muted)] text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-card)] hover:text-[var(--tc-text-primary)]",
            )}
          >
            <span
              className={cn(
                "flex size-9 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)]",
                isActive ? "bg-cyan-300/10 text-cyan-200" : "bg-black/15",
              )}
            >
              <Icon className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">
                {entry?.name ?? item.fallbackName}
              </span>
              <span className="mt-0.5 block text-xs text-[var(--tc-text-muted)]">
                {entry?.case_count ?? item.fallbackCount} 条 · {entry?.categories.length ?? 0} 类
              </span>
            </span>
            <ArrowRight className="size-4 shrink-0 text-[var(--tc-text-muted)]" />
          </Link>
        );
      })}
    </nav>
  );
}

function BenchmarkHeader({
  entry,
  artifact,
}: {
  entry: BenchmarkPortfolioEntry | null;
  artifact: BenchmarkSuiteArtifact | null;
}) {
  const caseIds = new Set(entry?.case_ids ?? []);
  const total = entry?.case_count ?? 0;
  const passed =
    artifact?.case_rows.filter(
      row => caseIds.has(row.case_id) && row.conclusion === "passed",
    ).length ?? 0;
  const allPassed = total > 0 && passed === total;

  return (
    <header className="mt-6">
      <p className="text-xs text-[var(--tc-text-muted)]">
        通用写作智能体能力证明 · {entry?.name ?? "正在读取评测入口"}
      </p>
      <h1 className="mt-1 flex items-center gap-3 text-[32px] font-semibold leading-tight text-[var(--tc-text-primary)]">
        {total ? `${passed}/${total} 条合同通过` : "正在读取固定基准"}
        {allPassed ? (
          <CircleCheck className="size-6 text-emerald-300" />
        ) : null}
      </h1>
      {entry ? (
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--tc-text-secondary)]">
          {entry.summary}
        </p>
      ) : null}
    </header>
  );
}

function OpikResultsPanel({
  snapshot,
  entryId,
}: {
  snapshot: BenchmarkObservabilitySnapshot | null | undefined;
  entryId: BenchmarkEntryId;
}) {
  const entry =
    snapshot?.entries.find(item => item.entry_id === entryId) ?? null;
  const isAvailable = snapshot?.status === "available" && entry !== null;

  return (
    <section
      aria-labelledby="opik-results-title"
      className="mt-5 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] px-5 py-4"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] bg-cyan-300/10 text-cyan-200">
          <Activity className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2
              id="opik-results-title"
              className="text-sm font-medium text-[var(--tc-text-primary)]"
            >
              Opik 云端评测结果
            </h2>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11px]",
                isAvailable
                  ? "bg-emerald-300/10 text-emerald-200"
                  : "bg-amber-300/10 text-amber-100",
              )}
            >
              {isAvailable ? "已校验" : opikStatusLabel(snapshot)}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
            {snapshot === undefined
              ? "正在读取 Dataset、Experiment、评分与 Trace 摘要。"
              : snapshot?.message ??
                "Opik 结果接口暂时不可读取；本地合同结果不受影响。"}
          </p>
        </div>
        {isAvailable ? <OpikResultLinks entry={entry} /> : null}
      </div>

      {isAvailable ? (
        <>
          <dl className="mt-4 grid grid-cols-4 gap-2">
            <OpikMetric
              icon={Database}
              label="Dataset 数据集"
              value={`${entry.dataset_item_count} 条 · ${entry.dataset_version}`}
            />
            <OpikMetric
              icon={CircleCheck}
              label="Experiment 实验"
              value={`${entry.passed_count}/${entry.case_count} 条通过`}
            />
            <OpikMetric
              icon={Activity}
              label="Trace 链路"
              value={`${entry.trace_count} 条根链路`}
            />
            <OpikMetric
              icon={Timer}
              label="案例耗时中位数"
              value={formatOpikDuration(entry.duration_p50_ms)}
            />
          </dl>

          <div className="mt-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs font-medium text-[var(--tc-text-primary)]">
                八维固定合同评分
              </p>
              <p className="text-[11px] text-[var(--tc-text-muted)]">
                最近实验 · {formatOpikDate(entry.created_at)}
              </p>
            </div>
            <dl className="mt-3 grid grid-cols-4 gap-x-5 gap-y-3">
              {entry.scores.map(score => (
                <div key={score.name} className="min-w-0">
                  <dt className="truncate text-[11px] text-[var(--tc-text-muted)]">
                    {score.name}
                  </dt>
                  <dd className="mt-0.5 font-mono text-sm text-emerald-200">
                    {Math.round(score.value * 100)}%
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-[11px] text-[var(--tc-text-muted)]">
              {entry.total_estimated_cost === null
                ? "本轮使用确定性合成运行时，Opik 未计量真实模型费用。"
                : `Opik 估算费用：$${entry.total_estimated_cost.toFixed(4)}`}
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}

function OpikResultLinks({ entry }: { entry: BenchmarkObservabilityEntry }) {
  const links = [
    { href: entry.experiment_url, label: "打开实验", emphasized: true },
    { href: entry.dataset_url, label: "查看数据集", emphasized: false },
    { href: entry.traces_url, label: "查看 Trace", emphasized: false },
  ] as const;
  return (
    <div className="flex shrink-0 items-center gap-1">
      {links.map(link => (
        <a
          key={link.label}
          href={link.href}
          target="_blank"
          rel="noreferrer"
          className={buttonVariants({
            variant: link.emphasized ? "outline" : "ghost",
            size: "sm",
          })}
        >
          {link.label}
          <ExternalLink className="size-3.5" />
        </a>
      ))}
    </div>
  );
}

function OpikMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-3">
      <dt className="flex items-center gap-1.5 text-[11px] text-[var(--tc-text-muted)]">
        <Icon className="size-3.5" />
        {label}
      </dt>
      <dd className="mt-1 text-sm font-medium text-[var(--tc-text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function opikStatusLabel(
  snapshot: BenchmarkObservabilitySnapshot | null | undefined,
) {
  if (snapshot === undefined) return "读取中";
  if (snapshot?.status === "disabled") return "未启用";
  return "暂不可用";
}

function formatOpikDuration(value: number | null) {
  if (value === null) return "未计量";
  if (value < 1000) return `${Math.round(value)} 毫秒`;
  return `${(value / 1000).toFixed(2)} 秒`;
}

function formatOpikDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function ContractPicker({
  categories,
  category,
  contracts,
  contract,
  artifact,
  onCategoryChange,
  onContractChange,
  onShowIntroduction,
}: {
  categories: BenchmarkScenarioCategory[];
  category: BenchmarkScenarioCategory | null;
  contracts: BenchmarkCaseExpectation[];
  contract: BenchmarkCaseExpectation | null;
  artifact: BenchmarkSuiteArtifact | null;
  onCategoryChange: (categoryId: string) => void;
  onContractChange: (caseId: string) => void;
  onShowIntroduction: () => void;
}) {
  const rowsById = new Map(
    (artifact?.case_rows ?? []).map(row => [row.case_id, row]),
  );
  return (
    <section className="flex items-center gap-3 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] px-4 py-3">
      <span className="shrink-0 text-sm font-medium text-[var(--tc-text-primary)]">
        查看合同
      </span>
      <label className="relative block w-[300px]">
        <span className="sr-only">选择任务分类</span>
        <select
          aria-label="选择任务分类"
          value={category?.category_id ?? ""}
          onChange={event => onCategoryChange(event.target.value)}
          className="h-9 w-full appearance-none rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 pr-9 text-sm text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-text-primary)]"
        >
          {categories.map(item => {
            const result = categoryResult(item, artifact);
            return (
              <option key={item.category_id} value={item.category_id}>
                {item.name}
                {result.available
                  ? ` · ${result.passed}/${result.total} 通过`
                  : ""}
              </option>
            );
          })}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--tc-text-muted)]" />
      </label>
      <label className="relative block min-w-0 flex-1">
        <span className="sr-only">选择具体合同</span>
        <select
          aria-label="选择具体合同"
          value={contract?.case_id ?? ""}
          onChange={event => onContractChange(event.target.value)}
          className="h-9 w-full appearance-none rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 pr-9 text-sm text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-text-primary)]"
        >
          <option value="">选择一条合同查看证明</option>
          {contracts.map(item => {
            const row = rowsById.get(item.case_id);
            return (
              <option key={item.case_id} value={item.case_id}>
                {String(item.ordinal).padStart(2, "0")} · {item.name}
                {row?.conclusion === "passed" ? " · 已通过" : ""}
              </option>
            );
          })}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--tc-text-muted)]" />
      </label>
      <Button
        type="button"
        variant={contract ? "outline" : "secondary"}
        size="sm"
        className="shrink-0"
        onClick={onShowIntroduction}
      >
        <FileQuestion className="size-4" />
        评测说明
      </Button>
    </section>
  );
}

const evaluationDimensions = [
  {
    title: "处理方式对不对",
    description: "该直接回答就直接回答，该检索或确认时才调用相应能力。",
  },
  {
    title: "结果有没有得到",
    description: "用户需要的回答、草稿、预览或修改确实形成。",
  },
  {
    title: "有没有越权修改",
    description: "没有授权时，正文、结构和知识库保持不变。",
  },
] as const;

const evaluationTerms = [
  {
    term: "能力调用",
    meaning:
      "系统调用正文检索、知识库、写作工具或专业智能体等能力；模型在内部组织一次回答不算能力调用。",
  },
  {
    term: "资源变化",
    meaning:
      "原评测数据中的“副作用”。任何会修改正文、结构、知识库，创建或删除持久化内容，或向外部系统发送数据的动作，都属于资源变化。只读检索、规划和直接回答不属于资源变化。",
  },
  {
    term: "产物",
    meaning:
      "合同要求最终得到的内容，例如直接回答、分析结论、写作草稿、修改预览或已授权的正式写入。",
  },
  {
    term: "上下文令牌",
    meaning:
      "本次运行组装给模型阅读的上下文规模估算；它不等于模型实际消耗量。合成评测未调用真实模型时，真实模型用量会显示为未计量。",
  },
] as const;

function EvaluationIntroduction({
  entry,
}: {
  entry: BenchmarkPortfolioEntry | null;
}) {
  return (
    <article className="mt-4 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] px-6 py-5">
      <p className="text-xs text-[var(--tc-text-muted)]">评测说明</p>
      <h2 className="mt-1 text-xl font-semibold text-[var(--tc-text-primary)]">
        每条合同主要检查三件事
      </h2>
      <p className="mt-2 text-sm leading-6 text-[var(--tc-text-secondary)]">
        页面同时展示原问题、实际执行和最终结果，不会只给一个“通过”。
      </p>

      {entry ? (
        <section className="mt-5 grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-3">
          <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-4 py-3">
            <p className="text-xs text-[var(--tc-text-muted)]">Opik 数据集</p>
            <p className="mt-1 font-mono text-sm text-[var(--tc-text-primary)]">
              {entry.opik_dataset_name}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
              {entry.case_count} 条真实合同，可复用为批量实验和版本对比输入。
            </p>
          </div>
          <div className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-4 py-3">
            <p className="text-xs text-[var(--tc-text-muted)]">Trace 采集范围</p>
            <p className="mt-1 text-sm text-[var(--tc-text-primary)]">
              任务 · 模型轮次 · 工具 · 子图 · 恢复点
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
              使用嵌套链路记录执行树，默认关闭外发，配置 Opik 后启用。
            </p>
          </div>
        </section>
      ) : null}

      {entry ? (
        <section className="mt-5">
          <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
            覆盖 {entry.categories.length} 类真实场景
          </h3>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {entry.categories.map((category, index) => (
              <div
                key={category.category_id}
                className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2.5"
              >
                <p className="font-mono text-[11px] text-[var(--tc-text-muted)]">
                  {String(index + 1).padStart(2, "0")} · {category.case_ids.length} 条
                </p>
                <p className="mt-1 text-sm text-[var(--tc-text-primary)]">
                  {category.name}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-5">
        <dl className="grid grid-cols-3 gap-3">
          {evaluationDimensions.map((item, index) => (
            <div
              key={item.title}
              className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-3"
            >
              <dt className="font-mono text-xs text-[var(--tc-text-muted)]">
                {String(index + 1).padStart(2, "0")}
              </dt>
              <dd className="mt-2">
                <p className="text-sm font-medium text-[var(--tc-text-primary)]">
                  {item.title}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
                  {item.description}
                </p>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {entry ? (
        <section className="mt-5">
          <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
            什么算无效工具调用
          </h3>
          <p className="mt-1 text-xs leading-5 text-[var(--tc-text-secondary)]">
            不是凭模型主观打分，而是由合同中的能力白名单、次数上限、依赖关系和证据消费规则判定。
          </p>
          <ol className="mt-2 grid grid-cols-2 gap-2">
            {entry.invalid_invocation_rules.map((rule, index) => (
              <li
                key={rule}
                className="flex gap-2 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2.5 text-xs leading-5 text-[var(--tc-text-secondary)]"
              >
                <span className="font-mono text-[var(--tc-text-muted)]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span>{rule}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <details className="group mt-4 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)]">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm text-[var(--tc-text-secondary)]">
          不明白合同中的名词？查看术语解释
          <ChevronDown className="ml-auto size-4 transition-transform group-open:rotate-180" />
        </summary>
        <dl className="px-3 pb-3">
          {evaluationTerms.map(item => (
            <div
              key={item.term}
              className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 py-1.5 text-xs leading-5"
            >
              <dt className="text-[var(--tc-text-primary)]">{item.term}</dt>
              <dd className="text-[var(--tc-text-secondary)]">{item.meaning}</dd>
            </div>
          ))}
        </dl>
      </details>
    </article>
  );
}

function ContractProof({
  contract,
  row,
  evidence,
  run,
}: {
  contract: BenchmarkCaseExpectation | null;
  row: BenchmarkCaseResult | null;
  evidence: EvidenceBundle | null;
  run: BenchmarkSuiteRun | null;
}) {
  if (!contract) {
    return (
      <article className="mt-4 flex min-h-80 items-center justify-center rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] text-sm text-[var(--tc-text-muted)]">
        正在读取合同证明。
      </article>
    );
  }

  const details = evidence?.details;
  const gates = details?.gates ?? [];
  const actualAnswer = evidenceAnswer(details);
  const passed = row?.conclusion === "passed";
  return (
    <article className="mt-4 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-card)] px-6 py-5">
      <p className="text-xs text-[var(--tc-text-muted)]">
        合同 {String(contract.ordinal).padStart(2, "0")} ·{" "}
        {contractResultLabel(row, run)}
      </p>
      <h2 className="mt-1 text-xl font-semibold text-[var(--tc-text-primary)]">
        {contract.name}
      </h2>

      <section className="mt-5 grid gap-5">
        <div>
          <h3 className="text-xs text-[var(--tc-text-muted)]">
            用户当时提出的问题
          </h3>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-primary)]">
            {contract.user_request}
          </p>
        </div>
        <div>
          <h3 className="text-xs text-[var(--tc-text-muted)]">
            系统实际给出的回答
          </h3>
          {actualAnswer ? (
            <>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-text-primary)]">
                {actualAnswer.text}
              </p>
              {actualAnswer.normalized ? (
                <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
                  这是运行证据中保存的回答内容，标点已由核验程序统一。
                </p>
              ) : null}
            </>
          ) : (
            <p className="mt-1 text-sm leading-6 text-[var(--tc-text-muted)]">
              这条合同没有形成可展示的最终回答；请在下方查看它要求的其他产物和运行状态。
            </p>
          )}
        </div>
      </section>

      <div className="mt-4 flex items-start gap-3 rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-muted)] p-4">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-emerald-950/30">
          {passed ? (
            <ShieldCheck className="size-4 text-emerald-300" />
          ) : (
            <CircleAlert className="size-4 text-amber-200" />
          )}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--tc-text-primary)]">
            {passed ? "能力结论成立" : "能力结论尚未成立"}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--tc-text-secondary)]">
            {passed
              ? `最新运行已经证明：${contract.objective}`
              : "最新运行尚未同时满足合同声明的过程、结果、安全边界与证据要求。"}
          </p>
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-[96px_minmax(0,1fr)] gap-x-5 gap-y-4 text-sm leading-6">
        <dt className="text-[var(--tc-text-muted)]">合同要求</dt>
        <dd className="space-y-1 text-[var(--tc-text-secondary)]">
          <p>{contract.target_final_artifact}</p>
          <p className="text-xs text-[var(--tc-text-muted)]">
            {terminalExpectation(contract)}
          </p>
        </dd>
        <dt className="text-[var(--tc-text-muted)]">最新运行</dt>
        <dd className="space-y-1 text-[var(--tc-text-secondary)]">
          <p>{executionSummary(details, passed)}</p>
          <p className="text-xs text-[var(--tc-text-muted)]">
            下方可查看实际运行过程和逐项核验结果。
          </p>
        </dd>
      </dl>

      <details className="group mt-5 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)]">
        <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3">
          <span className="text-sm font-medium text-[var(--tc-text-primary)]">
            查看完整合同与运行证据
          </span>
          <ArrowRight className="ml-auto size-4 text-[var(--tc-text-muted)] transition-transform group-open:rotate-90" />
        </summary>
        <div className="space-y-6 px-4 pb-4">
          <section>
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
              完整合同要求
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm leading-6 text-[var(--tc-text-secondary)]">
              {contract.behavior_expectations.map((expectation, index) => (
                <li
                  key={`${contract.case_id}-${index}`}
                  className="flex gap-2"
                >
                  <span className="font-mono text-xs text-[var(--tc-text-muted)]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>{contractExpectationText(contract, expectation)}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
              实际运行过程
            </h3>
            <div className="mt-2 space-y-1.5">
              {details?.normalization_actions.length ? (
                <>
                  {details.normalization_actions.map(action => (
                    <ExecutionActionRow
                      key={`${action.step_id}-${action.step_index}`}
                      action={action}
                    />
                  ))}
                  <ExecutionTerminal details={details} />
                </>
              ) : (
                <p className="text-sm leading-6 text-[var(--tc-text-muted)]">
                  {passed
                    ? "该合同要求在调用任何能力前安全停止；运行没有产生多余调用或副作用。"
                    : "最新运行尚未形成可展示的执行轨迹。"}
                </p>
              )}
            </div>
          </section>
          <section>
            <h3 className="text-sm font-medium text-[var(--tc-text-primary)]">
              核验依据
            </h3>
            <div className="mt-2 space-y-2">
              {proofGroups.map(group => (
                <ProofGroup
                  key={group.id}
                  title={group.title}
                  summary={group.summary}
                  gates={gates.filter(gate =>
                    group.gateKinds.includes(gate.gate_kind),
                  )}
                  actualAnswer={actualAnswer?.text ?? null}
                  synthetic={details?.track === "synthetic" || run?.track === "synthetic"}
                />
              ))}
            </div>
          </section>
        </div>
      </details>
    </article>
  );
}

function executionSummary(
  details: EvidenceDetails | null | undefined,
  passed: boolean,
): string {
  const actions = details?.normalization_actions ?? [];
  if (actions.length === 0) {
    return passed
      ? "运行在调用能力前按合同安全停止，没有产生多余调用或副作用。"
      : "最新运行尚未形成可展示的执行轨迹。";
  }
  const actionLabels = actions
    .slice(0, 3)
    .map(action => actionDisplay(action).label);
  const omitted = actions.length - actionLabels.length;
  const terminal = details?.terminal
    ? terminalStatusLabel(details.terminal.run_status)
    : "合同规定状态";
  return `共执行 ${actions.length} 步：${actionLabels.join("、")}${
    omitted > 0 ? `等 ${omitted + actionLabels.length} 步` : ""
  }，最终以“${terminal}”结束。`;
}

/*
 * 详细证据只在作者主动展开时展示。以下组件保留紧凑动作行与逐项核验，
 * 不再占据页面默认阅读层级。
 */
function ExecutionActionRow({ action }: { action: EvidenceAction }) {
  const display = actionDisplay(action);
  const Icon = display.icon;
  return (
    <div className="grid grid-cols-[32px_minmax(0,1fr)_70px] items-center gap-2 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-2">
      <span
        className={cn(
          "flex size-7 items-center justify-center rounded-full",
          display.iconSurface,
        )}
      >
        <Icon className={cn("size-3.5", display.iconColor)} />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm text-[var(--tc-text-primary)]">
          {display.label}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--tc-text-muted)]">
          第 {action.step_index + 1} 步
        </p>
      </div>
      <span className="text-right text-xs text-emerald-300">
        {action.outcome === "completed" ? "已完成" : "已记录"}
      </span>
    </div>
  );
}

function ExecutionTerminal({ details }: { details: EvidenceDetails }) {
  if (!details.terminal) return null;
  return (
    <div className="grid grid-cols-[32px_minmax(0,1fr)_70px] items-center gap-2 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2">
      <span className="flex size-7 items-center justify-center rounded-full bg-emerald-950/30">
        <Check className="size-3.5 text-emerald-300" />
      </span>
      <div>
        <p className="text-sm text-[var(--tc-text-primary)]">
          运行按合同结束
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--tc-text-muted)]">
          {terminalStatusLabel(details.terminal.run_status)}
          {" · "}
          {details.terminal.resumable ? "允许继续" : "无需继续"}
        </p>
      </div>
      <span className="text-right text-xs text-emerald-300">终态正确</span>
    </div>
  );
}

function ProofGroup({
  title,
  summary,
  gates,
  actualAnswer,
  synthetic,
}: {
  title: string;
  summary: string;
  gates: EvidenceGate[];
  actualAnswer: string | null;
  synthetic: boolean;
}) {
  const passed =
    gates.length > 0 && gates.every(gate => gate.status === "passed");
  const rows = proofRows(gates, { actualAnswer, synthetic });
  return (
    <details className="group rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)]">
      <summary className="grid cursor-pointer list-none grid-cols-[150px_minmax(0,1fr)_72px_18px] items-center gap-3 px-3 py-2.5">
        <span className="text-sm font-medium text-[var(--tc-text-primary)]">
          {title}
        </span>
        <span className="text-xs text-[var(--tc-text-muted)]">{summary}</span>
        <span
          className={cn(
            "text-right text-xs",
            passed ? "text-emerald-300" : "text-amber-200",
          )}
        >
          {passed ? "符合要求" : gates.length ? "未通过" : "等待证据"}
        </span>
        <ArrowRight className="size-4 text-[var(--tc-text-muted)] transition-transform group-open:rotate-90" />
      </summary>
      <div className="space-y-1.5 px-3 pb-3">
        {rows.map((row, index) => (
          <div
            key={`${row.title}-${index}`}
            className="grid grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)_52px] gap-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-card)] px-3 py-2 text-xs leading-5"
          >
            <span className="text-[var(--tc-text-primary)]">{row.title}</span>
            <span className="text-[var(--tc-text-secondary)]">
              <span className="mr-1 text-[var(--tc-text-muted)]">要求</span>
              {row.expected}
            </span>
            <span className="text-[var(--tc-text-secondary)]">
              <span className="mr-1 text-[var(--tc-text-muted)]">实际</span>
              {row.observed}
            </span>
            <span
              className={
                row.passed ? "text-emerald-300" : "text-amber-200"
              }
            >
              {row.passed ? "通过" : "未通过"}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

interface ProofRow {
  title: string;
  expected: string;
  observed: string;
  passed: boolean;
}

function proofRows(
  gates: EvidenceGate[],
  context: { actualAnswer: string | null; synthetic: boolean },
): ProofRow[] {
  const rows: ProofRow[] = [];
  for (const gate of gates) {
    if (gate.gate_kind === "security") {
      rows.push({
        title: "是否意外修改内容",
        expected:
          "只允许合同声明的动作；没有授权时，不得修改正文、结构、知识库或产生其他持久化写入。",
        observed:
          gate.status === "passed"
            ? "没有发现合同以外的修改；受保护的正文、结构和知识库保持原样。"
            : "运行证据表明安全边界没有全部满足。",
        passed: gate.status === "passed",
      });
      continue;
    }
    if (gate.gate_kind === "evidence") {
      rows.push({
        title: "证据完整性",
        expected: "六类核验证据必须存在、属于本次合同且内容可校验。",
        observed:
          gate.status === "passed"
            ? "全部核验证据完整，执行记录没有缺失、乱序或额外交互。"
            : "存在缺失或无法校验的运行证据。",
        passed: gate.status === "passed",
      });
      continue;
    }
    if (gate.conditions.length === 0) {
      rows.push({
        title: gateKindLabel(gate.gate_kind),
        expected: "该项合同条件必须成立。",
        observed: gate.status === "passed" ? "对应证据已经确认。" : "条件未成立。",
        passed: gate.status === "passed",
      });
      continue;
    }
    rows.push(
      ...gate.conditions.map(condition => ({
        title: conditionLabel(condition.condition_id),
        expected: humanizeEvidenceText(condition.expected, "expected", {
          ...context,
          conditionId: condition.condition_id,
        }),
        observed: humanizeEvidenceText(condition.observed, "observed", {
          ...context,
          conditionId: condition.condition_id,
        }),
        passed: condition.status === "passed",
      })),
    );
  }
  return rows;
}

function actionDisplay(action: EvidenceAction): {
  label: string;
  icon: ComponentType<{ className?: string }>;
  iconColor: string;
  iconSurface: string;
} {
  if (action.name === "orchestrator_plan") {
    return {
      label: "模型 · 判断最小执行路径并规划回答",
      icon: BrainCircuit,
      iconColor: "text-amber-200",
      iconSurface: "bg-amber-950/35",
    };
  }
  if (action.name === "orchestrator_verify") {
    return {
      label: "模型 · 核验执行结果与合同目标",
      icon: BrainCircuit,
      iconColor: "text-amber-200",
      iconSurface: "bg-amber-950/35",
    };
  }
  if (action.name === "write_authorization") {
    return {
      label: "人工确认 · 写入授权",
      icon: UserRound,
      iconColor: "text-orange-200",
      iconSurface: "bg-orange-950/35",
    };
  }
  const capabilityName = action.name.endsWith("_model")
    ? action.name.slice(0, -"_model".length)
    : action.name;
  const capabilityLabel = generalCapabilityLabel(capabilityName);
  const typeCopy = {
    human: {
      type: "人工确认",
      icon: UserRound,
      color: "text-orange-200",
      surface: "bg-orange-950/35",
    },
    model: {
      type: "模型",
      icon: BrainCircuit,
      color: "text-amber-200",
      surface: "bg-amber-950/35",
    },
    tool: {
      type: "工具",
      icon: Wrench,
      color: "text-cyan-200",
      surface: "bg-cyan-950/35",
    },
    subagent: {
      type: "专业智能体",
      icon: Bot,
      color: "text-purple-200",
      surface: "bg-purple-950/35",
    },
  }[action.kind];
  return {
    label: `${typeCopy.type} · ${capabilityLabel}`,
    icon: typeCopy.icon,
    iconColor: typeCopy.color,
    iconSurface: typeCopy.surface,
  };
}

function evidenceAnswer(
  details: EvidenceDetails | null | undefined,
): { text: string; normalized: boolean } | null {
  const rawText = details?.final_answer_text?.trim();
  if (rawText) {
    return { text: rawText, normalized: false };
  }
  const projection = details?.assertions
    ?.map(assertion => assertion.claim_projection?.normalized_text?.trim())
    .find((text): text is string => Boolean(text));
  return projection ? { text: projection, normalized: true } : null;
}

function contractExpectationText(
  contract: BenchmarkCaseExpectation,
  expectation: string,
): string {
  if (
    contract.case_id === "direct_answer_current_request" &&
    expectation.includes("冲突场景")
  ) {
    return "针对上方这道写作问题，回答要先给出明确结论：冲突双方需要有不能同时实现的目标；再解释目标互斥为什么会形成持续阻力。";
  }
  if (expectation.includes("禁止任何能力调用或副作用")) {
    return "这道题只能直接回答：不得调用检索、写作等能力，也不得修改正文、结构、知识库或创建写入内容。";
  }
  return expectation.replaceAll(
    "副作用",
    "资源变化（例如修改正文、结构、知识库或创建写入内容）",
  );
}

function terminalExpectation(contract: BenchmarkCaseExpectation): string {
  const terminal = contract.expected_terminal;
  const parts = [
    terminalStatusLabel(terminal.run_status),
    terminal.resumable ? "允许从当前状态继续" : "无需继续运行",
    terminal.pending_human_kind ? "需要人工处理" : "不等待人工处理",
    recoveryActionLabel(terminal.recovery_action),
  ];
  return parts.join("；");
}

function terminalStatusLabel(value: string): string {
  return {
    completed: "完成任务",
    preview_only: "只形成预览",
    write_rejected: "记录拒绝并安全结束",
    waiting_human: "等待人工确认",
    safe_failure: "无法安全执行并明确停止",
  }[value] ?? "按合同规定结束";
}

function recoveryActionLabel(value: string): string {
  return {
    none: "不需要恢复动作",
    resume: "确认后继续运行",
    reuse_checkpoint: "复用有效检查点",
    reconcile_effect: "先核对真实写入结果",
    stop: "停止后不再重试",
  }[value] ?? "按合同处理恢复";
}

function contractResultLabel(
  row: BenchmarkCaseResult | null,
  run: BenchmarkSuiteRun | null,
): string {
  if (!run) return "尚未运行";
  if (!row) return suiteRunLifecycleLabel(run.lifecycle);
  return row.conclusion === "passed" ? "合同已通过" : "合同未通过";
}

function categoryResult(
  category: BenchmarkScenarioCategory,
  artifact: BenchmarkSuiteArtifact | null,
): { total: number; passed: number; available: boolean } {
  const caseIds = new Set(category.case_ids);
  const rows = (artifact?.case_rows ?? []).filter(row =>
    caseIds.has(row.case_id),
  );
  return {
    total: category.case_ids.length,
    passed: rows.filter(row => row.conclusion === "passed").length,
    available: rows.length > 0,
  };
}

function conditionLabel(value: string): string {
  const labels: Array<[string, string]> = [
    ["budget_node_executions", "节点执行次数"],
    ["budget_replans", "重新规划次数"],
    ["budget_capability_calls", "能力调用次数"],
    ["budget_model_calls", "模型调用次数"],
    ["budget_total_tokens", "真实模型令牌用量"],
    ["budget_runtime_ms", "运行时长"],
    ["budget_context_tokens", "上下文令牌"],
    ["stop_run_status", "运行终态"],
    ["stop_resumable", "是否允许继续"],
    ["stop_pending_human", "人工确认状态"],
    ["stop_reason_code", "停止原因"],
    ["stop_recovery_action", "恢复动作"],
  ];
  const exact = labels.find(([key]) => key === value);
  if (exact) return exact[1];
  if (value.includes("count")) return "调用次数";
  if (value.includes("topology")) return "分支依赖关系";
  if (value.includes("flow")) return "上下游数据交接";
  if (value.includes("claim")) return "最终回答内容";
  if (value.includes("artifact")) return "所需产物";
  if (value.includes("source")) return "来源引用";
  if (value.includes("memory")) return "记忆隔离";
  if (value.includes("checkpoint")) return "检查点可用性";
  if (value.includes("authorization")) return "授权结果";
  if (value.includes("auth")) return "授权与写入绑定";
  if (value.includes("recovery")) return "恢复执行结果";
  if (value.includes("context")) return "上下文边界";
  if (value.includes("zero")) return "是否调用或修改内容";
  if (value.includes("human")) return "人工确认记录";
  if (
    value.includes("unchanged") ||
    value.includes("created") ||
    value.includes("updated") ||
    value.includes("deleted") ||
    value.includes("target_only")
  ) {
    return "目标资源变更";
  }
  return "固定合同条件";
}

function gateKindLabel(value: string): string {
  return {
    artifact: "结果产物",
    budget: "资源预算",
    evidence: "证据完整性",
    security: "安全边界",
    stop_reason: "结束状态",
    verifier: "行为校验",
  }[value] ?? "合同条件";
}

function humanizeEvidenceText(
  value: string,
  mode: "expected" | "observed",
  context?: {
    actualAnswer: string | null;
    synthetic: boolean;
    conditionId: string;
  },
): string {
  if (
    context?.conditionId === "budget_total_tokens" &&
    mode === "expected"
  ) {
    const limit = value.match(/(\d+)/)?.[1] ?? "合同上限";
    return `真实模型的输入与输出令牌合计不得超过 ${limit}。`;
  }
  if (
    context?.conditionId === "budget_context_tokens" &&
    mode === "expected"
  ) {
    const limit = value.match(/(\d+)/)?.[1] ?? "合同上限";
    return `组装给模型阅读的上下文不得超过 ${limit} 个令牌。`;
  }
  if (
    context?.conditionId === "budget_context_tokens" &&
    mode === "observed"
  ) {
    const total = value.match(/(\d+)/)?.[1] ?? "未知";
    return `本次组装的上下文约为 ${total} 个令牌。`;
  }
  if (
    context?.conditionId === "budget_runtime_ms" &&
    mode === "observed"
  ) {
    const duration = value.match(/(\d+)/)?.[1] ?? "未知";
    return `本次运行耗时 ${duration} 毫秒。`;
  }
  if (/observed=\(.+\).*missing=\(\).*forbidden=\(\)/.test(value)) {
    return context?.actualAnswer
      ? `核验程序在实际回答中识别到合同要求的内容。实际回答为：“${context.actualAnswer}”`
      : "核验程序在回答中识别到合同要求的内容，且未发现合同禁止出现的内容。";
  }
  if (
    mode === "expected" &&
    (value.includes("副作用") ||
      value.includes("require_zero_side_effects") ||
      value.includes("禁止任何能力调用"))
  ) {
    return "这道题只需直接回答：不得调用检索、写作等能力，也不得修改正文、结构、知识库或创建写入内容。";
  }
  if (value.includes("producer/consumer 身份一致")) {
    return "上游产物与下游输入一致。";
  }
  if (value.includes("实际关系满足 independent")) {
    return "执行分支彼此独立，没有隐藏依赖。";
  }
  if (value.includes("final_answer 存在")) {
    return context?.actualAnswer
      ? `最终回答已形成，内容为：“${context.actualAnswer}”`
      : "最终回答已经形成，但这份旧运行证据没有保留可展示的回答正文。";
  }
  if (value.includes("capability_artifact 存在")) {
    return "合同要求的能力产物已经生成。";
  }
  if (value.includes("source_reference 存在")) {
    return "所需来源引用已经保留。";
  }
  if (value.includes("human_intervention 存在")) {
    return "合同要求的人工确认记录已经产生。";
  }

  const zeroEffectMatch = value.match(
    /capability_calls=(\d+)；effect_count=(\d+)；resource_changed=(True|False)；write_artifact=(True|False)/,
  );
  if (zeroEffectMatch) {
    const [, capabilityCalls, effectCount, resourceChanged, writeArtifact] =
      zeroEffectMatch;
    const resourceResult =
      resourceChanged === "True"
        ? "正文、结构或知识库等受保护内容发生了变化"
        : "正文、结构和知识库等受保护内容均未改变";
    const artifactResult =
      writeArtifact === "True"
        ? "产生了持久化写入内容"
        : "没有产生持久化写入内容";
    return `调用检索、写作等能力 ${capabilityCalls} 次；记录到 ${effectCount} 次资源变化；${resourceResult}；${artifactResult}。`;
  }

  if (
    context?.synthetic &&
    context.conditionId === "budget_total_tokens" &&
    mode === "observed"
  ) {
    return "本次是合成评测，没有调用真实模型，因此没有可计量的真实模型令牌用量。";
  }
  if (
    context?.synthetic &&
    context.conditionId === "budget_model_calls" &&
    mode === "observed"
  ) {
    const callCount = value.match(/(\d+)/)?.[1] ?? "0";
    return `合成评测模拟了 ${callCount} 次模型交互。`;
  }

  const actualChangeMatch = value.match(
    /actual_change=(created|updated|deleted|unchanged).*protected_changed=\(\)/,
  );
  if (actualChangeMatch) {
    const changeLabel = {
      created: "目标资源已经创建",
      updated: "目标资源已经更新",
      deleted: "目标资源已经删除",
      unchanged: "目标资源保持不变",
    }[actualChangeMatch[1]];
    return `${changeLabel}，且没有改变任何受保护资源。`;
  }

  const authorizationMatch = value.match(
    /decision=(approved|confirmed|denied)；effect_count=(\d+)；target_ok=(True|False)；preview_ok=(True|False)；unbound_effects=\(\)/,
  );
  if (authorizationMatch) {
    const [, decision, effectCount, targetOk, previewOk] = authorizationMatch;
    const decisionLabel = {
      approved: "已批准",
      confirmed: "已完成二次确认",
      denied: "已拒绝",
    }[decision];
    return `授权结果${decisionLabel}，产生 ${effectCount} 次写入；${
      targetOk === "True" ? "写入目标正确" : "写入目标不正确"
    }，${previewOk === "True" ? "与预览一致" : "与预览不一致"}，没有无归属副作用。`;
  }

  const recoveryMatch = value.match(
    /plan_same=(True|False)；successful_node_reexecutions=(\d+)；duplicate_side_effects=(\d+)/,
  );
  if (recoveryMatch) {
    const [, planSame, repeatedNodes, duplicateEffects] = recoveryMatch;
    return `恢复后${planSame === "True" ? "沿用原计划" : "没有沿用原计划"}；已成功节点重复执行 ${repeatedNodes} 次；重复副作用 ${duplicateEffects} 次。`;
  }

  const checkpointMatch = value.match(
    /valid=\(\)；invalid=\(([^)]*)\)；selected=None；action=stop/,
  );
  if (checkpointMatch) {
    const invalidCount = checkpointMatch[1]
      .split(",")
      .map(item => item.trim())
      .filter(Boolean).length;
    return `检测到 ${invalidCount} 个无效检查点，没有选择其中任何一个，并安全停止。`;
  }

  const contextMatch = value.match(
    /current_request_ok=(True|False)；preserved=\(([^)]*)\)/,
  );
  if (contextMatch) {
    const memoryLabels: Record<string, string> = {
      stable_memory: "稳定记忆",
      long_term_memory: "长期记忆",
      history_memory: "历史对话",
      working_memory: "工作记忆",
      current_request: "当前请求",
    };
    const preserved = Array.from(
      contextMatch[2].matchAll(/'([^']+)'/g),
      match => memoryLabels[match[1]] ?? "受保护上下文",
    );
    return `${contextMatch[1] === "True" ? "当前请求原文保持完整" : "当前请求原文未能完整保留"}；${preserved.join("、")}均已保留。`;
  }

  if (value.includes("实际嵌套调用关系满足 before")) {
    return "嵌套调用遵守了合同规定的先后顺序。";
  }
  if (value.includes("实际关系满足 before")) {
    return "调用遵守了先执行上游、再执行下游的顺序。";
  }

  const termLabels: Record<string, string> = {
    completed: "完成",
    preview_only: "仅形成预览",
    write_rejected: "写入被拒绝",
    waiting_human: "等待人工确认",
    safe_failure: "安全停止",
    goal_satisfied: "目标已完成",
    unsafe_context: "上下文无法安全组装",
    waiting_authorization: "等待写入授权",
    checkpoint_invalid: "检查点损坏或不兼容",
    none: "无",
    resume: "继续运行",
    reuse_checkpoint: "复用有效检查点",
    reconcile_effect: "核对真实写入结果",
    stop: "停止",
    independent: "互不依赖",
    before: "先于",
    final_answer: "最终回答",
    capability_artifact: "能力产物",
    source_reference: "来源引用",
    artifact_id: "工件标识",
    producer: "产出者",
    payload: "工件内容",
    chapter_001: "第一章",
  };
  let hasUnknownInternalToken = false;
  const translated = value.replace(/\b[a-z][a-z0-9_.]*\b/g, token => {
    const capability = knownGeneralCapabilityLabel(
      token.endsWith("_model")
        ? token.slice(0, -"_model".length)
        : token,
    );
    const label = capability ?? termLabels[token];
    if (!label) {
      hasUnknownInternalToken = true;
      return token;
    }
    return label;
  });
  if (mode === "observed" && hasUnknownInternalToken) {
    return "运行证据已经满足这项合同条件。";
  }
  return translated
    .replaceAll("实际为", "为")
    .replace(/^实际/, "")
    .replaceAll("Checkpoint", "检查点")
    .replaceAll("Subagent", "专业智能体")
    .replaceAll("Tool", "工具")
    .replaceAll("Effect", "实际写入")
    .replaceAll("Token", "令牌")
    .replaceAll(" ID", "标识");
}
