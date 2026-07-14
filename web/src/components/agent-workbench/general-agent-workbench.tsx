"use client";

import {
  AlertTriangle,
  Ban,
  Check,
  ChevronRight,
  CirclePause,
  Clipboard,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  AgentWorkbenchSwitcher,
  type WorkbenchAgent,
} from "@/components/agent-workbench/agent-workbench-switcher";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  cancelGeneralAgentRun,
  deleteGeneralAgentRun,
  getGeneralAgentRun,
  listGeneralAgentRuns,
  resumeGeneralAgentRun,
  startGeneralAgentRun,
} from "@/lib/api/general-agent";
import { listChapters } from "@/lib/api/chapters";
import {
  currentGeneralAgentNodes,
  generalCapabilityLabel,
  generalNodeStatusLabels,
  generalRunStatusLabels,
  isGeneralAgentRunActive,
} from "@/lib/general-agent-display";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  GeneralAgentNodeRun,
  GeneralAgentRun,
  GeneralAgentRunStatus,
  GeneralAgentRunSummary,
  GeneralAgentScopeType,
} from "@/lib/types/general-agent";
import { cn } from "@/lib/utils";

const scopeOptions: Array<{
  value: GeneralAgentScopeType;
  label: string;
}> = [
  { value: "none", label: "无需正文范围" },
  { value: "selection", label: "选区" },
  { value: "chapter", label: "单章" },
  { value: "range", label: "多章" },
  { value: "novel", label: "全文" },
];

export function GeneralAgentWorkbench({
  onAgentChange,
}: {
  onAgentChange: (agent: WorkbenchAgent) => void;
}) {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [runs, setRuns] = useState<GeneralAgentRunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<GeneralAgentRun | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [goal, setGoal] = useState("");
  const [scopeType, setScopeType] = useState<GeneralAgentScopeType>("none");
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([]);
  const [selectionText, setSelectionText] = useState("");
  const [directContext, setDirectContext] = useState("");
  const [constraintsText, setConstraintsText] = useState("");
  const [externalAccessAllowed, setExternalAccessAllowed] = useState(false);
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [secondConfirmation, setSecondConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const reloadRuns = useCallback(async (preferredRunId = "") => {
    const response = await listGeneralAgentRuns();
    setRuns(response.runs);
    const runId = preferredRunId || response.runs[0]?.run_id || "";
    if (!runId) {
      return;
    }
    setSelectedRunId(runId);
    const detail = await getGeneralAgentRun(runId);
    setCurrentRun(detail.run);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [chapterResponse] = await Promise.all([
          listChapters(),
          reloadRuns(),
        ]);
        if (!cancelled) {
          setChapters(chapterResponse.chapters);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(errorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadRuns]);

  useEffect(() => {
    if (!currentRun || !isGeneralAgentRunActive(currentRun.status)) {
      return;
    }
    const runId = currentRun.run_id;
    const timer = window.setInterval(() => {
      void getGeneralAgentRun(runId)
        .then(response => {
          setCurrentRun(response.run);
          if (!isGeneralAgentRunActive(response.run.status)) {
            void reloadRuns(runId);
          }
        })
        .catch(pollError => setError(errorMessage(pollError)));
    }, 900);
    return () => window.clearInterval(timer);
  }, [currentRun, reloadRuns]);

  const currentNodes = useMemo(
    () => (currentRun ? currentGeneralAgentNodes(currentRun) : []),
    [currentRun],
  );

  async function handleStart() {
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) {
      setError("请先输入你希望通用写作助手完成的任务。");
      return;
    }
    if (scopeType === "selection" && !selectionText.trim()) {
      setError("选择“选区”范围时，请粘贴需要处理的正文。");
      return;
    }
    if (
      (scopeType === "chapter" || scopeType === "range") &&
      selectedChapterIds.length === 0
    ) {
      setError("请选择至少一个章节。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await startGeneralAgentRun({
        user_goal: trimmedGoal,
        scope: {
          scope_type: scopeType,
          current_chapter_id: selectedChapterIds[0] ?? null,
          chapter_ids:
            scopeType === "novel"
              ? chapters.map(chapter => chapter.id)
              : selectedChapterIds,
          selection_text: scopeType === "selection" ? selectionText.trim() : "",
          direct_context: directContext.trim(),
        },
        author_constraints: constraintsText
          .split("\n")
          .map(item => item.trim())
          .filter(Boolean),
        external_access_allowed: externalAccessAllowed,
      });
      setCurrentRun(response.run);
      setSelectedRunId(response.run.run_id);
      setClarificationAnswer("");
      setSecondConfirmation(false);
      await reloadRuns(response.run.run_id);
    } catch (startError) {
      setError(errorMessage(startError));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenRun(runId: string) {
    setSelectedRunId(runId);
    setError("");
    try {
      const response = await getGeneralAgentRun(runId);
      setCurrentRun(response.run);
    } catch (openError) {
      setError(errorMessage(openError));
    }
  }

  async function handleDeleteRun(run: GeneralAgentRunSummary) {
    if (!window.confirm(`确认删除任务“${shortText(run.user_goal, 28)}”的运行记录吗？`)) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await deleteGeneralAgentRun(run.run_id);
      if (selectedRunId === run.run_id) {
        setCurrentRun(null);
        setSelectedRunId("");
      }
      await reloadRuns();
    } catch (deleteError) {
      setError(errorMessage(deleteError));
    } finally {
      setBusy(false);
    }
  }

  async function handleResume(request: {
    answer?: string;
    approve?: boolean;
    second_confirmation?: boolean;
  }) {
    if (!currentRun) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await resumeGeneralAgentRun(currentRun.run_id, request);
      setCurrentRun(response.run);
      setClarificationAnswer("");
      setSecondConfirmation(false);
      await reloadRuns(response.run.run_id);
    } catch (resumeError) {
      setError(errorMessage(resumeError));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!currentRun) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await cancelGeneralAgentRun(currentRun.run_id);
      setCurrentRun(response.run);
      await reloadRuns(response.run.run_id);
    } catch (cancelError) {
      setError(errorMessage(cancelError));
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    if (!currentRun?.final_answer) {
      return;
    }
    try {
      await navigator.clipboard.writeText(currentRun.final_answer);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("复制失败，请手动选择结果文本。");
    }
  }

  return (
    <AppShell activePath="/agent-workbench">
      <section className="mx-auto grid max-w-[1440px] gap-4 px-4 py-4 xl:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="min-w-0 overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-2">
          <AgentWorkbenchSwitcher
            activeAgent="general"
            onAgentChange={onAgentChange}
          />

          <div className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3">
            <div className="mb-2 flex items-center justify-between gap-2 px-2">
              <h2 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                最近任务
              </h2>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="刷新最近任务"
                onClick={() => void reloadRuns(selectedRunId)}
              >
                <RefreshCw className="size-4" />
              </Button>
            </div>
            <GeneralRunList
              runs={runs}
              selectedRunId={selectedRunId}
              busy={busy}
              onOpen={runId => void handleOpenRun(runId)}
              onDelete={run => void handleDeleteRun(run)}
            />
          </div>
        </aside>

        <section className="min-w-0">
          <header className="flex items-start justify-between gap-4 border-b border-[var(--tc-border-subtle)] pb-4">
            <div>
              <p className="text-xs text-[var(--tc-text-muted)]">通用写作助手</p>
              <h2 className="mt-1 text-xl font-semibold text-[var(--tc-text-primary)]">
                处理任意规模的小说写作问题
              </h2>
              <p className="mt-1 max-w-[720px] text-sm text-[var(--tc-text-secondary)]">
                小问题直接收敛，复杂任务会按需调用工具和专业智能体；持久化修改始终等待你的授权。
              </p>
            </div>
            {currentRun && isGeneralAgentRunActive(currentRun.status) ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => void handleCancel()}
              >
                <Square className="size-3.5" />
                取消任务
              </Button>
            ) : null}
          </header>

          {error ? (
            <div className="mt-4 flex items-start gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)]">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          <section className="mt-4">
            <label
              htmlFor="general-agent-goal"
              className="text-sm font-semibold text-[var(--tc-text-primary)]"
            >
              你想完成什么
            </label>
            <textarea
              id="general-agent-goal"
              value={goal}
              onChange={event => {
                setGoal(event.target.value);
                if (error) {
                  setError("");
                }
              }}
              rows={4}
              placeholder="例如：主角第一次见到青铜令牌时发生了什么？或规划并续写接下来三章，再检查人物与时间线一致性。"
              className="mt-2 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]"
            />

            <details className="mt-3 border-t border-[var(--tc-border-subtle)] pt-3">
              <summary className="cursor-pointer text-sm font-medium text-[var(--tc-text-secondary)]">
                添加正文范围和约束
              </summary>
              <div className="mt-3 grid gap-4">
                <div>
                  <p className="text-xs text-[var(--tc-text-muted)]">正文范围</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {scopeOptions.map(option => (
                      <Button
                        key={option.value}
                        type="button"
                        variant={scopeType === option.value ? "default" : "outline"}
                        size="sm"
                        aria-pressed={scopeType === option.value}
                        onClick={() => {
                          setScopeType(option.value);
                          if (option.value === "none" || option.value === "novel") {
                            setSelectedChapterIds([]);
                          }
                        }}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>

                {scopeType === "selection" ? (
                  <textarea
                    value={selectionText}
                    onChange={event => setSelectionText(event.target.value)}
                    rows={5}
                    placeholder="粘贴需要处理的正文选区"
                    className="w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]"
                  />
                ) : null}

                {scopeType === "chapter" ? (
                  <label className="grid gap-1 text-xs text-[var(--tc-text-muted)]">
                    当前章节
                    <select
                      value={selectedChapterIds[0] ?? ""}
                      onChange={event =>
                        setSelectedChapterIds(
                          event.target.value ? [event.target.value] : [],
                        )
                      }
                      className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-2 text-sm text-[var(--tc-text-primary)] outline-none focus:border-[var(--tc-border-strong)]"
                    >
                      <option value="">请选择章节</option>
                      {chapters.map(chapter => (
                        <option key={chapter.id} value={chapter.id}>
                          {chapter.title}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                {scopeType === "range" ? (
                  <div className="max-h-44 overflow-y-auto border-y border-[var(--tc-border-subtle)]">
                    {chapters.map(chapter => {
                      const checked = selectedChapterIds.includes(chapter.id);
                      return (
                        <label
                          key={chapter.id}
                          className="flex cursor-pointer items-center gap-2 border-b border-[var(--tc-border-subtle)] px-2 py-2 text-sm text-[var(--tc-text-secondary)] last:border-b-0"
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={value =>
                              setSelectedChapterIds(current =>
                                value
                                  ? [...current, chapter.id]
                                  : current.filter(item => item !== chapter.id),
                              )
                            }
                          />
                          <span>{chapter.title}</span>
                          <span className="ml-auto text-xs text-[var(--tc-text-muted)]">
                            {chapter.word_count.toLocaleString("zh-CN")} 字
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                <div className="grid gap-3 xl:grid-cols-2">
                  <label className="grid gap-1 text-xs text-[var(--tc-text-muted)]">
                    补充上下文
                    <textarea
                      value={directContext}
                      onChange={event => setDirectContext(event.target.value)}
                      rows={3}
                      placeholder="可选：补充这次任务必须知道的信息"
                      className="resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]"
                    />
                  </label>
                  <label className="grid gap-1 text-xs text-[var(--tc-text-muted)]">
                    作者约束（每行一条）
                    <textarea
                      value={constraintsText}
                      onChange={event => setConstraintsText(event.target.value)}
                      rows={3}
                      placeholder="例如：不新增境界设定"
                      className="resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]"
                    />
                  </label>
                </div>

                <label className="flex items-start gap-2 text-sm text-[var(--tc-text-secondary)]">
                  <Checkbox
                    checked={externalAccessAllowed}
                    onCheckedChange={setExternalAccessAllowed}
                  />
                  <span>
                    允许本次任务研究外部资料
                    <span className="mt-0.5 block text-xs text-[var(--tc-text-muted)]">
                      默认关闭；小说内部事实问答不需要启用。
                    </span>
                  </span>
                </label>
              </div>
            </details>

            <div className="mt-3 flex items-center justify-between gap-3 border-t border-[var(--tc-border-subtle)] pt-3">
              <p className="text-xs text-[var(--tc-text-muted)]">
                助手会选择最小充分路径，不会强迫简单问题进入长流程。
              </p>
              <Button
                type="button"
                size="lg"
                disabled={busy || loading}
                onClick={() => void handleStart()}
              >
                {busy ? (
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Play className="size-4" />
                )}
                开始任务
              </Button>
            </div>
          </section>

          {currentRun ? (
            <GeneralRunPanel
              run={currentRun}
              nodes={currentNodes}
              busy={busy}
              clarificationAnswer={clarificationAnswer}
              secondConfirmation={secondConfirmation}
              copied={copied}
              onClarificationAnswerChange={setClarificationAnswer}
              onSecondConfirmationChange={setSecondConfirmation}
              onResume={request => void handleResume(request)}
              onCopy={() => void handleCopy()}
            />
          ) : (
            <div className="mt-8 border-t border-[var(--tc-border-subtle)] pt-6 text-sm text-[var(--tc-text-muted)]">
              输入问题后开始；运行结果、澄清请求和写入授权会显示在这里。
            </div>
          )}
        </section>
      </section>
    </AppShell>
  );
}

function GeneralRunList({
  runs,
  selectedRunId,
  busy,
  onOpen,
  onDelete,
}: {
  runs: GeneralAgentRunSummary[];
  selectedRunId: string;
  busy: boolean;
  onOpen: (runId: string) => void;
  onDelete: (run: GeneralAgentRunSummary) => void;
}) {
  if (runs.length === 0) {
    return <p className="px-2 py-3 text-xs text-[var(--tc-text-muted)]">暂无任务</p>;
  }
  return (
    <div className="grid gap-1">
      {runs.map(run => (
        <div
          key={run.run_id}
          className={cn(
            "group grid grid-cols-[minmax(0,1fr)_28px] items-center rounded-[var(--tc-radius-control)]",
            selectedRunId === run.run_id
              ? "bg-[var(--tc-surface-muted)]"
              : "hover:bg-[var(--tc-surface-muted)]",
          )}
        >
          <button
            type="button"
            className="min-w-0 px-2 py-2 text-left"
            onClick={() => onOpen(run.run_id)}
          >
            <span className="block truncate text-sm text-[var(--tc-text-primary)]">
              {run.user_goal}
            </span>
            <span className="mt-0.5 flex items-center gap-2 text-xs text-[var(--tc-text-muted)]">
              <span>{generalRunStatusLabels[run.status]}</span>
              <span>{formatTime(run.updated_at)}</span>
            </span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="删除任务记录"
            disabled={busy || isGeneralAgentRunActive(run.status)}
            onClick={() => onDelete(run)}
            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      ))}
    </div>
  );
}

function GeneralRunPanel({
  run,
  nodes,
  busy,
  clarificationAnswer,
  secondConfirmation,
  copied,
  onClarificationAnswerChange,
  onSecondConfirmationChange,
  onResume,
  onCopy,
}: {
  run: GeneralAgentRun;
  nodes: GeneralAgentNodeRun[];
  busy: boolean;
  clarificationAnswer: string;
  secondConfirmation: boolean;
  copied: boolean;
  onClarificationAnswerChange: (value: string) => void;
  onSecondConfirmationChange: (value: boolean) => void;
  onResume: (request: {
    answer?: string;
    approve?: boolean;
    second_confirmation?: boolean;
  }) => void;
  onCopy: () => void;
}) {
  const request = run.pending_human_request;
  const completedNodes = nodes.filter(node => node.status === "success").length;
  return (
    <section className="mt-8 border-t border-[var(--tc-border-subtle)] pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <RunStatusIcon status={run.status} />
            <h3 className="text-base font-semibold text-[var(--tc-text-primary)]">
              {generalRunStatusLabels[run.status]}
            </h3>
          </div>
          <p className="mt-1 text-xs text-[var(--tc-text-muted)]">
            计划修订 {run.plan_revision} · 已完成 {completedNodes}/{nodes.length} 个能力节点 · 检查点 {run.checkpoint_revision}
          </p>
        </div>
        <span className="font-mono text-xs text-[var(--tc-text-muted)]">
          {formatTime(run.updated_at)}
        </span>
      </div>

      {request?.kind === "clarification" ? (
        <div className="mt-4 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
          <div className="flex items-start gap-2">
            <CirclePause className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                需要你补充一个信息
              </h4>
              <p className="mt-1 text-sm leading-6 text-[var(--tc-text-secondary)]">
                {request.prompt}
              </p>
              <textarea
                value={clarificationAnswer}
                onChange={event => onClarificationAnswerChange(event.target.value)}
                rows={3}
                placeholder="输入你的回答"
                className="mt-3 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-3 py-2 text-sm text-[var(--tc-text-primary)] outline-none placeholder:text-[var(--tc-text-muted)] focus:border-[var(--tc-border-strong)]"
              />
              <div className="mt-3 flex justify-end">
                <Button
                  type="button"
                  disabled={busy || !clarificationAnswer.trim()}
                  onClick={() => onResume({ answer: clarificationAnswer.trim() })}
                >
                  <RotateCcw className="size-4" />
                  补充并继续
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {request?.kind === "write_authorization" ? (
        <div className="mt-4 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-[var(--tc-text-primary)]">
                等待写入授权
              </h4>
              <p className="mt-1 text-sm leading-6 text-[var(--tc-text-secondary)]">
                {request.prompt}
              </p>
              <div className="mt-3 grid gap-2 text-xs text-[var(--tc-text-muted)]">
                <p>
                  操作：{generalCapabilityLabel(request.tool_name ?? "")}
                </p>
                <p>
                  作用范围：
                  {request.resource_scopes.map(formatResourceScope).join("、") ||
                    "未标明"}
                </p>
                <p className="break-all font-mono">输入哈希：{request.input_sha256}</p>
              </div>
              <details className="mt-3 border-t border-[var(--tc-border-subtle)] pt-2">
                <summary className="cursor-pointer text-xs text-[var(--tc-text-secondary)]">
                  查看确定输入（技术字段）
                </summary>
                <p className="mt-2 text-xs text-white/45">
                  以下为授权绑定的技术输入，字段名称以接口契约为准。
                </p>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-[var(--tc-radius-control)] bg-[var(--tc-surface-muted)] p-3 font-mono text-xs leading-5 text-[var(--tc-text-secondary)]">
                  {JSON.stringify(request.input_summary, null, 2)}
                </pre>
              </details>
              {request.second_confirmation_required ? (
                <label className="mt-3 flex items-center gap-2 text-sm text-[var(--tc-text-secondary)]">
                  <Checkbox
                    checked={secondConfirmation}
                    onCheckedChange={onSecondConfirmationChange}
                  />
                  我已再次确认这是高风险写入
                </label>
              ) : null}
              <div className="mt-3 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => onResume({ approve: false })}
                >
                  <Ban className="size-4" />
                  拒绝写入
                </Button>
                <Button
                  type="button"
                  disabled={
                    busy ||
                    (request.second_confirmation_required && !secondConfirmation)
                  }
                  onClick={() =>
                    onResume({
                      approve: true,
                      second_confirmation: secondConfirmation,
                    })
                  }
                >
                  <Check className="size-4" />
                  授权并继续
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {run.final_answer ? (
        <div className="mt-4 rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-card)] p-4">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-sm font-semibold text-[var(--tc-text-primary)]">
              助手结果
            </h4>
            <Button type="button" variant="ghost" size="sm" onClick={onCopy}>
              {copied ? <Check className="size-3.5" /> : <Clipboard className="size-3.5" />}
              {copied ? "已复制" : "复制"}
            </Button>
          </div>
          <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[var(--tc-text-primary)]">
            {run.final_answer}
          </div>
          {run.verification_issues.length ? (
            <div className="mt-3 border-t border-[var(--tc-border-subtle)] pt-3 text-xs text-[var(--tc-text-muted)]">
              未完全解决：{run.verification_issues.join("；")}
            </div>
          ) : null}
        </div>
      ) : null}

      <details className="mt-4 border-t border-[var(--tc-border-subtle)] pt-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--tc-text-secondary)]">
          查看计划与能力进度
        </summary>
        {run.plan ? (
          <div className="mt-3">
            <p className="text-xs leading-5 text-[var(--tc-text-muted)]">
              {run.plan.rationale}
            </p>
            <div className="mt-2 divide-y divide-[var(--tc-border-subtle)] border-y border-[var(--tc-border-subtle)]">
              {nodes.length ? (
                nodes.map(node => <GeneralNodeRow key={node.node_id} node={node} />)
              ) : (
                <p className="px-2 py-3 text-sm text-[var(--tc-text-muted)]">
                  本次任务无需调用额外能力。
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-[var(--tc-text-muted)]">计划尚未生成。</p>
        )}
      </details>

      {run.errors.length ? (
        <details className="mt-3 border-t border-[var(--tc-border-subtle)] pt-3">
          <summary className="cursor-pointer text-sm text-[var(--tc-text-secondary)]">
            查看运行错误
          </summary>
          <ul className="mt-2 grid gap-1 text-xs text-[var(--tc-text-muted)]">
            {run.errors.map((item, index) => (
              <li key={`${index}-${item}`}>{item}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function GeneralNodeRow({ node }: { node: GeneralAgentNodeRun }) {
  return (
    <div className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-start gap-2 px-2 py-2.5">
      <ChevronRight className="mt-0.5 size-4 text-[var(--tc-text-muted)]" />
      <div className="min-w-0">
        <p className="text-sm font-medium text-[var(--tc-text-primary)]">
          {generalCapabilityLabel(node.capability_name)}
        </p>
        <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-[var(--tc-text-muted)]">
          {node.objective}
        </p>
        {node.error_message ? (
          <p className="mt-1 text-xs text-[var(--tc-text-secondary)]">
            {node.error_message}
          </p>
        ) : null}
      </div>
      <span className="whitespace-nowrap text-xs text-[var(--tc-text-muted)]">
        {generalNodeStatusLabels[node.status]}
      </span>
    </div>
  );
}

function RunStatusIcon({ status }: { status: GeneralAgentRunStatus }) {
  if (isGeneralAgentRunActive(status)) {
    return (
      <LoaderCircle className="size-4 animate-spin text-[var(--tc-text-secondary)] motion-reduce:animate-none" />
    );
  }
  if (status === "waiting_human") {
    return <CirclePause className="size-4 text-[var(--tc-text-secondary)]" />;
  }
  if (status === "completed") {
    return <Check className="size-4 text-[var(--tc-text-secondary)]" />;
  }
  if (status === "cancelled") {
    return <Ban className="size-4 text-[var(--tc-text-secondary)]" />;
  }
  return <AlertTriangle className="size-4 text-[var(--tc-text-secondary)]" />;
}

function formatResourceScope(scope: string): string {
  const [prefix, ...rest] = scope.split(":");
  const value = rest.join(":");
  const labels: Record<string, string> = {
    chapter_id: "章节",
    chapter_ids: "章节",
    card_id: "知识卡",
    card_ids: "知识卡",
    volume_id: "分卷",
    parent_id: "上级结构",
    item_ids: "结构项",
  };
  if (prefix === "tool") {
    return `操作：${generalCapabilityLabel(value)}`;
  }
  return labels[prefix] ? `${labels[prefix]}：${value}` : `资源：${scope}`;
}

function shortText(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间未知";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : "通用写作助手请求失败。";
}
