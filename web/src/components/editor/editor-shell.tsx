"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  BookOpen,
  Check,
  FilePlus2,
  History,
  Loader2,
  MessageSquare,
  Redo2,
  Save,
  Search,
  Send,
  Sparkles,
  Type,
  Undo2,
} from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { readChapter, saveChapter } from "@/lib/api/chapters";
import {
  createAIConversation,
  createChapter,
  createInboxIdea,
  createInboxPendingFact,
  createVolume,
  readOutline,
  readPreferences,
  sendAIMessage,
} from "@/lib/api/mvp";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  AIReferenceScope,
  AIWorkspaceConversation,
  AIWorkspaceMessage,
  AIWorkspaceTaskType,
  EditorPreferences,
  OutlineChapter,
  SourceReference,
  WritingOutline,
} from "@/lib/types/mvp";
import { cn } from "@/lib/utils";

type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";
type AIEntryKey =
  | "chat"
  | "continue"
  | "polish"
  | "setting"
  | "suggestion"
  | "evidence"
  | "chapter_summary"
  | "inspiration"
  | "fact";

type AIEntry = {
  key: AIEntryKey;
  label: string;
  brandLabel: string;
  placeholder: string;
  taskType?: AIWorkspaceTaskType;
};

type TextSelection = {
  start: number;
  end: number;
  text: string;
};

type LocalMessage = {
  role: "user" | "assistant";
  text: string;
};

const aiEntries: AIEntry[] = [
  {
    key: "chat",
    label: "纯对话",
    brandLabel: "问灵",
    placeholder: "输入你想临时询问的内容",
  },
  {
    key: "continue",
    label: "续写",
    brandLabel: "衍文",
    placeholder: "输入续写要求，可为空",
    taskType: "continue",
  },
  {
    key: "polish",
    label: "润色",
    brandLabel: "润笔",
    placeholder: "输入扩写、缩写或改写要求，可为空",
    taskType: "polish",
  },
  {
    key: "setting",
    label: "设定",
    brandLabel: "构界",
    placeholder: "输入你想补充的设定方向",
    taskType: "setting",
  },
  {
    key: "suggestion",
    label: "建议",
    brandLabel: "策议",
    placeholder: "输入你想判断或改进的问题",
    taskType: "suggestion",
  },
  {
    key: "evidence",
    label: "证据",
    brandLabel: "溯源",
    placeholder: "输入你想追问的依据或出处",
    taskType: "evidence",
  },
  {
    key: "chapter_summary",
    label: "章节摘要",
    brandLabel: "章要",
    placeholder: "本章暂未生成摘要",
    taskType: "chapter_summary",
  },
  {
    key: "inspiration",
    label: "灵感",
    brandLabel: "灵引",
    placeholder: "记下一条灵感",
  },
  {
    key: "fact",
    label: "事实",
    brandLabel: "事实簿",
    placeholder: "记下一条可能入库的事实",
  },
];

const defaultPreferences: EditorPreferences = {
  font_size: 18,
  font_style: "serif",
  editor_background: "soft",
  updated_at: "",
};

export default function EditorShell() {
  const [outline, setOutline] = useState<WritingOutline | null>(null);
  const [activeChapter, setActiveChapter] = useState<ChapterInfo | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<TextSelection | null>(null);
  const [preferences, setPreferences] =
    useState<EditorPreferences>(defaultPreferences);
  const [fontSize, setFontSize] = useState(defaultPreferences.font_size);
  const [fontStyle, setFontStyle] = useState<EditorPreferences["font_style"]>(
    defaultPreferences.font_style,
  );
  const [editorBackground, setEditorBackground] = useState<
    EditorPreferences["editor_background"]
  >(defaultPreferences.editor_background);
  const [searchText, setSearchText] = useState("");
  const [aiEntryKey, setAIEntryKey] = useState<AIEntryKey>("continue");
  const [brandMode, setBrandMode] = useState(false);
  const [aiInput, setAIInput] = useState("");
  const [aiBusy, setAIBusy] = useState(false);
  const [aiError, setAIError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<
    Partial<Record<AIEntryKey, AIWorkspaceConversation>>
  >({});
  const [localChatMessages, setLocalChatMessages] = useState<LocalMessage[]>([]);
  const [showPromptSnapshot, setShowPromptSnapshot] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const savedMarkdownRef = useRef("");
  const activeChapterRef = useRef<ChapterInfo | null>(null);
  const saveTimerRef = useRef<number | null>(null);

  const activeEntry = aiEntries.find(entry => entry.key === aiEntryKey) ?? aiEntries[1];
  const activeConversation = conversations[aiEntryKey] ?? null;
  const searchCount = useMemo(
    () => countOccurrences(markdown, searchText),
    [markdown, searchText],
  );
  const loadChapter = useCallback(async (chapterId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await readChapter(chapterId);
      activeChapterRef.current = response.chapter;
      setActiveChapter(response.chapter);
      setMarkdown(response.markdown);
      savedMarkdownRef.current = response.markdown;
      setSaveState("saved");
      setSelection(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "章节加载失败");
      setSaveState("error");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshOutline = useCallback(async () => {
    const response = await readOutline();
    setOutline(response.outline);
    return response.outline;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadInitialData() {
      setLoading(true);
      setError(null);
      try {
        const [outlineResponse, preferenceResponse] = await Promise.all([
          readOutline(),
          readPreferences().catch(() => ({ preferences: defaultPreferences })),
        ]);
        if (cancelled) {
          return;
        }
        setOutline(outlineResponse.outline);
        setPreferences(preferenceResponse.preferences);
        setFontSize(preferenceResponse.preferences.font_size);
        setFontStyle(preferenceResponse.preferences.font_style);
        setEditorBackground(preferenceResponse.preferences.editor_background);
        const requestedChapterId =
          new URLSearchParams(window.location.search).get("chapter_id");
        const initialChapterId =
          requestedChapterId ??
          outlineResponse.outline.current_chapter_id ??
          outlineChapters(outlineResponse.outline)[0]?.chapter_id;
        if (initialChapterId) {
          await loadChapter(initialChapterId);
        } else {
          setLoading(false);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "写作区加载失败");
          setLoading(false);
        }
      }
    }
    void loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [loadChapter]);

  const persistChapter = useCallback(async () => {
    const chapter = activeChapterRef.current;
    if (!chapter || markdown === savedMarkdownRef.current) {
      setSaveState(chapter ? "saved" : "idle");
      return true;
    }
    setSaveState("saving");
    setError(null);
    try {
      const response = await saveChapter(chapter.id, markdown);
      activeChapterRef.current = response.chapter;
      setActiveChapter(response.chapter);
      savedMarkdownRef.current = markdown;
      setSaveState("saved");
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败");
      setSaveState("error");
      return false;
    }
  }, [markdown]);

  useEffect(() => {
    if (saveState !== "dirty") {
      return;
    }
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = window.setTimeout(() => {
      void persistChapter();
    }, 1400);
    return () => {
      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current);
      }
    };
  }, [persistChapter, saveState]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void persistChapter();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [persistChapter]);

  async function switchChapter(chapterId: string) {
    if (activeChapter?.id === chapterId) {
      return;
    }
    if (saveState === "dirty" || saveState === "error") {
      const saved = await persistChapter();
      if (!saved) {
        return;
      }
    }
    await loadChapter(chapterId);
  }

  async function addVolume() {
    try {
      setOutline((await createVolume("新的一卷")).outline);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建分卷失败");
    }
  }

  async function addChapter(volumeId: string) {
    try {
      const nextOutline = (await createChapter(volumeId, "新章节")).outline;
      setOutline(nextOutline);
      const chapterId = nextOutline.current_chapter_id;
      if (chapterId) {
        await loadChapter(chapterId);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建章节失败");
    }
  }

  function updateMarkdown(nextMarkdown: string) {
    setMarkdown(nextMarkdown);
    setSaveState(nextMarkdown === savedMarkdownRef.current ? "saved" : "dirty");
  }

  function updateSelection() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    if (start === end) {
      setSelection(null);
      return;
    }
    setSelection({ start, end, text: markdown.slice(start, end) });
  }

  function runUndo() {
    textareaRef.current?.focus();
    document.execCommand("undo");
  }

  function runRedo() {
    textareaRef.current?.focus();
    document.execCommand("redo");
  }

  function formatSelectedParagraphs() {
    if (!selection) {
      setError("请先选择要排版的段落");
      return;
    }
    const formatted = selection.text
      .split(/\n+/)
      .map(line => line.trim())
      .filter(Boolean)
      .join("\n\n");
    const nextMarkdown =
      markdown.slice(0, selection.start) + formatted + markdown.slice(selection.end);
    updateMarkdown(nextMarkdown);
    setSelection({
      start: selection.start,
      end: selection.start + formatted.length,
      text: formatted,
    });
  }

  async function submitAI() {
    const input = aiInput.trim();
    const chapter = activeChapterRef.current;
    if (!chapter) {
      setAIError("当前章节为空，无法使用右侧入口");
      return;
    }
    if (!input && activeEntry.key !== "continue" && activeEntry.key !== "chapter_summary") {
      setAIError("请先输入内容");
      return;
    }
    setAIBusy(true);
    setAIError(null);
    try {
      if (activeEntry.key === "chat") {
        setLocalChatMessages(current => [
          ...current,
          { role: "user", text: input },
          {
            role: "assistant",
            text: "这是临时对话，不会保存到 AI 历史，也不会写入知识库。",
          },
        ]);
        setAIInput("");
        return;
      }
      if (activeEntry.key === "inspiration") {
        await createInboxIdea({
          content: input,
          source_chapter_id: chapter.id,
          priority: "normal",
        });
        setAIInput("");
        setAIError("灵感已保存到 Inbox");
        return;
      }
      if (activeEntry.key === "fact") {
        await createInboxPendingFact({
          title: input.slice(0, 24) || "待确认事实",
          content: input,
          source_chapter_id: chapter.id,
          origin: "作者手动记录",
          priority: "normal",
        });
        setAIInput("");
        setAIError("事实已保存到 Inbox 的待确认事实");
        return;
      }
      if (!activeEntry.taskType) {
        return;
      }
      const referenceScope = referenceScopeFor(activeEntry.taskType, selection);
      let conversation = conversations[activeEntry.key];
      if (!conversation) {
        conversation = (
          await createAIConversation({
            chapterId: chapter.id,
            taskType: activeEntry.taskType,
            referenceScope,
          })
        ).conversation;
      }
      const response = await sendAIMessage({
        conversationId: conversation.id,
        userInput: input || defaultPromptFor(activeEntry.key),
        reference: {
          scope: referenceScope,
          chapter_id: chapter.id,
          selected_text: selection?.text ?? "",
          selection_start: selection?.start ?? null,
          selection_end: selection?.end ?? null,
          chapter_text: markdown,
        },
      });
      setConversations(current => ({
        ...current,
        [activeEntry.key]: response.conversation,
      }));
      setAIInput("");
      void refreshOutline();
    } catch (caught) {
      setAIError(caught instanceof Error ? caught.message : "右侧入口处理失败");
    } finally {
      setAIBusy(false);
    }
  }

  return (
    <AppShell activePath="/editor">
      <div className="grid min-h-[calc(100vh-73px)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
        <aside className="border-b border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-4 py-4 xl:border-b-0 xl:border-r">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-smoke)]">写作</p>
              <h1 className="font-serif text-2xl text-[var(--tc-midnight-ink)]">
                分卷章节大纲
              </h1>
            </div>
            <Button type="button" size="icon" title="新建分卷" onClick={addVolume}>
              <FilePlus2 className="size-4" />
            </Button>
          </div>
          <div className="space-y-4">
            {outline?.volumes.map(volume => (
              <section
                key={volume.volume_id}
                className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-3"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="truncate text-left text-sm font-semibold text-[var(--tc-midnight-ink)]">
                    {volume.name}
                  </span>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="outline"
                    title="新建章节"
                    onClick={() => addChapter(volume.volume_id)}
                  >
                    <FilePlus2 className="size-4" />
                  </Button>
                </div>
                <div className="space-y-1">
                  {volume.chapters.map(chapter => (
                    <div key={chapter.chapter_id} className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => void switchChapter(chapter.chapter_id)}
                        className={cn(
                          "min-w-0 flex-1 truncate rounded-[10px] px-2 py-2 text-left text-sm transition-colors",
                          activeChapter?.id === chapter.chapter_id
                            ? "bg-[var(--tc-lavender-whisper)] text-[var(--tc-midnight-ink)]"
                            : "text-[var(--tc-smoke)] hover:bg-[var(--tc-white)] hover:text-[var(--tc-midnight-ink)]",
                        )}
                      >
                        {chapter.display_title}
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </aside>

        <section className="min-w-0 bg-[var(--tc-cream-paper)]">
          <header className="border-b border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-4 py-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <p className="text-xs text-[var(--tc-smoke)]">
                  {statusText(saveState, loading)}
                </p>
                <h2 className="truncate font-serif text-3xl text-[var(--tc-midnight-ink)]">
                  {activeChapterTitle(outline, activeChapter?.id) ?? "未选择章节"}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 text-sm">
                  <Type className="size-4" />
                  字号
                  <input
                    type="number"
                    min={14}
                    max={24}
                    value={fontSize}
                    onChange={event => setFontSize(Number(event.target.value))}
                    className="w-12 bg-transparent text-center outline-none"
                  />
                </label>
                <select
                  value={fontStyle}
                  onChange={event =>
                    setFontStyle(event.target.value as EditorPreferences["font_style"])
                  }
                  className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
                  aria-label="字体样式"
                >
                  <option value="serif">衬线</option>
                  <option value="sans">无衬线</option>
                </select>
                <select
                  value={editorBackground}
                  onChange={event =>
                    setEditorBackground(
                      event.target.value as EditorPreferences["editor_background"],
                    )
                  }
                  className="h-10 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
                  aria-label="编辑背景"
                >
                  <option value="soft">柔和纸面</option>
                  <option value="dark">墨色边框</option>
                </select>
                <IconButton label="撤销" onClick={runUndo}>
                  <Undo2 className="size-4" />
                </IconButton>
                <IconButton label="恢复" onClick={runRedo}>
                  <Redo2 className="size-4" />
                </IconButton>
                <label className="flex h-10 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm">
                  <Search className="size-4" />
                  <input
                    value={searchText}
                    onChange={event => setSearchText(event.target.value)}
                    placeholder="查找"
                    className="w-24 bg-transparent outline-none"
                  />
                  {searchText ? (
                    <span className="text-xs text-[var(--tc-smoke)]">{searchCount}</span>
                  ) : null}
                </label>
                <Button type="button" variant="outline" onClick={formatSelectedParagraphs}>
                  一键段落排版
                </Button>
                <Button
                  type="button"
                  onClick={() => void persistChapter()}
                  disabled={!activeChapter || saveState === "saving"}
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
            </div>
          </header>

          <div className="p-4 md:p-6">
            {error ? (
              <div className="tc-warning mb-4 rounded-[var(--tc-radius-control)] border px-4 py-3 text-sm">
                {error}
              </div>
            ) : null}
            <div
              className={cn(
                "mx-auto max-w-4xl rounded-[var(--tc-radius-card)] border bg-[var(--tc-white)] p-3 shadow-[var(--tc-shadow-paper)]",
                editorBackground === "dark"
                  ? "border-[var(--tc-midnight-ink)]"
                  : "border-[var(--tc-stone-mist)]",
              )}
            >
              <textarea
                ref={textareaRef}
                value={markdown}
                onChange={event => updateMarkdown(event.target.value)}
                onSelect={updateSelection}
                onKeyUp={updateSelection}
                onMouseUp={updateSelection}
                disabled={!activeChapter || loading}
                spellCheck={false}
                className={cn(
                  "min-h-[calc(100vh-260px)] w-full resize-none rounded-[24px] bg-[var(--tc-paper-bg)] px-5 py-5 leading-[1.9] text-[var(--tc-paper-ink)] outline-none md:px-8 md:py-7",
                  fontStyle === "serif"
                    ? "font-[var(--tc-font-editor)]"
                    : "font-[var(--tc-font-ui)]",
                )}
                style={{ fontSize: `${fontSize}px` }}
                placeholder="在这里写正文"
              />
            </div>
          </div>
        </section>

        <aside className="border-t border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-4 py-4 xl:border-l xl:border-t-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-[var(--tc-smoke)]">
                {brandMode ? "器灵" : "AI"} 入口
              </p>
              <h2 className="font-serif text-2xl text-[var(--tc-midnight-ink)]">
                右侧写作助手
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setBrandMode(current => !current)}
              className="rounded-full border border-[var(--tc-stone-mist)] px-3 py-1 text-xs text-[var(--tc-smoke)]"
            >
              {brandMode ? "清晰名" : "品牌名"}
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {aiEntries.map(entry => (
              <button
                key={entry.key}
                type="button"
                onClick={() => {
                  setAIEntryKey(entry.key);
                  setAIError(null);
                }}
                className={cn(
                  "h-11 rounded-[var(--tc-radius-control)] border px-2 text-sm font-medium transition-colors",
                  aiEntryKey === entry.key
                    ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-lavender-whisper)] text-[var(--tc-midnight-ink)]"
                    : "border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]",
                )}
              >
                {brandMode ? entry.brandLabel : entry.label}
              </button>
            ))}
          </div>

          <div className="mt-4 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="tc-tag px-3 py-1">正文参考</span>
              <span className="tc-tag px-3 py-1">
                当前参考：{selection ? "选区" : "本章"}
              </span>
              {activeConversation?.is_mock ? (
                <span className="tc-tag px-3 py-1">模拟输出</span>
              ) : null}
            </div>
            <textarea
              value={aiInput}
              onChange={event => setAIInput(event.target.value)}
              className="min-h-24 w-full resize-y rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm leading-6 outline-none"
              placeholder={activeEntry.placeholder}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                onClick={() => void submitAI()}
                disabled={aiBusy || !activeChapter}
              >
                {aiBusy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                发送
              </Button>
              <Link
                href="/ai-history"
                className="inline-flex h-8 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] px-3 text-sm text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
              >
                <History className="size-4" />
                查找对话
              </Link>
              {activeEntry.taskType ? (
                <button
                  type="button"
                  onClick={() => setConversations(current => ({ ...current, [aiEntryKey]: undefined }))}
                  className="inline-flex h-8 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] px-3 text-sm text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
                >
                  <MessageSquare className="size-4" />
                  新对话
                </button>
              ) : null}
            </div>
            {aiError ? (
              <p className="mt-3 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm text-[var(--tc-smoke)]">
                {aiError}
              </p>
            ) : null}
          </div>

          <AIMessageList
            entryKey={aiEntryKey}
            localMessages={localChatMessages}
            conversation={activeConversation}
            showPromptSnapshot={showPromptSnapshot}
            onTogglePromptSnapshot={() =>
              setShowPromptSnapshot(current => !current)
            }
          />
        </aside>
      </div>
      <span className="sr-only">
        {preferences.updated_at ? "偏好已加载" : "使用默认偏好"}
      </span>
    </AppShell>
  );
}

function AIMessageList({
  entryKey,
  localMessages,
  conversation,
  showPromptSnapshot,
  onTogglePromptSnapshot,
}: {
  entryKey: AIEntryKey;
  localMessages: LocalMessage[];
  conversation: AIWorkspaceConversation | null;
  showPromptSnapshot: boolean;
  onTogglePromptSnapshot: () => void;
}) {
  const messages =
    entryKey === "chat"
      ? localMessages.map(message => ({
          role: message.role,
          text: message.text,
          sourceRefs: [] as SourceReference[],
          snapshot: null as string | null,
          mock: true,
        }))
      : (conversation?.messages ?? []).map(message => ({
          role: message.role,
          text: messageContent(message),
          sourceRefs: message.source_refs,
          snapshot: message.prompt_snapshot?.final_prompt ?? null,
          mock: message.is_mock,
        }));
  const latestSnapshot = [...messages].reverse().find(message => message.snapshot);

  return (
    <section className="mt-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--tc-midnight-ink)]">
          对话记录
        </h3>
        {latestSnapshot ? (
          <button
            type="button"
            onClick={onTogglePromptSnapshot}
            className="text-xs text-[var(--tc-deep-forest-teal)]"
          >
            {showPromptSnapshot ? "收起提示词快照" : "查看提示词快照"}
          </button>
        ) : null}
      </div>
      {showPromptSnapshot && latestSnapshot?.snapshot ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-3 text-xs leading-5">
          {latestSnapshot.snapshot}
        </pre>
      ) : null}
      {messages.length ? (
        messages.map((message, index) => (
          <article
            key={`${message.role}-${index}`}
            className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-3"
          >
            <div className="mb-2 flex items-center gap-2 text-xs text-[var(--tc-smoke)]">
              {message.role === "user" ? (
                <BookOpen className="size-4" />
              ) : message.role === "assistant" ? (
                <Bot className="size-4" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {message.role === "user" ? "作者" : "模拟输出"}
              {message.mock ? <span>模拟</span> : null}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6">{message.text}</p>
            {message.sourceRefs.length ? (
              <div className="mt-3 space-y-2 border-t border-[var(--tc-stone-mist)] pt-3">
                {message.sourceRefs.map((source, sourceIndex) => (
                  <div
                    key={`${source.source_id}-${sourceIndex}`}
                    className="rounded-[10px] bg-[var(--tc-cream-paper)] px-3 py-2 text-xs"
                  >
                    <p className="font-medium">
                      来源 {sourceIndex + 1}：{source.display_name}
                    </p>
                    <p className="mt-1 text-[var(--tc-smoke)]">{source.excerpt}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))
      ) : (
        <div className="rounded-[var(--tc-radius-control)] border border-dashed border-[var(--tc-stone-mist)] px-3 py-8 text-center text-sm text-[var(--tc-smoke)]">
          暂无对话记录
        </div>
      )}
    </section>
  );
}

function IconButton({
  label,
  children,
  onClick,
}: {
  label: string;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex size-10 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
    >
      {children}
    </button>
  );
}

function outlineChapters(outline: WritingOutline | null): OutlineChapter[] {
  return (
    outline?.volumes.flatMap(volume =>
      [...volume.chapters].sort((left, right) => left.order - right.order),
    ) ?? []
  );
}

function activeChapterTitle(
  outline: WritingOutline | null,
  chapterId?: string | null,
): string | null {
  if (!chapterId) {
    return null;
  }
  return (
    outlineChapters(outline).find(chapter => chapter.chapter_id === chapterId)
      ?.display_title ?? null
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

function countOccurrences(text: string, query: string): number {
  if (!query) {
    return 0;
  }
  let count = 0;
  let index = text.indexOf(query);
  while (index !== -1) {
    count += 1;
    index = text.indexOf(query, index + query.length);
  }
  return count;
}

function referenceScopeFor(
  taskType: AIWorkspaceTaskType,
  selection: TextSelection | null,
): AIReferenceScope {
  if (taskType === "chapter_summary") {
    return "chapter";
  }
  return selection ? "selection" : "chapter";
}

function defaultPromptFor(entryKey: AIEntryKey): string {
  if (entryKey === "chapter_summary") {
    return "生成本章摘要";
  }
  if (entryKey === "continue") {
    return "续写当前段落";
  }
  return "请根据当前正文参考给出模拟结果";
}

function messageContent(message: AIWorkspaceMessage): string {
  if (typeof message.content === "string") {
    return message.content;
  }
  const content = message.content;
  if (typeof content.text === "string") {
    return content.text;
  }
  if (typeof content.setting_addition === "string") {
    return [
      `设定补充：${content.setting_addition}`,
      `使用建议：${stringValue(content.usage_suggestion)}`,
      `可能影响：${stringValue(content.possible_impact)}`,
    ].join("\n");
  }
  if (typeof content.suggestion === "string") {
    return [
      `问题：${stringValue(content.problem)}`,
      `判断：${stringValue(content.judgement)}`,
      `建议：${content.suggestion}`,
    ].join("\n");
  }
  if (typeof content.conclusion === "string") {
    const points = Array.isArray(content.unconfirmed_points)
      ? content.unconfirmed_points.filter(
          (item): item is string => typeof item === "string",
        )
      : [];
    return [
      `结论：${content.conclusion}`,
      `推断：${stringValue(content.inference)}`,
      points.length ? `未确认点：${points.join("；")}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (typeof content.summary === "string") {
    return content.summary;
  }
  return JSON.stringify(content, null, 2);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "暂无";
}
