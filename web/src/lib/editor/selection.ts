import type { Editor } from "@tiptap/react";
import type { ChapterInfo } from "@/lib/types/chapters";

export type SelectionContext = {
  chapter_id: string;
  selected_text: string;
  surrounding_text: string;
  selection_range: {
    from: number;
    to: number;
  };
  source_ref: {
    source_type: "chapter";
    source_id: string;
    path: string;
    chapter_id: string;
    anchor_type: "paragraph";
    paragraph_start: number;
    char_start: number;
    char_end: number;
    excerpt: string;
    excerpt_hash: string;
    source_hash: string;
    created_at: string;
  };
};

export function captureSelectionContext(
  editor: Editor,
  chapter: ChapterInfo,
): SelectionContext | null {
  const { from, to, empty } = editor.state.selection;
  if (empty) {
    return null;
  }

  const doc = editor.state.doc;
  const selectedText = doc.textBetween(from, to, "\n").trim();
  if (!selectedText) {
    return null;
  }

  const fullText = doc.textBetween(0, doc.content.size, "\n");
  const before = doc.textBetween(0, from, "\n");
  const paragraphStart = before.split(/\n{2,}|\n/).length - 1;
  const paragraphText = before.split(/\n{2,}|\n/).at(-1) ?? "";
  const charStart = paragraphText.length;

  return {
    chapter_id: chapter.id,
    selected_text: selectedText,
    surrounding_text: doc
      .textBetween(Math.max(0, from - 80), Math.min(doc.content.size, to + 80), "\n")
      .trim(),
    selection_range: { from, to },
    source_ref: {
      source_type: "chapter",
      source_id: chapter.id,
      path: chapter.markdown_path,
      chapter_id: chapter.id,
      anchor_type: "paragraph",
      paragraph_start: Math.max(0, paragraphStart),
      char_start: charStart,
      char_end: charStart + selectedText.length,
      excerpt: selectedText,
      excerpt_hash: stableHash(selectedText),
      source_hash: stableHash(fullText),
      created_at: new Date().toISOString(),
    },
  };
}

function stableHash(input: string): string {
  let hash = 5381;
  for (let index = 0; index < input.length; index += 1) {
    hash = (hash * 33) ^ input.charCodeAt(index);
  }
  return `h${(hash >>> 0).toString(16)}`;
}
