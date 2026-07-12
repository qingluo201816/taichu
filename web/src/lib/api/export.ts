import { apiRequest } from "@/lib/api-client";
import type { ExportBundleResponse } from "@/lib/types/export";

export async function buildExportBundle(): Promise<ExportBundleResponse> {
  return apiRequest<ExportBundleResponse>("/api/export/bundle");
}
