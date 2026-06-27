export type ChapterInfo = {
  id: string;
  volume_id: string | null;
  title: string;
  order: number;
  markdown_path: string;
  status: string;
  word_count: number;
  created_at: string;
  updated_at: string;
};

export type ChapterListResponse = {
  chapters: ChapterInfo[];
};

export type ChapterReadResponse = {
  chapter: ChapterInfo;
  markdown: string;
};
