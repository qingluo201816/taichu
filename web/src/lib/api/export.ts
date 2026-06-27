import { apiRequest } from "@/lib/api-client";
import type {
  ExportBundleResponse,
  IndexBuildJobResponse,
} from "@/lib/types/export";

export async function buildExportBundle(): Promise<ExportBundleResponse> {
  return apiRequest<ExportBundleResponse>("/api/export/bundle");
}

export async function rebuildGeneratedProjection(): Promise<IndexBuildJobResponse> {
  return apiRequest<IndexBuildJobResponse>("/api/generated/rebuild", {
    method: "POST",
  });
}

export async function clearGeneratedProjection(): Promise<IndexBuildJobResponse> {
  return apiRequest<IndexBuildJobResponse>("/api/generated/clear", {
    method: "POST",
  });
}
