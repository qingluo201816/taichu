export type VectorGraphIndexState =
  | "not_built"
  | "building"
  | "ready"
  | "stale"
  | "incomplete"
  | "failed"
  | "unavailable";

export type VectorGraphBuildStage =
  | "planning"
  | "extracting"
  | "indexing"
  | "completed"
  | "failed";

export interface VectorGraphBuildPlan {
  snapshot_sha256: string;
  manuscript_count: number;
  manuscript_chunk_count: number;
  knowledge_card_count: number;
  document_count: number;
  total_content_chars: number;
}

export interface VectorGraphBuildProgress {
  stage: VectorGraphBuildStage;
  snapshot_sha256: string;
  processed_documents: number;
  total_documents: number;
  processed_sources: number;
  total_sources: number;
  current_source_key: string | null;
  started_at: string;
  updated_at: string;
  error_message: string | null;
}

export interface VectorGraphBuildResult {
  status: string;
  plan: VectorGraphBuildPlan;
  entity_count: number;
  relation_count: number;
  passage_count: number;
  updated_source_count: number;
  deleted_source_count: number;
  unchanged_source_count: number;
}

export interface VectorGraphCollectionStatus {
  role: string;
  name: string;
  exists: boolean;
  row_count: number | null;
}

export interface VectorGraphIndexStatus {
  state: VectorGraphIndexState;
  current_plan: VectorGraphBuildPlan;
  progress: VectorGraphBuildProgress | null;
  active_build: VectorGraphBuildResult | null;
  is_current: boolean;
  collections: VectorGraphCollectionStatus[];
  message: string;
}

export interface VectorGraphUpdateStartResult {
  accepted: boolean;
  message: string;
  plan: VectorGraphBuildPlan;
}
