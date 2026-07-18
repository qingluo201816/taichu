import type {
  RetrievalAtKMetric,
  RetrievalEvaluationCategory,
  RetrievalEvaluationRecord,
  RetrievalEvaluationSummary,
} from "@/lib/types/retrieval-evaluation";

export const retrievalEvaluationCategoryLabels: Record<
  RetrievalEvaluationCategory,
  string
> = {
  exact_name_alias: "精确名称与别名",
  semantic_paraphrase: "语义改写与隐含表达",
  state_relation_event_rule: "状态、关系、事件与规则",
  multi_entity_disambiguation: "多实体消歧",
  no_answer_adversarial: "无答案与对抗查询",
};

export const retrievalKnowledgeTypeLabels: Record<string, string> = {
  character: "人物",
  realm: "境界",
  technique: "功法",
  location: "地点",
  faction: "势力",
  item: "物品",
  rule: "规则",
  event: "事件",
};

export function metricAtK(
  summary: RetrievalEvaluationSummary | null | undefined,
  k: 1 | 3 | 5 | 10,
): RetrievalAtKMetric | null {
  return summary?.at_k.find(item => item.k === k) ?? null;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function retrievalCaseOutcome(
  caseId: string,
  evaluation: RetrievalEvaluationRecord | null,
): "通过" | "未通过" | "未评测" {
  if (!evaluation?.cases.some(item => item.case_id === caseId)) return "未评测";
  return evaluation.failures.some(item => item.case_id === caseId)
    ? "未通过"
    : "通过";
}

export function retrievalStrategyLabel(strategy: string): string {
  if (strategy === "mongo_lexical") return "MongoDB 词法召回";
  return `实验策略（${strategy}）`;
}
