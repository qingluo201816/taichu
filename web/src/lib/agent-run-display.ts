import type { AgentRunSummary } from "@/lib/types/agent-workbench";

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
