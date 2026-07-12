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
