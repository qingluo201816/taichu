import {
  CaseExecutionState,
  ProviderExecutionState,
  SuiteConclusion,
  SuiteRunLifecycle,
  type BenchmarkSuiteArtifact,
  type BenchmarkSuiteRun,
} from "./types/general-agent-benchmark";

export type ConclusionTone = "success" | "danger" | "warning" | "neutral";

export interface BenchmarkHeadline {
  title: string;
  detail: string;
  tone: ConclusionTone;
}

export interface BenchmarkRunProgress {
  total: number;
  passed: number;
  failed: number;
  invalid: number;
  pending: number;
  allPassed: boolean;
}

const lifecycleLabels: Record<SuiteRunLifecycle, string> = {
  [SuiteRunLifecycle.QUEUED]: "等待运行",
  [SuiteRunLifecycle.RUNNING]: "正在运行",
  [SuiteRunLifecycle.CANCELLING]: "正在取消",
  [SuiteRunLifecycle.FINALIZING]: "正在汇总结论",
  [SuiteRunLifecycle.COMPLETED]: "运行完成",
  [SuiteRunLifecycle.UNFINISHED]: "运行未完成",
  [SuiteRunLifecycle.CANCELLED]: "已取消",
};

const conclusionHeadlines: Record<SuiteConclusion, BenchmarkHeadline> = {
  [SuiteConclusion.PASSED]: {
    title: "整体能力硬门禁通过",
    detail: "固定基准的全部必要条件均已满足。",
    tone: "success",
  },
  [SuiteConclusion.FAILED]: {
    title: "整体能力硬门禁未通过",
    detail: "至少一个必要能力条件未满足，请下钻查看失败案例。",
    tone: "danger",
  },
  [SuiteConclusion.INVALID]: {
    title: "套件结论无效",
    detail: "证据或运行条件不足，不能据此判断能力是否达标。",
    tone: "warning",
  },
  [SuiteConclusion.NOT_EVALUATED]: {
    title: "套件未形成评测结论",
    detail: "本次运行没有满足可评测条件。",
    tone: "neutral",
  },
};

export function suiteRunLifecycleLabel(lifecycle: SuiteRunLifecycle): string {
  return lifecycleLabels[lifecycle];
}

export function providerExecutionStateLabel(
  state: ProviderExecutionState,
): string {
  return {
    [ProviderExecutionState.NOT_APPLICABLE]: "不涉及真实提供商",
    [ProviderExecutionState.PENDING]: "等待提供商",
    [ProviderExecutionState.RUNNING]: "提供商执行中",
    [ProviderExecutionState.BLOCKED]: "提供商已阻断",
    [ProviderExecutionState.ERROR]: "提供商错误",
    [ProviderExecutionState.COMPLETED]: "提供商执行完成",
  }[state];
}

export function caseExecutionStateLabel(state: CaseExecutionState): string {
  return {
    [CaseExecutionState.PENDING]: "等待执行",
    [CaseExecutionState.RUNNING]: "执行中",
    [CaseExecutionState.COMPLETED]: "已完成",
    [CaseExecutionState.BLOCKED]: "已阻断",
    [CaseExecutionState.ERROR]: "执行错误",
    [CaseExecutionState.CANCELLED]: "已取消",
    [CaseExecutionState.UNFINISHED]: "未完成",
  }[state];
}

export function evidenceAvailabilityLabel(value: string): string {
  return {
    available: "证据完整",
    missing: "证据缺失",
    corrupt: "证据损坏",
    not_applicable: "不适用",
    conflicting: "证据冲突",
  }[value] ?? "证据状态未知";
}

export function caseConclusionLabel(value: string | null): string {
  if (value === null) return "尚无结论";
  return {
    passed: "通过",
    failed: "未通过",
    invalid: "无效",
    unfinished: "未完成",
    cancelled: "已取消",
  }[value] ?? "未知结论";
}

export function benchmarkRunHeadline(
  run: BenchmarkSuiteRun,
  detailAvailable: boolean,
): BenchmarkHeadline {
  if (run.lifecycle === SuiteRunLifecycle.COMPLETED && run.conclusion) {
    if (!detailAvailable) {
      return {
        title: "评测证据不可用",
        detail: "终态详情、案例或证据不完整，不能显示整体能力硬门禁通过。",
        tone: "warning",
      };
    }
    return conclusionHeadlines[run.conclusion];
  }
  if (run.lifecycle === SuiteRunLifecycle.CANCELLED) {
    return {
      title: "套件运行已取消",
      detail: "已形成的案例证据仍会保留，但不会伪造整体结论。",
      tone: "neutral",
    };
  }
  if (run.lifecycle === SuiteRunLifecycle.UNFINISHED) {
    return {
      title: "套件尚未形成结论",
      detail: "运行中断，需恢复后才能形成套件结论。",
      tone: "warning",
    };
  }
  if (run.provider_state === ProviderExecutionState.BLOCKED) {
    return {
      title: "套件尚未形成结论",
      detail: "真实模型提供商已阻断，请先处理提供商条件。",
      tone: "warning",
    };
  }
  if (run.provider_state === ProviderExecutionState.ERROR) {
    return {
      title: "套件尚未形成结论",
      detail: "真实模型提供商执行错误，不能据此判断能力。",
      tone: "danger",
    };
  }
  return {
    title: "套件尚未形成结论",
    detail: `${lifecycleLabels[run.lifecycle]}，完成后再展示整体能力硬门禁。`,
    tone: "neutral",
  };
}

export function benchmarkArtifactSupportsConclusion(
  run: BenchmarkSuiteRun,
  artifact: BenchmarkSuiteArtifact | null,
): boolean {
  if (
    artifact === null ||
    artifact.run_id !== run.run_id ||
    artifact.conclusion !== run.conclusion ||
    artifact.case_rows.length !== run.selected_case_ids.length ||
    artifact.evidence_bundles.length !== run.selected_case_ids.length
  ) {
    return false;
  }
  const rowByCaseId = new Map(
    artifact.case_rows.map(row => [row.case_id, row]),
  );
  const bundleById = new Map(
    artifact.evidence_bundles.map(bundle => [
      bundle.identity.bundle_id,
      bundle,
    ]),
  );
  return run.selected_case_ids.every(caseId => {
    const row = rowByCaseId.get(caseId);
    if (!row || row.evidence_availability !== "available") return false;
    const bundle = bundleById.get(row.evidence_bundle_id);
    if (!bundle || bundle.identity.case_id !== caseId || !bundle.details) {
      return false;
    }
    const hasNormalizationEvidence =
      bundle.details.normalization_actions.length > 0 ||
      isProvenPreplanSafeFailure(bundle.details);
    return (
      bundle.details.gates.length > 0 &&
      hasNormalizationEvidence &&
      Object.values(bundle.availability).every(
        value => value === "available" || value === "not_applicable",
      )
    );
  });
}

function isProvenPreplanSafeFailure(
  details: NonNullable<
    BenchmarkSuiteArtifact["evidence_bundles"][number]["details"]
  >,
): boolean {
  const terminal = details.terminal;
  const failure = details.runtime_failure;
  return (
    terminal?.run_status === "safe_failure" &&
    terminal.stop_reason === "unsafe_context" &&
    terminal.resumable === false &&
    failure?.run_status === "failed" &&
    failure.resumable === false &&
    failure.plan_present === false &&
    failure.node_count === 0 &&
    failure.interaction_count === 0 &&
    failure.capability_result_count === 0 &&
    failure.effect_count === 0 &&
    failure.failure_evidence.length > 0
  );
}

export function benchmarkRunProgress(
  run: BenchmarkSuiteRun,
  artifact: BenchmarkSuiteArtifact | null,
): BenchmarkRunProgress {
  const total = run.selected_case_ids.length;
  const ownedRows =
    artifact?.run_id === run.run_id ? artifact.case_rows : [];
  const passed = ownedRows.filter(row => row.conclusion === "passed").length;
  const failed = ownedRows.filter(row => row.conclusion === "failed").length;
  const invalid = ownedRows.filter(row => row.conclusion === "invalid").length;
  const terminal = passed + failed + invalid;
  return {
    total,
    passed,
    failed,
    invalid,
    pending: Math.max(0, total - terminal),
    allPassed:
      total > 0 &&
      passed === total &&
      run.conclusion === SuiteConclusion.PASSED &&
      benchmarkArtifactSupportsConclusion(run, artifact),
  };
}
