import type { LLMCallRecord } from "@/lib/types/llm";
import type { WritingAIStreamEvent } from "@/lib/types/writing-ai";

export function appendWritingStreamText(
  current: string,
  event: WritingAIStreamEvent,
): string {
  return event.type === "text_delta" ? current + event.delta : current;
}

export function writingStreamFailure(event: WritingAIStreamEvent): string {
  return event.type === "run_failed" ? event.message : "";
}

export function monitoredCostLabel(
  call: Pick<LLMCallRecord, "cost_amount" | "cost_currency" | "cost_kind">,
): string {
  if (call.cost_kind === "unavailable" || call.cost_amount == null) {
    return "未配置价格";
  }
  return `${call.cost_amount} ${call.cost_currency}`;
}

export function monitoredStatusLabel(status: LLMCallRecord["status"]): string {
  if (status === "completed") return "成功";
  if (status === "failed") return "失败";
  return "运行中";
}
