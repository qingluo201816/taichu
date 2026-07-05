"use client";

import {
  Activity,
  AlertTriangle,
  Ban,
  Bot,
  Check,
  ChevronRight,
  Copy,
  Database,
  Download,
  FileText,
  PencilLine,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  confirmKnowledgeExtractionCandidate,
  createKnowledgeExtractionRun,
  deleteKnowledgeExtractionRun,
  editConfirmKnowledgeExtractionCandidate,
  getKnowledgeExtractionRun,
  listKnowledgeExtractionRuns,
  rejectKnowledgeExtractionCandidate,
} from "@/lib/api/agent-workbench";
import { listChapters } from "@/lib/api/chapters";
import { readKnowledgeCard } from "@/lib/api/mvp";
import type {
  AgentEntityGroup,
  AgentIgnoredExtraction,
  AgentLLMCall,
  AgentRawMention,
  AgentReviewItem,
  AgentRun,
  AgentRunNode,
  AgentRunSummary,
  EditConfirmMergeMode,
  KnowledgeType,
  ReviewCandidateAction,
  ReviewCandidateStatus,
} from "@/lib/types/agent-workbench";
import type { ChapterInfo } from "@/lib/types/chapters";
import type { StructuredKnowledgeCard } from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type WorkbenchSection = "run" | "candidates" | "detail" | "metrics";
type CandidateStatusFilter = ReviewCandidateStatus | "all";

const sections: Array<{
  key: WorkbenchSection;
  label: string;
  description: string;
  icon: typeof Play;
}> = [
  {
    key: "run",
    label: "运行任务",
    description: "选择当前章节并启动正文知识沉淀",
    icon: Play,
  },
  {
    key: "candidates",
    label: "待处理候选",
    description: "审核抽取出的角色、地点、势力和物品",
    icon: Database,
  },
  {
    key: "detail",
    label: "运行详情",
    description: "查看节点状态、提示词和模型原始响应",
    icon: FileText,
  },
  {
    key: "metrics",
    label: "评测指标",
    description: "查看候选数量、校验结果和节点耗时",
    icon: Activity,
  },
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
};

const candidateStatusFilters: Array<{
  value: CandidateStatusFilter;
  label: string;
}> = [
  { value: "pending", label: "待处理" },
  { value: "confirmed", label: "已确认" },
  { value: "rejected", label: "已废弃" },
  { value: "all", label: "全部" },
];

const mergeModeLabel: Record<EditConfirmMergeMode, string> = {
  append: "追加到现有知识卡",
  overwrite: "覆盖为编辑内容",
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

const qualityDecisionLabels: Record<string, string> = {
  accepted: "已通过",
  rejected: "已过滤",
  pending: "待判断",
};

const nodeLabel: Record<string, string> = {
  LoadChapterNode: "读取章节",
  SegmentChapterNode: "切分正文",
  GeneralExtractionNode: "通用抽取",
  MentionNormalizeNode: "提及清洗",
  EntityAggregationNode: "实体聚合",
  CandidateQualityGateNode: "质量闸门",
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
  const [activeSection, setActiveSection] = useState<WorkbenchSection>("run");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [candidateStatusFilter, setCandidateStatusFilter] =
    useState<CandidateStatusFilter>("pending");
  const [selectedCallId, setSelectedCallId] = useState("");
  const [candidateDrafts, setCandidateDrafts] = useState<Record<string, string>>(
    {},
  );
  const [candidateMergeModes, setCandidateMergeModes] = useState<
    Record<string, EditConfirmMergeMode>
  >({});
  const [targetCards, setTargetCards] = useState<
    Record<string, StructuredKnowledgeCard | null>
  >({});
  const [targetCardErrors, setTargetCardErrors] = useState<Record<string, string>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [actionBusyKey, setActionBusyKey] = useState("");
  const [deletingRunId, setDeletingRunId] = useState("");
  const [error, setError] = useState("");

  const selectedCandidate = useMemo(
    () => {
      if (!selectedCandidateId) {
        return null;
      }
      return (
        currentRun?.review_items.find(
          candidate => candidate.review_item_id === selectedCandidateId,
        ) ?? null
      );
    },
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

  const selectedCandidateMergeMode = selectedCandidate
    ? candidateMergeModes[selectedCandidate.review_item_id] ?? "append"
    : "append";

  const selectedTargetCardId = selectedCandidate?.target_card_id ?? "";
  const selectedTargetCard = selectedTargetCardId
    ? targetCards[selectedTargetCardId]
    : null;
  const selectedTargetCardError = selectedTargetCardId
    ? targetCardErrors[selectedTargetCardId] ?? ""
    : "";

  const activeSectionInfo =
    sections.find(section => section.key === activeSection) ?? sections[0];

  const openRun = useCallback(async (runId: string): Promise<AgentRun> => {
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
    return response.run;
  }, []);

  const handleOpenRun = useCallback(
    async (runId: string) => {
      await openRun(runId);
    },
    [openRun],
  );

  const reloadRuns = useCallback(async () => {
    const response = await listKnowledgeExtractionRuns();
    setRuns(response.runs);
    return response.runs;
  }, []);

  async function handleDeleteRun(runId: string) {
    const targetRun = runs.find(run => run.run_id === runId);
    const title = targetRun?.chapter_title || "未命名章节";
    const confirmed = window.confirm(
      `删除“${title}”这次抽取运行记录？已入库知识卡不会回滚。`,
    );
    if (!confirmed) {
      return;
    }

    setDeletingRunId(runId);
    setError("");
    try {
      await deleteKnowledgeExtractionRun(runId);
      const nextRuns = await reloadRuns();
      if (selectedRunId === runId || currentRun?.run_id === runId) {
        const nextRun = nextRuns[0];
        if (nextRun) {
          await openRun(nextRun.run_id);
          setActiveSection("run");
        } else {
          setSelectedRunId("");
          setCurrentRun(null);
          setSelectedCandidateId("");
          setSelectedCallId("");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除运行记录失败");
    } finally {
      setDeletingRunId("");
    }
  }

  function handleCandidateStatusFilterChange(filter: CandidateStatusFilter) {
    setCandidateStatusFilter(filter);
    if (!currentRun) {
      return;
    }
    setSelectedCandidateId(
      pickVisibleCandidateId(currentRun, filter, selectedCandidateId),
    );
  }

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
        setSelectedChapterId(chapterResponse.chapters[0]?.id ?? "");
        if (runResponse.runs[0]) {
          await openRun(runResponse.runs[0].run_id);
          setActiveSection("run");
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

  useEffect(() => {
    const targetId = selectedCandidate?.target_card_id;
    if (!targetId || hasOwnKey(targetCards, targetId)) {
      return;
    }

    let ignore = false;
    void readKnowledgeCard(targetId)
      .then(response => {
        if (ignore) {
          return;
        }
        setTargetCardErrors(current => ({ ...current, [targetId]: "" }));
        setTargetCards(current =>
          hasOwnKey(current, targetId)
            ? current
            : { ...current, [targetId]: response.card },
        );
      })
      .catch(caught => {
        if (ignore) {
          return;
        }
        setTargetCards(current =>
          hasOwnKey(current, targetId)
            ? current
            : { ...current, [targetId]: null },
        );
        setTargetCardErrors(current => ({
          ...current,
          [targetId]:
            caught instanceof Error ? caught.message : "现有知识卡读取失败",
        }));
      });

    return () => {
      ignore = true;
    };
  }, [selectedCandidate?.target_card_id, targetCards]);

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
      setActiveSection("candidates");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "抽取运行失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleCandidateAction(
    candidate: AgentReviewItem,
    action: "confirm" | "edit-confirm" | "reject",
    mergeMode: EditConfirmMergeMode = "append",
  ) {
    setSelectedCandidateId(candidate.review_item_id);
    setActionBusyKey(`${candidate.review_item_id}:${action}`);
    setError("");
    try {
      const response =
        action === "confirm"
          ? await confirmKnowledgeExtractionCandidate(
              candidate.run_id,
              candidate.review_item_id,
            )
          : action === "edit-confirm"
            ? await editConfirmKnowledgeExtractionCandidate(
                candidate.run_id,
                candidate.review_item_id,
                {
                  card_updates: parseCandidateDraft(
                    candidate.review_item_id === selectedCandidateId
                      ? selectedCandidateDraft
                      : formatJson(candidate.suggested_card),
                  ),
                  target_card_id: candidate.target_card_id ?? null,
                  merge_mode: candidate.target_card_id ? mergeMode : "append",
                },
              )
            : await rejectKnowledgeExtractionCandidate(
                candidate.run_id,
                candidate.review_item_id,
              );
      setCurrentRun(response.run);
      setSelectedCandidateId(
        pickVisibleCandidateId(
          response.run,
          candidateStatusFilter,
          candidate.review_item_id,
        ),
      );
      await reloadRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "候选处理失败");
    } finally {
      setActionBusyKey("");
    }
  }

  async function copyText(text: string): Promise<boolean> {
    setError("");
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // Fall back to the legacy path below.
    }
    try {
      if (copyTextWithFallback(text)) {
        return true;
      }
    } catch {
      // Keep the user-facing message stable and Chinese.
    }
    setError("复制失败，可使用运行详情里的下载按钮导出同一份内容。");
    return false;
  }

  return (
    <AppShell activePath="/agent-workbench">
      <section className="mx-auto grid max-w-[1440px] gap-5 px-5 py-6 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <div className="px-2 py-2">
            <p className="text-xs text-[var(--tc-text-muted)]">智能体工作台</p>
            <h1 className="text-xl font-semibold text-[var(--tc-text-primary)]">
              智能体
            </h1>
            <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
              当前开放 1 个
            </p>
          </div>

          <div className="mt-2 grid gap-1">
            <button
              type="button"
              className="rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-3 text-left text-sm text-[var(--tc-text-primary)]"
            >
              <span className="flex items-center gap-2 font-semibold">
                <Bot className="size-4" />
                正文知识沉淀
              </span>
              <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
                章节正文到候选知识卡
              </span>
            </button>
            <button
              type="button"
              disabled
              className="rounded-[var(--tc-radius-control)] px-3 py-3 text-left text-sm text-[var(--tc-text-muted)] opacity-60"
            >
              后续智能体
              <span className="mt-1 block text-xs">暂未启用</span>
            </button>
          </div>

          <div className="mt-6 border-t border-[var(--tc-border-subtle)] pt-4">
            <div className="mb-2 flex items-center justify-between gap-2 px-2">
              <h2 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                最近运行
              </h2>
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
            <RecentRunList
              runs={runs}
              selectedRunId={selectedRunId}
              deletingRunId={deletingRunId}
              onOpenRun={runId => void handleOpenRun(runId)}
              onDeleteRun={runId => void handleDeleteRun(runId)}
            />
          </div>
        </aside>

        <section className="flex min-h-[calc(100vh-7rem)] min-w-0 flex-col">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
                <Bot className="size-4" />
                正文知识沉淀
              </p>
              <h2 className="text-2xl font-semibold text-[var(--tc-text-primary)]">
                当前智能体条目
              </h2>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void reloadRuns()}
            >
              <RefreshCw className="size-4" />
              刷新
            </Button>
          </div>

          {error ? (
            <div className="mb-4 flex max-w-[980px] items-start gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
              <AlertTriangle className="mt-0.5 size-4" />
              <span>{error}</span>
            </div>
          ) : null}

          <RunSummaryStrip run={currentRun} loading={loading} />

          <div className="mt-5 grid min-w-0 max-w-[1240px] gap-5 xl:grid-cols-[minmax(0,1fr)_140px]">
            <section className="min-w-0 border-t border-[var(--tc-border-subtle)] pt-5">
              <div className="mb-5">
                <h3 className="text-lg font-semibold text-[var(--tc-text-primary)]">
                  {activeSectionInfo.label}
                </h3>
                <p className="mt-1 text-sm text-[var(--tc-text-muted)]">
                  {activeSectionInfo.description}
                </p>
              </div>

              {loading ? (
                <EmptyPanel text="正在加载工作台数据..." />
              ) : activeSection === "run" ? (
                <RunTaskPanel
                  chapters={chapters}
                  selectedChapterId={selectedChapterId}
                  currentRun={currentRun}
                  running={running}
                  onChapterChange={setSelectedChapterId}
                  onCreateRun={() => void handleCreateRun()}
                />
              ) : activeSection === "candidates" ? (
                <CandidatePanel
                  run={currentRun}
                  selectedCandidate={selectedCandidate}
                  selectedCandidateDraft={selectedCandidateDraft}
                  selectedTargetCard={selectedTargetCard}
                  selectedTargetCardError={selectedTargetCardError}
                  selectedCandidateMergeMode={selectedCandidateMergeMode}
                  statusFilter={candidateStatusFilter}
                  actionBusyKey={actionBusyKey}
                  onSelectCandidate={setSelectedCandidateId}
                  onStatusFilterChange={handleCandidateStatusFilterChange}
                  onMergeModeChange={value => {
                    if (!selectedCandidate) {
                      return;
                    }
                    setCandidateMergeModes(current => ({
                      ...current,
                      [selectedCandidate.review_item_id]: value,
                    }));
                  }}
                  onCandidateDraftChange={value => {
                    if (!selectedCandidate) {
                      return;
                    }
                    setCandidateDrafts(current => ({
                      ...current,
                      [selectedCandidate.review_item_id]: value,
                    }));
                  }}
                  onAction={(candidate, action, mergeMode) =>
                    void handleCandidateAction(candidate, action, mergeMode)
                  }
                />
              ) : activeSection === "detail" ? (
                <RunDetailPanel
                  run={currentRun}
                  selectedCall={selectedLLMCall}
                  selectedCallId={selectedCallId}
                  onSelectCall={setSelectedCallId}
                  onCopy={copyText}
                />
              ) : (
                <MetricsPanel run={currentRun} />
              )}
            </section>
            <SectionRail
              activeSection={activeSection}
              onSectionChange={setActiveSection}
            />
          </div>
        </section>
      </section>
    </AppShell>
  );
}

function SectionRail({
  activeSection,
  onSectionChange,
}: {
  activeSection: WorkbenchSection;
  onSectionChange: (section: WorkbenchSection) => void;
}) {
  return (
    <nav
      aria-label="智能体工作台功能"
      className="grid h-max gap-2 self-start xl:sticky xl:top-24"
    >
      {sections.map(section => {
        const Icon = section.icon;
        const isActive = activeSection === section.key;
        return (
          <Button
            key={section.key}
            type="button"
            variant={isActive ? "default" : "outline"}
            size="sm"
            aria-pressed={isActive}
            onClick={() => onSectionChange(section.key)}
            className="h-11 w-full justify-start px-4"
          >
            <Icon className="size-4" />
            {section.label}
          </Button>
        );
      })}
    </nav>
  );
}

function RecentRunList({
  runs,
  selectedRunId,
  deletingRunId,
  onOpenRun,
  onDeleteRun,
}: {
  runs: AgentRunSummary[];
  selectedRunId: string;
  deletingRunId: string;
  onOpenRun: (runId: string) => void;
  onDeleteRun: (runId: string) => void;
}) {
  if (runs.length === 0) {
    return (
      <p className="px-2 text-sm text-[var(--tc-text-muted)]">暂无运行记录</p>
    );
  }
  return (
    <div className="grid max-h-[360px] gap-1 overflow-y-auto pr-1">
      {runs.map(run => (
        <div
          key={run.run_id}
          className={cn(
            "flex items-stretch gap-1 rounded-[var(--tc-radius-control)] text-sm transition-colors",
            selectedRunId === run.run_id
              ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
              : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
          )}
        >
          <button
            type="button"
            onClick={() => onOpenRun(run.run_id)}
            className="min-w-0 flex-1 px-3 py-2 text-left"
          >
            <span className="block truncate font-medium">
              {run.chapter_title || "未命名章节"}
            </span>
            <span className="mt-1 flex items-center justify-between gap-2 text-xs text-[var(--tc-text-muted)]">
              <span>{formatRunTimestamp(run.started_at)}</span>
              <span>{run.candidate_count} 个候选</span>
            </span>
            <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
              {runStatusLabel[run.status] ?? "未知状态"}
            </span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={deletingRunId !== ""}
            aria-label={`删除${run.chapter_title || "未命名章节"}运行记录`}
            onClick={() => onDeleteRun(run.run_id)}
            className="my-1 mr-1 shrink-0 text-[var(--tc-text-muted)]"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      ))}
    </div>
  );
}

function RunSummaryStrip({
  run,
  loading,
}: {
  run: AgentRun | null;
  loading: boolean;
}) {
  const values = run
    ? [
        ["运行状态", runStatusLabel[run.status] ?? "未知状态"],
        ["当前章节", run.scope.chapter_title || "未命名章节"],
        ["候选数量", `${run.metrics.candidate_total} 个`],
        ["总耗时", formatDuration(run.metrics.total_duration_ms)],
      ]
    : [
        ["运行状态", loading ? "加载中" : "未运行"],
        ["当前章节", "尚未选择运行"],
        ["候选数量", "0 个"],
        ["总耗时", "0 毫秒"],
      ];

  return (
    <dl className="grid max-w-[1080px] gap-2 border-y border-[var(--tc-border-subtle)] py-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
      {values.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs text-[var(--tc-text-muted)]">{label}</dt>
          <dd className="mt-1 truncate text-[var(--tc-text-primary)]">{value}</dd>
        </div>
      ))}
    </dl>
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
    <div className="grid max-w-[860px] gap-3">
      <label className="grid gap-2 text-sm">
        <span className="font-medium text-[var(--tc-text-primary)]">当前章节</span>
        <select
          className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 text-sm text-[var(--tc-text-primary)] outline-none"
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

      <div className="border-y border-[var(--tc-border-subtle)] py-3 text-sm">
        {selectedChapter ? (
          <>
            <p className="font-medium text-[var(--tc-text-primary)]">
              {selectedChapter.title}
            </p>
            <p className="mt-1 text-[var(--tc-text-muted)]">
              正文约 {selectedChapter.word_count} 字，运行后生成 JSON 中间态。
            </p>
          </>
        ) : (
          <p className="text-[var(--tc-text-muted)]">
            暂无可运行章节，请先在写作页创建章节。
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          disabled={!selectedChapterId || running}
          onClick={onCreateRun}
        >
          <Play className="size-4" />
          {running ? "正在抽取" : "开始抽取"}
        </Button>
        {currentRun ? (
          <span className="text-sm text-[var(--tc-text-muted)]">
            最近一次：{runStatusLabel[currentRun.status] ?? "未知状态"}，
            {currentRun.metrics.candidate_total} 个候选
          </span>
        ) : null}
      </div>
    </div>
  );
}

function CandidatePanel({
  run,
  selectedCandidate,
  selectedCandidateDraft,
  selectedTargetCard,
  selectedTargetCardError,
  selectedCandidateMergeMode,
  statusFilter,
  actionBusyKey,
  onSelectCandidate,
  onStatusFilterChange,
  onMergeModeChange,
  onCandidateDraftChange,
  onAction,
}: {
  run: AgentRun | null;
  selectedCandidate: AgentReviewItem | null;
  selectedCandidateDraft: string;
  selectedTargetCard?: StructuredKnowledgeCard | null;
  selectedTargetCardError: string;
  selectedCandidateMergeMode: EditConfirmMergeMode;
  statusFilter: CandidateStatusFilter;
  actionBusyKey: string;
  onSelectCandidate: (candidateId: string) => void;
  onStatusFilterChange: (filter: CandidateStatusFilter) => void;
  onMergeModeChange: (value: EditConfirmMergeMode) => void;
  onCandidateDraftChange: (value: string) => void;
  onAction: (
    candidate: AgentReviewItem,
    action: "confirm" | "edit-confirm" | "reject",
    mergeMode?: EditConfirmMergeMode,
  ) => void;
}) {
  if (!run) {
    return <EmptyPanel text="请选择或创建一次运行。" />;
  }
  if (run.review_items.length === 0) {
    return <EmptyPanel text="本次运行没有生成候选。" />;
  }

  const candidates = filterCandidates(run.review_items, statusFilter);

  return (
    <div className="grid max-w-[980px] gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {candidateStatusFilters.map(filter => (
          <Button
            key={filter.value}
            type="button"
            variant={statusFilter === filter.value ? "default" : "outline"}
            size="sm"
            aria-pressed={statusFilter === filter.value}
            onClick={() => onStatusFilterChange(filter.value)}
          >
            {filter.label}
            <span className="font-mono text-xs">
              {countCandidates(run.review_items, filter.value)}
            </span>
          </Button>
        ))}
      </div>

      {candidates.length === 0 ? (
        <EmptyPanel text="当前筛选下暂无候选。" />
      ) : null}

      <div className="grid gap-0">
        {candidates.map(candidate => {
          const isSelected =
            selectedCandidate?.review_item_id === candidate.review_item_id;
          const requiresEditedConfirm =
            candidate.candidate_action === "conflict" ||
            Boolean(candidate.target_card_id);
          const canConfirm = candidate.candidate_action !== "ignore";
          return (
            <article
              key={candidate.review_item_id}
              className="border-b border-[var(--tc-border-subtle)] py-3 last:border-b-0"
            >
            <button
              type="button"
              className="flex w-full items-start gap-3 text-left"
              onClick={() =>
                onSelectCandidate(isSelected ? "" : candidate.review_item_id)
              }
              aria-expanded={isSelected}
            >
              <ChevronRight
                className={cn(
                  "mt-1 size-4 shrink-0 text-[var(--tc-text-muted)] transition-transform",
                  isSelected ? "rotate-90" : "",
                )}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-[var(--tc-text-primary)]">
                  {candidate.display_title}
                </span>
                <span className="mt-2 flex flex-wrap gap-2">
                  <Tag>{knowledgeTypeLabel[candidate.knowledge_type]}</Tag>
                  <Tag>{candidateActionLabel[candidate.candidate_action]}</Tag>
                  <Tag>{candidateStatusLabel[candidate.candidate_status]}</Tag>
                </span>
              </span>
              <span className="hidden text-sm text-[var(--tc-text-muted)] md:block">
                {candidate.schema_validation.passed
                  ? "校验通过"
                  : "校验失败"}
              </span>
            </button>

            {isSelected ? (
              <div className="mt-3 grid gap-3 pl-7">
                {candidate.source_excerpt ? (
                  <p className="border-l border-[var(--tc-border-subtle)] pl-3 text-sm leading-6 text-[var(--tc-text-secondary)]">
                    {candidate.source_excerpt}
                  </p>
                ) : null}
                {candidate.schema_validation.errors.length > 0 ? (
                  <ul className="grid gap-1 text-sm text-[var(--tc-text-muted)]">
                    {candidate.schema_validation.errors.map(item => (
                      <li key={item}>校验提示：{item}</li>
                    ))}
                  </ul>
                ) : null}

                {candidate.target_card_id ? (
                  <section className="grid gap-2 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-[var(--tc-text-primary)]">
                        现有知识卡
                      </span>
                      <Tag>{candidate.target_card_id}</Tag>
                    </div>
                    {selectedTargetCardError ? (
                      <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-[var(--tc-text-muted)]">
                        {selectedTargetCardError}
                      </p>
                    ) : selectedTargetCard === undefined ? (
                      <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-[var(--tc-text-muted)]">
                        正在读取现有知识卡...
                      </p>
                    ) : selectedTargetCard ? (
                      <KnowledgeCardPreview card={selectedTargetCard} />
                    ) : (
                      <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-[var(--tc-text-muted)]">
                        未找到现有知识卡。
                      </p>
                    )}
                  </section>
                ) : null}

                {candidate.target_card_id ? (
                  <fieldset className="grid gap-2 text-sm">
                    <legend className="font-medium text-[var(--tc-text-primary)]">
                      编辑确认方式
                    </legend>
                    <div className="flex flex-wrap gap-2">
                      {(["append", "overwrite"] as EditConfirmMergeMode[]).map(
                        mode => (
                          <Button
                            key={mode}
                            type="button"
                            variant={
                              selectedCandidateMergeMode === mode
                                ? "default"
                                : "outline"
                            }
                            size="sm"
                            aria-pressed={selectedCandidateMergeMode === mode}
                            onClick={() => onMergeModeChange(mode)}
                          >
                            {mergeModeLabel[mode]}
                          </Button>
                        ),
                      )}
                    </div>
                    <p className="text-xs leading-5 text-[var(--tc-text-muted)]">
                      追加会合并别名、追加摘要和来源说明，并保留现有非空字段；覆盖会用下方编辑内容替换可编辑字段。
                    </p>
                  </fieldset>
                ) : null}

                <label className="grid gap-2 text-sm">
                  <span className="font-medium text-[var(--tc-text-primary)]">
                    编辑后确认内容
                  </span>
                  <textarea
                    className="min-h-48 resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-3 font-mono text-xs leading-relaxed text-[var(--tc-text-primary)] outline-none"
                    value={selectedCandidateDraft}
                    onChange={event => onCandidateDraftChange(event.target.value)}
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  {canConfirm ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={isProcessed(candidate) || actionBusyKey !== ""}
                      onClick={() =>
                        onAction(
                          candidate,
                          requiresEditedConfirm ? "edit-confirm" : "confirm",
                          selectedCandidateMergeMode,
                        )
                      }
                    >
                      <Check className="size-4" />
                      确认入库
                    </Button>
                  ) : null}
                  {!requiresEditedConfirm ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isProcessed(candidate) || actionBusyKey !== ""}
                      onClick={() =>
                        onAction(
                          candidate,
                          "edit-confirm",
                          selectedCandidateMergeMode,
                        )
                      }
                    >
                      <PencilLine className="size-4" />
                      编辑后确认
                    </Button>
                  ) : null}
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
              </div>
            ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function RunDetailPanel({
  run,
  selectedCall,
  selectedCallId,
  onSelectCall,
  onCopy,
}: {
  run: AgentRun | null;
  selectedCall: AgentLLMCall | null;
  selectedCallId: string;
  onSelectCall: (callId: string) => void;
  onCopy: (text: string) => Promise<boolean>;
}) {
  const [copiedTrace, setCopiedTrace] = useState(false);
  const [downloadedTrace, setDownloadedTrace] = useState(false);

  if (!run) {
    return <EmptyPanel text="请选择或创建一次运行。" />;
  }
  const activeRun = run;

  async function handleCopyLLMTrace() {
    const copied = await onCopy(buildRunLLMTrace(activeRun));
    if (!copied) {
      return;
    }
    setCopiedTrace(true);
    window.setTimeout(() => setCopiedTrace(false), 1800);
  }

  function handleDownloadLLMTrace() {
    downloadTextFile(
      `taichu_llm_trace_${activeRun.run_id}.md`,
      buildRunLLMTrace(activeRun),
    );
    setDownloadedTrace(true);
    window.setTimeout(() => setDownloadedTrace(false), 1800);
  }

  return (
    <div className="grid max-w-[980px] gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tc-border-subtle)] pb-3">
        <p className="text-sm text-[var(--tc-text-muted)]">
          一键整理本次运行的节点顺序、模型输入、原始响应和解析结果。
        </p>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {copiedTrace ? (
            <span className="text-xs text-[var(--tc-text-muted)]">已复制</span>
          ) : null}
          {downloadedTrace ? (
            <span className="text-xs text-[var(--tc-text-muted)]">已下载</span>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void handleCopyLLMTrace()}
          >
            <Copy className="size-4" />
            复制 LLM 链路
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownloadLLMTrace}
          >
            <Download className="size-4" />
            下载 LLM 链路
          </Button>
        </div>
      </div>

      <section>
        <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
          节点状态
        </h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead className="text-left text-[var(--tc-text-muted)]">
              <tr className="border-b border-[var(--tc-border-subtle)]">
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

      <ReplayDataSection run={run} />

      <section>
        <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
          模型调用记录
        </h3>
        <div className="mt-3 grid gap-0 border-t border-[var(--tc-border-subtle)]">
          {run.llm_calls.map(call => (
            <article
              key={call.call_id}
              className="border-b border-[var(--tc-border-subtle)] py-3"
            >
              <button
                type="button"
                className="flex w-full items-start gap-3 text-left"
                onClick={() => onSelectCall(call.call_id)}
              >
                <ChevronRight
                  className={cn(
                    "mt-1 size-4 shrink-0 text-[var(--tc-text-muted)] transition-transform",
                    selectedCallId === call.call_id ? "rotate-90" : "",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-[var(--tc-text-primary)]">
                    {nodeLabel[call.node_name] ?? call.node_name}
                  </span>
                  <span className="mt-1 block text-xs text-[var(--tc-text-muted)]">
                    {call.prompt_version} · {formatDuration(call.duration_ms)}
                  </span>
                </span>
                <span className="text-sm text-[var(--tc-text-muted)]">
                  {call.error ? "调用失败" : "调用完成"}
                </span>
              </button>
              {selectedCall?.call_id === call.call_id ? (
                <div className="mt-3 grid gap-3 pl-7">
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
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      {run.errors.length > 0 ? (
        <section>
          <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
            错误信息
          </h3>
          <ul className="mt-3 grid gap-2 text-sm text-[var(--tc-text-muted)]">
            {run.errors.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
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
    ["原始提及数", run.raw_mentions.length],
    ["实体聚合数", run.entity_groups.length],
    ["忽略项数", run.ignored.length],
    ["模型调用次数", run.metrics.llm_call_count],
    ["总耗时", formatDuration(run.metrics.total_duration_ms)],
  ];
  return (
    <div className="grid max-w-[980px] gap-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div
            key={label}
            className="border-b border-[var(--tc-border-subtle)] pb-3"
          >
            <div className="text-xs text-[var(--tc-text-muted)]">{label}</div>
            <div className="mt-2 text-xl font-semibold text-[var(--tc-text-primary)]">
              {value}
            </div>
          </div>
        ))}
      </div>
      <section>
        <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
          各节点耗时
        </h3>
        <div className="mt-3 grid gap-0 border-t border-[var(--tc-border-subtle)]">
          {Object.entries(run.metrics.node_duration_ms).map(([node, duration]) => (
            <div
              key={node}
              className="flex items-center justify-between gap-3 border-b border-[var(--tc-border-subtle)] py-2 text-sm"
            >
              <span className="text-[var(--tc-text-primary)]">
                {nodeLabel[node] ?? node}
              </span>
              <span className="font-mono text-[var(--tc-text-muted)]">
                {formatDuration(duration)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ReplayDataSection({ run }: { run: AgentRun }) {
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
          中间态回放
        </h3>
        <div className="flex flex-wrap gap-2">
          <Tag>原始提及 {run.raw_mentions.length}</Tag>
          <Tag>实体聚合 {run.entity_groups.length}</Tag>
          <Tag>忽略项 {run.ignored.length}</Tag>
        </div>
      </div>
      <div className="mt-3 grid gap-4">
        <RawMentionList mentions={run.raw_mentions} />
        <EntityGroupList groups={run.entity_groups} />
        <IgnoredExtractionList ignored={run.ignored} />
      </div>
    </section>
  );
}

function RawMentionList({ mentions }: { mentions: AgentRawMention[] }) {
  return (
    <ReplayList title="原始提及" emptyText="本次运行没有记录原始提及。">
      {mentions.map(mention => (
        <ReplayItem
          key={mention.mention_id}
          title={mention.name || "未命名提及"}
          meta={`${knowledgeTypeLabel[mention.knowledge_type] ?? mention.knowledge_type} · 第 ${mention.segment_index} 段`}
          detail={formatJson(mention)}
        >
          <ReplayRow label="抽取理由" value={mention.reason} />
          <ReplayRow label="描述" value={mention.description} />
          <EvidenceList values={mention.evidence_excerpts} />
        </ReplayItem>
      ))}
    </ReplayList>
  );
}

function EntityGroupList({ groups }: { groups: AgentEntityGroup[] }) {
  return (
    <ReplayList title="实体聚合" emptyText="本次运行没有记录实体聚合。">
      {groups.map(group => (
        <ReplayItem
          key={group.entity_group_id}
          title={group.canonical_name || "未命名实体组"}
          meta={`${knowledgeTypeLabel[group.knowledge_type] ?? group.knowledge_type} · ${qualityDecisionLabel(group.quality_decision)} · ${group.mention_count} 次提及`}
          detail={formatJson(group)}
        >
          <ReplayRow label="质量判断" value={group.quality_reason} />
          <ReplayRow label="原始名称" value={group.raw_names.join("、")} />
          <EvidenceList values={group.evidence_excerpts} />
        </ReplayItem>
      ))}
    </ReplayList>
  );
}

function IgnoredExtractionList({
  ignored,
}: {
  ignored: AgentIgnoredExtraction[];
}) {
  return (
    <ReplayList title="忽略项" emptyText="本次运行没有记录忽略项。">
      {ignored.map((item, index) => (
        <ReplayItem
          key={`${item.text}-${index}`}
          title={item.text || "未命名忽略项"}
          meta={
            item.segment_index ? `第 ${item.segment_index} 段` : "未记录段落"
          }
          detail={formatJson(item)}
        >
          <ReplayRow label="忽略原因" value={item.reason} />
        </ReplayItem>
      ))}
    </ReplayList>
  );
}

function ReplayList({
  title,
  emptyText,
  children,
}: {
  title: string;
  emptyText: string;
  children: ReactNode;
}) {
  return (
    <div className="border-t border-[var(--tc-border-subtle)] pt-3">
      <h4 className="text-sm font-semibold text-[var(--tc-text-primary)]">
        {title}
      </h4>
      <div className="mt-2 grid gap-0 border-t border-[var(--tc-border-subtle)]">
        {Array.isArray(children) && children.length === 0 ? (
          <p className="border-b border-[var(--tc-border-subtle)] py-3 text-sm text-[var(--tc-text-muted)]">
            {emptyText}
          </p>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function ReplayItem({
  title,
  meta,
  detail,
  children,
}: {
  title: string;
  meta: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <article className="border-b border-[var(--tc-border-subtle)] py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h5 className="text-sm font-semibold text-[var(--tc-text-primary)]">
          {title}
        </h5>
        <span className="text-xs text-[var(--tc-text-muted)]">{meta}</span>
      </div>
      <div className="mt-2 grid gap-2">{children}</div>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-[var(--tc-text-muted)]">
          查看完整字段
        </summary>
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] px-3 py-2 font-mono text-xs leading-relaxed text-[var(--tc-text-secondary)]">
          {detail}
        </pre>
      </details>
    </article>
  );
}

function ReplayRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 text-sm">
      <span className="text-xs text-[var(--tc-text-muted)]">{label}</span>
      <span className="whitespace-pre-wrap break-words leading-6 text-[var(--tc-text-secondary)]">
        {value || "无"}
      </span>
    </div>
  );
}

function EvidenceList({ values }: { values: string[] }) {
  return (
    <div className="grid gap-1 text-sm">
      <span className="text-xs text-[var(--tc-text-muted)]">证据摘录</span>
      {values.length > 0 ? (
        values.map((value, index) => (
          <blockquote
            key={`${value}-${index}`}
            className="border-l border-[var(--tc-border-strong)] pl-3 leading-6 text-[var(--tc-text-secondary)]"
          >
            {value}
          </blockquote>
        ))
      ) : (
        <span className="text-[var(--tc-text-muted)]">无</span>
      )}
    </div>
  );
}

function NodeRow({ node }: { node: AgentRunNode }) {
  return (
    <tr className="border-b border-[var(--tc-border-subtle)] last:border-b-0">
      <td className="py-3 pr-3 text-[var(--tc-text-primary)]">
        {nodeLabel[node.node_name] ?? node.node_name}
      </td>
      <td className="py-3 pr-3 text-[var(--tc-text-secondary)]">
        {nodeStatusLabel[node.status]}
      </td>
      <td className="py-3 pr-3 font-mono text-[var(--tc-text-muted)]">
        {formatDuration(node.duration_ms)}
      </td>
      <td className="py-3 text-[var(--tc-text-muted)]">
        {node.error || node.output_summary || "无"}
      </td>
    </tr>
  );
}

function TraceBlock({
  title,
  text,
  onCopy,
}: {
  title: string;
  text: string;
  onCopy: (text: string) => Promise<boolean>;
}) {
  return (
    <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--tc-border-subtle)] px-3 py-2">
        <span className="text-xs font-medium text-[var(--tc-text-muted)]">
          {title}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={`复制${title}`}
          onClick={() => void onCopy(text)}
        >
          <Copy className="size-3" />
        </Button>
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words bg-[var(--tc-surface-muted)] p-3 font-mono text-xs leading-relaxed text-[var(--tc-text-secondary)]">
        {text || "无内容"}
      </pre>
    </div>
  );
}

function KnowledgeCardPreview({ card }: { card: StructuredKnowledgeCard }) {
  const rows: Array<[string, string]> = [
    ["名称", card.name],
    ["摘要", card.summary],
    ["来源说明", card.source_note],
  ];
  const detail = formatJson(card);

  return (
    <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)]">
      <div className="grid gap-2 p-3">
        {rows.map(([label, value]) => (
          <div key={label} className="grid gap-1 text-sm">
            <span className="text-xs text-[var(--tc-text-muted)]">{label}</span>
            <span className="whitespace-pre-wrap break-words leading-6 text-[var(--tc-text-secondary)]">
              {value || "无"}
            </span>
          </div>
        ))}
      </div>
      <details className="border-t border-[var(--tc-border-subtle)]">
        <summary className="cursor-pointer px-3 py-2 text-xs text-[var(--tc-text-muted)]">
          查看完整字段
        </summary>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words px-3 pb-3 font-mono text-xs leading-relaxed text-[var(--tc-text-secondary)]">
          {detail}
        </pre>
      </details>
    </div>
  );
}

function buildRunLLMTrace(run: AgentRun): string {
  const nodeByName = new Map(run.nodes.map(node => [node.node_name, node]));
  const orderedCalls = run.llm_calls
    .map((call, index) => ({ call, index }))
    .sort((left, right) => compareCallOrder(left, right))
    .map(item => item.call);
  const lines: string[] = [
    `# 正文知识沉淀 LLM 链路`,
    "",
    "## 运行概览",
    "",
    `- 运行 ID：${run.run_id}`,
    `- Agent：${run.agent_name} / ${run.agent_version}`,
    `- 运行状态：${runStatusLabel[run.status] ?? run.status}`,
    `- 章节：${run.scope.chapter_title || "未命名章节"}（${run.scope.chapter_id}）`,
    `- 模型：${run.model_name || "未记录"}`,
    `- Schema 版本：${run.schema_version}`,
    `- Prompt 版本：${run.prompt_version}`,
    `- 开始时间：${formatNullable(run.started_at)}`,
    `- 结束时间：${formatNullable(run.finished_at)}`,
    `- 总耗时：${formatDuration(run.metrics.total_duration_ms)}`,
    `- LLM 调用次数：${run.metrics.llm_call_count}`,
    `- 候选总数：${run.metrics.candidate_total}`,
    "",
    "## 代码流程顺序（节点）",
    "",
  ];

  if (run.nodes.length === 0) {
    lines.push("本次运行没有记录节点。", "");
  } else {
    run.nodes.forEach((node, index) => {
      lines.push(
        `### ${index + 1}. ${nodeLabel[node.node_name] ?? node.node_name}`,
        "",
        `- 内部节点：${node.node_name}`,
        `- 状态：${nodeStatusLabel[node.status] ?? node.status}`,
        `- 开始时间：${formatNullable(node.started_at)}`,
        `- 结束时间：${formatNullable(node.finished_at)}`,
        `- 耗时：${formatDuration(node.duration_ms)}`,
        `- 输入摘要：${node.input_summary || "无"}`,
        `- 输出摘要：${node.output_summary || "无"}`,
        `- 错误：${node.error || "无"}`,
        "",
      );
    });
  }

  lines.push("## 中间态回放", "");
  appendReplayJsonBlock(lines, "原始提及 raw_mentions", run.raw_mentions);
  appendReplayJsonBlock(lines, "实体聚合 entity_groups", run.entity_groups);
  appendReplayJsonBlock(lines, "忽略项 ignored", run.ignored);

  lines.push("## 时间顺序 LLM 调用", "");
  if (orderedCalls.length === 0) {
    lines.push("本次运行没有记录 LLM 调用。", "");
  } else {
    orderedCalls.forEach((call, index) => {
      const node = nodeByName.get(call.node_name);
      lines.push(
        `### ${index + 1}. ${nodeLabel[call.node_name] ?? call.node_name}`,
        "",
        `- 调用 ID：${call.call_id}`,
        `- 对应内部节点：${call.node_name}`,
        `- 节点状态：${node ? nodeStatusLabel[node.status] ?? node.status : "未记录"}`,
        `- 节点输入摘要：${node?.input_summary || "无"}`,
        `- 节点输出摘要：${node?.output_summary || "无"}`,
        `- 节点错误：${node?.error || "无"}`,
        `- 模型：${call.model_name || "未记录"}`,
        `- Prompt 版本：${call.prompt_version}`,
        `- 开始时间：${formatNullable(call.started_at)}`,
        `- 结束时间：${formatNullable(call.finished_at)}`,
        `- 耗时：${formatDuration(call.duration_ms)}`,
        `- 调用错误：${call.error || "无"}`,
        "",
        markdownFence("输入提示词", "", call.input_prompt),
        "",
        markdownFence("原始响应", "", call.raw_response),
        "",
        markdownFence("解析结果 JSON", "json", formatJson(call.parsed_output)),
        "",
      );
    });
  }

  if (run.errors.length > 0) {
    lines.push("## 运行错误", "");
    run.errors.forEach((item, index) => {
      lines.push(`${index + 1}. ${item}`);
    });
    lines.push("");
  }

  return lines.join("\n").trimEnd();
}

function appendReplayJsonBlock(
  lines: string[],
  title: string,
  value: unknown,
): void {
  const content = formatJson(value);
  const fence = fenceFor(content);
  lines.push(`### ${title}`, "", `${fence}json`, content, fence, "");
}

function compareCallOrder(
  left: { call: AgentLLMCall; index: number },
  right: { call: AgentLLMCall; index: number },
): number {
  const leftTime = callSortTime(left.call);
  const rightTime = callSortTime(right.call);
  if (leftTime === rightTime) {
    return left.index - right.index;
  }
  return leftTime - rightTime;
}

function callSortTime(call: AgentLLMCall): number {
  const value = call.started_at ?? call.finished_at ?? "";
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : Number.MAX_SAFE_INTEGER;
}

function markdownFence(title: string, language: string, content: string): string {
  const value = content || "无内容";
  const fence = fenceFor(value);
  return [`#### ${title}`, "", `${fence}${language}`, value, fence].join("\n");
}

function fenceFor(value: string): string {
  const matches = value.match(/`+/g) ?? [];
  const longest = matches.reduce(
    (max, item) => Math.max(max, item.length),
    2,
  );
  return "`".repeat(longest + 1);
}

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-[var(--tc-radius-badge)] border border-[var(--tc-border-subtle)] px-2 py-1 text-xs text-[var(--tc-text-secondary)]">
      {children}
    </span>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <p className="text-sm text-[var(--tc-text-muted)]">{text}</p>;
}

function isProcessed(candidate: AgentReviewItem): boolean {
  return candidate.candidate_status !== "pending";
}

function filterCandidates(
  candidates: AgentReviewItem[],
  filter: CandidateStatusFilter,
): AgentReviewItem[] {
  if (filter === "all") {
    return candidates;
  }
  return candidates.filter(candidate => candidate.candidate_status === filter);
}

function countCandidates(
  candidates: AgentReviewItem[],
  filter: CandidateStatusFilter,
): number {
  return filterCandidates(candidates, filter).length;
}

function pickVisibleCandidateId(
  run: AgentRun,
  filter: CandidateStatusFilter,
  preferredId = "",
): string {
  const candidates = filterCandidates(run.review_items, filter);
  if (
    preferredId &&
    candidates.some(candidate => candidate.review_item_id === preferredId)
  ) {
    return preferredId;
  }
  return candidates[0]?.review_item_id ?? "";
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

function formatNullable(value?: string | null): string {
  return value && value.trim() ? value : "未记录";
}

function formatRunTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间未知";
  }
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hours}:${minutes}`;
}

function qualityDecisionLabel(decision: string): string {
  return qualityDecisionLabels[decision] ?? (decision || "未记录");
}

function copyTextWithFallback(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function hasOwnKey<T>(record: Record<string, T>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function formatDuration(value: number): string {
  if (value < 1000) {
    return `${value} 毫秒`;
  }
  return `${(value / 1000).toFixed(1)} 秒`;
}
