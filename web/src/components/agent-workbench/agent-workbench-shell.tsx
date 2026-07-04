"use client";

import {
  Activity,
  AlertTriangle,
  Ban,
  Bot,
  Check,
  Clock3,
  Copy,
  Database,
  FileText,
  PencilLine,
  Play,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  confirmKnowledgeExtractionCandidate,
  createKnowledgeExtractionRun,
  deferKnowledgeExtractionCandidate,
  editConfirmKnowledgeExtractionCandidate,
  getKnowledgeExtractionRun,
  listKnowledgeExtractionRuns,
  rejectKnowledgeExtractionCandidate,
} from "@/lib/api/agent-workbench";
import { listChapters } from "@/lib/api/chapters";
import type {
  AgentLLMCall,
  AgentReviewItem,
  AgentRun,
  AgentRunNode,
  AgentRunSummary,
  KnowledgeType,
  ReviewCandidateAction,
  ReviewCandidateStatus,
} from "@/lib/types/agent-workbench";
import type { ChapterInfo } from "@/lib/types/chapters";
import { cn } from "@/lib/utils";

type WorkbenchTab = "run" | "candidates" | "detail" | "metrics";

const tabs: Array<{ key: WorkbenchTab; label: string; icon: typeof Play }> = [
  { key: "run", label: "运行任务", icon: Play },
  { key: "candidates", label: "待处理候选", icon: Database },
  { key: "detail", label: "运行详情", icon: FileText },
  { key: "metrics", label: "评测指标", icon: Activity },
];

const runStatusLabel: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const nodeStatusLabel: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  success: "成功",
  failed: "失败",
  skipped: "已跳过",
};

const candidateStatusLabel: Record<ReviewCandidateStatus, string> = {
  pending: "待处理",
  confirmed: "已确认",
  rejected: "已废弃",
  deferred: "稍后处理",
};

const candidateActionLabel: Record<ReviewCandidateAction, string> = {
  create_card: "候选新卡",
  update_card: "候选更新",
  conflict: "候选冲突",
  ignore: "建议忽略",
};

const knowledgeTypeLabel: Record<KnowledgeType, string> = {
  character: "角色",
  location: "地点",
  faction: "势力",
  item: "物品",
};

const nodeLabel: Record<string, string> = {
  LoadChapterNode: "读取章节",
  SegmentChapterNode: "切分正文",
  GeneralExtractionNode: "通用抽取",
  MergeChapterCandidatesNode: "合并候选",
  TypeDispatchNode: "类型分发",
  CharacterExpertNode: "角色专家",
  EntityExpertNode: "实体专家",
  NormalizeAndValidateNode: "规范校验",
  RunInternalConflictCheckNode: "本轮冲突检查",
  MatchExistingKnowledgeNode: "匹配有效知识",
  BuildReviewItemsNode: "生成审核项",
  WriteIntermediateJsonNode: "写入中间态",
};

export function AgentWorkbenchShell() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [currentRun, setCurrentRun] = useState<AgentRun | null>(null);
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("run");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [selectedCallId, setSelectedCallId] = useState("");
  const [candidateDrafts, setCandidateDrafts] = useState<Record<string, string>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [actionBusyKey, setActionBusyKey] = useState("");
  const [error, setError] = useState("");

  const selectedCandidate = useMemo(
    () =>
      currentRun?.review_items.find(
        candidate => candidate.review_item_id === selectedCandidateId,
      ) ?? currentRun?.review_items[0] ?? null,
    [currentRun, selectedCandidateId],
  );

  const selectedLLMCall = useMemo(
    () =>
      currentRun?.llm_calls.find(call => call.call_id === selectedCallId) ??
      currentRun?.llm_calls[0] ??
      null,
    [currentRun, selectedCallId],
  );

  const selectedCandidateDraft = selectedCandidate
    ? candidateDrafts[selectedCandidate.review_item_id] ??
      formatJson(selectedCandidate.suggested_card)
    : "";

  const openRun = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    const response = await getKnowledgeExtractionRun(runId);
    setCurrentRun(response.run);
    setSelectedCandidateId(
      response.run.review_items.find(item => item.candidate_status === "pending")
        ?.review_item_id ??
        response.run.review_items[0]?.review_item_id ??
        "",
    );
    setSelectedCallId(response.run.llm_calls[0]?.call_id ?? "");
  }, []);

  const reloadRuns = useCallback(async () => {
    const response = await listKnowledgeExtractionRuns();
    setRuns(response.runs);
    return response.runs;
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadInitial() {
      setLoading(true);
      setError("");
      try {
        const [chapterResponse, runResponse] = await Promise.all([
          listChapters(),
          listKnowledgeExtractionRuns(),
        ]);
        if (ignore) {
          return;
        }
        setChapters(chapterResponse.chapters);
        setRuns(runResponse.runs);
        setSelectedChapterId(
          chapterResponse.chapters[0]?.id ?? "",
        );
        if (runResponse.runs[0]) {
          await openRun(runResponse.runs[0].run_id);
        }
      } catch (caught) {
        if (!ignore) {
          setError(caught instanceof Error ? caught.message : "工作台加载失败");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }
    void loadInitial();
    return () => {
      ignore = true;
    };
  }, [openRun]);

  async function handleCreateRun() {
    if (!selectedChapterId) {
      setError("请先选择当前章节。");
      return;
    }
    setRunning(true);
    setError("");
    try {
      const response = await createKnowledgeExtractionRun({
        chapter_id: selectedChapterId,
      });
      await reloadRuns();
      await openRun(response.run.run_id);
      setActiveTab("candidates");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "抽取运行失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleCandidateAction(
    candidate: AgentReviewItem,
    action: "confirm" | "edit-confirm" | "reject" | "defer",
  ) {
    setActionBusyKey(`${candidate.review_item_id}:${action}`);
    setError("");
    try {
      const response =
        action === "confirm"
          ? await confirmKnowledgeExtractionCandidate(candidate.review_item_id)
          : action === "edit-confirm"
            ? await editConfirmKnowledgeExtractionCandidate(
                candidate.review_item_id,
                {
                card_updates: parseCandidateDraft(
                  candidate.review_item_id === selectedCandidateId
                    ? selectedCandidateDraft
                    : formatJson(candidate.suggested_card),
                ),
                  target_card_id: candidate.target_card_id ?? null,
                },
              )
            : action === "reject"
              ? await rejectKnowledgeExtractionCandidate(candidate.review_item_id)
              : await deferKnowledgeExtractionCandidate(candidate.review_item_id);
      setCurrentRun(response.run);
      setSelectedCandidateId(candidate.review_item_id);
      await reloadRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "候选处理失败");
    } finally {
      setActionBusyKey("");
    }
  }

  function copyText(text: string) {
    if (!navigator.clipboard) {
      setError("当前浏览器不支持复制到剪贴板。");
      return;
    }
    void navigator.clipboard.writeText(text);
  }

  return (
    <AppShell activePath="/agent-workbench">
      <div className="mx-auto grid min-h-[calc(100vh-73px)] max-w-[1440px] grid-cols-1 gap-4 px-4 py-4 lg:grid-cols-[280px_minmax(0,1fr)_340px] lg:px-6">
        <aside className="flex min-h-0 flex-col gap-4">
          <section className="tc-panel p-4">
            <div className="flex items-start gap-3">
              <span className="inline-flex size-9 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-panel-soft)]">
                <Bot className="size-4" />
              </span>
              <div className="min-w-0">
                <h1 className="text-lg font-semibold leading-tight">智能体工作台</h1>
                <p className="mt-1 text-sm text-[var(--tc-workspace-text-muted)]">
                  当前开放正文知识沉淀流程
                </p>
              </div>
            </div>
          </section>

          <section className="tc-panel flex flex-col gap-3 p-4">
            <h2 className="text-sm font-semibold">智能体列表</h2>
            <button className="tc-recess flex w-full items-start gap-3 p-3 text-left">
              <span className="tc-status-dot mt-1" />
              <span>
                  <span className="block text-sm font-semibold">正文知识沉淀智能体</span>
                <span className="mt-1 block text-xs text-[var(--tc-workspace-text-muted)]">
                  当前章节正文到候选知识卡
                </span>
              </span>
            </button>
            <button
              disabled
              className="flex w-full items-start gap-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border-weak)] p-3 text-left opacity-55"
            >
              <span className="mt-1 size-2 rounded-full border border-[var(--tc-workspace-border)]" />
              <span>
                <span className="block text-sm font-medium">后续智能体</span>
                <span className="mt-1 block text-xs text-[var(--tc-workspace-text-muted)]">
                  暂未启用
                </span>
              </span>
            </button>
          </section>

          <section className="tc-panel min-h-0 flex-1 p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">最近运行</h2>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="刷新最近运行"
                onClick={() => void reloadRuns()}
              >
                <RefreshCw className="size-4" />
              </Button>
            </div>
            <div className="flex max-h-[360px] flex-col gap-2 overflow-y-auto pr-1">
              {runs.length === 0 ? (
                <p className="text-sm text-[var(--tc-workspace-text-muted)]">
                  暂无运行记录
                </p>
              ) : (
                runs.map(run => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => void openRun(run.run_id)}
                    className={cn(
                      "rounded-[var(--tc-radius-control)] border p-3 text-left text-sm transition-colors",
                      selectedRunId === run.run_id
                        ? "border-[var(--tc-workspace-focus)] bg-[var(--tc-workspace-panel-soft)]"
                        : "border-[var(--tc-workspace-border-weak)] hover:bg-[var(--tc-workspace-panel-soft)]",
                    )}
                  >
                    <span className="block truncate font-medium">
                      {run.chapter_title || "未命名章节"}
                    </span>
                    <span className="mt-1 flex items-center justify-between gap-2 text-xs text-[var(--tc-workspace-text-muted)]">
                      <span>{runStatusLabel[run.status] ?? "未知状态"}</span>
                      <span>{run.candidate_count} 个候选</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </section>
        </aside>

        <main className="tc-panel min-w-0 p-4 lg:p-5">
          <div className="mb-4 flex flex-col gap-3 border-b border-[var(--tc-workspace-border-weak)] pb-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <p className="tc-display-font text-xs text-[var(--tc-workspace-text-muted)]">
                正文知识沉淀
              </p>
              <h2 className="mt-1 text-xl font-semibold">正文知识沉淀 Agent</h2>
            </div>
            <div className="flex gap-2 overflow-x-auto">
              {tabs.map(tab => {
                const Icon = tab.icon;
                return (
                  <Button
                    key={tab.key}
                    type="button"
                    variant={activeTab === tab.key ? "default" : "outline"}
                    size="sm"
                    onClick={() => setActiveTab(tab.key)}
                  >
                    <Icon className="size-4" />
                    {tab.label}
                  </Button>
                );
              })}
            </div>
          </div>

          {error ? (
            <div className="tc-warning mb-4 flex items-start gap-2 rounded-[var(--tc-radius-control)] border p-3 text-sm">
              <AlertTriangle className="mt-0.5 size-4" />
              <span>{error}</span>
            </div>
          ) : null}

          {loading ? (
            <div className="tc-recess p-4 text-sm text-[var(--tc-workspace-text-muted)]">
              正在加载工作台数据...
            </div>
          ) : activeTab === "run" ? (
            <RunTaskPanel
              chapters={chapters}
              selectedChapterId={selectedChapterId}
              currentRun={currentRun}
              running={running}
              onChapterChange={setSelectedChapterId}
              onCreateRun={() => void handleCreateRun()}
            />
          ) : activeTab === "candidates" ? (
            <CandidatePanel
              run={currentRun}
              selectedCandidateId={selectedCandidateId}
              actionBusyKey={actionBusyKey}
              onSelectCandidate={setSelectedCandidateId}
              onAction={(candidate, action) =>
                void handleCandidateAction(candidate, action)
              }
            />
          ) : activeTab === "detail" ? (
            <RunDetailPanel
              run={currentRun}
              selectedCallId={selectedCallId}
              onSelectCall={setSelectedCallId}
              onCopy={copyText}
            />
          ) : (
            <MetricsPanel run={currentRun} />
          )}
        </main>

        <aside className="tc-panel min-w-0 p-4">
          <RightDetailPanel
            run={currentRun}
            candidate={selectedCandidate}
            llmCall={selectedLLMCall}
            candidateDraft={selectedCandidateDraft}
            onCandidateDraftChange={value => {
              if (!selectedCandidate) {
                return;
              }
              setCandidateDrafts(current => ({
                ...current,
                [selectedCandidate.review_item_id]: value,
              }));
            }}
            onCopy={copyText}
          />
        </aside>
      </div>
    </AppShell>
  );
}

function RunTaskPanel({
  chapters,
  selectedChapterId,
  currentRun,
  running,
  onChapterChange,
  onCreateRun,
}: {
  chapters: ChapterInfo[];
  selectedChapterId: string;
  currentRun: AgentRun | null;
  running: boolean;
  onChapterChange: (chapterId: string) => void;
  onCreateRun: () => void;
}) {
  const selectedChapter = chapters.find(chapter => chapter.id === selectedChapterId);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
      <section className="tc-recess p-4">
        <h3 className="text-base font-semibold">运行任务</h3>
        <div className="mt-4 grid gap-3">
          <label className="grid gap-2 text-sm">
            <span className="font-medium">当前章节</span>
            <select
              className="tc-input h-10 px-3"
              value={selectedChapterId}
              onChange={event => onChapterChange(event.target.value)}
            >
              {chapters.length === 0 ? (
                <option value="">暂无章节</option>
              ) : (
                chapters.map(chapter => (
                  <option key={chapter.id} value={chapter.id}>
                    {chapter.title}
                  </option>
                ))
              )}
            </select>
          </label>
          <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border-weak)] p-3 text-sm text-[var(--tc-workspace-text-muted)]">
            {selectedChapter ? (
              <>
                <span className="block text-[var(--tc-workspace-text)]">
                  {selectedChapter.title}
                </span>
                <span className="mt-1 block">
                  正文约 {selectedChapter.word_count} 字，运行后生成 JSON 中间态。
                </span>
              </>
            ) : (
              "暂无可运行章节，请先在写作页创建章节。"
            )}
          </div>
          <Button
            type="button"
            className="w-fit"
            disabled={!selectedChapterId || running}
            onClick={onCreateRun}
          >
            <Play className="size-4" />
            {running ? "正在抽取" : "开始抽取"}
          </Button>
        </div>
      </section>
      <section className="tc-recess p-4">
        <h3 className="text-base font-semibold">当前运行摘要</h3>
        {currentRun ? (
          <dl className="mt-4 grid gap-3 text-sm">
            <SummaryRow label="状态" value={runStatusLabel[currentRun.status]} />
            <SummaryRow label="候选总数" value={`${currentRun.metrics.candidate_total}`} />
            <SummaryRow label="待处理" value={`${currentRun.metrics.pending_count}`} />
            <SummaryRow label="耗时" value={formatDuration(currentRun.metrics.total_duration_ms)} />
          </dl>
        ) : (
          <p className="mt-4 text-sm text-[var(--tc-workspace-text-muted)]">
            尚未选择运行记录
          </p>
        )}
      </section>
    </div>
  );
}

function CandidatePanel({
  run,
  selectedCandidateId,
  actionBusyKey,
  onSelectCandidate,
  onAction,
}: {
  run: AgentRun | null;
  selectedCandidateId: string;
  actionBusyKey: string;
  onSelectCandidate: (candidateId: string) => void;
  onAction: (
    candidate: AgentReviewItem,
    action: "confirm" | "edit-confirm" | "reject" | "defer",
  ) => void;
}) {
  if (!run) {
    return <EmptyPanel text="请选择或创建一次运行。" />;
  }
  if (run.review_items.length === 0) {
    return <EmptyPanel text="本次运行没有生成候选。" />;
  }
  return (
    <div className="grid gap-3">
      {run.review_items.map(candidate => (
        <article
          key={candidate.review_item_id}
          className={cn(
            "rounded-[var(--tc-radius-control)] border p-4",
            selectedCandidateId === candidate.review_item_id
              ? "border-[var(--tc-workspace-focus)] bg-[var(--tc-workspace-panel-soft)]"
              : "border-[var(--tc-workspace-border-weak)]",
          )}
        >
          <button
            type="button"
            className="flex w-full items-start justify-between gap-3 text-left"
            onClick={() => onSelectCandidate(candidate.review_item_id)}
          >
            <span className="min-w-0">
              <span className="block truncate font-semibold">
                {candidate.display_title}
              </span>
              <span className="mt-2 flex flex-wrap gap-2">
                <Tag>{knowledgeTypeLabel[candidate.knowledge_type]}</Tag>
                <Tag>{candidateActionLabel[candidate.candidate_action]}</Tag>
                <Tag>{candidateStatusLabel[candidate.candidate_status]}</Tag>
              </span>
            </span>
            <span className="text-xs text-[var(--tc-workspace-text-muted)]">
              {candidate.schema_validation.passed ? "结构校验通过" : "结构校验失败"}
            </span>
          </button>
          {candidate.candidate_action === "update_card" ? (
            <p className="mt-3 text-xs text-[var(--tc-workspace-text-muted)]">
              候选更新确认后只补充空字段或追加来源说明，不覆盖已有非空字段。
            </p>
          ) : null}
          {candidate.source_excerpt ? (
            <p className="mt-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border-weak)] p-3 text-sm text-[var(--tc-workspace-text-secondary)]">
              {candidate.source_excerpt}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            {candidate.candidate_action !== "conflict" &&
            candidate.candidate_action !== "ignore" ? (
              <Button
                type="button"
                size="sm"
                disabled={isProcessed(candidate) || actionBusyKey !== ""}
                onClick={() => onAction(candidate, "confirm")}
              >
                <Check className="size-4" />
                确认入库
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isProcessed(candidate) || actionBusyKey !== ""}
              onClick={() => onAction(candidate, "edit-confirm")}
            >
              <PencilLine className="size-4" />
              编辑后确认
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isProcessed(candidate) || actionBusyKey !== ""}
              onClick={() => onAction(candidate, "defer")}
            >
              <Clock3 className="size-4" />
              稍后处理
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={isProcessed(candidate) || actionBusyKey !== ""}
              onClick={() => onAction(candidate, "reject")}
            >
              <Ban className="size-4" />
              废弃
            </Button>
          </div>
        </article>
      ))}
    </div>
  );
}

function RunDetailPanel({
  run,
  selectedCallId,
  onSelectCall,
  onCopy,
}: {
  run: AgentRun | null;
  selectedCallId: string;
  onSelectCall: (callId: string) => void;
  onCopy: (text: string) => void;
}) {
  if (!run) {
    return <EmptyPanel text="请选择或创建一次运行。" />;
  }
  return (
    <div className="grid gap-5">
      <section>
        <h3 className="mb-3 text-base font-semibold">节点状态</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead className="text-left text-[var(--tc-workspace-text-muted)]">
              <tr className="border-b border-[var(--tc-workspace-border-weak)]">
                <th className="py-2 pr-3 font-medium">节点</th>
                <th className="py-2 pr-3 font-medium">状态</th>
                <th className="py-2 pr-3 font-medium">耗时</th>
                <th className="py-2 font-medium">摘要</th>
              </tr>
            </thead>
            <tbody>
              {run.nodes.map(node => (
                <NodeRow key={node.node_name} node={node} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3 className="mb-3 text-base font-semibold">LLM 调用记录</h3>
        <div className="grid gap-3">
          {run.llm_calls.map(call => (
            <article
              key={call.call_id}
              className={cn(
                "rounded-[var(--tc-radius-control)] border p-3",
                selectedCallId === call.call_id
                  ? "border-[var(--tc-workspace-focus)] bg-[var(--tc-workspace-panel-soft)]"
                  : "border-[var(--tc-workspace-border-weak)]",
              )}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => onSelectCall(call.call_id)}
              >
                <span>
                  <span className="block text-sm font-semibold">
                    {nodeLabel[call.node_name] ?? call.node_name}
                  </span>
                  <span className="mt-1 block text-xs text-[var(--tc-workspace-text-muted)]">
                    {call.prompt_version} · {formatDuration(call.duration_ms)}
                  </span>
                </span>
                <span className="text-xs text-[var(--tc-workspace-text-muted)]">
                  {call.error ? "调用失败" : "调用完成"}
                </span>
              </button>
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-[var(--tc-workspace-text-secondary)]">
                  展开提示词与原始响应
                </summary>
                <TraceBlock
                  title="提示词"
                  text={call.input_prompt}
                  onCopy={onCopy}
                />
                <TraceBlock
                  title="原始响应"
                  text={call.raw_response}
                  onCopy={onCopy}
                />
                <TraceBlock
                  title="解析结果"
                  text={formatJson(call.parsed_output)}
                  onCopy={onCopy}
                />
              </details>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function MetricsPanel({ run }: { run: AgentRun | null }) {
  if (!run) {
    return <EmptyPanel text="请选择或创建一次运行。" />;
  }
  const metrics: Array<[string, string | number]> = [
    ["候选总数", run.metrics.candidate_total],
    ["角色候选数", run.metrics.character_candidate_count],
    ["地点候选数", run.metrics.location_candidate_count],
    ["势力候选数", run.metrics.faction_candidate_count],
    ["物品候选数", run.metrics.item_candidate_count],
    ["候选新卡数", run.metrics.create_card_count],
    ["候选更新数", run.metrics.update_card_count],
    ["候选冲突数", run.metrics.conflict_count],
    ["结构校验通过数", run.metrics.schema_passed_count],
    ["结构校验失败数", run.metrics.schema_failed_count],
    ["已确认数", run.metrics.confirmed_count],
    ["已废弃数", run.metrics.rejected_count],
    ["待处理数", run.metrics.pending_count],
    ["稍后处理数", run.metrics.deferred_count],
    ["LLM 调用次数", run.metrics.llm_call_count],
    ["总耗时", formatDuration(run.metrics.total_duration_ms)],
  ];
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div
            key={label}
            className="tc-recess min-h-24 p-4"
          >
            <div className="text-sm text-[var(--tc-workspace-text-muted)]">
              {label}
            </div>
            <div className="tc-display-font mt-3 text-2xl">{value}</div>
          </div>
        ))}
      </div>
      <section className="tc-recess p-4">
        <h3 className="mb-3 text-base font-semibold">各节点耗时</h3>
        <div className="grid gap-2">
          {Object.entries(run.metrics.node_duration_ms).map(([node, duration]) => (
            <div
              key={node}
              className="flex items-center justify-between gap-3 border-b border-[var(--tc-workspace-border-weak)] py-2 text-sm last:border-b-0"
            >
              <span>{nodeLabel[node] ?? node}</span>
              <span className="tc-display-font text-[var(--tc-workspace-text-muted)]">
                {formatDuration(duration)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function RightDetailPanel({
  run,
  candidate,
  llmCall,
  candidateDraft,
  onCandidateDraftChange,
  onCopy,
}: {
  run: AgentRun | null;
  candidate: AgentReviewItem | null;
  llmCall: AgentLLMCall | null;
  candidateDraft: string;
  onCandidateDraftChange: (value: string) => void;
  onCopy: (text: string) => void;
}) {
  return (
    <div className="grid gap-5">
      <section>
        <h2 className="text-base font-semibold">详情区</h2>
        {run ? (
          <dl className="mt-3 grid gap-2 text-sm">
            <SummaryRow label="运行状态" value={runStatusLabel[run.status]} />
            <SummaryRow label="章节" value={run.scope.chapter_title || "未命名章节"} />
            <SummaryRow label="候选" value={`${run.metrics.candidate_total} 个`} />
          </dl>
        ) : (
          <p className="mt-3 text-sm text-[var(--tc-workspace-text-muted)]">
            暂无运行详情
          </p>
        )}
      </section>

      <section className="border-t border-[var(--tc-workspace-border-weak)] pt-4">
        <h3 className="text-sm font-semibold">当前候选详情</h3>
        {candidate ? (
          <div className="mt-3 grid gap-3">
            <div className="flex flex-wrap gap-2">
              <Tag>{knowledgeTypeLabel[candidate.knowledge_type]}</Tag>
              <Tag>{candidateActionLabel[candidate.candidate_action]}</Tag>
              <Tag>{candidateStatusLabel[candidate.candidate_status]}</Tag>
            </div>
            <p className="text-sm text-[var(--tc-workspace-text-secondary)]">
              {candidate.display_title}
            </p>
            {candidate.schema_validation.errors.length > 0 ? (
              <ul className="grid gap-1 text-sm text-[var(--tc-workspace-text-muted)]">
                {candidate.schema_validation.errors.map(error => (
                  <li key={error}>校验提示：{error}</li>
                ))}
              </ul>
            ) : null}
            <label className="grid gap-2 text-sm">
              <span className="font-medium">编辑后确认内容</span>
              <textarea
                className="tc-input min-h-56 resize-y p-3 font-mono text-xs leading-relaxed"
                value={candidateDraft}
                onChange={event => onCandidateDraftChange(event.target.value)}
              />
            </label>
          </div>
        ) : (
          <p className="mt-3 text-sm text-[var(--tc-workspace-text-muted)]">
            暂无候选
          </p>
        )}
      </section>

      <section className="border-t border-[var(--tc-workspace-border-weak)] pt-4">
        <h3 className="text-sm font-semibold">当前 LLM 调用</h3>
        {llmCall ? (
          <div className="mt-3 grid gap-3 text-sm">
            <SummaryRow
              label="节点"
              value={nodeLabel[llmCall.node_name] ?? llmCall.node_name}
            />
            <SummaryRow label="耗时" value={formatDuration(llmCall.duration_ms)} />
            <TraceBlock
              title="提示词"
              text={llmCall.input_prompt}
              onCopy={onCopy}
              compact
            />
            <TraceBlock
              title="原始响应"
              text={llmCall.raw_response}
              onCopy={onCopy}
              compact
            />
          </div>
        ) : (
          <p className="mt-3 text-sm text-[var(--tc-workspace-text-muted)]">
            暂无 LLM 调用
          </p>
        )}
      </section>

      {run?.errors.length ? (
        <section className="border-t border-[var(--tc-workspace-border-weak)] pt-4">
          <h3 className="text-sm font-semibold">错误信息</h3>
          <ul className="mt-3 grid gap-2 text-sm text-[var(--tc-workspace-text-muted)]">
            {run.errors.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function NodeRow({ node }: { node: AgentRunNode }) {
  return (
    <tr className="border-b border-[var(--tc-workspace-border-weak)] last:border-b-0">
      <td className="py-3 pr-3">{nodeLabel[node.node_name] ?? node.node_name}</td>
      <td className="py-3 pr-3">{nodeStatusLabel[node.status]}</td>
      <td className="py-3 pr-3">{formatDuration(node.duration_ms)}</td>
      <td className="py-3 text-[var(--tc-workspace-text-muted)]">
        {node.error || node.output_summary || "无"}
      </td>
    </tr>
  );
}

function TraceBlock({
  title,
  text,
  onCopy,
  compact = false,
}: {
  title: string;
  text: string;
  onCopy: (text: string) => void;
  compact?: boolean;
}) {
  return (
    <div className="mt-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border-weak)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--tc-workspace-border-weak)] px-3 py-2">
        <span className="text-xs font-medium text-[var(--tc-workspace-text-muted)]">
          {title}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={`复制${title}`}
          onClick={() => onCopy(text)}
        >
          <Copy className="size-3" />
        </Button>
      </div>
      <pre
        className={cn(
          "overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed text-[var(--tc-workspace-text-secondary)]",
          compact ? "max-h-44" : "max-h-72",
        )}
      >
        {text || "无内容"}
      </pre>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-[var(--tc-workspace-text-muted)]">{label}</dt>
      <dd className="text-right text-[var(--tc-workspace-text)]">{value}</dd>
    </div>
  );
}

function Tag({ children }: { children: string }) {
  return <span className="tc-tag px-2 py-1">{children}</span>;
}

function EmptyPanel({ text }: { text: string }) {
  return (
    <div className="tc-recess p-4 text-sm text-[var(--tc-workspace-text-muted)]">
      {text}
    </div>
  );
}

function isProcessed(candidate: AgentReviewItem): boolean {
  return candidate.candidate_status === "confirmed" ||
    candidate.candidate_status === "rejected";
}

function parseCandidateDraft(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!isRecord(parsed)) {
    throw new Error("编辑后确认内容必须是 JSON 对象。");
  }
  return parsed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDuration(value: number): string {
  if (value < 1000) {
    return `${value} ms`;
  }
  return `${(value / 1000).toFixed(1)} 秒`;
}
