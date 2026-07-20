const DEFAULT_IDEA_TITLE = "未命名灵感";
const IDEA_TITLE_PREVIEW_LENGTH = 28;

export function inboxIdeaDisplayTitle(item: {
  title?: string;
  content: string;
}): string {
  const title = item.title?.trim();
  if (title) {
    return title;
  }
  const contentPreview = item.content.trim().replace(/\s+/g, " ");
  if (!contentPreview) {
    return DEFAULT_IDEA_TITLE;
  }
  return contentPreview.length > IDEA_TITLE_PREVIEW_LENGTH
    ? `${contentPreview.slice(0, IDEA_TITLE_PREVIEW_LENGTH)}…`
    : contentPreview;
}
