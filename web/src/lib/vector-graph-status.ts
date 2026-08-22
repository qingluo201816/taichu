import type {
  VectorGraphBuildStage,
  VectorGraphIndexState,
} from "@/lib/types/vector-graph";

export const vectorGraphStateLabels: Record<VectorGraphIndexState, string> = {
  not_built: "尚未建立索引",
  building: "正在同步索引",
  ready: "可以使用",
  stale: "需要更新",
  incomplete: "索引不完整",
  failed: "索引同步失败",
  unavailable: "服务不可用",
};

export const vectorGraphStageLabels: Record<VectorGraphBuildStage, string> = {
  planning: "整理索引来源",
  extracting: "抽取实体与关系",
  indexing: "写入 Milvus 索引",
  completed: "索引同步完成",
  failed: "索引同步失败",
};

export const vectorGraphCollectionLabels: Record<string, string> = {
  passages: "正文与知识卡片段",
  entities: "实体",
  relations: "关系",
};

export function vectorGraphProgressPercent(
  processed: number,
  total: number,
): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((processed / total) * 100)));
}
