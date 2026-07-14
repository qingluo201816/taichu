import type {
  GeneralAgentNodeRun,
  GeneralAgentNodeStatus,
  GeneralAgentRun,
  GeneralAgentRunStatus,
} from "@/lib/types/general-agent";

const activeStatuses = new Set<GeneralAgentRunStatus>([
  "init",
  "clarifying",
  "planning",
  "executing",
  "verifying",
  "replanning",
]);

export const generalRunStatusLabels: Record<GeneralAgentRunStatus, string> = {
  init: "正在初始化",
  clarifying: "正在判断信息缺口",
  planning: "正在规划",
  executing: "正在执行",
  waiting_human: "等待作者",
  verifying: "正在校验",
  replanning: "正在重新规划",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  timeout: "已超时",
};

export const generalNodeStatusLabels: Record<GeneralAgentNodeStatus, string> = {
  pending: "等待中",
  running: "执行中",
  success: "已完成",
  failed: "失败",
  skipped: "已跳过",
  waiting_human: "等待作者",
};

const capabilityLabels: Record<string, string> = {
  get_novel_structure: "读取小说结构",
  read_manuscript: "读取正文",
  search_manuscript: "搜索正文证据",
  retrieve_knowledge: "相关知识召回",
  resolve_knowledge_identity: "知识身份匹配",
  list_knowledge_catalog: "浏览知识目录",
  read_knowledge_cards: "读取知识卡",
  search_external_sources: "搜索外部资料",
  read_external_source: "读取外部来源",
  preview_manuscript_patch: "预览正文修改",
  apply_manuscript_patch: "写入正文修改",
  create_novel_structure_items: "创建卷章",
  update_novel_structure: "调整卷章结构",
  delete_novel_structure_items: "归档卷章",
  create_confirmed_knowledge: "创建确认知识",
  update_confirmed_knowledge: "更新确认知识",
  canon_evidence: "小说事实取证",
  external_research: "外部资料研究",
  narrative_summary: "叙事归纳",
  worldbuilding: "世界设定",
  character: "人物设计",
  story_architecture: "剧情架构",
  scene_planning: "场景规划",
  drafting: "正文创作",
  revision: "正文修改",
  consistency_reviewer: "一致性审查",
  narrative_reviewer: "叙事审查",
  style_reviewer: "文风审查",
  "general_writing_orchestrator.plan": "高层任务规划",
  "general_writing_orchestrator.verify": "执行结果校验",
};

export function isGeneralAgentRunActive(status: GeneralAgentRunStatus): boolean {
  return activeStatuses.has(status);
}

export function generalCapabilityLabel(name: string): string {
  return capabilityLabels[name] ?? "未识别能力";
}

export function currentGeneralAgentNodes(run: GeneralAgentRun): GeneralAgentNodeRun[] {
  return run.node_runs.filter(node => node.plan_revision === run.plan_revision);
}
