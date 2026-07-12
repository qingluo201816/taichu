"use client";

import { type FormEvent, useState } from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";

export function CompactPagination({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(totalPages, Math.max(1, page));
  const [jumpDraft, setJumpDraft] = useState({
    page: currentPage,
    value: String(currentPage),
  });
  const jumpValue =
    jumpDraft.page === currentPage ? jumpDraft.value : String(currentPage);

  function submitPageJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPage = Number(jumpValue);
    if (!jumpValue.trim() || !Number.isFinite(parsedPage)) {
      setJumpDraft({ page: currentPage, value: String(currentPage) });
      return;
    }
    const nextPage = Math.min(totalPages, Math.max(1, Math.trunc(parsedPage)));
    setJumpDraft({ page: nextPage, value: String(nextPage) });
    onPageChange(nextPage);
  }

  return (
    <div
      className={cn(
        "flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-[var(--tc-border-subtle)] pt-2 text-xs text-[var(--tc-text-muted)]",
        className,
      )}
    >
      <span>
        第 {currentPage} / {totalPages} 页，共 {total} 条
      </span>
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
        >
          上一页
        </Button>
        <form onSubmit={submitPageJump} className="flex items-center gap-1">
          <input
            value={jumpValue}
            onChange={event =>
              setJumpDraft({ page: currentPage, value: event.target.value })
            }
            className="h-8 w-12 rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] px-1 text-center text-xs text-[var(--tc-text-primary)] outline-none"
            aria-label="页码"
          />
          <Button type="submit" variant="outline" size="sm">
            跳转
          </Button>
        </form>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
