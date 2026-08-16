import type { AgentRun, AgentRunSummary } from "@/lib/types/agent-workbench";

type BatchRunScope = Pick<
  AgentRunSummary,
  "chapter_ids" | "chapter_titles" | "total_chapter_count"
>;

const CHAPTER_TITLE_NUMBER_PATTERN = /第\s*([〇零一二三四五六七八九十百千万两0-9]+)\s*章/;
const CHAPTER_ID_NUMBER_PATTERN = /(?:chapter|章节)[-_]?(\d+)/i;

/**
 * 用紧凑、可读的章节编号概述批量任务，避免把内部 ID 或冗长章节标题直接放进列表。
 */
export function formatBatchRunTitle(scope: BatchRunScope): string {
  const chapterNumbers = scope.chapter_titles
    .map(extractChapterNumber)
    .filter((chapterNumber): chapterNumber is string => Boolean(chapterNumber));
  const fallbackNumbers = scope.chapter_ids
    .map(extractChapterNumber)
    .filter((chapterNumber): chapterNumber is string => Boolean(chapterNumber));
  const labels = chapterNumbers.length > 0 ? chapterNumbers : fallbackNumbers;

  if (labels.length > 0) {
    return `批量任务：第${labels.join("、")}章`;
  }

  const chapterCount = scope.total_chapter_count || scope.chapter_ids.length;
  return `批量任务：${chapterCount}章`;
}

type FailureDisplayRun = Pick<
  AgentRun,
  | "status"
  | "failed_chapter_count"
  | "model_display_name"
  | "model_name"
  | "batch_chapter_progress"
  | "nodes"
  | "llm_calls"
  | "errors"
>;

/**
 * 把运行轨迹中的底层错误整理成可直接处理的中文提示。
 */
export function formatAgentRunFailure(run: FailureDisplayRun): string | null {
  if (run.status !== "failed" && run.failed_chapter_count === 0) {
    return null;
  }

  const errors = [
    ...run.batch_chapter_progress.map(item => item.error),
    ...run.nodes.map(node => node.error),
    ...run.llm_calls.map(call => call.error),
    ...run.errors,
  ].filter((error): error is string => Boolean(error?.trim()));
  const permissionError = errors.find(error => error.includes("无权调用该模型"));

  if (permissionError) {
    const modelName = run.model_display_name || run.model_name || "当前模型";
    return `模型调用失败：${modelName} 无调用权限。请检查当前密钥权限，或更换可用模型后重新运行。`;
  }

  const firstError = errors[0]?.trim();
  return firstError
    ? `任务失败：${firstError}`
    : "任务运行失败，请查看红色节点中的具体原因后重新运行。";
}

function extractChapterNumber(value: string): string | null {
  const titleMatch = value.match(CHAPTER_TITLE_NUMBER_PATTERN);
  if (titleMatch?.[1]) {
    return titleMatch[1];
  }

  const idMatch = value.match(CHAPTER_ID_NUMBER_PATTERN);
  if (!idMatch?.[1]) {
    return null;
  }

  return String(Number(idMatch[1]));
}
