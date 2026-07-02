"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  BadgeCheck,
  Bot,
  BookOpen,
  BookmarkPlus,
  ChevronDown,
  ChevronRight,
  Check,
  FileText,
  FilePlus2,
  History,
  Lightbulb,
  Loader2,
  MessageSquare,
  MoreVertical,
  Palette,
  PenLine,
  Plus,
  Redo2,
  Save,
  Search,
  SearchCheck,
  Send,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Type,
  Undo2,
  X,
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
  deleteChapter,
  deleteVolume,
  patchPreferences,
  readOutline,
  readPreferences,
  renameChapter,
  renameVolume,
  sendAIMessage,
} from "@/lib/api/mvp";
import { formatNovelParagraphs } from "@/lib/editor/markdown";
import type { ChapterInfo } from "@/lib/types/chapters";
import type {
  AIReferenceScope,
  AIWorkspaceConversation,
  AIWorkspaceMessage,
  AIWorkspaceTaskType,
  EditorPreferences,
  OutlineChapter,
  OutlineVolume,
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

type ReferenceRangeChoice = "auto" | "chapter" | "selection";
type EditorPaperToneKey =
  | "mist"
  | "charcoal"
  | "obsidian"
  | "blueNight"
  | "pineNight"
  | "green"
  | "classic"
  | "blue"
  | "pink"
  | "peach"
  | "snow"
  | "aqua";

type EditorPaperTone = {
  key: EditorPaperToneKey;
  label: string;
  surface: string;
  swatch: string;
  ink: string;
  selection: string;
};

const EDITOR_PAPER_TONE_STORAGE_KEY = "taichu-editor-paper-tone";
const EDITOR_PAPER_TONE_EVENT = "taichu-editor-paper-tone-change";
const EDITOR_COLLAPSED_VOLUMES_STORAGE_KEY = "taichu-editor-collapsed-volumes";
const EDITOR_ACTIVE_CHAPTER_STORAGE_KEY = "taichu-editor-active-chapter";

const editorPaperTones: EditorPaperTone[] = [
  {
    key: "mist",
    label: "薄雾灰",
    surface: "#f7f7f8",
    swatch: "#f7f7f8",
    ink: "#202124",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "charcoal",
    label: "炭灰夜",
    surface: "#202124",
    swatch: "#202124",
    ink: "#eceff3",
    selection: "rgba(255, 255, 255, 0.18)",
  },
  {
    key: "obsidian",
    label: "玄墨黑",
    surface: "#141416",
    swatch: "#141416",
    ink: "#f1f1ee",
    selection: "rgba(255, 255, 255, 0.2)",
  },
  {
    key: "blueNight",
    label: "蓝黑夜",
    surface: "#18202b",
    swatch: "#1d2a38",
    ink: "#edf3fb",
    selection: "rgba(166, 205, 255, 0.22)",
  },
  {
    key: "pineNight",
    label: "松烟青",
    surface: "#18231f",
    swatch: "#1f302a",
    ink: "#ecf4ef",
    selection: "rgba(169, 230, 204, 0.2)",
  },
  {
    key: "green",
    label: "护眼绿",
    surface: "#dceedd",
    swatch: "#c8dfc8",
    ink: "#1d2b20",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "classic",
    label: "古典黄",
    surface: "#f0e6cf",
    swatch: "#e5d9bd",
    ink: "#2a2318",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "blue",
    label: "静谧蓝",
    surface: "#e5edf6",
    swatch: "#d0dcea",
    ink: "#1f2834",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "pink",
    label: "浪漫粉",
    surface: "#f4e4e8",
    swatch: "#ead6dc",
    ink: "#302226",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "peach",
    label: "兔年大吉",
    surface: "linear-gradient(135deg, #fff4ef 0%, #ffe2cf 100%)",
    swatch: "linear-gradient(135deg, #fff4ef 0%, #f7bda4 100%)",
    ink: "#2f211c",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "snow",
    label: "白雪飞腊",
    surface: "linear-gradient(135deg, #ffffff 0%, #f0f0ed 100%)",
    swatch: "linear-gradient(135deg, #ffffff 0%, #e7e7e2 100%)",
    ink: "#242526",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "aqua",
    label: "绿水青山",
    surface: "linear-gradient(135deg, #f2fffc 0%, #d8f1ee 100%)",
    swatch: "linear-gradient(135deg, #f2fffc 0%, #bfe5df 100%)",
    ink: "#1c2d2b",
    selection: "rgba(0, 0, 0, 0.14)",
  },
];

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
  font_style: "sans",
  editor_background: "soft",
  updated_at: "",
};

export default function EditorShell() {
  const [outline, setOutline] = useState<WritingOutline | null>(null);
  const [activeChapter, setActiveChapter] = useState<ChapterInfo | null>(null);
  const [chapterTitleDraft, setChapterTitleDraft] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<TextSelection | null>(null);
  const [preferences, setPreferences] =
    useState<EditorPreferences>(defaultPreferences);
  const [fontSize, setFontSize] = useState(defaultPreferences.font_size);
  const [editorBackground, setEditorBackground] = useState<
    EditorPreferences["editor_background"]
  >(defaultPreferences.editor_background);
  const paperToneKey = useSyncExternalStore(
    subscribeStoredPaperToneKey,
    readStoredPaperToneKey,
    () => "mist",
  );
  const [isBackgroundMenuOpen, setBackgroundMenuOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [referenceRange, setReferenceRange] =
    useState<ReferenceRangeChoice>("auto");
  const [selectedAiTool, setSelectedAiTool] = useState<AIEntryKey>("continue");
  const [isAssistantPanelOpen, setAssistantPanelOpen] = useState(false);
  const [collapsedVolumeIds, setCollapsedVolumeIds] = useState<Set<string>>(
    () => readStoredCollapsedVolumeIds(),
  );
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
  const savedChapterTitleRef = useRef("");
  const activeChapterRef = useRef<ChapterInfo | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const assistantPanelOpenRef = useRef(false);
  const assistantHistoryOpenRef = useRef(false);
  const activePaperTone =
    editorPaperTones.find(tone => tone.key === paperToneKey) ??
    editorPaperTones[0];
  const volumeCount = outline?.volumes.length ?? 0;
  const chapterCount = outlineChapters(outline).length;

  const activeEntry =
    aiEntries.find(entry => entry.key === selectedAiTool) ?? aiEntries[1];
  const activeConversation = conversations[selectedAiTool] ?? null;
  const currentOutlineChapter = activeChapter
    ? outlineChapterById(outline, activeChapter.id)
    : null;
  const currentChapterTitle =
    activeChapterTitle(outline, activeChapter?.id) ?? activeChapter?.title ?? "";
  const currentChapterPrefix = currentOutlineChapter
    ? chapterNumberLabel(currentOutlineChapter.order)
    : "章节";
  const currentReferenceScope = activeEntry.taskType
    ? referenceScopeFor(activeEntry.taskType, selection, referenceRange)
    : selection && referenceRange !== "chapter"
      ? "selection"
      : "chapter";
  const searchCount = useMemo(
    () => countOccurrences(markdown, searchText),
    [markdown, searchText],
  );
  const saveDisabled =
    !activeChapter ||
    loading ||
    saveState === "saving" ||
    saveState === "saved" ||
    saveState === "idle";

  const resizeEditorTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    const minHeight =
      typeof window === "undefined" ? 360 : Math.max(window.innerHeight - 330, 360);
    textarea.style.height = `${Math.max(textarea.scrollHeight, minHeight)}px`;
  }, []);
  const loadChapter = useCallback(async (chapterId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await readChapter(chapterId);
      activeChapterRef.current = response.chapter;
      setActiveChapter(response.chapter);
      writeStoredActiveChapterId(response.chapter.id);
      setChapterTitleDraft(chapterTitleBody(response.chapter.title));
      savedChapterTitleRef.current = chapterTitleBody(response.chapter.title);
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

  const openAssistantPanel = useCallback(() => {
    if (!assistantPanelOpenRef.current) {
      const currentState =
        typeof window.history.state === "object" && window.history.state !== null
          ? window.history.state
          : {};
      window.history.pushState(
        { ...currentState, taichuAssistantPanel: true },
        "",
        window.location.href,
      );
      assistantHistoryOpenRef.current = true;
      assistantPanelOpenRef.current = true;
    }
    setAssistantPanelOpen(true);
  }, []);

  const closeAssistantPanel = useCallback(() => {
    setAIError(null);
    if (
      assistantHistoryOpenRef.current &&
      window.history.state?.taichuAssistantPanel
    ) {
      window.history.back();
      return;
    }
    assistantHistoryOpenRef.current = false;
    assistantPanelOpenRef.current = false;
    setAssistantPanelOpen(false);
  }, []);

  useEffect(() => {
    assistantPanelOpenRef.current = isAssistantPanelOpen;
  }, [isAssistantPanelOpen]);

  useEffect(() => {
    writeStoredCollapsedVolumeIds(collapsedVolumeIds);
  }, [collapsedVolumeIds]);

  useEffect(() => {
    resizeEditorTextarea();
  }, [activeChapter?.id, fontSize, markdown, resizeEditorTextarea]);

  useEffect(() => {
    function handlePopState(event: PopStateEvent) {
      if (event.state?.taichuAssistantPanel) {
        assistantHistoryOpenRef.current = true;
        assistantPanelOpenRef.current = true;
        setAssistantPanelOpen(true);
        return;
      }
      if (assistantPanelOpenRef.current) {
        assistantHistoryOpenRef.current = false;
        assistantPanelOpenRef.current = false;
        setAssistantPanelOpen(false);
        setAIError(null);
      }
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
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
        setEditorBackground(preferenceResponse.preferences.editor_background);
        const requestedChapterId =
          new URLSearchParams(window.location.search).get("chapter_id");
        const storedChapterId = readStoredActiveChapterId();
        const storedChapterExists =
          storedChapterId !== null &&
          outlineChapterById(outlineResponse.outline, storedChapterId) !== null;
        const initialChapterId =
          requestedChapterId ??
          (storedChapterExists ? storedChapterId : null) ??
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

  function clearActiveChapter() {
    activeChapterRef.current = null;
    setActiveChapter(null);
    setChapterTitleDraft("");
    savedChapterTitleRef.current = "";
    setMarkdown("");
    savedMarkdownRef.current = "";
    setSaveState("idle");
    setSelection(null);
    clearStoredActiveChapterId();
  }

  async function addVolume() {
    const defaultName = `第${(outline?.volumes.length ?? 0) + 1}卷`;
    const requestedName = window.prompt("请输入卷名", defaultName);
    if (requestedName === null) {
      return;
    }
    const name = requestedName.trim() || defaultName;
    try {
      setOutline((await createVolume(name)).outline);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建分卷失败");
    }
  }

  async function updateFontSizePreference(nextFontSize: number) {
    const safeFontSize = Math.min(24, Math.max(14, nextFontSize || 18));
    setFontSize(safeFontSize);
    try {
      const response = await patchPreferences({ font_size: safeFontSize });
      setPreferences(response.preferences);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "字号偏好保存失败");
    }
  }

  async function updateEditorBackgroundPreference(
    nextBackground: EditorPreferences["editor_background"],
  ) {
    setEditorBackground(nextBackground);
    try {
      const response = await patchPreferences({
        editor_background: nextBackground,
      });
      setPreferences(response.preferences);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "边框偏好保存失败");
    }
  }

  async function renameVolumeName(volume: OutlineVolume) {
    const requestedName = window.prompt("请输入卷名", volume.name);
    if (requestedName === null) {
      return;
    }
    const name = requestedName.trim();
    if (!name || name === volume.name) {
      return;
    }
    try {
      setOutline((await renameVolume(volume.volume_id, name)).outline);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "分卷重命名失败");
    }
  }

  async function removeVolume(volume: OutlineVolume) {
    if (saveState === "dirty" || saveState === "error") {
      const saved = await persistChapter();
      if (!saved) {
        return;
      }
    }
    const confirmed = window.confirm(
      `确认删除“${volume.name}”？该卷下 ${volume.chapters.length} 章正文会移动到删除章节目录。`,
    );
    if (!confirmed) {
      return;
    }
    try {
      const nextOutline = (await deleteVolume(volume.volume_id)).outline;
      setOutline(nextOutline);
      const nextChapterId = nextOutline.current_chapter_id;
      if (nextChapterId) {
        await loadChapter(nextChapterId);
        return;
      }
      clearActiveChapter();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除分卷失败");
    }
  }

  async function addChapter(volumeId: string, afterChapterId?: string | null) {
    try {
      const nextOutline = (await createChapter(volumeId, null, afterChapterId)).outline;
      setOutline(nextOutline);
      const chapterId = nextOutline.current_chapter_id;
      if (chapterId) {
        await loadChapter(chapterId);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建章节失败");
    }
  }

  async function addChapterToCurrentVolume() {
    const targetVolumeId =
      activeChapter?.volume_id ??
      outline?.current_volume_id ??
      outline?.volumes[0]?.volume_id;
    if (!targetVolumeId) {
      setError("请先新建分卷");
      return;
    }
    const afterChapterId =
      activeChapter?.volume_id === targetVolumeId ? activeChapter.id : null;
    await addChapter(targetVolumeId, afterChapterId);
  }

  async function removeChapter(chapter: OutlineChapter) {
    if (saveState === "dirty" || saveState === "error") {
      const saved = await persistChapter();
      if (!saved) {
        return;
      }
    }
    const confirmed = window.confirm(
      `确认删除“${chapter.display_title}”？章节正文会移动到删除章节目录。`,
    );
    if (!confirmed) {
      return;
    }
    try {
      const nextOutline = (await deleteChapter(chapter.chapter_id)).outline;
      setOutline(nextOutline);
      const nextChapterId = nextOutline.current_chapter_id;
      if (nextChapterId) {
        await loadChapter(nextChapterId);
        return;
      }
      clearActiveChapter();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除章节失败");
    }
  }

  function toggleVolume(volumeId: string) {
    setCollapsedVolumeIds(current => {
      const next = new Set(current);
      if (next.has(volumeId)) {
        next.delete(volumeId);
      } else {
        next.add(volumeId);
      }
      return next;
    });
  }

  function updateChapterTitleDraft(nextTitle: string) {
    const chapterId = activeChapter?.id;
    setChapterTitleDraft(nextTitle);
    if (!chapterId) {
      return;
    }
    if (activeChapterRef.current?.id === chapterId) {
      activeChapterRef.current = {
        ...activeChapterRef.current,
        title: nextTitle,
      };
    }
    setActiveChapter(current =>
      current?.id === chapterId ? { ...current, title: nextTitle } : current,
    );
    setOutline(current =>
      updateOutlineChapterTitle(current, chapterId, nextTitle),
    );
  }

  async function commitChapterTitle() {
    const chapter = activeChapterRef.current;
    if (!chapter) {
      return;
    }
    const nextTitle = chapterTitleDraft.trim();
    if (nextTitle === savedChapterTitleRef.current) {
      updateChapterTitleDraft(nextTitle);
      return;
    }
    try {
      const response = await renameChapter(chapter.id, nextTitle);
      const savedTitle =
        activeChapterTitle(response.outline, chapter.id) ?? nextTitle;
      const savedTitleBody = chapterTitleBody(savedTitle);
      savedChapterTitleRef.current = savedTitleBody;
      setOutline(response.outline);
      activeChapterRef.current = { ...chapter, title: savedTitle };
      setActiveChapter(current =>
        current?.id === chapter.id ? { ...current, title: savedTitle } : current,
      );
      setChapterTitleDraft(savedTitleBody);
      setError(null);
    } catch (caught) {
      const fallbackTitle = savedChapterTitleRef.current || chapter.title;
      activeChapterRef.current = { ...chapter, title: fallbackTitle };
      setChapterTitleDraft(chapterTitleBody(fallbackTitle));
      setActiveChapter(current =>
        current?.id === chapter.id
          ? { ...current, title: fallbackTitle }
          : current,
      );
      setOutline(current =>
        updateOutlineChapterTitle(current, chapter.id, fallbackTitle),
      );
      setError(caught instanceof Error ? caught.message : "章节标题保存失败");
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

  function formatFullText() {
    if (!markdown.trim()) {
      setError("当前正文为空，无法排版");
      return;
    }
    const formatted = formatNovelParagraphs(markdown);
    updateMarkdown(formatted);
    setSelection(null);
    setError(null);
  }

  function selectAiTool(entryKey: AIEntryKey) {
    if (isAssistantPanelOpen && selectedAiTool === entryKey) {
      closeAssistantPanel();
      return;
    }
    setSelectedAiTool(entryKey);
    openAssistantPanel();
    setAIError(null);
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
      const referenceScope = referenceScopeFor(
        activeEntry.taskType,
        selection,
        referenceRange,
      );
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

  const editorToolbar = (
    <div className="flex min-w-max flex-wrap items-center justify-end gap-2">
      <span className="hidden rounded-full border border-[var(--tc-stone-mist)] px-3 py-1 text-xs text-[var(--tc-smoke)] 2xl:inline-flex">
        {statusText(saveState, loading)}
      </span>
      <label className="flex h-9 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm">
        <Type className="size-4" />
        字号
        <input
          type="number"
          min={14}
          max={24}
          value={fontSize}
          onChange={event =>
            void updateFontSizePreference(Number(event.target.value))
          }
          className="w-12 bg-transparent text-center outline-none"
        />
      </label>
      <div className="relative">
        <Button
          type="button"
          variant="outline"
          className="h-9"
          aria-expanded={isBackgroundMenuOpen}
          onClick={() => setBackgroundMenuOpen(current => !current)}
        >
          <Palette className="size-4" />
          背景
          <span
            className="size-4 rounded-[5px] border border-[var(--tc-stone-mist)]"
            style={{ background: activePaperTone.swatch }}
            aria-hidden="true"
          />
        </Button>
        {isBackgroundMenuOpen ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-[360px] rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
            <div className="mb-3 flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-[var(--tc-midnight-ink)]">
                编辑背景
              </span>
              <button
                type="button"
                onClick={() => setBackgroundMenuOpen(false)}
                className="text-xs text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
              >
                收起
              </button>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {editorPaperTones.map(tone => (
                <button
                  key={tone.key}
                  type="button"
                  onClick={() => {
                    writeStoredPaperToneKey(tone.key);
                    setBackgroundMenuOpen(false);
                  }}
                  className="group text-center text-xs text-[var(--tc-smoke)]"
                  aria-pressed={tone.key === paperToneKey}
                >
                  <span
                    className={cn(
                      "mb-1 block h-10 rounded-[var(--tc-radius-control)] border transition",
                      tone.key === paperToneKey
                        ? "border-[var(--tc-workspace-focus)] ring-2 ring-[var(--tc-workspace-focus)]"
                        : "border-[var(--tc-stone-mist)] group-hover:border-[var(--tc-midnight-ink)]",
                    )}
                    style={{ background: tone.swatch }}
                  />
                  <span className="block truncate">{tone.label}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <select
        value={editorBackground}
        onChange={event =>
          void updateEditorBackgroundPreference(
            event.target.value as EditorPreferences["editor_background"],
          )
        }
        className="h-9 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm"
        aria-label="编辑背景"
      >
        <option value="soft">柔色纸面</option>
        <option value="dark">无边框</option>
      </select>
      <IconButton label="撤销" onClick={runUndo}>
        <Undo2 className="size-4" />
      </IconButton>
      <IconButton label="恢复" onClick={runRedo}>
        <Redo2 className="size-4" />
      </IconButton>
      <label className="flex h-9 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 text-sm">
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
      <Button type="button" variant="outline" onClick={formatFullText}>
        一键全文排版
      </Button>
      <Button
        type="button"
        variant={saveDisabled ? "secondary" : "default"}
        onClick={() => void persistChapter()}
        disabled={saveDisabled}
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
  );

  return (
    <AppShell
      activePath="/editor"
      escapeToHome
      showNavigation={false}
      headerActions={editorToolbar}
    >
      <div className="flex min-h-[calc(100vh-57px)] flex-col bg-[var(--tc-workspace-bg)] xl:h-[calc(100vh-57px)] xl:flex-row xl:overflow-hidden">
        <aside className="flex shrink-0 flex-col border-b border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-[280px] xl:border-b-0 xl:border-r">
          <div className="shrink-0 px-4 pb-3 pt-4">
            <p className="text-xs text-[var(--tc-smoke)]">写作</p>
            <h1 className="mt-1 text-2xl font-semibold text-[var(--tc-midnight-ink)]">
              分卷章节大纲
            </h1>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <Button
                type="button"
                onClick={() => void addChapterToCurrentVolume()}
                className="h-9 text-sm"
              >
                <Plus className="size-4" />
                新建章
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={addVolume}
                className="h-9 text-sm"
              >
                <FilePlus2 className="size-4" />
                新建卷
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-3">
            {outline?.volumes.map(volume => {
              const collapsed = collapsedVolumeIds.has(volume.volume_id);
              return (
                <section
                  key={volume.volume_id}
                  className="rounded-[18px] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-2.5"
                >
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => toggleVolume(volume.volume_id)}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-sm font-semibold text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
                    >
                      {collapsed ? (
                        <ChevronRight className="size-4 shrink-0" />
                      ) : (
                        <ChevronDown className="size-4 shrink-0" />
                      )}
                      <span className="truncate">{volume.name}</span>
                    </button>
                    <button
                      type="button"
                      title="新建章节"
                      onClick={() => void addChapter(volume.volume_id)}
                      className="inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
                    >
                      <Plus className="size-4" />
                    </button>
                    <button
                      type="button"
                      title="重命名卷"
                      aria-label={`重命名${volume.name}`}
                      onClick={() => void renameVolumeName(volume)}
                      className="inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                    >
                      <PenLine className="size-4" />
                    </button>
                    <button
                      type="button"
                      title="删除卷"
                      aria-label={`删除${volume.name}`}
                      onClick={() => void removeVolume(volume)}
                      className="inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                  {!collapsed ? (
                    <div className="mt-2 space-y-0.5">
                      {volume.chapters.map(chapter => {
                        const active = activeChapter?.id === chapter.chapter_id;
                        return (
                          <div
                            key={chapter.chapter_id}
                            className={cn(
                              "group relative flex w-full items-center rounded-[14px] transition-colors",
                              active
                                ? "bg-[color-mix(in_srgb,var(--tc-workspace-text)_6%,transparent)] font-medium text-[var(--tc-midnight-ink)]"
                                : "text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]",
                            )}
                          >
                            <span
                              className={cn(
                                "absolute bottom-2 left-0 top-2 w-1 rounded-full",
                                active
                                  ? "bg-[var(--tc-midnight-ink)]"
                                  : "bg-transparent",
                              )}
                              aria-hidden="true"
                            />
                            <button
                              type="button"
                              onClick={() => void switchChapter(chapter.chapter_id)}
                              className="min-w-0 flex-1 truncate px-3 py-2 pr-2 text-left text-[13px] outline-none"
                            >
                              {chapter.display_title}
                            </button>
                            <button
                              type="button"
                              title="删除章节"
                              aria-label={`删除${chapter.display_title}`}
                              onClick={() => void removeChapter(chapter)}
                              className="mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] opacity-100 transition hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)] focus:opacity-100 md:opacity-0 md:group-hover:opacity-100"
                            >
                              <Trash2 className="size-4" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>

          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-[var(--tc-stone-mist)] px-4 py-2.5 text-xs text-[var(--tc-smoke)]">
            <span className="flex items-center gap-2">
              <BookOpen className="size-4" />
              共 {volumeCount} 卷 · {chapterCount} 章
            </span>
            <MoreVertical className="size-4" />
          </div>
        </aside>

        <section
          className="flex min-w-0 flex-1 flex-col bg-[var(--tc-workspace-bg)]"
          style={
            {
              background: activePaperTone.surface,
              color: activePaperTone.ink,
              "--tc-editor-selection-bg": activePaperTone.selection,
            } as CSSProperties
          }
        >
          <div
            className="min-h-0 flex-1 overflow-y-auto px-3 py-3 md:px-6 md:py-5 xl:px-10"
            style={{ scrollbarGutter: "stable" }}
          >
            {error ? (
              <div className="tc-warning mb-4 rounded-[var(--tc-radius-control)] border px-4 py-3 text-sm">
                {error}
              </div>
            ) : null}
            <div
              className={cn(
                "mx-auto min-h-[calc(100vh-150px)] w-full max-w-[760px] border shadow-none",
                editorBackground === "dark"
                  ? "border-transparent"
                  : "border-[var(--tc-stone-mist)]",
              )}
              style={{
                color: activePaperTone.ink,
              } as CSSProperties}
            >
              <div className="px-6 pb-8 pt-6 md:px-10 md:pb-10 md:pt-8">
                <p className="mb-3 text-xs opacity-65">
                  {statusText(saveState, loading)}
                </p>
                <div className="flex min-w-0 items-baseline gap-3">
                  <span
                    className="shrink-0 font-serif"
                    style={{
                      color: activePaperTone.ink,
                      fontSize: `${Math.round(fontSize * 1.55)}px`,
                      lineHeight: "1.28",
                    }}
                  >
                    {currentChapterPrefix}
                  </span>
                  <input
                    value={chapterTitleDraft}
                    onChange={event => updateChapterTitleDraft(event.target.value)}
                    onBlur={() => void commitChapterTitle()}
                    onKeyDown={event => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        event.currentTarget.blur();
                      }
                    }}
                    disabled={!activeChapter || loading}
                    className="min-w-0 flex-1 bg-transparent font-serif outline-none placeholder:opacity-60 selection:bg-[var(--tc-editor-selection-bg)] selection:text-[inherit]"
                    style={{
                      color: activePaperTone.ink,
                      fontSize: `${Math.round(fontSize * 1.55)}px`,
                      lineHeight: "1.28",
                    }}
                    placeholder={currentChapterTitle ? "章节标题" : "未选择章节"}
                    aria-label="章节标题"
                  />
                </div>
              </div>
              <textarea
                ref={textareaRef}
                value={markdown}
                onChange={event => updateMarkdown(event.target.value)}
                onSelect={updateSelection}
                onKeyUp={updateSelection}
                onMouseUp={updateSelection}
                disabled={!activeChapter || loading}
                spellCheck={false}
                className="block min-h-[calc(100vh-330px)] w-full resize-none overflow-hidden bg-transparent px-6 pb-10 pt-0 font-[var(--tc-font-ui)] leading-[2.05] outline-none selection:bg-[var(--tc-editor-selection-bg)] selection:text-[inherit] md:px-10 md:pb-12"
                style={{
                  color: activePaperTone.ink,
                  fontSize: `${fontSize}px`,
                }}
                placeholder="在这里写正文"
              />
            </div>
          </div>
        </section>

        {isAssistantPanelOpen ? (
          <aside className="flex shrink-0 flex-col border-t border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-[400px] xl:border-l xl:border-t-0">
            <header className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--tc-stone-mist)] px-4 py-3">
              <div className="min-w-0">
                <p className="text-xs text-[var(--tc-smoke)]">
                  {brandMode ? "器灵入口" : "AI 入口"}
                </p>
                <h2 className="truncate font-serif text-2xl text-[var(--tc-midnight-ink)]">
                  {brandMode ? activeEntry.brandLabel : activeEntry.label}
                </h2>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setBrandMode(current => !current)}
                  className="rounded-full border border-[var(--tc-stone-mist)] px-3 py-1 text-xs text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
                >
                  {brandMode ? "清晰名" : "品牌名"}
                </button>
                <button
                  type="button"
                  aria-label="关闭助手面板"
                  title="关闭助手面板"
                  onClick={closeAssistantPanel}
                  className="inline-flex size-9 items-center justify-center rounded-[var(--tc-radius-small)] border border-[var(--tc-stone-mist)] text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
                >
                  <X className="size-4" />
                </button>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <AIMessageList
                entryKey={selectedAiTool}
                localMessages={localChatMessages}
                conversation={activeConversation}
                showPromptSnapshot={showPromptSnapshot}
                onTogglePromptSnapshot={() =>
                  setShowPromptSnapshot(current => !current)
                }
              />
            </div>

            <div className="shrink-0 border-t border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-4">
              <div className="mb-3 grid gap-2 text-xs sm:grid-cols-2">
                <label className="flex items-center justify-between gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2">
                  <span className="text-[var(--tc-smoke)]">参考范围</span>
                  <select
                    value={referenceRange}
                    onChange={event =>
                      setReferenceRange(event.target.value as ReferenceRangeChoice)
                    }
                    className="bg-transparent text-right text-[var(--tc-midnight-ink)] outline-none"
                    aria-label="参考范围"
                    disabled={activeEntry.key === "chapter_summary"}
                  >
                    <option value="auto">自动</option>
                    <option value="chapter">本章</option>
                    <option value="selection" disabled={!selection}>
                      选区
                    </option>
                  </select>
                </label>
                <span className="flex items-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-[var(--tc-smoke)]">
                  当前参考：{referenceScopeLabel(currentReferenceScope)}
                </span>
                {activeConversation?.is_mock ? (
                  <span className="flex items-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-[var(--tc-smoke)]">
                    模拟输出
                  </span>
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
                  {aiBusy ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Send className="size-4" />
                  )}
                  发送
                </Button>
                <Link
                  href="/ai-history"
                  className="inline-flex h-8 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
                >
                  <History className="size-4" />
                  查找对话
                </Link>
                {activeEntry.taskType ? (
                  <button
                    type="button"
                    onClick={() =>
                      setConversations(current => ({
                        ...current,
                        [selectedAiTool]: undefined,
                      }))
                    }
                    className="inline-flex h-8 items-center gap-2 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
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
          </aside>
        ) : null}

        <aside className="shrink-0 border-t border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-16 xl:border-l xl:border-t-0">
          <div className="flex gap-1 overflow-x-auto p-2 xl:h-full xl:flex-col xl:items-stretch xl:overflow-visible">
            {aiEntries.map(entry => (
              <button
                key={entry.key}
                type="button"
                aria-label={`${brandMode ? entry.brandLabel : entry.label}入口`}
                aria-pressed={selectedAiTool === entry.key}
                title={`${brandMode ? entry.brandLabel : entry.label}入口`}
                onClick={() => selectAiTool(entry.key)}
                className={cn(
                  "group relative flex h-12 min-w-12 flex-col items-center justify-center gap-0.5 rounded-[var(--tc-radius-small)] border text-[10px] leading-none transition-colors xl:min-w-0",
                  selectedAiTool === entry.key
                    ? "border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-panel-soft)] text-[var(--tc-midnight-ink)]"
                    : "border-transparent text-[var(--tc-smoke)] hover:border-[var(--tc-stone-mist)] hover:bg-[var(--tc-cream-paper)] hover:text-[var(--tc-midnight-ink)]",
                )}
              >
                <AIEntryIcon entryKey={entry.key} className="size-4" />
                <span>{brandMode ? entry.brandLabel : entry.label}</span>
                <span className="pointer-events-none absolute right-[calc(100%+8px)] top-1/2 z-20 hidden -translate-y-1/2 whitespace-nowrap rounded-[var(--tc-radius-small)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-2 py-1 text-xs text-[var(--tc-midnight-ink)] opacity-0 shadow-sm transition-opacity group-hover:opacity-100 xl:block">
                  {brandMode ? entry.brandLabel : entry.label}
                </span>
              </button>
            ))}
          </div>
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

function AIEntryIcon({
  entryKey,
  className,
}: {
  entryKey: AIEntryKey;
  className?: string;
}) {
  if (entryKey === "chat") {
    return <MessageSquare className={className} />;
  }
  if (entryKey === "continue") {
    return <Sparkles className={className} />;
  }
  if (entryKey === "polish") {
    return <PenLine className={className} />;
  }
  if (entryKey === "setting") {
    return <SlidersHorizontal className={className} />;
  }
  if (entryKey === "suggestion") {
    return <Lightbulb className={className} />;
  }
  if (entryKey === "evidence") {
    return <SearchCheck className={className} />;
  }
  if (entryKey === "chapter_summary") {
    return <FileText className={className} />;
  }
  if (entryKey === "inspiration") {
    return <BookmarkPlus className={className} />;
  }
  return <BadgeCheck className={className} />;
}

function outlineChapters(outline: WritingOutline | null): OutlineChapter[] {
  return (
    outline?.volumes.flatMap(volume =>
      [...volume.chapters].sort((left, right) => left.order - right.order),
    ) ?? []
  );
}

function updateOutlineChapterTitle(
  outline: WritingOutline | null,
  chapterId: string,
  displayTitle: string,
): WritingOutline | null {
  if (!outline) {
    return outline;
  }
  const nextTitleBody = chapterTitleBody(displayTitle);
  return {
    ...outline,
    volumes: outline.volumes.map(volume => ({
      ...volume,
      chapters: volume.chapters.map(chapter =>
        chapter.chapter_id === chapterId
          ? {
              ...chapter,
              display_title: formatChapterDisplayTitle(
                chapter.order,
                nextTitleBody,
              ),
            }
          : chapter,
      ),
    })),
  };
}

function outlineChapterById(
  outline: WritingOutline | null,
  chapterId?: string | null,
): OutlineChapter | null {
  if (!chapterId) {
    return null;
  }
  return (
    outlineChapters(outline).find(chapter => chapter.chapter_id === chapterId) ??
    null
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

function chapterNumberLabel(order: number): string {
  return `第${order}章`;
}

function chapterTitleBody(title: string): string {
  return title
    .trim()
    .replace(/^第[0-9零〇一二三四五六七八九十百千万两]+章[\s\u3000:：、-]*/, "")
    .trim();
}

function formatChapterDisplayTitle(order: number, titleBody: string): string {
  const prefix = chapterNumberLabel(order);
  const body = chapterTitleBody(titleBody);
  return body ? `${prefix} ${body}` : prefix;
}

function readStoredPaperToneKey(): EditorPaperToneKey {
  if (typeof window === "undefined") {
    return "mist";
  }
  const storedTone = window.localStorage.getItem(EDITOR_PAPER_TONE_STORAGE_KEY);
  if (editorPaperTones.some(tone => tone.key === storedTone)) {
    return storedTone as EditorPaperToneKey;
  }
  return "mist";
}

function writeStoredPaperToneKey(paperToneKey: EditorPaperToneKey) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EDITOR_PAPER_TONE_STORAGE_KEY, paperToneKey);
  window.dispatchEvent(new Event(EDITOR_PAPER_TONE_EVENT));
}

function subscribeStoredPaperToneKey(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(EDITOR_PAPER_TONE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(EDITOR_PAPER_TONE_EVENT, onStoreChange);
  };
}

function readStoredCollapsedVolumeIds(): Set<string> {
  if (typeof window === "undefined") {
    return new Set();
  }
  try {
    const raw = window.localStorage.getItem(
      EDITOR_COLLAPSED_VOLUMES_STORAGE_KEY,
    );
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(parsed)) {
      return new Set();
    }
    return new Set(parsed.filter(item => typeof item === "string"));
  } catch {
    return new Set();
  }
}

function writeStoredCollapsedVolumeIds(volumeIds: Set<string>) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(
    EDITOR_COLLAPSED_VOLUMES_STORAGE_KEY,
    JSON.stringify([...volumeIds]),
  );
}

function readStoredActiveChapterId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(EDITOR_ACTIVE_CHAPTER_STORAGE_KEY);
}

function writeStoredActiveChapterId(chapterId: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EDITOR_ACTIVE_CHAPTER_STORAGE_KEY, chapterId);
}

function clearStoredActiveChapterId() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(EDITOR_ACTIVE_CHAPTER_STORAGE_KEY);
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
  range: ReferenceRangeChoice = "auto",
): AIReferenceScope {
  if (taskType === "chapter_summary") {
    return "chapter";
  }
  if (range === "chapter") {
    return "chapter";
  }
  if (range === "selection") {
    return selection ? "selection" : "chapter";
  }
  return selection ? "selection" : "chapter";
}

function referenceScopeLabel(scope: AIReferenceScope): string {
  return scope === "selection" ? "选区" : "本章";
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
