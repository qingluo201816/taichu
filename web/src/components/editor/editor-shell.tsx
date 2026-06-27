"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Check,
  ChevronLeft,
  FileText,
  Heading1,
  Heading2,
  Italic,
  Loader2,
  MessageSquare,
  Pilcrow,
  Quote,
  Save,
  Scissors,
  SeparatorHorizontal,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { listChapters, readChapter, saveChapter } from "@/lib/api/chapters";
import {
  markdownToTiptapContent,
  tiptapContentToMarkdown,
} from "@/lib/editor/markdown";
import {
  captureSelectionContext,
  type SelectionContext,
} from "@/lib/editor/selection";
import type { ChapterInfo } from "@/lib/types/chapters";
import { cn } from "@/lib/utils";

type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

export default function EditorShell() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [activeChapter, setActiveChapter] = useState<ChapterInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [selection, setSelection] = useState<SelectionContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const saveSequence = useRef(0);
  const activeChapterRef = useRef<ChapterInfo | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
    ],
    editorProps: {
      attributes: {
        class:
          "taichu-editor min-h-[calc(100vh-12rem)] outline-none px-8 py-7 text-[17px] leading-8",
      },
    },
    content: markdownToTiptapContent(""),
    immediatelyRender: false,
    onUpdate: () => setSaveState("dirty"),
    onSelectionUpdate: ({ editor: nextEditor }) => {
      const chapter = activeChapterRef.current;
      setSelection(chapter ? captureSelectionContext(nextEditor, chapter) : null);
    },
  });

  const loadChapter = useCallback(
    async (chapterId: string) => {
      if (!editor) {
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const response = await readChapter(chapterId);
        activeChapterRef.current = response.chapter;
        setActiveChapter(response.chapter);
        editor.commands.setContent(markdownToTiptapContent(response.markdown));
        setSelection(null);
        setSaveState("saved");
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "章节加载失败");
        setSaveState("error");
      } finally {
        setLoading(false);
      }
    },
    [editor],
  );

  const persistChapter = useCallback(async () => {
    if (!editor || !activeChapterRef.current) {
      return;
    }
    const sequence = saveSequence.current + 1;
    saveSequence.current = sequence;
    setSaveState("saving");

    try {
      const markdown = tiptapContentToMarkdown(editor.getJSON());
      const response = await saveChapter(activeChapterRef.current.id, markdown);
      if (saveSequence.current !== sequence) {
        return;
      }
      activeChapterRef.current = response.chapter;
      setActiveChapter(response.chapter);
      setChapters(current =>
        current.map(chapter =>
          chapter.id === response.chapter.id ? response.chapter : chapter,
        ),
      );
      setSaveState("saved");
    } catch (saveError) {
      if (saveSequence.current === sequence) {
        setError(saveError instanceof Error ? saveError.message : "保存失败");
        setSaveState("error");
      }
    }
  }, [editor]);

  const switchChapter = useCallback(
    async (chapterId: string) => {
      if (activeChapterRef.current?.id === chapterId) {
        return;
      }
      if (saveState === "dirty") {
        await persistChapter();
      }
      await loadChapter(chapterId);
    },
    [loadChapter, persistChapter, saveState],
  );

  useEffect(() => {
    if (!editor) {
      return;
    }

    let cancelled = false;
    async function loadInitialData() {
      setLoading(true);
      setError(null);
      try {
        const response = await listChapters();
        if (cancelled) {
          return;
        }
        const sortedChapters = [...response.chapters].sort(
          (left, right) => left.order - right.order,
        );
        setChapters(sortedChapters);
        if (sortedChapters[0]) {
          await loadChapter(sortedChapters[0].id);
        } else {
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "章节加载失败");
          setLoading(false);
        }
      }
    }

    void loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [editor, loadChapter]);

  useEffect(() => {
    if (saveState !== "dirty") {
      return;
    }
    const timer = window.setTimeout(() => {
      void persistChapter();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [persistChapter, saveState]);

  return (
    <main className="min-h-screen bg-[#fffefc] text-black">
      <div className="grid min-h-screen grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="border-r-[3px] border-black bg-white px-4 py-5">
          <Link
            href="/"
            className="mb-6 inline-flex items-center gap-2 rounded-full border-2 border-black px-3 py-1.5 text-sm font-semibold hover:bg-gray-100"
          >
            <ChevronLeft className="size-4" />
            返回太初
          </Link>
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-600">
            <FileText className="size-4" />
            章节
          </div>
          <nav className="space-y-2">
            {chapters.map(chapter => (
              <button
                key={chapter.id}
                onClick={() => void switchChapter(chapter.id)}
                className={cn(
                  "w-full rounded-lg border-2 border-black px-3 py-2 text-left text-sm transition-colors",
                  activeChapter?.id === chapter.id
                    ? "bg-black text-white"
                    : "bg-white hover:bg-gray-100",
                )}
              >
                <span className="block truncate font-semibold">{chapter.title}</span>
                <span className="block text-xs opacity-70">
                  {chapter.word_count} 字
                </span>
              </button>
            ))}
            {!chapters.length && !loading ? (
              <div className="rounded-lg border-2 border-dashed border-black px-3 py-4 text-sm text-gray-600">
                暂无章节
              </div>
            ) : null}
          </nav>
        </aside>

        <section className="flex min-w-0 flex-col">
          <header className="flex h-16 items-center justify-between border-b-[3px] border-black bg-[#fffefc] px-5">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold">
                {activeChapter?.title ?? "编辑器"}
              </h1>
              <p className="text-xs font-semibold text-gray-500">
                {statusText(saveState, loading)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <ToolbarButton
                active={editor?.isActive("heading", { level: 1 }) ?? false}
                label="标题一"
                onClick={() =>
                  editor?.chain().focus().toggleHeading({ level: 1 }).run()
                }
              >
                <Heading1 className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                active={editor?.isActive("heading", { level: 2 }) ?? false}
                label="标题二"
                onClick={() =>
                  editor?.chain().focus().toggleHeading({ level: 2 }).run()
                }
              >
                <Heading2 className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                active={editor?.isActive("paragraph") ?? false}
                label="段落"
                onClick={() => editor?.chain().focus().setParagraph().run()}
              >
                <Pilcrow className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                active={editor?.isActive("bold") ?? false}
                label="粗体"
                onClick={() => editor?.chain().focus().toggleBold().run()}
              >
                <Bold className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                active={editor?.isActive("italic") ?? false}
                label="斜体"
                onClick={() => editor?.chain().focus().toggleItalic().run()}
              >
                <Italic className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                active={editor?.isActive("blockquote") ?? false}
                label="引用"
                onClick={() => editor?.chain().focus().toggleBlockquote().run()}
              >
                <Quote className="size-4" />
              </ToolbarButton>
              <ToolbarButton
                label="分割线"
                onClick={() => editor?.chain().focus().setHorizontalRule().run()}
              >
                <SeparatorHorizontal className="size-4" />
              </ToolbarButton>
              <Button
                size="sm"
                onClick={() => void persistChapter()}
                disabled={!activeChapter || saveState === "saving"}
                className="ml-2 rounded-full border-2 border-black"
              >
                {saveState === "saving" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : saveState === "saved" ? (
                  <Check className="size-4" />
                ) : (
                  <Save className="size-4" />
                )}
                保存
              </Button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-auto bg-[#fffefc]">
            {error ? (
              <div className="m-6 rounded-lg border-2 border-black bg-white px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}
            <EditorContent editor={editor} />
          </div>
        </section>

        <aside className="border-l-[3px] border-black bg-white px-4 py-5">
          <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-gray-600">
            <MessageSquare className="size-4" />
            AI 卡片
          </div>
          <div className="rounded-lg border-2 border-black px-4 py-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Scissors className="size-4" />
              当前选区
            </div>
            {selection ? (
              <div className="space-y-3 text-sm">
                <p className="max-h-28 overflow-auto rounded-md bg-gray-50 p-2 leading-6">
                  {selection.selected_text}
                </p>
                <dl className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                  <dt>段落</dt>
                  <dd>{selection.source_ref.paragraph_start}</dd>
                  <dt>起止</dt>
                  <dd>
                    {selection.source_ref.char_start}-
                    {selection.source_ref.char_end}
                  </dd>
                </dl>
              </div>
            ) : (
              <p className="text-sm text-gray-500">未选择正文</p>
            )}
          </div>
          <div className="mt-4 rounded-lg border-2 border-dashed border-black px-4 py-4 text-sm text-gray-500">
            Phase 3 接入
          </div>
          <pre className="mt-4 max-h-64 overflow-auto rounded-lg bg-gray-50 p-3 text-xs leading-5 text-gray-600">
            {selection ? JSON.stringify(selection, null, 2) : "{}"}
          </pre>
        </aside>
      </div>
    </main>
  );
}

function ToolbarButton({
  active = false,
  label,
  children,
  onClick,
}: {
  active?: boolean;
  label: string;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg border-2 border-black transition-colors",
        active ? "bg-black text-white" : "bg-white hover:bg-gray-100",
      )}
    >
      {children}
    </button>
  );
}

function statusText(saveState: SaveState, loading: boolean): string {
  if (loading) {
    return "加载中";
  }
  if (saveState === "dirty") {
    return "未保存";
  }
  if (saveState === "saving") {
    return "保存中";
  }
  if (saveState === "saved") {
    return "已保存";
  }
  if (saveState === "error") {
    return "保存失败";
  }
  return "就绪";
}
