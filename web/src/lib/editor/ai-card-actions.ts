import type { AIResultCard } from "@/lib/types/ai-cards";

export type TextCandidatePlacement =
  | "insert_cursor"
  | "replace_selection"
  | "append_after_selection";

export type TextEditOperation = {
  from: number;
  to: number;
  text: string;
};

export function textCandidateContent(card: AIResultCard): string {
  if (typeof card.content === "string") {
    return card.content;
  }
  const text = card.content.text;
  return typeof text === "string" ? text : "";
}

export function buildTextCandidateEdit({
  card,
  placement,
  cursorPosition,
}: {
  card: AIResultCard;
  placement: TextCandidatePlacement;
  cursorPosition: number;
}): TextEditOperation {
  const text = textCandidateContent(card);
  const selectionRange = card.input_context.selection_range as
    | { from?: unknown; to?: unknown }
    | undefined;
  const from = numberOrFallback(selectionRange?.from, cursorPosition);
  const to = numberOrFallback(selectionRange?.to, from);

  if (placement === "replace_selection") {
    return { from, to, text };
  }
  if (placement === "append_after_selection") {
    return { from: to, to, text: `\n\n${text}` };
  }
  return { from: cursorPosition, to: cursorPosition, text };
}

function numberOrFallback(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
