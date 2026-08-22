import { apiRequest } from "@/lib/api-client";
import type {
  VectorGraphIndexStatus,
  VectorGraphUpdateStartResult,
} from "@/lib/types/vector-graph";

export function getVectorGraphStatus(): Promise<VectorGraphIndexStatus> {
  return apiRequest<VectorGraphIndexStatus>("/api/vector-graph/status");
}

export function startVectorGraphUpdate(): Promise<VectorGraphUpdateStartResult> {
  return apiRequest<VectorGraphUpdateStartResult>("/api/vector-graph/update", {
    method: "POST",
  });
}
