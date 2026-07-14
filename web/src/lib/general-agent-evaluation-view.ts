import type {
  GeneralAgentEvaluationCase,
  GeneralAgentEvaluationRecord,
} from "@/lib/types/general-agent-evaluation";
import type { GeneralAgentRunSummary } from "@/lib/types/general-agent";

export const generalAgentEvaluationCategoryLabels: Record<
  GeneralAgentEvaluationCase["category"],
  string
> = {
  fact_qa: "事实问答",
  writing_advice: "写作建议",
  character_analysis: "人物分析",
  story_planning: "剧情规划",
  drafting: "正文创作",
  revision: "局部改写",
  consistency_review: "一致性审查",
  authorization_boundary: "授权边界",
};

export function matchingRunsForCase(
  runs: GeneralAgentRunSummary[],
  evaluationCase: GeneralAgentEvaluationCase,
): GeneralAgentRunSummary[] {
  const normalizedGoal = normalize(evaluationCase.user_goal);
  return runs.filter(run => normalize(run.user_goal) === normalizedGoal);
}

export function evaluationOutcomeLabel(
  evaluation: GeneralAgentEvaluationRecord,
): string {
  if (!evaluation.passed) return "未通过";
  if (evaluation.semantic_review_required) return "确定性检查通过，待语义复核";
  return "通过";
}

export function scoreLabel(score: number): string {
  return `${Math.round(score)} 分`;
}

function normalize(value: string): string {
  return value.replace(/\s+/g, "").toLocaleLowerCase("zh-CN");
}
