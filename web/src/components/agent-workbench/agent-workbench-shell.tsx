"use client";

import {
  Activity,
  AlertTriangle,
  Check,
  ChevronRight,
  Copy,
  Database,
  Download,
  Eye,
  FileText,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { CandidateReviewDialog } from "@/components/agent-workbench/candidate-review-dialog";
import {
  BulkAcceptConfirmDialogs,
  type BulkAcceptConfirmationStep,
} from "@/components/agent-workbench/bulk-accept-confirm-dialogs";
import { GeneralAgentWorkbench } from "@/components/agent-workbench/general-agent-workbench";
import {
  AgentWorkbenchSwitcher,
  type WorkbenchAgent,
} from "@/components/agent-workbench/agent-workbench-switcher";
import { ModelSelector } from "@/components/llm/model-selector";
import type { ReturnTypeOfModelSelection } from "@/components/llm/types";
import { Button } from "@/components/ui/button";
import { useModelSelection } from "@/hooks/use-model-selection";
import {
  confirmKnowledgeExtractionCandidate,
  acceptKnowledgeExtractionRun,
  deleteKnowledgeExtractionRun,
  editConfirmKnowledgeExtractionCandidate,
  getAgentTask,
  listKnowledgeExtractionRuns,
  getKnowledgeSedimentationProgress,
  rejectKnowledgeExtractionCandidate,
  startBatchKnowledgeExtractionRun,
  startKnowledgeExtractionRun,
} from "@/lib/api/agent-workbench";
import { listChapters } from "@/lib/api/chapters";
import {
  listKnowledgeCards,
  listKnowledgeSchemas,
  readKnowledgeCard,
} from "@/lib/api/mvp";
import {
  buildKnowledgeReferenceOptions,
  CANDIDATE_LOCKED_FIELD_KEYS,
  formStateFromKnowledgeValues,
  knowledgePayloadFromForm,
  validateKnowledgeForm,
  type KnowledgeFormErrors,
  type KnowledgeFormState,
  type KnowledgeReferenceOptions,
} from "@/lib/knowledge/structured-fields";
import { formatBatchRunTitle } from "@/lib/agent-run-display";
import type {
  AgentEntityGroup,
  AgentIgnoredExtraction,
  AgentLLMCall,
  AgentRawMention,
  AgentReviewItem,
  AgentRun,
  AgentRunNode,
  AgentRunSummary,
  KnowledgeSedimentationProgress,
  EditConfirmMergeMode,
  KnowledgeType,
  ReviewCandidateAction,
  ReviewCandidateStatus,
} from "@/lib/types/agent-workbench";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  KnowledgeTypeSchema,
  StructuredKnowledgeCard,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type WorkbenchSection = "run" | "candidates" | "detail" | "metrics";
type CandidateStatusFilter = ReviewCandidateStatus | "all";
type RunNotice = {
  message: string;
  runId?: string;
  state: "submitting" | "started";
};

const sections: Array<{
  key: WorkbenchSection;
  label: string;
  description: string;
  icon: typeof Play;
}> = [
  {
    key: "run",
    label: "任务配置",
    description: "选择当前章节并启动正文知识沉淀",
    icon: Play,
  },
  {
    key: "candidates",
    label: "待处理候选",
    description: "审核抽取出的角色、实体、事件和规则",
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

const candidateActionLabel: Record<ReviewCandidateAction, string> = {
  create_card: "候选新卡",
  update_card: "候选更新",
  conflict: "候选冲突",
  ignore: "建议忽略",
};

const knowledgeTypeLabel: Record<KnowledgeType, string> = {
  character: "角色",
  realm: "境界",
  technique: "功法",
  location: "地点",
  faction: "势力",
  item: "物品",
  rule: "规则",
  event: "事件",
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
  EventRuleExpertNode: "事件规则专家",
  MergeExpertCandidatesNode: "合并候选",
  NormalizeAndValidateNode: "规范校验",
  RunInternalConflictCheckNode: "本次冲突检查",
  MatchExistingKnowledgeNode: "匹配有效知识",
  BuildReviewItemsNode: "生成审核项",
  WriteIntermediateJsonNode: "写入中间态",
};

export function AgentWorkbenchShell() {
  const [activeAgent, setActiveAgent] = useState<WorkbenchAgent>("general");

  if (activeAgent === "general") {
    return <GeneralAgentWorkbench onAgentChange={setActiveAgent} />;
  }
  return <KnowledgeExtractionWorkbench onAgentChange={setActiveAgent} />;
}

function KnowledgeExtractionWorkbench({
  onAgentChange,
}: {
  onAgentChange: (agent: WorkbenchAgent) => void;
}) {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [sedimentationProgress, setSedimentationProgress] =
    useState<KnowledgeSedimentationProgress>({});
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [currentRun, setCurrentRun] = useState<AgentRun | null>(null);
  const [activeSection, setActiveSection] = useState<WorkbenchSection>("run");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [candidateStatusFilter, setCandidateStatusFilter] =
    useState<CandidateStatusFilter>("pending");
  const [selectedCallId, setSelectedCallId] = useState("");
  const [knowledgeSchemas, setKnowledgeSchemas] = useState<KnowledgeTypeSchema[]>([]);
  const [referenceOptions, setReferenceOptions] =
    useState<KnowledgeReferenceOptions>({});
  const [candidateDrafts, setCandidateDrafts] = useState<
    Record<string, KnowledgeFormState>
  >({});
  const [candidateFormErrors, setCandidateFormErrors] = useState<
    Record<string, KnowledgeFormErrors>
  >({});
  const [editingCandidateId, setEditingCandidateId] = useState("");
  const [candidateDialogOpen, setCandidateDialogOpen] = useState(false);
  const [bulkAcceptConfirmationStep, setBulkAcceptConfirmationStep] =
    useState<BulkAcceptConfirmationStep>(null);
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
  const [runNotice, setRunNotice] = useState<RunNotice | null>(null);
  const modelSelection = useModelSelection();

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

  const knowledgeSchemaByType = useMemo(
    () => new Map(knowledgeSchemas.map(schema => [schema.type, schema])),
    [knowledgeSchemas],
  );
  const selectedCandidateSchema = selectedCandidate
    ? knowledgeSchemaByType.get(selectedCandidate.knowledge_type) ?? null
    : null;
  const selectedCandidateDraft =
    selectedCandidate && selectedCandidateSchema
      ? candidateDrafts[selectedCandidate.review_item_id] ??
        formStateFromKnowledgeValues(
          selectedCandidateSchema,
          selectedCandidate.suggested_card,
        )
      : {};
  const selectedCandidateFormErrors = selectedCandidate
    ? candidateFormErrors[selectedCandidate.review_item_id] ?? {}
    : {};

  const selectedCandidateMergeMode = selectedCandidate
    ? candidateMergeModes[selectedCandidate.review_item_id] ?? "merge"
    : "merge";

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
    const response = await getAgentTask(runId);
    setCurrentRun(response.run);
    setEditingCandidateId("");
    setCandidateDialogOpen(false);
    setBulkAcceptConfirmationStep(null);
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
    const title = targetRun ? runSummaryTitle(targetRun) : "未命名任务";
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
          setCandidateDialogOpen(false);
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
    setCandidateDialogOpen(false);
    setEditingCandidateId("");
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
        const [chapterResponse, runResponse, schemaResponse, progressResponse] = await Promise.all([
          listChapters(),
          listKnowledgeExtractionRuns(),
          listKnowledgeSchemas(),
          getKnowledgeSedimentationProgress(),
        ]);
        const [characterResult, factionResult] = await Promise.allSettled([
          listKnowledgeCards({
            type: "character",
            lifecycle: "confirmed",
            page: 1,
            pageSize: 100,
          }),
          listKnowledgeCards({
            type: "faction",
            lifecycle: "confirmed",
            page: 1,
            pageSize: 100,
          }),
        ]);
        if (ignore) {
          return;
        }
        setChapters(chapterResponse.chapters);
        setRuns(runResponse.runs);
        setSedimentationProgress(progressResponse);
        setKnowledgeSchemas(schemaResponse.schemas);
        setReferenceOptions(
          buildKnowledgeReferenceOptions(
            schemaResponse.schemas,
            chapterResponse.chapters,
            characterResult.status === "fulfilled"
              ? characterResult.value.cards
              : [],
            factionResult.status === "fulfilled"
              ? factionResult.value.cards
              : [],
          ),
        );
        const acceptedIndex = progressResponse.last_accepted_chapter_id
          ? chapterResponse.chapters.findIndex(
              chapter => chapter.id === progressResponse.last_accepted_chapter_id,
            )
          : -1;
        const nextChapter = chapterResponse.chapters[acceptedIndex + 1];
        setSelectedChapterIds(nextChapter ? [nextChapter.id] : []);
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
    if (!runNotice || runNotice.state === "submitting") {
      return;
    }
    const timer = window.setTimeout(() => setRunNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [runNotice]);

  useEffect(() => {
    if (activeSection !== "candidates" || !selectedRunId) {
      return;
    }
    let ignore = false;

    async function syncSelectedRun() {
      try {
        const response = await getAgentTask(selectedRunId);
        if (ignore) {
          return;
        }
        setCurrentRun(response.run);
        setSelectedCandidateId(current =>
          pickVisibleCandidateId(response.run, candidateStatusFilter, current),
        );
      } catch {
        // Keep the last usable snapshot; explicit actions still surface failures.
      }
    }

    const handleWindowFocus = () => {
      void syncSelectedRun();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void syncSelectedRun();
      }
    };

    void syncSelectedRun();
    window.addEventListener("focus", handleWindowFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      ignore = true;
      window.removeEventListener("focus", handleWindowFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [activeSection, candidateStatusFilter, selectedRunId]);

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
    if (selectedChapterIds.length === 0) {
      setError("请先勾选至少一个章节。");
      return;
    }
    if (!modelSelection.modelId) {
      setError(modelSelection.error || "模型列表尚未加载完成。");
      return;
    }
    setRunning(true);
    setError("");
    const isBatchRun = selectedChapterIds.length > 1;
    setRunNotice({
      state: "submitting",
      message: isBatchRun
        ? "正在提交批量知识沉淀任务..."
        : "正在提交知识沉淀任务...",
    });
    try {
      const response = isBatchRun
          ? await startBatchKnowledgeExtractionRun({
            chapter_ids: selectedChapterIds,
            model_id: modelSelection.modelId,
          })
        : await startKnowledgeExtractionRun({
            chapter_id: selectedChapterIds[0],
            model_id: modelSelection.modelId,
          });
      setSelectedRunId(response.run.run_id);
      setRuns(current => upsertRunSummary(current, response.run));
      setRunNotice({
        state: "started",
        runId: response.run.run_id,
        message: isBatchRun
          ? "批量任务已开始，可前往任务监控查看节点流转。"
          : "任务已开始，可前往任务监控查看节点流转。",
      });
      try {
        const taskResponse = await getAgentTask(response.run.run_id);
        setCurrentRun(taskResponse.run);
        setSelectedCandidateId(
          taskResponse.run.review_items.find(
            item => item.candidate_status === "pending",
          )?.review_item_id ??
            taskResponse.run.review_items[0]?.review_item_id ??
            "",
        );
        setSelectedCallId(taskResponse.run.llm_calls[0]?.call_id ?? "");
      } catch {
        void reloadRuns();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "任务启动失败");
      setRunNotice(null);
    } finally {
      setRunning(false);
    }
  }

  async function handleCandidateAction(
    candidate: AgentReviewItem,
    action: "confirm" | "edit-confirm" | "reject",
    mergeMode: EditConfirmMergeMode = "merge",
  ) {
    setSelectedCandidateId(candidate.review_item_id);
    setError("");
    let cardUpdates: Record<string, unknown> | null = null;
    if (action === "edit-confirm") {
      const schema = knowledgeSchemaByType.get(candidate.knowledge_type);
      if (!schema) {
        setError("知识字段配置尚未加载完成，请稍后重试。");
        return;
      }
      const draft =
        candidateDrafts[candidate.review_item_id] ??
        formStateFromKnowledgeValues(schema, candidate.suggested_card);
      const formErrors = validateKnowledgeForm(
        schema,
        draft,
        CANDIDATE_LOCKED_FIELD_KEYS,
      );
      setCandidateFormErrors(current => ({
        ...current,
        [candidate.review_item_id]: formErrors,
      }));
      if (Object.keys(formErrors).length) {
        setEditingCandidateId(candidate.review_item_id);
        setError("请先补全必填字段后再确认入库。");
        return;
      }
      cardUpdates = knowledgePayloadFromForm(
        schema,
        draft,
        CANDIDATE_LOCKED_FIELD_KEYS,
      );
    }
    setActionBusyKey(`${candidate.review_item_id}:${action}`);
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
                  card_updates: cardUpdates ?? {},
                  target_card_id: candidate.target_card_id ?? null,
                  merge_mode: candidate.target_card_id ? mergeMode : "merge",
                },
              )
            : await rejectKnowledgeExtractionCandidate(
                candidate.run_id,
                candidate.review_item_id,
              );
      setCurrentRun(response.run);
      setEditingCandidateId("");
      setCandidateFormErrors(current => ({
        ...current,
        [candidate.review_item_id]: {},
      }));
      const targetCardId = candidate.target_card_id;
      if (targetCardId) {
        setTargetCards(current => omitRecordKey(current, targetCardId));
        setTargetCardErrors(current => omitRecordKey(current, targetCardId));
      }
      const nextCandidateId = pickNextPendingCandidateId(
        response.run,
        candidateStatusFilter,
        candidate.review_item_id,
      );
      setSelectedCandidateId(nextCandidateId);
      setCandidateDialogOpen(Boolean(nextCandidateId));
      await reloadRuns();
    } catch (caught) {
      const actionError =
        caught instanceof Error ? caught.message : "候选处理失败";
      try {
        const response = await getAgentTask(candidate.run_id);
        setCurrentRun(response.run);
        setSelectedCandidateId(current =>
          pickVisibleCandidateId(response.run, candidateStatusFilter, current),
        );
        const synchronizedCandidate = response.run.review_items.find(
          item => item.review_item_id === candidate.review_item_id,
        );
        const actionAlreadyApplied =
          (action === "reject" &&
            synchronizedCandidate?.candidate_status === "rejected") ||
          (action !== "reject" &&
            synchronizedCandidate?.candidate_status === "confirmed");
        const targetCardId = candidate.target_card_id;
        if (actionAlreadyApplied && targetCardId) {
          setTargetCards(current => omitRecordKey(current, targetCardId));
          setTargetCardErrors(current => omitRecordKey(current, targetCardId));
        }
        if (actionAlreadyApplied) {
          const nextCandidateId = pickNextPendingCandidateId(
            response.run,
            candidateStatusFilter,
            candidate.review_item_id,
          );
          setSelectedCandidateId(nextCandidateId);
          setCandidateDialogOpen(Boolean(nextCandidateId));
        }
        setError(actionAlreadyApplied ? "" : actionError);
        void reloadRuns();
      } catch {
        setError(actionError);
      }
    } finally {
      setActionBusyKey("");
    }
  }

  async function handleAcceptRun() {
    if (!currentRun) return;
    const runId = currentRun.run_id;
    setError("");
    setActionBusyKey("accept-run");
    try {
      const progress = await acceptKnowledgeExtractionRun(runId);
      const response = await getAgentTask(runId);
      setSedimentationProgress(progress);
      setCurrentRun(response.run);
      setCandidateDialogOpen(false);
      setSelectedCandidateId(
        pickVisibleCandidateId(response.run, candidateStatusFilter, ""),
      );
      await reloadRuns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "采纳本次沉淀失败");
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
      {runNotice ? <RunStartNotice notice={runNotice} /> : null}
      <BulkAcceptConfirmDialogs
        step={bulkAcceptConfirmationStep}
        pendingCount={
          currentRun?.review_items.filter(
            item => item.candidate_status === "pending",
          ).length ?? 0
        }
        onStepChange={setBulkAcceptConfirmationStep}
        onConfirm={() => {
          setBulkAcceptConfirmationStep(null);
          void handleAcceptRun();
        }}
      />
      <section className="mx-auto grid max-w-[1440px] gap-4 px-4 py-4 xl:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="min-w-0 overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <AgentWorkbenchSwitcher
            activeAgent="knowledge"
            onAgentChange={onAgentChange}
          />

          <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3">
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

        <section className="flex min-h-0 min-w-0 flex-col">
          {error ? (
            <div className="mx-auto mb-4 flex w-full max-w-[960px] items-start gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
              <AlertTriangle className="mt-0.5 size-4" />
              <span>{error}</span>
            </div>
          ) : null}

          <RunSummaryStrip run={currentRun} loading={loading} />

          <div className="mx-auto mt-4 grid w-full min-w-0 max-w-[1180px] gap-4 xl:grid-cols-[minmax(0,1fr)_128px]">
            <section className="min-w-0 border-t border-[var(--tc-border-subtle)] pt-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
                  {activeSectionInfo.label}
                </h3>
                <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
                  {activeSectionInfo.description}
                </p>
              </div>

              {loading ? (
                <EmptyPanel text="正在加载工作台数据..." />
              ) : activeSection === "run" ? (
                <RunTaskPanel
                  chapters={chapters}
                  sedimentationProgress={sedimentationProgress}
                  selectedChapterIds={selectedChapterIds}
                  currentRun={currentRun}
                  running={running}
                  modelSelection={modelSelection}
                  onChapterToggle={(chapterId, checked) => {
                    const acceptedIndex = sedimentationProgress.last_accepted_chapter_id
                      ? chapters.findIndex(
                          chapter =>
                            chapter.id ===
                            sedimentationProgress.last_accepted_chapter_id,
                        )
                      : -1;
                    const clickedIndex = chapters.findIndex(
                      chapter => chapter.id === chapterId,
                    );
                    const start = acceptedIndex + 1;
                    setSelectedChapterIds(
                      checked
                        ? chapters.slice(start, clickedIndex + 1).map(chapter => chapter.id)
                        : chapters.slice(start, clickedIndex).map(chapter => chapter.id),
                    );
                  }}
                  onCreateRun={() => void handleCreateRun()}
                />
              ) : activeSection === "candidates" ? (
                <CandidatePanel
                  run={currentRun}
                  selectedCandidate={selectedCandidate}
                  selectedCandidateSchema={selectedCandidateSchema}
                  selectedCandidateDraft={selectedCandidateDraft}
                  selectedCandidateFormErrors={selectedCandidateFormErrors}
                  referenceOptions={referenceOptions}
                  editingCandidateId={editingCandidateId}
                  selectedTargetCard={selectedTargetCard}
                  selectedTargetCardError={selectedTargetCardError}
                  selectedCandidateMergeMode={selectedCandidateMergeMode}
                  dialogOpen={candidateDialogOpen}
                  statusFilter={candidateStatusFilter}
                  actionBusyKey={actionBusyKey}
                  onAcceptRun={() => setBulkAcceptConfirmationStep("first")}
                  onSelectCandidate={candidateId => {
                    setSelectedCandidateId(candidateId);
                    setCandidateDialogOpen(true);
                    if (editingCandidateId && editingCandidateId !== candidateId) {
                      setEditingCandidateId("");
                    }
                  }}
                  onDialogOpenChange={nextOpen => {
                    setCandidateDialogOpen(nextOpen);
                    if (!nextOpen) {
                      setEditingCandidateId("");
                    }
                  }}
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
                    setCandidateFormErrors(current => ({
                      ...current,
                      [selectedCandidate.review_item_id]: {},
                    }));
                  }}
                  onStartEdit={candidate => {
                    const schema = knowledgeSchemaByType.get(candidate.knowledge_type);
                    if (!schema) {
                      setError("知识字段配置尚未加载完成，请稍后重试。");
                      return;
                    }
                    setCandidateDrafts(current => ({
                      ...current,
                      [candidate.review_item_id]:
                        current[candidate.review_item_id] ??
                        formStateFromKnowledgeValues(
                          schema,
                          candidate.suggested_card,
                        ),
                    }));
                    setCandidateFormErrors(current => ({
                      ...current,
                      [candidate.review_item_id]: {},
                    }));
                    setEditingCandidateId(candidate.review_item_id);
                  }}
                  onCancelEdit={candidate => {
                    const schema = knowledgeSchemaByType.get(candidate.knowledge_type);
                    if (schema) {
                      setCandidateDrafts(current => ({
                        ...current,
                        [candidate.review_item_id]: formStateFromKnowledgeValues(
                          schema,
                          candidate.suggested_card,
                        ),
                      }));
                    }
                    setCandidateFormErrors(current => ({
                      ...current,
                      [candidate.review_item_id]: {},
                    }));
                    setEditingCandidateId("");
                    setError("");
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
              onSectionChange={section => {
                setActiveSection(section);
                if (section !== "candidates") {
                  setCandidateDialogOpen(false);
                  setEditingCandidateId("");
                }
              }}
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
      className="grid h-max gap-2 self-start xl:sticky xl:top-20"
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
            className="h-9 w-full justify-start px-3"
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
    <div className="grid max-h-[300px] min-w-0 gap-0.5 overflow-x-hidden overflow-y-auto pr-1">
      {runs.map(run => {
        const title = runSummaryTitle(run);
        return (
          <div
            key={run.run_id}
            className={cn(
              "group relative min-w-0 overflow-hidden rounded-[var(--tc-radius-control)] text-sm transition-colors",
              selectedRunId === run.run_id
                ? "bg-[var(--tc-surface-muted)] text-[var(--tc-text-primary)]"
                : "text-[var(--tc-text-secondary)] hover:bg-[var(--tc-surface-muted)] hover:text-[var(--tc-text-primary)]",
            )}
          >
            <button
              type="button"
              onClick={() => onOpenRun(run.run_id)}
              className="block w-full min-w-0 overflow-hidden px-2 py-1.5 pr-8 text-left"
            >
              <span className="block break-words font-medium leading-5">{title}</span>
              <span className="mt-0.5 flex min-w-0 items-center justify-between gap-2 text-xs text-[var(--tc-text-muted)]">
                <span className="whitespace-nowrap">
                  {formatRunTimestamp(run.started_at)} · {runStatusLabel[run.status] ?? "未知状态"}
                </span>
                <span className="whitespace-nowrap">{run.candidate_count} 个候选</span>
              </span>
            </button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={deletingRunId !== ""}
              aria-label={`删除${title}运行记录`}
              onClick={() => onDeleteRun(run.run_id)}
              className="absolute right-1 top-1 opacity-0 text-[var(--tc-text-muted)] transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function runSummaryTitle(run: AgentRunSummary): string {
  if (run.scope_type === "chapter_batch") {
    return formatBatchRunTitle(run);
  }
  if (run.scope_type === "summary_repair") {
    return "历史摘要修复";
  }
  return run.chapter_title || "未命名章节";
}

function RunSummaryStrip({
  run,
  loading,
}: {
  run: AgentRun | null;
  loading: boolean;
}) {
  const scopeLabel =
    run?.scope.scope_type === "chapter_batch"
      ? `${run.total_chapter_count} 章批量`
      : run?.scope.scope_type === "summary_repair"
        ? "有效知识卡摘要"
      : run?.scope.chapter_title || "未命名章节";
  const values = run
    ? [
        ["运行状态", runStatusLabel[run.status] ?? "未知状态"],
        ["任务范围", scopeLabel],
        ["候选数量", `${run.metrics.candidate_total} 个`],
        ["总耗时", formatDuration(run.metrics.total_duration_ms)],
      ]
    : [
        ["运行状态", loading ? "加载中" : "未运行"],
        ["任务范围", "尚未选择运行"],
        ["候选数量", "0 个"],
        ["总耗时", "0 毫秒"],
      ];

  return (
    <dl className="mx-auto grid w-full max-w-[960px] gap-2 border-y border-[var(--tc-border-subtle)] py-2 text-center text-sm sm:grid-cols-2 xl:grid-cols-4">
      {values.map(([label, value]) => (
        <div key={label} className="min-w-0 px-2">
          <dt className="text-xs text-[var(--tc-text-muted)]">{label}</dt>
          <dd className="mt-1 truncate text-[var(--tc-text-primary)]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function upsertRunSummary(
  runs: AgentRunSummary[],
  next: AgentRunSummary,
): AgentRunSummary[] {
  const rest = runs.filter(run => run.run_id !== next.run_id);
  return [next, ...rest];
}

function RunStartNotice({ notice }: { notice: RunNotice }) {
  const submitting = notice.state === "submitting";
  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-50 flex justify-center px-4">
      <div className="pointer-events-auto flex max-w-[min(92vw,560px)] items-center gap-3 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] px-4 py-2 text-sm text-[var(--tc-text-primary)] shadow-[0_18px_48px_rgba(0,0,0,0.36)]">
        <span
          className={cn(
            "flex size-6 items-center justify-center rounded-full border",
            submitting
              ? "border-amber-300/35 text-amber-200"
              : "border-emerald-300/35 text-emerald-200",
          )}
        >
          {submitting ? (
            <Activity className="size-3.5" />
          ) : (
            <Check className="size-3.5" />
          )}
        </span>
        <span className="min-w-0 flex-1 truncate">{notice.message}</span>
        {notice.state === "started" ? (
          <Link
            href="/task-monitor/knowledge-extraction"
            className="shrink-0 rounded-[var(--tc-radius-pill)] border border-[var(--tc-border-subtle)] px-2.5 py-1 text-xs text-[var(--tc-text-primary)] hover:bg-[var(--tc-surface-muted)]"
          >
            前往监控台
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function RunTaskPanel({
  chapters,
  sedimentationProgress,
  selectedChapterIds,
  currentRun,
  running,
  modelSelection,
  onChapterToggle,
  onCreateRun,
}: {
  chapters: ChapterInfo[];
  sedimentationProgress: KnowledgeSedimentationProgress;
  selectedChapterIds: string[];
  currentRun: AgentRun | null;
  running: boolean;
  modelSelection: ReturnTypeOfModelSelection;
  onChapterToggle: (chapterId: string, checked: boolean) => void;
  onCreateRun: () => void;
}) {
  const chapterListRef = useRef<HTMLDivElement>(null);
  const nextChapterRowRef = useRef<HTMLLabelElement>(null);
  const selectedChapterSet = new Set(selectedChapterIds);
  const acceptedIndex = sedimentationProgress.last_accepted_chapter_id
    ? chapters.findIndex(
        chapter => chapter.id === sedimentationProgress.last_accepted_chapter_id,
      )
    : -1;
  const nextChapter = chapters[acceptedIndex + 1] ?? null;
  const acceptedChapter = acceptedIndex >= 0 ? chapters[acceptedIndex] : null;
  const selectedChapters = chapters.filter(chapter =>
    selectedChapterSet.has(chapter.id),
  );
  const selectedCount = selectedChapters.length;
  const buttonLabel =
    running
      ? selectedCount > 1
        ? "正在批量生成"
        : "正在抽取"
      : selectedCount > 1
        ? "批量生成候选"
        : "开始抽取";

  useEffect(() => {
    const chapterList = chapterListRef.current;
    const nextChapterRow = nextChapterRowRef.current;
    if (!chapterList || !nextChapterRow) {
      return;
    }

    const listRect = chapterList.getBoundingClientRect();
    const rowRect = nextChapterRow.getBoundingClientRect();
    const rowTop = rowRect.top - listRect.top + chapterList.scrollTop;
    const centeredScrollTop =
      rowTop - (chapterList.clientHeight - nextChapterRow.offsetHeight) / 2;
    const maximumScrollTop =
      chapterList.scrollHeight - chapterList.clientHeight;

    chapterList.scrollTop = Math.max(
      0,
      Math.min(centeredScrollTop, maximumScrollTop),
    );
  }, [chapters.length, nextChapter?.id]);

  return (
    <div className="mx-auto grid w-full max-w-[960px] gap-2">
      <div className="grid gap-2 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium text-[var(--tc-text-primary)]">
            勾选章节
          </span>
          <span className="text-xs text-[var(--tc-text-muted)]">
            已选 {selectedCount} 章
          </span>
        </div>
        <p className="text-xs text-[var(--tc-text-muted)]">
          {nextChapter
            ? acceptedChapter
              ? `知识已沉淀至《${acceptedChapter.title}》；下一次从《${nextChapter.title}》开始。`
              : `尚未采纳知识沉淀；请从《${nextChapter.title}》开始。`
            : "全部现有章节均已完成知识沉淀。"}
        </p>
        {chapters.length === 0 ? (
          <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-4 text-[var(--tc-text-muted)]">
            暂无可运行章节，请先在写作页创建章节。
          </div>
        ) : (
          <div
            ref={chapterListRef}
            className="max-h-[292px] overflow-y-auto rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)]"
          >
            {chapters.map((chapter, index) => {
              const checked = selectedChapterSet.has(chapter.id);
              const unavailable = index < acceptedIndex + 1;
              return (
                <label
                  key={chapter.id}
                  ref={chapter.id === nextChapter?.id ? nextChapterRowRef : null}
                  className={cn(
                    "flex cursor-pointer items-start gap-2.5 border-b border-[var(--tc-border-subtle)] px-3 py-2 text-sm last:border-b-0",
                    unavailable
                      ? "cursor-not-allowed opacity-45"
                      : checked
                      ? "bg-[color-mix(in_srgb,var(--tc-surface-card),var(--tc-aurora-line)_8%)]"
                      : "hover:bg-[var(--tc-surface-card)]",
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-[var(--tc-workspace-focus)]"
                    checked={checked}
                    disabled={unavailable}
                    onChange={event =>
                      onChapterToggle(chapter.id, event.target.checked)
                    }
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-[var(--tc-text-primary)]">
                      {chapter.title}
                    </span>
                    <span className="block text-xs text-[var(--tc-text-muted)]">
                      正文约 {chapter.word_count} 字
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-y border-[var(--tc-border-subtle)] py-2 text-sm">
        {selectedCount > 0 ? (
          <p className="text-[var(--tc-text-muted)]">
            将为 {selectedCount} 章生成候选知识卡；节点流转请到任务监控查看，候选审核仍在当前工作台处理。
          </p>
        ) : (
          <p className="text-[var(--tc-text-muted)]">
            请至少勾选一个章节后再启动正文知识沉淀。
          </p>
        )}
      </div>

      <ModelSelector selection={modelSelection} />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          disabled={selectedCount === 0 || running}
          onClick={onCreateRun}
        >
          <Play className="size-4" />
          {buttonLabel}
        </Button>
        <Link
          href="/task-monitor/knowledge-extraction"
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-[var(--tc-radius-control)] border border-[var(--tc-workspace-border)] px-2.5 text-sm text-[var(--tc-workspace-text)] hover:bg-[var(--tc-workspace-panel-soft)]"
        >
          <Activity className="size-4" />
          任务监控
        </Link>
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
  selectedCandidateSchema,
  selectedCandidateDraft,
  selectedCandidateFormErrors,
  referenceOptions,
  editingCandidateId,
  selectedTargetCard,
  selectedTargetCardError,
  selectedCandidateMergeMode,
  dialogOpen,
  statusFilter,
  actionBusyKey,
  onAcceptRun,
  onSelectCandidate,
  onDialogOpenChange,
  onStatusFilterChange,
  onMergeModeChange,
  onCandidateDraftChange,
  onStartEdit,
  onCancelEdit,
  onAction,
}: {
  run: AgentRun | null;
  selectedCandidate: AgentReviewItem | null;
  selectedCandidateSchema: KnowledgeTypeSchema | null;
  selectedCandidateDraft: KnowledgeFormState;
  selectedCandidateFormErrors: KnowledgeFormErrors;
  referenceOptions: KnowledgeReferenceOptions;
  editingCandidateId: string;
  selectedTargetCard?: StructuredKnowledgeCard | null;
  selectedTargetCardError: string;
  selectedCandidateMergeMode: EditConfirmMergeMode;
  dialogOpen: boolean;
  statusFilter: CandidateStatusFilter;
  actionBusyKey: string;
  onAcceptRun: () => void;
  onSelectCandidate: (candidateId: string) => void;
  onDialogOpenChange: (open: boolean) => void;
  onStatusFilterChange: (filter: CandidateStatusFilter) => void;
  onMergeModeChange: (value: EditConfirmMergeMode) => void;
  onCandidateDraftChange: (value: KnowledgeFormState) => void;
  onStartEdit: (candidate: AgentReviewItem) => void;
  onCancelEdit: (candidate: AgentReviewItem) => void;
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

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] px-3 py-2">
        <p className="text-xs text-[var(--tc-text-muted)]">
          可逐条审核，也可一键按合并更新采纳全部待处理候选；已废弃项保持不变。
        </p>
        <Button
          type="button"
          size="sm"
          disabled={actionBusyKey !== ""}
          onClick={onAcceptRun}
        >
          <Check className="size-4" />
          {actionBusyKey === "accept-run" ? "正在采纳..." : "采纳本次沉淀"}
        </Button>
      </div>

      {candidates.length === 0 ? (
        <EmptyPanel text="当前筛选下暂无候选。" />
      ) : null}

      <div className="grid gap-1">
        {candidates.map(candidate => {
          return (
            <button
              key={candidate.review_item_id}
              type="button"
              className="grid min-h-11 w-full grid-cols-[auto_minmax(96px,128px)_minmax(160px,1fr)_auto_auto] items-center gap-2 rounded-[var(--tc-radius-control)] px-3 py-2 text-left outline-none transition-colors hover:bg-[var(--tc-surface-muted)] hover:[&>svg]:text-[var(--tc-text-primary)]"
              onClick={() => onSelectCandidate(candidate.review_item_id)}
              aria-haspopup="dialog"
            >
              <Eye
                aria-hidden="true"
                className="size-4 shrink-0 text-[var(--tc-text-muted)]"
              />
              <span className="min-w-0 truncate text-sm font-semibold text-[var(--tc-text-primary)]">
                {candidate.display_title}
              </span>
              <span className="min-w-0 truncate text-xs text-[var(--tc-text-muted)]">
                {candidate.source_excerpt || candidate.suggested_action_label}
              </span>
              <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
                <CandidateTag>
                  {knowledgeTypeLabel[candidate.knowledge_type]}
                </CandidateTag>
                <CandidateTag>
                  {candidateActionLabel[candidate.candidate_action]}
                </CandidateTag>
                <CandidateTag>
                  {candidateStatusLabel[candidate.candidate_status]}
                </CandidateTag>
              </span>
              <span className="whitespace-nowrap text-xs text-[var(--tc-text-muted)]">
                {candidate.schema_validation.passed ? "校验通过" : "校验失败"}
              </span>
            </button>
          );
        })}
      </div>

      <CandidateReviewDialog
        open={dialogOpen}
        candidate={selectedCandidate}
        schema={selectedCandidateSchema}
        draft={selectedCandidateDraft}
        formErrors={selectedCandidateFormErrors}
        referenceOptions={referenceOptions}
        isEditing={
          Boolean(selectedCandidate) &&
          editingCandidateId === selectedCandidate?.review_item_id
        }
        targetCard={selectedTargetCard}
        targetCardError={selectedTargetCardError}
        mergeMode={selectedCandidateMergeMode}
        actionBusyKey={actionBusyKey}
        knowledgeTypeText={
          selectedCandidate
            ? knowledgeTypeLabel[selectedCandidate.knowledge_type]
            : "知识卡"
        }
        candidateActionText={
          selectedCandidate
            ? candidateActionLabel[selectedCandidate.candidate_action]
            : "候选"
        }
        onOpenChange={onDialogOpenChange}
        onMergeModeChange={onMergeModeChange}
        onDraftChange={onCandidateDraftChange}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        onAction={onAction}
      />
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
    ["境界候选数", run.metrics.realm_candidate_count],
    ["功法候选数", run.metrics.technique_candidate_count],
    ["地点候选数", run.metrics.location_candidate_count],
    ["势力候选数", run.metrics.faction_candidate_count],
    ["物品候选数", run.metrics.item_candidate_count],
    ["规则候选数", run.metrics.rule_candidate_count],
    ["事件候选数", run.metrics.event_candidate_count],
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
      {mentions.map((mention, index) => (
        <ReplayItem
          key={`${mention.mention_id}-${mention.knowledge_type}-${mention.segment_index}-${index}`}
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
      {groups.map((group, index) => (
        <ReplayItem
          key={`${group.entity_group_id}-${group.knowledge_type}-${group.canonical_name}-${index}`}
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

function buildRunLLMTrace(run: AgentRun): string {
  const nodeByName = new Map(run.nodes.map(node => [node.node_name, node]));
  const scopeLine =
    run.scope.scope_type === "chapter_batch"
      ? `- 任务范围：批量 ${run.total_chapter_count} 章（完成 ${run.completed_chapter_count}，失败 ${run.failed_chapter_count}）`
      : run.scope.scope_type === "summary_repair"
        ? `- 任务范围：历史摘要修复（${run.metrics.candidate_total} 个候选）`
      : `- 章节：${run.scope.chapter_title || "未命名章节"}（${run.scope.chapter_id}）`;
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
    scopeLine,
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
        `- 模型内部 ID：${call.model_id || "未记录"}`,
        `- 上游模型：${call.upstream_model || "未记录"}`,
        `- 传输协议：${call.wire_protocol || "未记录"}`,
        `- 输入 Token：${formatNullableNumber(call.input_tokens)}`,
        `- 缓存 Token：${formatNullableNumber(call.cached_input_tokens)}`,
        `- 输出 Token：${formatNullableNumber(call.output_tokens)}`,
        `- 推理 Token：${formatNullableNumber(call.reasoning_tokens)}`,
        `- 总 Token：${formatNullableNumber(call.total_tokens)}`,
        `- 费用：${formatCallCost(call)}`,
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

function CandidateTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-[var(--tc-radius-badge)] border border-[var(--tc-border-subtle)] px-1.5 py-0.5 text-xs leading-4 text-[var(--tc-text-secondary)]">
      {children}
    </span>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <p className="text-sm text-[var(--tc-text-muted)]">{text}</p>;
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

function pickNextPendingCandidateId(
  run: AgentRun,
  filter: CandidateStatusFilter,
  currentCandidateId: string,
): string {
  const candidates = filterCandidates(run.review_items, filter);
  const currentIndex = candidates.findIndex(
    candidate => candidate.review_item_id === currentCandidateId,
  );
  const orderedCandidates =
    currentIndex >= 0
      ? [
          ...candidates.slice(currentIndex + 1),
          ...candidates.slice(0, currentIndex),
        ]
      : candidates;
  return (
    orderedCandidates.find(candidate => candidate.candidate_status === "pending")
      ?.review_item_id ?? ""
  );
}

function omitRecordKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatNullable(value?: string | null): string {
  return value && value.trim() ? value : "未记录";
}

function formatNullableNumber(value?: number | null): string {
  return value == null ? "未返回" : value.toLocaleString("zh-CN");
}

function formatCallCost(call: AgentLLMCall): string {
  if (call.cost_kind === "unavailable" || call.cost_amount == null) {
    return "未配置价格";
  }
  const kind = call.cost_kind === "actual" ? "实际" : "预估";
  return `${kind} ${call.cost_amount} ${call.cost_currency}`;
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
