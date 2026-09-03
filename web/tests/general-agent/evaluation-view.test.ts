import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  BenchmarkApiError,
  benchmarkApiRequest,
  getBenchmarkOpikSummary,
  getBenchmarkSuite,
  listBenchmarkRuns,
} from "../../src/lib/api/general-agent-benchmark";
import { ApiError, apiRequest } from "../../src/lib/api-client";
import {
  benchmarkCaseDisplay,
  benchmarkFieldDisplay,
  benchmarkRunDisplay,
} from "../../src/lib/general-agent-benchmark-display";
import {
  comparisonSelectionFromSearch,
  benchmarkRevisionConflictNotice,
  inboxCasConflictNotice,
  issueIntentConflictNotice,
  inboxIssuePatchRequest,
  normalizeInboxIssueContract,
  symmetryGateNotice,
  withComparisonSelection,
} from "../../src/lib/general-agent-benchmark-interactions";
import {
  normalizeBenchmarkRequestError,
  RequestCoordinator,
} from "../../src/lib/general-agent-benchmark-state";
import { ServerPaginationState } from "../../src/lib/general-agent-benchmark-pagination";
import {
  benchmarkArtifactSupportsConclusion,
  benchmarkRunProgress,
  benchmarkRunHeadline,
  caseExecutionStateLabel,
  evidenceAvailabilityLabel,
  providerExecutionStateLabel,
} from "../../src/lib/general-agent-benchmark-view";
import {
  AdmissionStatus,
  CaseConclusion,
  CaseExecutionState,
  ComparabilityStatus,
  ProviderExecutionState,
  SuiteConclusion,
  SuiteRunLifecycle,
  TrackKind,
  type BenchmarkPage,
  type BenchmarkSuiteArtifact,
  type BenchmarkSuiteRun,
} from "../../src/lib/types/general-agent-benchmark";

assert.equal(SuiteRunLifecycle.FINALIZING, "finalizing");
assert.equal(SuiteConclusion.NOT_EVALUATED, "not_evaluated");
assert.equal(ProviderExecutionState.BLOCKED, "blocked");
assert.equal(ComparabilityStatus.INCOMPARABLE, "incomparable");
assert.equal(AdmissionStatus.ADMITTED, "admitted");
assert.equal(caseExecutionStateLabel(CaseExecutionState.BLOCKED), "已阻断");
assert.equal(providerExecutionStateLabel(ProviderExecutionState.ERROR), "提供商错误");
assert.equal(evidenceAvailabilityLabel("missing"), "证据缺失");
assert.deepEqual(benchmarkRunDisplay(
  "benchmark_run_20260727T120000Z_aaaaaaaaaaaa",
  3,
), {
  name: "第 3 次评测",
  timeLabel: "2026年7月27日 20:00",
});
assert.deepEqual(benchmarkRunDisplay(
  "benchmark_run_19700101T000000Z_baseline",
  1,
), {
  name: "第 1 次评测",
  timeLabel: "固定基线记录",
});
assert.equal(
  benchmarkCaseDisplay("recovery_verification_interruption").label,
  "其他合同能力",
);
assert.deepEqual(benchmarkFieldDisplay("Director and Client Request"), {
  label: "编排与用户请求",
  description: "验证高层编排能够准确承接用户目标并保持全局控制。",
});
assert.equal(
  benchmarkFieldDisplay("unknown_internal_field").label,
  "其他评测字段",
);

const completedRun: BenchmarkSuiteRun = {
  run_id: "benchmark_run_20260727T120000Z_aaaaaaaaaaaa",
  revision: 0,
  lifecycle: SuiteRunLifecycle.COMPLETED,
  conclusion: SuiteConclusion.PASSED,
  suite_content_hash: "b".repeat(64),
  selected_case_ids: ["case_one"],
  track: TrackKind.SYNTHETIC,
  provider_state: ProviderExecutionState.NOT_APPLICABLE,
  case_row_refs: ["case-row-one"],
  pending_case_ids: [],
  terminal_artifact_ref: "runs/baseline.json",
};
assert.deepEqual(benchmarkRunHeadline(completedRun, false), {
  title: "评测证据不可用",
  detail: "终态详情、案例或证据不完整，不能显示整体能力硬门禁通过。",
  tone: "warning",
});

const hydratedArtifact = {
  artifact_id: "synthetic-detail",
  run_id: completedRun.run_id,
  conclusion: SuiteConclusion.PASSED,
  case_rows: [
    {
      suite_id: "general_writing_agent_core",
      case_id: "case_one",
      case_execution_id: `benchmark_case_${"a".repeat(32)}`,
      attempt_number: 1,
      execution_state: CaseExecutionState.COMPLETED,
      conclusion: CaseConclusion.PASSED,
      failure_category: null,
      failure_categories: [],
      evidence_bundle_id: `evidence_${"b".repeat(64)}`,
      evidence_availability: "available",
    },
  ],
  evidence_bundles: [
    {
      identity: {
        bundle_id: `evidence_${"b".repeat(64)}`,
        case_id: "case_one",
      },
      availability: {
        normalization: "available",
        gates: "available",
        invocations: "available",
        budget: "available",
      },
      problems: [],
      details: {
        gates: [{ gate_kind: "budget", status: "passed", conditions: [] }],
        capability_invocations: [],
        normalization_actions: [
          {
            kind: "model",
            name: "orchestrator_plan",
            outcome: "completed",
            step_id: "plan_step",
            step_index: 0,
            evidence: {},
          },
        ],
        normalization_hash: "c".repeat(64),
        runtime_evidence_refs: ["normalization:example"],
      },
    },
  ],
  provider_state: ProviderExecutionState.NOT_APPLICABLE,
  artifact_hash: "d".repeat(64),
} satisfies BenchmarkSuiteArtifact;
assert.equal(
  benchmarkArtifactSupportsConclusion(completedRun, hydratedArtifact),
  true,
);

const provenPreplanSafeFailureArtifact: BenchmarkSuiteArtifact =
  structuredClone(hydratedArtifact);
provenPreplanSafeFailureArtifact.evidence_bundles[0].details = {
  ...provenPreplanSafeFailureArtifact.evidence_bundles[0].details!,
  normalization_actions: [],
  terminal: {
    pending_human_kind: null,
    resumable: false,
    run_status: "safe_failure",
    stop_reason: "unsafe_context",
  },
  runtime_failure: {
    run_status: "failed",
    resumable: false,
    plan_present: false,
    node_count: 0,
    interaction_count: 0,
    capability_result_count: 0,
    effect_count: 0,
    failure_evidence: [{ reason_code: "unsafe_context" }],
  },
};
assert.equal(
  benchmarkArtifactSupportsConclusion(
    completedRun,
    provenPreplanSafeFailureArtifact,
  ),
  true,
);

const unprovenPreplanSafeFailureArtifact: BenchmarkSuiteArtifact =
  structuredClone(provenPreplanSafeFailureArtifact);
unprovenPreplanSafeFailureArtifact.evidence_bundles[0].details!.runtime_failure = null;
assert.equal(
  benchmarkArtifactSupportsConclusion(
    completedRun,
    unprovenPreplanSafeFailureArtifact,
  ),
  false,
);

assert.equal(
  benchmarkRunHeadline(
    completedRun,
    benchmarkArtifactSupportsConclusion(completedRun, hydratedArtifact),
  ).title,
  "整体能力硬门禁通过",
);

function completedProgressFixture(count: number): {
  run: BenchmarkSuiteRun;
  artifact: BenchmarkSuiteArtifact;
} {
  const caseIds = Array.from({ length: count }, (_, index) => `case_${index + 1}`);
  const run = {
    ...completedRun,
    selected_case_ids: caseIds,
    case_row_refs: caseIds.map(caseId => `rows/${caseId}`),
  };
  const artifact: BenchmarkSuiteArtifact = {
    ...hydratedArtifact,
    case_rows: caseIds.map((caseId, index) => ({
      ...hydratedArtifact.case_rows[0],
      case_id: caseId,
      case_execution_id: `benchmark_case_${String(index).padStart(32, "0")}`,
      evidence_bundle_id: `evidence_${String(index).padStart(64, "0")}`,
    })),
    evidence_bundles: caseIds.map((caseId, index) => ({
      ...hydratedArtifact.evidence_bundles[0],
      identity: {
        bundle_id: `evidence_${String(index).padStart(64, "0")}`,
        case_id: caseId,
      },
    })),
  };
  return { run, artifact };
}

for (const total of [37, 21, 23]) {
  const fixture = completedProgressFixture(total);
  assert.deepEqual(benchmarkRunProgress(fixture.run, fixture.artifact), {
    total,
    passed: total,
    failed: 0,
    invalid: 0,
    pending: 0,
    allPassed: true,
  });
}

const mixedFixture = completedProgressFixture(4);
mixedFixture.artifact.case_rows[1].conclusion = CaseConclusion.FAILED;
mixedFixture.artifact.case_rows[2].conclusion = CaseConclusion.INVALID;
mixedFixture.artifact.case_rows.pop();
assert.deepEqual(
  benchmarkRunProgress(mixedFixture.run, mixedFixture.artifact),
  {
    total: 4,
    passed: 1,
    failed: 1,
    invalid: 1,
    pending: 1,
    allPassed: false,
  },
);

const page: BenchmarkPage<{ run_id: string }> = {
  items: [{ run_id: "run-latest" }],
  page: 2,
  page_size: 20,
  total: 42,
  total_pages: 3,
  index_revision: 9,
  total_snapshot: "a".repeat(64),
};
assert.equal(page.index_revision, 9);
assert.equal(page.total_snapshot.length, 64);

const coordinator = new RequestCoordinator();
const first = coordinator.begin();
const second = coordinator.begin();
assert.equal(first.signal.aborted, true);
assert.equal(second.generation, first.generation + 1);

let applied = "";
assert.equal(
  coordinator.apply(first, 99, () => {
    applied = "陈旧响应";
  }),
  false,
);
assert.equal(
  coordinator.apply(second, 8, () => {
    applied = "最新响应";
  }),
  true,
);
assert.equal(applied, "最新响应");
assert.equal(coordinator.lastAppliedRevision, 8);

const pagination = new ServerPaginationState(20);
assert.deepEqual(pagination.query(), { page: 1, pageSize: 20 });
assert.equal(
  pagination.apply({
    ...page,
    page: 1,
    items: Array.from({ length: 20 }, (_, index) => ({ run_id: `run-${index}` })),
  }),
  null,
);
pagination.goTo(3);
assert.deepEqual(pagination.query(), {
  page: 3,
  pageSize: 20,
  totalSnapshot: "a".repeat(64),
});
assert.equal(
  pagination.apply({
    ...page,
    page: 3,
    total: 40,
    total_pages: 2,
    items: [],
  }),
  2,
);
assert.equal(pagination.page, 2);
pagination.refresh();
assert.deepEqual(pagination.query(), { page: 2, pageSize: 20 });

const legacyIssue = normalizeInboxIssueContract({
  id: "issue-legacy",
  title: "旧问题",
  content: "待核对",
  priority: "normal",
  status: "todo",
  created_at: "2026-07-27T00:00:00Z",
  updated_at: "2026-07-27T00:00:00Z",
});
assert.equal(legacyIssue.revision, 0);
assert.deepEqual(legacyIssue.links, []);
assert.deepEqual(inboxIssuePatchRequest(legacyIssue, { status: "processed" }), {
  expected_revision: 0,
  updates: { status: "processed" },
});

const conflict = new ApiError({
  status: 409,
  code: "REVISION_CONFLICT",
  message: "系统问题修订冲突。",
  requestId: "request_revision_9",
  details: { current_revision: 9 },
});
assert.equal(
  inboxCasConflictNotice(conflict),
  "记录已被其他操作更新，已刷新，请确认后重试。",
);
assert.equal(
  issueIntentConflictNotice(
    new ApiError({
      status: 409,
      code: "resource_conflict",
      message: "问题关联意图已绑定不同内容。",
      requestId: "req_intent_1",
    }),
  ),
  "已存在内容不同的问题关联意图，请先核对原记录。",
);
assert.equal(
  benchmarkRevisionConflictNotice(
    new BenchmarkApiError({
      status: 409,
      code: "resource_conflict",
      message: "运行修订冲突。",
      requestId: "req_run_revision",
    }),
  ),
  "评测状态已被其他操作更新，已刷新，请确认后重试。",
);
assert.equal(
  symmetryGateNotice(["relation_manifest", "iteration_manifest"]),
  "问题闭环尚未完成：关联记录、首轮迭代未对称确认。",
);

const restoredSelection = comparisonSelectionFromSearch(
  new URLSearchParams("iteration=iteration-one&comparison=comparison-two"),
);
assert.deepEqual(restoredSelection, {
  iterationId: "iteration-one",
  comparisonId: "comparison-two",
});
assert.equal(
  withComparisonSelection(
    new URLSearchParams("run_page=2"),
    restoredSelection,
  ).toString(),
  "run_page=2&iteration=iteration-one&comparison=comparison-two",
);

assert.deepEqual(
  benchmarkRunHeadline({
    run_id: "benchmark_run_20260727T120000Z_aaaaaaaaaaaa",
    revision: 3,
    lifecycle: SuiteRunLifecycle.UNFINISHED,
    conclusion: null,
    suite_content_hash: "b".repeat(64),
    selected_case_ids: ["CASE_ONE"],
    track: TrackKind.SYNTHETIC,
    provider_state: ProviderExecutionState.COMPLETED,
    case_row_refs: ["case-row-one"],
    pending_case_ids: ["CASE_ONE"],
    terminal_artifact_ref: null,
  }, false),
  {
    title: "套件尚未形成结论",
    detail: "运行中断，需恢复后才能形成套件结论。",
    tone: "warning",
  },
);

const third = coordinator.begin();
assert.equal(
  coordinator.apply(third, 7, () => {
    applied = "较旧修订";
  }),
  false,
);
assert.equal(applied, "最新响应");
assert.equal(coordinator.lastAppliedRevision, 8);

const abortError = new Error("aborted");
abortError.name = "AbortError";
assert.equal(normalizeBenchmarkRequestError(abortError), null);

async function verifyApiContract(): Promise<void> {
  const originalFetch = globalThis.fetch;
  try {
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: {
          error: "resource_conflict",
          message: "运行修订已变化。",
          request_id: "req_conflict_1",
          details: { actual_revision: 4 },
        },
      }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );

    await assert.rejects(
      () => benchmarkApiRequest("/runs/example"),
      (error: unknown) => {
        if (!(error instanceof BenchmarkApiError)) {
          return false;
        }
      assert.equal(error.status, 409);
      assert.equal(error.code, "resource_conflict");
      assert.equal(error.requestId, "req_conflict_1");
      assert.deepEqual(error.details, { actual_revision: 4 });
      assert.equal(
        normalizeBenchmarkRequestError(error),
        "运行修订已变化。",
      );
      return true;
        return true;
      },
    );

    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          detail: {
            error: {
              code: "REVISION_CONFLICT",
              message: "系统问题修订冲突。",
              current_revision: 9,
              request_id: "request_revision_nested",
            },
          },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      );
    await assert.rejects(
      () => apiRequest("/api/inbox/issues/issue-one"),
      (error: unknown) => {
        if (!(error instanceof ApiError)) return false;
        assert.equal(error.status, 409);
        assert.equal(error.code, "REVISION_CONFLICT");
        assert.equal(error.requestId, "request_revision_nested");
        assert.deepEqual(error.details, { current_revision: 9 });
        return true;
      },
    );

    let requestedUrl = "";
    let requestedSignal: AbortSignal | undefined;
    globalThis.fetch = async (input, init) => {
      requestedUrl = String(input);
      requestedSignal = init?.signal ?? undefined;
      return Response.json(page);
    };
    const request = coordinator.begin();
    assert.deepEqual(
      await listBenchmarkRuns(
        { page: 2, pageSize: 20, totalSnapshot: "a".repeat(64) },
        request.signal,
      ),
      page,
    );
    assert.match(
      requestedUrl,
      /\/api\/general-agent-benchmarks\/runs\?page=2&page_size=20&total_snapshot=a{64}$/,
    );
    assert.equal(requestedSignal, request.signal);

    const opikSummary = {
      provider: "opik",
      status: "available",
      project_name: "taichu-general-agent-benchmark",
      project_url: "https://example.test/opik/project",
      suite_content_hash: "b".repeat(64),
      refreshed_at: "2026-09-01T12:00:00Z",
      message: "已校验当前套件对应的云端实验。",
      entries: [],
    } as const;
    globalThis.fetch = async input => {
      requestedUrl = String(input);
      return Response.json(opikSummary);
    };
    assert.deepEqual(await getBenchmarkOpikSummary(), opikSummary);
    assert.match(
      requestedUrl,
      /\/api\/general-agent-benchmarks\/opik\/summary$/,
    );

    const suiteDetail = {
      suite_id: "general_writing_agent_core",
      name: "通用写作智能体固定基准",
      content_hash: "b".repeat(64),
      case_count: 37,
      case_order: ["direct_answer_current_request"],
      track_case_counts: {
        synthetic: 37,
        live_provider: 21,
      },
      benchmark_entries: [
        {
          entry_id: "multi_step",
          name: "多步骤组合任务",
          summary: "验证跨能力组合任务的规划、执行与证据闭环。",
          opik_dataset_name: "taichu-general-agent-multi-step",
          case_count: 18,
          case_ids: ["structure_coverage_read"],
          categories: [
            {
              category_id: "outline_decomposition",
              name: "拆解小说大纲",
              purpose: "验证大纲读取与结构化拆解。",
              case_ids: ["structure_coverage_read"],
            },
          ],
          invalid_invocation_rules: [
            "调用合同白名单之外的能力。",
            "同一能力调用次数超过合同上限。",
            "调用顺序、并行关系或父子依赖不符合合同。",
            "工具结果没有被下游节点或最终回答消费。",
          ],
        },
        {
          entry_id: "recovery",
          name: "异常中断恢复",
          summary: "验证真实故障窗口中的恢复语义与副作用控制。",
          opik_dataset_name: "taichu-general-agent-recovery",
          case_count: 8,
          case_ids: ["recovery_after_plan_before_execution"],
          categories: [
            {
              category_id: "plan_and_tool_recovery",
              name: "规划与工具结果恢复",
              purpose: "验证计划与工具结果的可恢复性。",
              case_ids: ["recovery_after_plan_before_execution"],
            },
          ],
          invalid_invocation_rules: [
            "调用合同白名单之外的能力。",
            "同一能力调用次数超过合同上限。",
            "调用顺序、并行关系或父子依赖不符合合同。",
            "工具结果没有被下游节点或最终回答消费。",
          ],
        },
      ],
      capability_domains: [
        {
          domain_id: "routing_and_retrieval",
          name: "简单路由与检索",
          purpose: "验证最小充分路径与基础取证行为。",
          case_ids: ["direct_answer_current_request"],
        },
      ],
      cases: [
        {
          ordinal: 1,
          case_id: "direct_answer_current_request",
          name: "当前请求直接回答",
          summary: "验证简单请求不被错误复杂化。",
          user_request:
            "写冲突场景时，最先应该明确什么？请先给结论，再说明依据。",
          tracks: ["synthetic", "live_provider"],
          objective: "直接回答写作问题且不调用不必要能力。",
          target_final_artifact: "形成满足用户目标的直接回答。",
          behavior_expectations: ["不得调用无关能力。"],
          expected_terminal: {
            run_status: "completed",
            resumable: false,
            pending_human_kind: null,
            recovery_action: "none",
            reason_code: "goal_satisfied",
          },
          budget_limits: {
            max_node_executions: 50,
            max_replans: 4,
            max_capability_calls: 20,
            max_model_calls: 20,
            max_total_tokens: 100000,
            max_runtime_ms: 600000,
          },
          capability_domain_id: "routing_and_retrieval",
        },
      ],
    };
    globalThis.fetch = async input => {
      requestedUrl = String(input);
      return Response.json({ suite: suiteDetail });
    };
    assert.deepEqual(
      await getBenchmarkSuite("general_writing_agent_core"),
      suiteDetail,
    );
    assert.match(
      requestedUrl,
      /\/api\/general-agent-benchmarks\/suites\/general_writing_agent_core$/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
}

void verifyApiContract().then(() => {
  const shellSource = readFileSync(
    resolve(
      process.cwd(),
      "src/components/agent-task-monitor/general-agent-evaluation-shell.tsx",
    ),
    "utf8",
  );
  const multiStepPageSource = readFileSync(
    resolve(
      process.cwd(),
      "src/app/task-monitor/general-agent/evaluation/multi-step/page.tsx",
    ),
    "utf8",
  );
  const recoveryPageSource = readFileSync(
    resolve(
      process.cwd(),
      "src/app/task-monitor/general-agent/evaluation/recovery/page.tsx",
    ),
    "utf8",
  );
  assert.match(multiStepPageSource, /entryId="multi_step"/);
  assert.match(recoveryPageSource, /entryId="recovery"/);
  assert.match(shellSource, /suite_content_hash === detail\.content_hash/);
  assert.doesNotMatch(
    shellSource,
    /runPage\.items\[0\]/,
    "当前 Suite 没有匹配运行时不得回退展示旧 Suite 工件。",
  );
  for (const requiredCopy of [
    "通用写作智能体能力证明",
    "多步骤组合任务",
    "异常中断恢复",
    "选择任务分类",
    "选择具体合同",
    "评测说明",
    "Opik 数据集",
    "Opik 云端评测结果",
    "八维固定合同评分",
    "打开实验",
    "查看数据集",
    "查看 Trace",
    "Trace 采集范围",
    "什么算无效工具调用",
    "每条合同主要检查三件事",
    "不明白合同中的名词？查看术语解释",
    "处理方式对不对",
    "有没有越权修改",
    "不会只给一个“通过”",
    "用户当时提出的问题",
    "系统实际给出的回答",
    "任何会修改正文、结构、知识库",
    "能力结论成立",
    "合同要求",
    "最新运行",
    "查看完整合同与运行证据",
    "完整合同要求",
    "实际运行过程",
    "核验依据",
  ]) {
    assert.match(shellSource, new RegExp(requiredCopy));
  }
  assert.doesNotMatch(shellSource, /overall_score|evaluation\.dimensions|五维/);
  assert.doesNotMatch(
    shellSource,
    /23\/23 Benchmark 全部通过|23 条固定任务/,
  );
  assert.doesNotMatch(
    shellSource,
    /运行标识：|失败案例标识：|内容身份：|candidate\.actual_model_id|\.code_hash\.slice|\.artifact_hash\.slice/,
  );
  assert.doesNotMatch(
    shellSource,
    /工作记忆专项硬门禁|局部机制结论|能力实际调用与预算/,
  );
  assert.doesNotMatch(
    shellSource,
    /发起套件运行|最近运行|最近评测记录|准备发起评测/,
  );
  assert.doesNotMatch(
    shellSource,
    /submitBenchmarkRun|changeBenchmarkRunLifecycle|showWorkspace|paginations/,
  );
  assert.doesNotMatch(
    shellSource,
    /proofMethod|HeaderMetric|DomainNavigation|ContractNavigation|ProofSection|ExpectationItem|grid-cols-\[200px_270px_minmax\(0,1fr\)\]/,
    "默认页面不得继续使用多栏导航与五段报告结构。",
  );
  assert.doesNotMatch(
    shellSource,
    /六组能力、37 条固定合同|只展示最新一次覆盖结果|刷新最新评测结果|benchmarkRunDisplay/,
    "顶部不得恢复说明句、运行时间或刷新入口。",
  );
  assert.doesNotMatch(
    shellSource,
    /结论只覆盖这条固定合同声明的场景|不外推为模型排名|不代表未被合同覆盖的能力/,
    "证据详情不得恢复冗余的结论范围提示。",
  );
  assert.doesNotMatch(
    shellSource,
    /已核验内容/,
    "合同证明不得用占位词掩盖实际运行证据。",
  );
  assert.doesNotMatch(
    shellSource,
    /所需结论均已出现，没有遗漏或禁用内容|产生 0 次副作用/,
    "合同证明必须展示实际回答并把抽象副作用翻译成具体资源变化。",
  );
  assert.doesNotMatch(
    shellSource,
    /结论能不能核对|为什么能判定通过|用户问题、执行步骤和实际结果都来自同一次运行/,
    "默认说明页不得使用缺少具体含义的审计术语。",
  );
  assert.doesNotMatch(
    shellSource,
    /个执行步骤 · .*项核验|conditionCount|actionCount/,
    "详情入口不得展示与可见内容口径不一致的内部计数。",
  );
  assert.match(
    shellSource,
    /listBenchmarkRuns\(\{ page: 1, pageSize: 1 \}/,
    "证明页只应读取最新一条运行结果。",
  );
  console.log("通用写作智能体评测客户端与请求协调测试通过。");
});
