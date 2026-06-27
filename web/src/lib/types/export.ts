export type ExportFileInfo = {
  path: string;
  media_type: string;
  content: string;
};

export type ExportBundleResponse = {
  id: string;
  schema_version: string;
  created_at: string;
  files: ExportFileInfo[];
};

export type IndexBuildJobInfo = {
  id: string;
  action: "clear" | "rebuild";
  status: "completed" | "failed";
  generated_path: string;
  created_at: string;
  completed_at: string;
  message: string;
};

export type IndexBuildJobResponse = {
  job: IndexBuildJobInfo;
};
