"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Pilcrow,
  Quote,
  Save,
  SeparatorHorizontal,
} from "lucide-react";
import Link from "next/link";

import { AICardList } from "@/components/ai-card/ai-card-list";
import { Button } from "@/components/ui/button";
import {
  applyAICardAction,
  createSelectionAICard,
  listAICards,
} from "@/lib/api/ai-cards";
import {
  listChapters,
  readChapter,
  saveChapter,
  summarizeChapter,
} from "@/lib/api/chapters";
import { convertAICardToPendingFact } from "@/lib/api/inbox";
import {
  buildTextCandidateEdit,
  textCandidateContent,
  type TextCandidatePlacement,
} from "@/lib/editor/ai-card-actions";
import {
  markdownToTiptapContent,
  tiptapContentToMarkdown,
} from "@/lib/editor/markdown";
import {
  ChapterSaveCoordinator,
  ChapterSaveFailedError,
  isBlockingSaveFailure,
  isDirtySaveSatisfied,
  shouldApplySaveOutcome,
} from "@/lib/editor/save-coordinator";
import {
  captureSelectionContext,
  type SelectionContext,
} from "@/lib/editor/selection";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  AIResultCard,
  SelectionMode,
} from "@/lib/types/ai-cards";
import { cn } from "@/lib/utils";

type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

type PendingSave = {
  chapterId: string;
  editorVersion: number;
  promise: Promise<boolean>;
};

export default function EditorShell() {
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [activeChapter, setActiveChapter] = useState<ChapterInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [selection, setSelection] = useState<SelectionContext | null>(null);
  const [aiCards, setAICards] = useState<AIResultCard[]>([]);
  const [aiLoading, setAILoading] = useState(false);
  const [aiError, setAIError] = useState<string | null>(null);
  const [aiPrompt, setAIPrompt] = useState("");
  const [aiMode, setAIMode] = useState<SelectionMode>("ask");
  const [targetWords, setTargetWords] = useState("200");
  const [error, setError] = useState<string | null>(null);
  const chapterSaveCoordinator = useMemo(
    () => new ChapterSaveCoordinator<ChapterInfo>(saveChapter),
    [],
  );
  const activeChapterRef = useRef<ChapterInfo | null>(null);
  const editorVersionRef = useRef(0);
  const pendingSaveRef = useRef<PendingSave | null>(null);
  const savedEditorVersionRef = useRef(0);
  const settingChapterContentRef = useRef(false);

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
    onUpdate: () => {
      if (settingChapterContentRef.current) {
        return;
      }
      editorVersionRef.current += 1;
      setSaveState("dirty");
    },
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
        settingChapterContentRef.current = true;
        try {
          editor.commands.setContent(markdownToTiptapContent(response.markdown));
        } finally {
          settingChapterContentRef.current = false;
        }
        editorVersionRef.current += 1;
        savedEditorVersionRef.current = editorVersionRef.current;
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

  const persistChapter = useCallback(async (): Promise<boolean> => {
    const chapter = activeChapterRef.current;
    if (!editor || !chapter) {
      return true;
    }

    const editorVersionAtSave = editorVersionRef.current;
    const pendingSave = pendingSaveRef.current;
    if (
      pendingSave?.chapterId === chapter.id &&
      pendingSave.editorVersion === editorVersionAtSave
    ) {
      return pendingSave.promise;
    }

    const markdown = tiptapContentToMarkdown(editor.getJSON());
    const operation = (async (): Promise<boolean> => {
      setError(null);
      setSaveState("saving");

      try {
        const outcome = await chapterSaveCoordinator.save(chapter, markdown);
        if (!outcome.stale) {
          setChapters(current =>
            current.map(currentChapter =>
              currentChapter.id === outcome.chapter.id
                ? outcome.chapter
                : currentChapter,
            ),
          );
        }

        const activeChapterId = activeChapterRef.current?.id ?? null;
        if (!shouldApplySaveOutcome(activeChapterId, outcome)) {
          return false;
        }

        activeChapterRef.current = outcome.chapter;
        setActiveChapter(outcome.chapter);

        if (
          isDirtySaveSatisfied({
            activeChapterId,
            outcome,
            editorVersionAtSave,
            currentEditorVersion: editorVersionRef.current,
          })
        ) {
          savedEditorVersionRef.current = editorVersionAtSave;
          setSaveState("saved");
          return true;
        }

        setSaveState("dirty");
        return false;
      } catch (saveError) {
        const activeChapterId = activeChapterRef.current?.id ?? null;
        if (
          saveError instanceof ChapterSaveFailedError &&
          isBlockingSaveFailure(activeChapterId, saveError)
        ) {
          setError(saveError.message);
          setSaveState("error");
        } else if (!(saveError instanceof ChapterSaveFailedError)) {
          setError(saveError instanceof Error ? saveError.message : "保存失败");
          setSaveState("error");
        }
        return false;
      }
    })();

    pendingSaveRef.current = {
      chapterId: chapter.id,
      editorVersion: editorVersionAtSave,
      promise: operation,
    };
    void operation.finally(() => {
      if (pendingSaveRef.current?.promise === operation) {
        pendingSaveRef.current = null;
      }
    });

    return operation;
  }, [chapterSaveCoordinator, editor]);

  const switchChapter = useCallback(
    async (chapterId: string) => {
      if (activeChapterRef.current?.id === chapterId) {
        return;
      }
      if (editorVersionRef.current !== savedEditorVersionRef.current) {
        const saved = await persistChapter();
        if (!saved) {
          return;
        }
      }
      await loadChapter(chapterId);
    },
    [loadChapter, persistChapter],
  );

  const upsertAICard = useCallback((card: AIResultCard) => {
    setAICards(current => {
      const exists = current.some(currentCard => currentCard.id === card.id);
      if (!exists) {
        return [...current, card];
      }
      return current.map(currentCard =>
        currentCard.id === card.id ? card : currentCard,
      );
    });
  }, []);

  const refreshAICards = useCallback(async (chapterId: string) => {
    const response = await listAICards(chapterId);
    setAICards(response.cards);
  }, []);

  const runSelectionAI = useCallback(
    async (mode: SelectionMode, parentCard?: AIResultCard) => {
      const chapter = activeChapterRef.current;
      const sourceRef =
        parentCard?.input_context.selection_ref ?? selection?.source_ref;
      const selectionRange =
        parentCard?.input_context.selection_range ?? selection?.selection_range;
      const selectedText =
        parentCard?.input_context.selected_text ?? selection?.selected_text;
      const surroundingText =
        parentCard?.input_context.surrounding_text ??
        selection?.surrounding_text ??
        "";
      if (!chapter || !sourceRef || !selectionRange || !selectedText) {
        setAIError("请先选择正文");
        return;
      }

      setAILoading(true);
      setAIError(null);
      try {
        const words =
          mode === "continue_text"
            ? positiveIntegerOrNull(
                parentCard?.input_context.target_words ?? targetWords,
              )
            : null;
        const response = await createSelectionAICard({
          mode,
          selection_context: {
            chapter_id: chapter.id,
            selected_text: selectedText,
            surrounding_text: surroundingText,
            selection_range: selectionRange,
            source_ref: sourceRef,
          },
          user_prompt:
            parentCard?.input_context.user_prompt ?? (aiPrompt.trim() || null),
          target_words: words,
          parent_card_id: parentCard?.id,
        });
        upsertAICard(response.card);
        await refreshAICards(chapter.id);
      } catch (selectionError) {
        setAIError(
          selectionError instanceof Error
            ? selectionError.message
            : "智能助手卡片生成失败",
        );
      } finally {
        setAILoading(false);
      }
    },
    [aiPrompt, refreshAICards, selection, targetWords, upsertAICard],
  );

  const applyTextCandidate = useCallback(
    async (card: AIResultCard, placement: TextCandidatePlacement) => {
      if (!editor) {
        return;
      }
      const edit = buildTextCandidateEdit({
        card,
        placement,
        cursorPosition: editor.state.selection.from,
      });
      editor.chain().focus().insertContentAt(
        { from: edit.from, to: edit.to },
        edit.text,
      ).run();
      try {
        const response = await applyAICardAction(card.id, "inserted");
        upsertAICard(response.card);
      } catch (actionError) {
        setAIError(
          actionError instanceof Error ? actionError.message : "卡片状态更新失败",
        );
      }
    },
    [editor, upsertAICard],
  );

  const copyTextCandidate = useCallback(async (card: AIResultCard) => {
    const text = textCandidateContent(card);
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
    }
  }, []);

  const saveIdea = useCallback(
    async (card: AIResultCard) => {
      try {
        const response = await applyAICardAction(card.id, "save_to_idea");
        upsertAICard(response.card);
      } catch (actionError) {
        setAIError(
          actionError instanceof Error ? actionError.message : "保存灵感失败",
        );
      }
    },
    [upsertAICard],
  );

  const convertPendingFact = useCallback(
    async (card: AIResultCard) => {
      try {
        const response = await convertAICardToPendingFact(card.id);
        upsertAICard(response.card);
      } catch (actionError) {
        setAIError(
          actionError instanceof Error ? actionError.message : "转为待确认设定失败",
        );
      }
    },
    [upsertAICard],
  );

  const discardAICard = useCallback(
    async (card: AIResultCard) => {
      try {
        const response = await applyAICardAction(card.id, "discard");
        upsertAICard(response.card);
      } catch (actionError) {
        setAIError(
          actionError instanceof Error ? actionError.message : "丢弃卡片失败",
        );
      }
    },
    [upsertAICard],
  );

  const runChapterSummary = useCallback(async () => {
    const chapter = activeChapterRef.current;
    if (!chapter) {
      setAIError("请先打开章节");
      return;
    }
    if (editorVersionRef.current !== savedEditorVersionRef.current) {
      const saved = await persistChapter();
      if (!saved) {
        setAIError("请先保存当前章节");
        return;
      }
    }

    setAILoading(true);
    setAIError(null);
    try {
      const response = await summarizeChapter(chapter.id);
      upsertAICard(response.card);
      await refreshAICards(chapter.id);
    } catch (summaryError) {
      setAIError(
        summaryError instanceof Error
          ? summaryError.message
          : "章节整理失败",
      );
    } finally {
      setAILoading(false);
    }
  }, [persistChapter, refreshAICards, upsertAICard]);

  const retryAICard = useCallback(
    (card: AIResultCard) => {
      const mode = card.input_context.mode ?? aiMode;
      void runSelectionAI(mode, card);
    },
    [aiMode, runSelectionAI],
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
        const requestedChapterId =
          new URLSearchParams(window.location.search).get("chapter_id");
        const initialChapter =
          sortedChapters.find(chapter => chapter.id === requestedChapterId) ??
          sortedChapters[0];
        if (initialChapter) {
          await loadChapter(initialChapter.id);
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

  const activeChapterId = activeChapter?.id;

  useEffect(() => {
    if (!activeChapterId) {
      return;
    }

    let cancelled = false;
    async function loadCards() {
      try {
        const response = await listAICards(activeChapterId);
        if (!cancelled) {
          setAICards(response.cards);
        }
      } catch (cardError) {
        if (!cancelled) {
          setAIError(
            cardError instanceof Error
              ? cardError.message
              : "智能助手卡片加载失败",
          );
        }
      }
    }

    void loadCards();
    return () => {
      cancelled = true;
    };
  }, [activeChapterId]);

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

        <aside className="min-h-0 border-l-[3px] border-black bg-white px-4 py-5">
          <AICardList
            cards={aiCards}
            selection={selection}
            prompt={aiPrompt}
            targetWords={targetWords}
            selectedMode={aiMode}
            loading={aiLoading}
            error={aiError}
            onPromptChange={setAIPrompt}
            onTargetWordsChange={setTargetWords}
            onModeChange={setAIMode}
            onRunSelection={mode => void runSelectionAI(mode)}
            onRunChapterSummary={() => void runChapterSummary()}
            onApplyText={(card, placement) =>
              void applyTextCandidate(card, placement)
            }
            onCopyText={card => void copyTextCandidate(card)}
            onSaveIdea={card => void saveIdea(card)}
            onConvertPendingFact={card => void convertPendingFact(card)}
            onRetry={retryAICard}
            onDiscard={card => void discardAICard(card)}
          />
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

function positiveIntegerOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  }
  return null;
}
