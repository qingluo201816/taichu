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
  AlignLeft,
  BadgeCheck,
  Baseline,
  Book,
  Bot,
  BookOpen,
  BookmarkPlus,
  CaseSensitive,
  Check,
  Copy,
  FileText,
  History,
  Lightbulb,
  Loader2,
  MessageSquare,
  MoreVertical,
  Palette,
  PenLine,
  Plus,
  Redo2,
  RefreshCcw,
  Rows3,
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

import { AppShell } from "@/components/app-shell";
import { ModelSelector } from "@/components/llm/model-selector";
import { Button } from "@/components/ui/button";
import { useModelSelection } from "@/hooks/use-model-selection";
import {
  listChapterSummaries,
  readChapter,
  saveChapter,
} from "@/lib/api/chapters";
import {
  createChapter,
  createVolume,
  deleteChapter,
  deleteVolume,
  patchPreferences,
  readOutline,
  readPreferences,
  renameChapter,
  renameVolume,
} from "@/lib/api/mvp";
import {
  getWritingAIRun,
  listWritingAIRuns,
  replayWritingAIRun,
  streamWritingAIRun,
} from "@/lib/api/writing-ai";
import {
  humanReadableListItem,
  humanReadableStructuredContent,
} from "@/lib/ai/human-readable-content";
import { formatNovelParagraphs } from "@/lib/editor/markdown";
import {
  appendWritingStreamText,
  writingStreamFailure,
} from "@/lib/llm/view-model";
import type { ChapterInfo, ChapterSummaryInfo } from "@/lib/types/chapters";
import type {
  EditorPreferences,
  OutlineChapter,
  OutlineVolume,
  WritingOutline,
} from "@/lib/types/mvp";
import type {
  WritingAIButtonType,
  WritingAIReferenceScope,
  WritingAIRetrievalEvidenceItem,
  WritingAIRun,
} from "@/lib/types/writing-ai";
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
  placeholder: string;
  buttonType: WritingAIButtonType;
};

type TextSelection = {
  start: number;
  end: number;
  text: string;
};

type ReferenceRangeChoice = WritingAIReferenceScope;
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
  isDark: boolean;
  pageBackground: string;
  toolbarBackground: string;
  sidebarBackground: string;
  rightRailBackground: string;
  canvasBackground: string;
  paperBackground: string;
  panelBackground: string;
  panelSoftBackground: string;
  border: string;
  borderSoft: string;
  swatch: string;
  ink: string;
  muted: string;
  focus: string;
  selection: string;
};

type EditorTypographyMenu = "fontSize" | "lineHeight" | "lineWidth" | "font";

type EditorFontKey =
  | "hyQiHei"
  | "lxgwWenkai"
  | "songti"
  | "kaiti"
  | "sourceSerif";

type EditorFontOption = {
  key: EditorFontKey;
  label: string;
  fontFamily: string;
};

type EditorToastTone = "success" | "info" | "error";

type EditorToastState = {
  id: number;
  message: string;
  tone: EditorToastTone;
};

const EDITOR_PAPER_TONE_STORAGE_KEY = "taichu-editor-paper-tone";
const EDITOR_PAPER_TONE_EVENT = "taichu-editor-paper-tone-change";
const EDITOR_COLLAPSED_VOLUMES_STORAGE_KEY = "taichu-editor-collapsed-volumes";
const EDITOR_ACTIVE_CHAPTER_STORAGE_KEY = "taichu-editor-active-chapter";
const EDITOR_LINE_HEIGHT_STORAGE_KEY = "taichu-editor-line-height";
const EDITOR_LINE_WIDTH_STORAGE_KEY = "taichu-editor-line-width";
const EDITOR_FONT_STORAGE_KEY = "taichu-editor-font";
const DEFAULT_EDITOR_LINE_HEIGHT = 1.72;
const DEFAULT_EDITOR_LINE_WIDTH = 760;
const DEFAULT_EDITOR_FONT_KEY: EditorFontKey = "hyQiHei";
const editorLineHeightRange = { min: 1.45, max: 2.2, step: 0.01 };
const editorLineWidthRange = { min: 620, max: 980, step: 10 };

const editorFontOptions: EditorFontOption[] = [
  {
    key: "hyQiHei",
    label: "汉仪旗黑（默认）",
    fontFamily:
      '"HYQiHei", "Hanyi Qihei", var(--tc-font-ui), "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  {
    key: "lxgwWenkai",
    label: "霞鹜文楷",
    fontFamily:
      '"LXGW WenKai", "霞鹜文楷", "STKaiti", "KaiTi", "Kaiti SC", serif',
  },
  {
    key: "songti",
    label: "宋体",
    fontFamily: '"Songti SC", "SimSun", "Noto Serif SC", serif',
  },
  {
    key: "kaiti",
    label: "楷体",
    fontFamily: '"Kaiti SC", "KaiTi", "STKaiti", serif',
  },
  {
    key: "sourceSerif",
    label: "思源宋体",
    fontFamily:
      '"Source Han Serif SC", "Noto Serif CJK SC", "Noto Serif SC", "Songti SC", serif',
  },
];

const editorPaperTones: EditorPaperTone[] = [
  {
    key: "mist",
    label: "凝神雾灰",
    isDark: false,
    pageBackground: "#e6e7e9",
    toolbarBackground: "#f1f2f4",
    sidebarBackground: "#eeeef0",
    rightRailBackground: "#f2f2f3",
    canvasBackground: "#ececef",
    paperBackground: "#f7f7f8",
    panelBackground: "#f5f5f6",
    panelSoftBackground: "#eeeeef",
    border: "#c8c9cc",
    borderSoft: "#d9dade",
    swatch: "#f7f7f8",
    ink: "#202124",
    muted: "#6d7076",
    focus: "#4d5560",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "charcoal",
    label: "墨夜炭灰",
    isDark: true,
    pageBackground: "#1b1c1f",
    toolbarBackground: "#18191c",
    sidebarBackground: "#1f2023",
    rightRailBackground: "#1c1d20",
    canvasBackground: "#232428",
    paperBackground: "#202124",
    panelBackground: "#25262a",
    panelSoftBackground: "#2d2e33",
    border: "#42444a",
    borderSoft: "#33353a",
    swatch: "#202124",
    ink: "#eceff3",
    muted: "#a9adb6",
    focus: "#d8dde8",
    selection: "rgba(255, 255, 255, 0.18)",
  },
  {
    key: "obsidian",
    label: "玄墨静夜",
    isDark: true,
    pageBackground: "#101012",
    toolbarBackground: "#0c0c0e",
    sidebarBackground: "#141416",
    rightRailBackground: "#111113",
    canvasBackground: "#17171a",
    paperBackground: "#141416",
    panelBackground: "#19191d",
    panelSoftBackground: "#202026",
    border: "#33333a",
    borderSoft: "#25252b",
    swatch: "#141416",
    ink: "#f1f1ee",
    muted: "#aaa9a4",
    focus: "#e4e2d8",
    selection: "rgba(255, 255, 255, 0.2)",
  },
  {
    key: "blueNight",
    label: "夜读蓝黑",
    isDark: true,
    pageBackground: "#121821",
    toolbarBackground: "#101722",
    sidebarBackground: "#17202b",
    rightRailBackground: "#141c27",
    canvasBackground: "#1a2430",
    paperBackground: "#18202b",
    panelBackground: "#1d2a38",
    panelSoftBackground: "#243243",
    border: "#3b4b60",
    borderSoft: "#2d3a4b",
    swatch: "#1d2a38",
    ink: "#edf3fb",
    muted: "#a6b6ca",
    focus: "#a6cdff",
    selection: "rgba(166, 205, 255, 0.22)",
  },
  {
    key: "pineNight",
    label: "青林松夜",
    isDark: true,
    pageBackground: "#111a17",
    toolbarBackground: "#0f1714",
    sidebarBackground: "#17231f",
    rightRailBackground: "#141e1b",
    canvasBackground: "#1a2823",
    paperBackground: "#18231f",
    panelBackground: "#1f302a",
    panelSoftBackground: "#263a32",
    border: "#3d594e",
    borderSoft: "#30453d",
    swatch: "#1f302a",
    ink: "#ecf4ef",
    muted: "#a9bdb4",
    focus: "#a9e6cc",
    selection: "rgba(169, 230, 204, 0.2)",
  },
  {
    key: "green",
    label: "养目浅青",
    isDark: false,
    pageBackground: "#cddfce",
    toolbarBackground: "#d9ead9",
    sidebarBackground: "#d3e4d3",
    rightRailBackground: "#d9ead9",
    canvasBackground: "#d2e5d3",
    paperBackground: "#dceedd",
    panelBackground: "#e8f4e8",
    panelSoftBackground: "#d3e5d4",
    border: "#a9bea9",
    borderSoft: "#bfd2bf",
    swatch: "#c8dfc8",
    ink: "#1d2b20",
    muted: "#526855",
    focus: "#3f6d4c",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "classic",
    label: "书页暖黄",
    isDark: false,
    pageBackground: "#ded2b7",
    toolbarBackground: "#e9dec6",
    sidebarBackground: "#e6dbc4",
    rightRailBackground: "#e7dcc4",
    canvasBackground: "#e5d8be",
    paperBackground: "#f0e6cf",
    panelBackground: "#f5ecd9",
    panelSoftBackground: "#e8dcc3",
    border: "#b6a686",
    borderSoft: "#cfbf9f",
    swatch: "#e5d9bd",
    ink: "#2a2318",
    muted: "#6c5b3e",
    focus: "#7a6038",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "blue",
    label: "静蓝晨雾",
    isDark: false,
    pageBackground: "#d5e1ef",
    toolbarBackground: "#e0eaf5",
    sidebarBackground: "#dce7f3",
    rightRailBackground: "#e0eaf5",
    canvasBackground: "#d9e5f2",
    paperBackground: "#e5edf6",
    panelBackground: "#eff5fb",
    panelSoftBackground: "#d8e4f0",
    border: "#aebbd0",
    borderSoft: "#c5d1e2",
    swatch: "#d0dcea",
    ink: "#1f2834",
    muted: "#5e6b7a",
    focus: "#54708e",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "pink",
    label: "桃笺淡粉",
    isDark: false,
    pageBackground: "#e8d5dc",
    toolbarBackground: "#f2e0e6",
    sidebarBackground: "#eedce2",
    rightRailBackground: "#f1e0e6",
    canvasBackground: "#ebdae0",
    paperBackground: "#f4e4e8",
    panelBackground: "#faedf0",
    panelSoftBackground: "#ead6dc",
    border: "#c8aeb8",
    borderSoft: "#dcc6ce",
    swatch: "#ead6dc",
    ink: "#302226",
    muted: "#765d66",
    focus: "#9a6678",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "peach",
    label: "晨桃暖光",
    isDark: false,
    pageBackground: "#f2d8cb",
    toolbarBackground: "#fae7dc",
    sidebarBackground: "#f7e1d5",
    rightRailBackground: "#fae7dc",
    canvasBackground: "#f6dfd1",
    paperBackground: "linear-gradient(135deg, #fff4ef 0%, #ffe2cf 100%)",
    panelBackground: "#fff1e9",
    panelSoftBackground: "#f3d3c3",
    border: "#d8a891",
    borderSoft: "#eac7b6",
    swatch: "linear-gradient(135deg, #fff4ef 0%, #f7bda4 100%)",
    ink: "#2f211c",
    muted: "#75584d",
    focus: "#b86d4e",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "snow",
    label: "明净素白",
    isDark: false,
    pageBackground: "#e6e6e3",
    toolbarBackground: "#f4f4f1",
    sidebarBackground: "#eeeeeb",
    rightRailBackground: "#f3f3f0",
    canvasBackground: "#ecece8",
    paperBackground: "linear-gradient(135deg, #ffffff 0%, #f0f0ed 100%)",
    panelBackground: "#fafaf7",
    panelSoftBackground: "#e7e7e2",
    border: "#c5c5bf",
    borderSoft: "#d8d8d1",
    swatch: "linear-gradient(135deg, #ffffff 0%, #e7e7e2 100%)",
    ink: "#242526",
    muted: "#666864",
    focus: "#5d6570",
    selection: "rgba(0, 0, 0, 0.14)",
  },
  {
    key: "aqua",
    label: "青水远山",
    isDark: false,
    pageBackground: "#cfe3df",
    toolbarBackground: "#e4f4f1",
    sidebarBackground: "#dbede9",
    rightRailBackground: "#e5f4f1",
    canvasBackground: "#d8ebe7",
    paperBackground: "linear-gradient(135deg, #f2fffc 0%, #d8f1ee 100%)",
    panelBackground: "#f2fffc",
    panelSoftBackground: "#cfe7e2",
    border: "#9fbfba",
    borderSoft: "#b8d7d2",
    swatch: "linear-gradient(135deg, #f2fffc 0%, #bfe5df 100%)",
    ink: "#1c2d2b",
    muted: "#56706c",
    focus: "#348378",
    selection: "rgba(0, 0, 0, 0.14)",
  },
];

function editorThemeVariables(tone: EditorPaperTone): CSSProperties {
  const primaryText = tone.isDark ? tone.pageBackground : tone.panelBackground;

  return {
    colorScheme: tone.isDark ? "dark" : "light",
    "--tc-editor-selection-bg": tone.selection,
    "--tc-editor-scrollbar-track": tone.paperBackground,
    "--tc-editor-scrollbar-thumb": tone.border,
    "--tc-editor-scrollbar-thumb-hover": tone.focus,
    "--tc-workspace-bg": tone.pageBackground,
    "--tc-workspace-shell": tone.toolbarBackground,
    "--tc-workspace-panel": tone.panelBackground,
    "--tc-workspace-panel-soft": tone.panelSoftBackground,
    "--tc-workspace-recess": tone.canvasBackground,
    "--tc-workspace-editor": tone.paperBackground,
    "--tc-workspace-border": tone.border,
    "--tc-workspace-border-weak": tone.borderSoft,
    "--tc-workspace-text": tone.ink,
    "--tc-workspace-text-secondary": tone.muted,
    "--tc-workspace-focus": tone.focus,
    "--tc-nav-bg": tone.toolbarBackground,
    "--tc-nav-border": tone.borderSoft,
    "--tc-midnight-ink": tone.ink,
    "--tc-smoke": tone.muted,
    "--tc-stone-mist": tone.border,
    "--tc-white": tone.panelBackground,
    "--tc-cream-paper": tone.panelSoftBackground,
    "--tc-deep-forest-teal": tone.focus,
    "--tc-action-primary-bg": tone.focus,
    "--tc-action-primary-text": primaryText,
    "--tc-action-primary-border": tone.focus,
    "--tc-action-primary-hover-bg": `color-mix(in srgb, ${tone.focus} 88%, ${tone.pageBackground} 12%)`,
  } as CSSProperties;
}

const aiEntries: AIEntry[] = [
  {
    key: "chat",
    label: "纯对话",
    placeholder: "输入你想临时询问的内容",
    buttonType: "chat",
  },
  {
    key: "continue",
    label: "续写",
    placeholder: "输入续写要求，可为空",
    buttonType: "continue",
  },
  {
    key: "polish",
    label: "润色",
    placeholder: "输入扩写、缩写或改写要求，可为空",
    buttonType: "polish",
  },
  {
    key: "setting",
    label: "设定",
    placeholder: "输入你想补充的设定方向",
    buttonType: "setting",
  },
  {
    key: "suggestion",
    label: "建议",
    placeholder: "输入你想判断或改进的问题",
    buttonType: "suggestion",
  },
  {
    key: "evidence",
    label: "证据",
    placeholder: "输入你想追问的依据或出处",
    buttonType: "evidence",
  },
  {
    key: "chapter_summary",
    label: "章节摘要",
    placeholder: "本章暂未生成摘要",
    buttonType: "chapter_summary",
  },
  {
    key: "inspiration",
    label: "灵感",
    placeholder: "记下一条灵感",
    buttonType: "inspiration",
  },
  {
    key: "fact",
    label: "事实",
    placeholder: "记下一条可能入库的事实",
    buttonType: "fact",
  },
];

const referenceOptions: Record<WritingAIReferenceScope, string> = {
  none: "无小说上下文",
  selection: "选区",
  chapter: "本章",
  full_text: "全文",
};

const aiReferenceConfigs: Record<
  WritingAIButtonType,
  { defaultScope: ReferenceRangeChoice; options: ReferenceRangeChoice[] }
> = {
  chat: { defaultScope: "none", options: ["none"] },
  continue: { defaultScope: "chapter", options: ["chapter", "selection"] },
  polish: { defaultScope: "selection", options: ["selection"] },
  setting: { defaultScope: "selection", options: ["selection", "chapter", "full_text"] },
  suggestion: { defaultScope: "chapter", options: ["selection", "chapter", "full_text"] },
  evidence: { defaultScope: "full_text", options: ["chapter", "full_text"] },
  chapter_summary: { defaultScope: "chapter", options: ["chapter"] },
  inspiration: { defaultScope: "chapter", options: ["selection", "chapter"] },
  fact: { defaultScope: "selection", options: ["selection", "chapter"] },
};

const entryDescriptions: Record<AIEntryKey, string> = {
  chat: "临时问答，不保存到历史",
  continue: "根据当前章节续写正文",
  polish: "处理当前选区文字",
  setting: "补充世界观、人设或规则",
  suggestion: "检查问题并给出修改方向",
  evidence: "追问依据和前文线索",
  chapter_summary: "整理当前章节摘要",
  inspiration: "快速记录创意点",
  fact: "记录待确认事实",
};

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
  const [activeTypographyMenu, setActiveTypographyMenu] =
    useState<EditorTypographyMenu | null>(null);
  const [lineHeight, setLineHeight] = useState(DEFAULT_EDITOR_LINE_HEIGHT);
  const [lineWidth, setLineWidth] = useState(DEFAULT_EDITOR_LINE_WIDTH);
  const [editorFontKey, setEditorFontKey] = useState<EditorFontKey>(
    DEFAULT_EDITOR_FONT_KEY,
  );
  const [editorToast, setEditorToast] = useState<EditorToastState | null>(null);
  const paperToneKey = useSyncExternalStore(
    subscribeStoredPaperToneKey,
    readStoredPaperToneKey,
    () => "mist",
  );
  const [isBackgroundMenuOpen, setBackgroundMenuOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [referenceRange, setReferenceRange] =
    useState<ReferenceRangeChoice>("chapter");
  const [selectedAiTool, setSelectedAiTool] = useState<AIEntryKey>("continue");
  const [isAssistantPanelOpen, setAssistantPanelOpen] = useState(false);
  const [collapsedVolumeIds, setCollapsedVolumeIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [aiInput, setAIInput] = useState("");
  const [aiBusy, setAIBusy] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [aiError, setAIError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<
    Partial<Record<AIEntryKey, WritingAIRun>>
  >({});
  const [isHistoryPickerOpen, setHistoryPickerOpen] = useState(false);
  const [historyConversations, setHistoryConversations] = useState<
    WritingAIRun[]
  >([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [chapterSummary, setChapterSummary] =
    useState<ChapterSummaryInfo | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [showPromptSnapshot, setShowPromptSnapshot] = useState(false);
  const modelSelection = useModelSelection();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const savedMarkdownRef = useRef("");
  const savedChapterTitleRef = useRef("");
  const activeChapterRef = useRef<ChapterInfo | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const editorToastTimerRef = useRef<number | null>(null);
  const editorToastIdRef = useRef(0);
  const assistantPanelOpenRef = useRef(false);
  const assistantHistoryOpenRef = useRef(false);
  const activePaperTone =
    editorPaperTones.find(tone => tone.key === paperToneKey) ??
    editorPaperTones[0];
  const editorThemeStyle = editorThemeVariables(activePaperTone);
  const activeEditorFont =
    editorFontOptions.find(option => option.key === editorFontKey) ??
    editorFontOptions[0];
  const volumeCount = outline?.volumes.length ?? 0;
  const chapterCount = outlineChapters(outline).length;

  const activeEntry =
    aiEntries.find(entry => entry.key === selectedAiTool) ?? aiEntries[1];
  const activeConversation = conversations[selectedAiTool] ?? null;
  const isSummaryEntry = false;
  const isRecordEntry = false;
  const isConversationEntry = Boolean(activeEntry.buttonType);
  const activeReferenceConfig = aiReferenceConfigs[activeEntry.buttonType] ?? null;
  const currentOutlineChapter = activeChapter
    ? outlineChapterById(outline, activeChapter.id)
    : null;
  const currentChapterTitle =
    activeChapterTitle(outline, activeChapter?.id) ?? activeChapter?.title ?? "";
  const currentChapterPrefix = currentOutlineChapter
    ? chapterNumberLabel(currentOutlineChapter.order)
    : "章节";
  const currentReferenceScope = referenceScopeFor(
    activeEntry.buttonType,
    referenceRange,
  );
  const currentWordCount = useMemo(() => countReadableWords(markdown), [markdown]);
  const showSelectionPreview =
    activeReferenceConfig?.options.includes("selection") === true &&
    Boolean(selection?.text.trim());
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

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setLineHeight(
        readStoredEditorNumber(
          EDITOR_LINE_HEIGHT_STORAGE_KEY,
          DEFAULT_EDITOR_LINE_HEIGHT,
          editorLineHeightRange.min,
          editorLineHeightRange.max,
        ),
      );
      setLineWidth(
        readStoredEditorNumber(
          EDITOR_LINE_WIDTH_STORAGE_KEY,
          DEFAULT_EDITOR_LINE_WIDTH,
          editorLineWidthRange.min,
          editorLineWidthRange.max,
        ),
      );
      setEditorFontKey(readStoredEditorFontKey());
      setCollapsedVolumeIds(readStoredCollapsedVolumeIds());
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

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
      setHistoryPickerOpen(false);
      setHistoryConversations([]);
      setChapterSummary(null);
      setSummaryError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "章节加载失败");
      setSaveState("error");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLatestChapterSummary = useCallback(async (chapterId: string) => {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const response = await listChapterSummaries(chapterId);
      const latest =
        [...response.summaries]
          .filter(summary => summary.status !== "ignored")
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0] ??
        null;
      setChapterSummary(latest);
    } catch (caught) {
      setSummaryError(caught instanceof Error ? caught.message : "章节摘要加载失败");
    } finally {
      setSummaryLoading(false);
    }
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
    if (!isAssistantPanelOpen) {
      return;
    }
    function handleAssistantEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      closeAssistantPanel();
    }
    window.addEventListener("keydown", handleAssistantEscape, true);
    return () => window.removeEventListener("keydown", handleAssistantEscape, true);
  }, [closeAssistantPanel, isAssistantPanelOpen]);

  useEffect(() => {
    writeStoredCollapsedVolumeIds(collapsedVolumeIds);
  }, [collapsedVolumeIds]);

  useEffect(() => {
    resizeEditorTextarea();
  }, [activeChapter?.id, fontSize, lineHeight, markdown, resizeEditorTextarea]);

  useEffect(() => {
    return () => {
      if (editorToastTimerRef.current) {
        window.clearTimeout(editorToastTimerRef.current);
      }
    };
  }, []);

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

  async function loadChapterForWorkspace(chapterId: string) {
    await loadChapter(chapterId);
    if (selectedAiTool === "chapter_summary") {
      await loadLatestChapterSummary(chapterId);
    }
  }

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
    await loadChapterForWorkspace(chapterId);
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

  function updateLineHeightPreference(nextLineHeight: number) {
    const safeLineHeight = clampNumber(
      nextLineHeight,
      editorLineHeightRange.min,
      editorLineHeightRange.max,
    );
    setLineHeight(safeLineHeight);
    writeStoredEditorNumber(EDITOR_LINE_HEIGHT_STORAGE_KEY, safeLineHeight);
  }

  function updateLineWidthPreference(nextLineWidth: number) {
    const safeLineWidth = clampNumber(
      nextLineWidth,
      editorLineWidthRange.min,
      editorLineWidthRange.max,
    );
    setLineWidth(safeLineWidth);
    writeStoredEditorNumber(EDITOR_LINE_WIDTH_STORAGE_KEY, safeLineWidth);
  }

  function updateEditorFontPreference(nextFontKey: EditorFontKey) {
    setEditorFontKey(nextFontKey);
    writeStoredEditorFontKey(nextFontKey);
    setActiveTypographyMenu(null);
  }

  function showEditorToast(
    message: string,
    tone: EditorToastTone = "success",
  ) {
    editorToastIdRef.current += 1;
    setEditorToast({ id: editorToastIdRef.current, message, tone });
    if (editorToastTimerRef.current) {
      window.clearTimeout(editorToastTimerRef.current);
    }
    editorToastTimerRef.current = window.setTimeout(() => {
      setEditorToast(null);
    }, tone === "error" ? 2600 : 1900);
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
        await loadChapterForWorkspace(nextChapterId);
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
        await loadChapterForWorkspace(chapterId);
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
        await loadChapterForWorkspace(nextChapterId);
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
    showEditorToast("排版完成");
  }

  function selectAiTool(entryKey: AIEntryKey) {
    if (isAssistantPanelOpen && selectedAiTool === entryKey) {
      closeAssistantPanel();
      return;
    }
    const nextEntry = aiEntries.find(entry => entry.key === entryKey);
    if (nextEntry?.buttonType) {
      setReferenceRange(
        aiReferenceConfigs[nextEntry.buttonType]?.defaultScope ?? "chapter",
      );
    } else {
      setReferenceRange("none");
    }
    setSelectedAiTool(entryKey);
    openAssistantPanel();
    setAIError(null);
    setShowPromptSnapshot(false);
    setHistoryPickerOpen(false);
    setHistoryConversations([]);
    if (entryKey === "chapter_summary" && activeChapterRef.current) {
      void loadLatestChapterSummary(activeChapterRef.current.id);
    }
  }

  async function openHistoryPicker() {
    const chapter = activeChapterRef.current;
    if (!chapter || !isConversationEntry) {
      return;
    }
    if (isHistoryPickerOpen) {
      setHistoryPickerOpen(false);
      return;
    }
    setHistoryPickerOpen(true);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await listWritingAIRuns({
        chapterId: chapter.id,
        buttonType: activeEntry.buttonType,
        page: 1,
        pageSize: 20,
      });
      setHistoryConversations(response.runs);
    } catch (caught) {
      setHistoryError(caught instanceof Error ? caught.message : "历史对话加载失败");
    } finally {
      setHistoryLoading(false);
    }
  }

  function startNewConversation() {
    setConversations(current => ({
      ...current,
      [selectedAiTool]: undefined,
    }));
    setHistoryPickerOpen(false);
    setAIInput("");
    setAIError(null);
    setShowPromptSnapshot(false);
  }

  function selectHistoryConversation(conversation: WritingAIRun) {
    setConversations(current => ({
      ...current,
      [selectedAiTool]: conversation,
    }));
    setHistoryPickerOpen(false);
    setAIError(null);
    setShowPromptSnapshot(false);
  }

  function cycleReferenceRange() {
    if (!activeReferenceConfig) {
      return;
    }
    const options = activeReferenceConfig.options.filter(
      option => option !== "selection" || Boolean(selection?.text.trim()),
    );
    const availableOptions = options.length ? options : activeReferenceConfig.options;
    const currentIndex = availableOptions.indexOf(currentReferenceScope);
    const nextIndex = currentIndex === -1 ? 0 : (currentIndex + 1) % availableOptions.length;
    setReferenceRange(availableOptions[nextIndex]);
  }

  async function regenerateCurrentConversation() {
    if (!activeConversation) {
      return;
    }
    setAIBusy(true);
    setAIError(null);
    setStreamingText("");
    try {
      const response = await replayWritingAIRun(activeConversation.run_id);
      setConversations(current => ({
        ...current,
        [selectedAiTool]: response,
      }));
      setHistoryConversations(current =>
        current.map(conversation =>
          conversation.run_id === response.run_id ? response : conversation,
        ),
      );
      showEditorToast("已回放保存记录");
    } catch (caught) {
      setAIError(caught instanceof Error ? caught.message : "回放失败");
    } finally {
      setAIBusy(false);
    }
  }

  async function copyAIMessage(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setAIError(null);
      showEditorToast("已复制模型回答");
    } catch {
      setAIError("复制失败，请手动选择文本复制");
    }
  }

  async function deleteCurrentConversation() {
    if (!activeConversation) {
      return;
    }
    setAIError(null);
    setConversations(current => ({
      ...current,
      [selectedAiTool]: undefined,
    }));
    showEditorToast("已清空当前面板，历史记录仍保留");
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
      const referenceScope = referenceScopeFor(activeEntry.buttonType, referenceRange);
      if (referenceScope === "selection" && !selection?.text.trim()) {
        setAIError("请先在正文中选择一段文字");
        return;
      }
      if (!modelSelection.modelId) {
        setAIError(modelSelection.error || "模型列表尚未加载完成");
        return;
      }
      let completedRunId = "";
      let streamFailure = "";
      await streamWritingAIRun({
        button_type: activeEntry.buttonType,
        chapter_id: chapter.id,
        reference_scope: referenceScope,
        user_input: input || defaultPromptFor(activeEntry.key),
        selected_text: selection?.text ?? "",
        selection_range: selection
          ? {
              char_start: selection.start,
              char_end: selection.end,
            }
          : null,
        draft_chapter_text: markdown,
        model_id: modelSelection.modelId,
      }, event => {
        if (event.type === "text_delta") {
          setStreamingText(current => appendWritingStreamText(current, event));
        } else if (event.type === "run_completed") {
          completedRunId = event.run_id;
        } else if (event.type === "run_failed") {
          streamFailure = writingStreamFailure(event);
        }
      });
      if (streamFailure) {
        throw new Error(streamFailure);
      }
      if (!completedRunId) {
        throw new Error("模型流式任务未返回完成记录");
      }
      const response = await getWritingAIRun(completedRunId);
      setConversations(current => ({
        ...current,
        [activeEntry.key]: response,
      }));
      setAIInput("");
      setStreamingText("");
      showEditorToast(response.status === "completed" ? "模型调用完成" : "模型调用失败");
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
      <div className="relative">
        <button
          type="button"
          aria-expanded={activeTypographyMenu === "fontSize"}
          onClick={() =>
            setActiveTypographyMenu(current =>
              current === "fontSize" ? null : "fontSize",
            )
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-2.5 text-sm text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
        >
          <Type className="size-4" />
          字号
        </button>
        {activeTypographyMenu === "fontSize" ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-56 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
            <div className="mb-3 flex items-center justify-between text-xs text-[var(--tc-smoke)]">
              <span>小</span>
              <span className="font-medium text-[var(--tc-midnight-ink)]">字号</span>
              <span>大</span>
            </div>
            <input
              type="range"
              min={14}
              max={24}
              step={1}
              value={fontSize}
              onChange={event =>
                void updateFontSizePreference(Number(event.target.value))
              }
              className="w-full accent-[var(--tc-workspace-focus)]"
              aria-label="字号"
            />
          </div>
        ) : null}
      </div>
      <div className="relative">
        <button
          type="button"
          aria-expanded={activeTypographyMenu === "lineHeight"}
          onClick={() =>
            setActiveTypographyMenu(current =>
              current === "lineHeight" ? null : "lineHeight",
            )
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-2.5 text-sm text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
        >
          <Rows3 className="size-4" />
          行高
        </button>
        {activeTypographyMenu === "lineHeight" ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-56 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
            <div className="mb-3 flex items-center justify-between text-xs text-[var(--tc-smoke)]">
              <span>紧</span>
              <span className="font-medium text-[var(--tc-midnight-ink)]">行高</span>
              <span>松</span>
            </div>
            <input
              type="range"
              min={editorLineHeightRange.min}
              max={editorLineHeightRange.max}
              step={editorLineHeightRange.step}
              value={lineHeight}
              onChange={event =>
                updateLineHeightPreference(Number(event.target.value))
              }
              className="w-full accent-[var(--tc-workspace-focus)]"
              aria-label="行高"
            />
          </div>
        ) : null}
      </div>
      <div className="relative">
        <button
          type="button"
          aria-expanded={activeTypographyMenu === "lineWidth"}
          onClick={() =>
            setActiveTypographyMenu(current =>
              current === "lineWidth" ? null : "lineWidth",
            )
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-2.5 text-sm text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
        >
          <Baseline className="size-4" />
          行宽
        </button>
        {activeTypographyMenu === "lineWidth" ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-56 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
            <div className="mb-3 flex items-center justify-between text-xs text-[var(--tc-smoke)]">
              <span>窄</span>
              <span className="font-medium text-[var(--tc-midnight-ink)]">行宽</span>
              <span>宽</span>
            </div>
            <input
              type="range"
              min={editorLineWidthRange.min}
              max={editorLineWidthRange.max}
              step={editorLineWidthRange.step}
              value={lineWidth}
              onChange={event =>
                updateLineWidthPreference(Number(event.target.value))
              }
              className="w-full accent-[var(--tc-workspace-focus)]"
              aria-label="行宽"
            />
          </div>
        ) : null}
      </div>
      <div className="relative">
        <button
          type="button"
          aria-expanded={activeTypographyMenu === "font"}
          onClick={() =>
            setActiveTypographyMenu(current =>
              current === "font" ? null : "font",
            )
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-2.5 text-sm text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
        >
          <CaseSensitive className="size-4" />
          字体
        </button>
        {activeTypographyMenu === "font" ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-52 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] py-2 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
            {editorFontOptions.map(option => (
              <button
                key={option.key}
                type="button"
                onClick={() => updateEditorFontPreference(option.key)}
                className="flex h-12 w-full items-center justify-between gap-3 px-3 text-left text-sm leading-none text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
              >
                <span
                  className="min-w-0 flex-1 truncate leading-6"
                  style={{ fontFamily: option.fontFamily }}
                >
                  {option.label}
                </span>
                {option.key === editorFontKey ? (
                  <Check className="size-4 shrink-0 text-[var(--tc-workspace-focus)]" />
                ) : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="relative">
        <Button
          type="button"
          variant="outline"
          className="h-9"
          aria-expanded={isBackgroundMenuOpen}
          onClick={() => setBackgroundMenuOpen(current => !current)}
        >
          <Palette className="size-4" />
          页面主题
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
                写作页主题
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
        aria-label="正文边框"
      >
        <option value="soft">显示页缘</option>
        <option value="dark">隐藏页缘</option>
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
      <Button
        type="button"
        variant="outline"
        onClick={formatFullText}
        className="h-9 gap-1.5 px-3"
      >
        <AlignLeft className="size-4" />
        一键排版
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
      workspaceStyle={editorThemeStyle}
    >
      <div
        className="tc-editor-theme-scope flex min-h-[calc(100dvh-62px)] flex-col bg-[var(--tc-workspace-bg)] xl:h-[calc(100dvh-62px)] xl:flex-row xl:overflow-hidden"
        style={{
          ...editorThemeStyle,
          background: activePaperTone.pageBackground,
          color: activePaperTone.ink,
        }}
      >
        <aside
          className="flex shrink-0 flex-col border-b border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-[280px] xl:border-b-0 xl:border-r"
          style={{
            background: activePaperTone.sidebarBackground,
            borderColor: activePaperTone.border,
          }}
        >
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
                新建章
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={addVolume}
                className="h-9 text-sm"
              >
                新建卷
              </Button>
            </div>
          </div>

          <div className="tc-editor-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-3">
            {outline?.volumes.map(volume => {
              const collapsed = collapsedVolumeIds.has(volume.volume_id);
              return (
                <section
                  key={volume.volume_id}
                  className="group/volume rounded-[var(--tc-radius-control)] bg-transparent"
                >
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => toggleVolume(volume.volume_id)}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-[var(--tc-radius-control)] px-2 py-1.5 text-left text-sm font-semibold text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
                    >
                      {collapsed ? (
                        <Book className="size-4 shrink-0 text-[var(--tc-smoke)]" />
                      ) : (
                        <BookOpen className="size-4 shrink-0 text-[var(--tc-smoke)]" />
                      )}
                      <span className="truncate">{volume.name}</span>
                    </button>
                    <span className="shrink-0 pr-2 text-xs text-[var(--tc-smoke)] group-hover/volume:hidden">
                      {volume.chapters.length} 章
                    </span>
                    <div className="hidden shrink-0 items-center gap-1 group-hover/volume:flex">
                      <button
                        type="button"
                        title="新建章节"
                        onClick={() => void addChapter(volume.volume_id)}
                        className="inline-flex size-7 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
                      >
                        <Plus className="size-4" />
                      </button>
                      <button
                        type="button"
                        title="重命名卷"
                        aria-label={`重命名${volume.name}`}
                        onClick={() => void renameVolumeName(volume)}
                        className="inline-flex size-7 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                      >
                        <PenLine className="size-4" />
                      </button>
                      <button
                        type="button"
                        title="删除卷"
                        aria-label={`删除${volume.name}`}
                        onClick={() => void removeVolume(volume)}
                        className="inline-flex size-7 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                  {!collapsed ? (
                    <div className="mt-0.5 space-y-0.5 pl-4">
                      {volume.chapters.map(chapter => {
                        const active = activeChapter?.id === chapter.chapter_id;
                        return (
                          <div
                            key={chapter.chapter_id}
                            className={cn(
                              "group relative flex w-full items-center rounded-[var(--tc-radius-control)] transition-colors",
                              active
                                ? "bg-[var(--tc-workspace-panel-soft)] font-medium text-[var(--tc-midnight-ink)]"
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
                              className="min-w-0 flex-1 truncate px-2.5 py-1 pr-2 text-left text-[13px] outline-none"
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
          className="relative flex min-w-0 flex-1 flex-col bg-[var(--tc-workspace-bg)]"
          style={
            {
              background: activePaperTone.paperBackground,
              color: activePaperTone.ink,
              "--tc-editor-selection-bg": activePaperTone.selection,
            } as CSSProperties
          }
        >
          <div
            className="tc-editor-scrollbar min-h-0 flex-1 overflow-y-auto bg-[var(--tc-workspace-recess)] px-3 py-3 md:px-6 md:py-5 xl:px-10"
            style={{
              background: activePaperTone.paperBackground,
              scrollbarGutter: "stable",
            }}
          >
            {error ? (
              <div className="tc-warning mb-4 rounded-[var(--tc-radius-control)] border px-4 py-3 text-sm">
                {error}
              </div>
            ) : null}
            <div
              className={cn(
                "mx-auto min-h-[calc(100vh-150px)] w-full border shadow-none",
                editorBackground === "dark"
                  ? "border-transparent"
                  : "border-[var(--tc-stone-mist)]",
              )}
              style={{
                background: activePaperTone.paperBackground,
                borderColor:
                  editorBackground === "dark" ? "transparent" : activePaperTone.border,
                color: activePaperTone.ink,
                maxWidth: `${lineWidth}px`,
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
                      fontFamily: activeEditorFont.fontFamily,
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
                      fontFamily: activeEditorFont.fontFamily,
                      fontSize: `${Math.round(fontSize * 1.55)}px`,
                      lineHeight: "1.28",
                    }}
                    placeholder={currentChapterTitle ? "章节标题" : "未选择章节"}
                    aria-label="章节标题"
                  />
                </div>
              </div>
              <div className="relative">
                <textarea
                  ref={textareaRef}
                  value={markdown}
                  onChange={event => updateMarkdown(event.target.value)}
                  onSelect={updateSelection}
                  onKeyUp={updateSelection}
                  onMouseUp={updateSelection}
                  disabled={!activeChapter || loading}
                  spellCheck={false}
                  className="block min-h-[calc(100vh-330px)] w-full resize-none overflow-hidden bg-transparent px-6 pb-10 pt-0 outline-none selection:bg-[var(--tc-editor-selection-bg)] selection:text-[inherit] md:px-10 md:pb-12"
                  style={{
                    color: activePaperTone.ink,
                    fontFamily: activeEditorFont.fontFamily,
                    fontSize: `${fontSize}px`,
                    lineHeight,
                  }}
                  placeholder="在这里写正文"
                />
              </div>
            </div>
          </div>
          <div
            className="pointer-events-none absolute bottom-2 right-3 px-0 py-0 text-right text-xs text-[var(--tc-smoke)] md:right-4"
            style={{
              color: activePaperTone.muted,
            }}
          >
            本章 {currentWordCount} 字
          </div>
          <EditorFloatingToast toast={editorToast} />
        </section>

        {isAssistantPanelOpen ? (
          <aside
            className="flex shrink-0 flex-col border-t border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-[400px] xl:border-l xl:border-t-0"
            style={{
              background: activePaperTone.sidebarBackground,
              borderColor: activePaperTone.border,
            }}
          >
            <header className="relative shrink-0 border-b border-[var(--tc-stone-mist)] px-4 py-4 pr-12">
              <button
                type="button"
                aria-label="关闭助手面板"
                title="关闭助手面板"
                onClick={closeAssistantPanel}
                className="absolute right-3 top-3 inline-flex size-7 items-center justify-center rounded-full border border-[var(--tc-stone-mist)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
              >
                <X className="size-3.5" />
              </button>
              <div className="flex min-w-0 items-start gap-3">
                <AIEntryIcon
                  entryKey={activeEntry.key}
                  className="mt-1 size-5 shrink-0 text-[var(--tc-smoke)]"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs leading-5 text-[var(--tc-smoke)]">
                    {entryDescriptions[activeEntry.key]}
                  </p>
                  <div className="mt-1 flex min-w-0 items-end justify-between gap-2">
                    <h2 className="truncate font-serif text-2xl leading-none text-[var(--tc-midnight-ink)]">
                      {activeEntry.label}
                    </h2>
                    {isConversationEntry ? (
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => void openHistoryPicker()}
                          className="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-2.5 text-xs text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                        >
                          <History className="size-3.5" />
                          历史对话
                        </button>
                        <button
                          type="button"
                          onClick={startNewConversation}
                          className="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-2.5 text-xs text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)]"
                        >
                          <MessageSquare className="size-3.5" />
                          新对话
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </header>

            <div className="tc-editor-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {showSelectionPreview ? (
                <SelectionPreview selection={selection} />
              ) : null}
              {isHistoryPickerOpen && isConversationEntry ? (
                <AIHistoryPicker
                  conversations={historyConversations}
                  loading={historyLoading}
                  error={historyError}
                  activeConversationId={activeConversation?.run_id ?? null}
                  onSelect={selectHistoryConversation}
                />
              ) : null}
              {isSummaryEntry ? (
                <ChapterSummaryPanel
                  summary={chapterSummary}
                  loading={summaryLoading}
                  error={summaryError}
                />
              ) : null}
              {!isSummaryEntry && !isRecordEntry ? (
                <>
                  {aiBusy && streamingText ? (
                    <div className="mb-3 whitespace-pre-wrap rounded-[var(--tc-radius-control)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] p-3 text-sm leading-6 text-[var(--tc-text-primary)]">
                      {streamingText}
                    </div>
                  ) : null}
                  <AIMessageList
                    conversation={activeConversation}
                    showPromptSnapshot={showPromptSnapshot}
                    actionsDisabled={aiBusy}
                    onTogglePromptSnapshot={() =>
                      setShowPromptSnapshot(current => !current)
                    }
                    onRegenerate={() => void regenerateCurrentConversation()}
                    onCopy={message => void copyAIMessage(message)}
                    onDelete={() => void deleteCurrentConversation()}
                  />
                </>
              ) : null}
            </div>

            <div className="shrink-0 border-t border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-3">
              <div className="mb-2 flex justify-end">
                <ModelSelector selection={modelSelection} compact />
              </div>
              {isSummaryEntry ? (
                <Button
                  type="button"
                  onClick={() => void submitAI()}
                  disabled={
                    aiBusy || summaryLoading || !activeChapter || Boolean(chapterSummary)
                  }
                  className="h-10 w-full"
                >
                  {aiBusy || summaryLoading ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <FileText className="size-4" />
                  )}
                  生成本章摘要
                </Button>
              ) : (
                <>
                  {isRecordEntry ? (
                    <div className="space-y-2">
                      <textarea
                        value={aiInput}
                        onChange={event => setAIInput(event.target.value)}
                        className="h-40 min-h-0 w-full resize-none rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm leading-6 outline-none"
                        placeholder={activeEntry.placeholder}
                      />
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void submitAI()}
                        disabled={aiBusy || !activeChapter}
                        className="h-9 w-full"
                        aria-label="发送"
                      >
                        {aiBusy ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Send className="size-4" />
                        )}
                        发送
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-stretch gap-2">
                      <textarea
                        value={aiInput}
                        onChange={event => setAIInput(event.target.value)}
                        className="h-20 min-h-0 flex-1 resize-none rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 py-2 text-sm leading-6 outline-none"
                        placeholder={activeEntry.placeholder}
                      />
                      <div
                        className={cn(
                          "flex shrink-0 flex-col items-stretch gap-2",
                          isConversationEntry && activeReferenceConfig
                            ? "justify-start"
                            : "justify-center",
                        )}
                      >
                        {isConversationEntry && activeReferenceConfig ? (
                          <button
                            type="button"
                            onClick={cycleReferenceRange}
                            title="参考范围，点击切换"
                            aria-label="参考范围，点击切换"
                            className="inline-flex h-9 min-w-[72px] items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-3 text-sm text-[var(--tc-midnight-ink)] hover:bg-[var(--tc-workspace-panel-soft)]"
                          >
                            {referenceScopeLabel(currentReferenceScope)}
                          </button>
                        ) : null}
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => void submitAI()}
                          disabled={aiBusy || !activeChapter}
                          className="h-9 min-w-[72px]"
                          aria-label="发送"
                        >
                          {aiBusy ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Send className="size-4" />
                          )}
                          发送
                        </Button>
                      </div>
                    </div>
                  )}
                  {activeConversation ? (
                    <p className="mt-2 text-xs text-[var(--tc-smoke)]">
                      状态：{runStatusLabel(activeConversation.status)} · 模型：
                      {activeConversation.model || "未记录"}
                    </p>
                  ) : null}
                </>
              )}
              {aiError ? (
                <p className="mt-3 px-1 text-sm leading-6 text-[var(--tc-smoke)]">
                  {aiError}
                </p>
              ) : null}
            </div>
          </aside>
        ) : null}

        <aside
          className="shrink-0 border-t border-[var(--tc-stone-mist)] bg-[var(--tc-white)] xl:h-full xl:w-16 xl:border-l xl:border-t-0"
          style={{
            background: activePaperTone.rightRailBackground,
            borderColor: activePaperTone.border,
          }}
        >
          <div className="tc-editor-scrollbar flex gap-1 overflow-x-auto p-2 xl:h-full xl:flex-col xl:items-stretch xl:overflow-visible">
            {aiEntries.map(entry => (
              <button
                key={entry.key}
                type="button"
                aria-label={`${entry.label}入口`}
                aria-pressed={selectedAiTool === entry.key}
                title={`${entry.label}入口`}
                onClick={() => selectAiTool(entry.key)}
                className={cn(
                  "group relative flex h-12 min-w-12 flex-col items-center justify-center gap-0.5 rounded-[var(--tc-radius-small)] border text-[10px] leading-none transition-colors xl:min-w-0",
                  selectedAiTool === entry.key
                    ? "border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-panel-soft)] text-[var(--tc-midnight-ink)]"
                    : "border-transparent text-[var(--tc-smoke)] hover:border-[var(--tc-stone-mist)] hover:bg-[var(--tc-cream-paper)] hover:text-[var(--tc-midnight-ink)]",
                )}
                >
                  <AIEntryIcon entryKey={entry.key} className="size-4" />
                <span>{entry.label}</span>
                <span className="pointer-events-none absolute right-[calc(100%+8px)] top-1/2 z-20 hidden -translate-y-1/2 whitespace-nowrap rounded-[var(--tc-radius-small)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] px-2 py-1 text-xs text-[var(--tc-midnight-ink)] opacity-0 shadow-sm transition-opacity group-hover:opacity-100 xl:block">
                  {entry.label}
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
  conversation,
  showPromptSnapshot,
  actionsDisabled,
  onTogglePromptSnapshot,
  onRegenerate,
  onCopy,
  onDelete,
}: {
  conversation: WritingAIRun | null;
  showPromptSnapshot: boolean;
  actionsDisabled: boolean;
  onTogglePromptSnapshot: () => void;
  onRegenerate: () => void;
  onCopy: (message: string) => void;
  onDelete: () => void;
}) {
  const messages = writingRunMessages(conversation);
  const latestSnapshot = [...messages].reverse().find(message => message.snapshot);
  const latestAssistantIndex = lastAssistantMessageIndex(messages);
  if (!messages.length) {
    return null;
  }

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
      {messages.map((message, index) => (
        <article
          key={message.id}
          className={cn(
            "flex",
            message.role === "user" ? "justify-end" : "justify-start",
          )}
        >
          <div
            className={cn(
              "max-w-[86%] rounded-[var(--tc-radius-card)] border p-3",
              message.role === "user"
                ? "border-[var(--tc-action-primary-border)] bg-[var(--tc-action-primary-bg)] text-[var(--tc-action-primary-text)]"
                : "border-[var(--tc-stone-mist)] bg-[var(--tc-white)] text-[var(--tc-midnight-ink)]",
            )}
          >
            <div className="mb-2 flex items-center gap-2 text-xs opacity-70">
              {message.role === "user" ? (
                <BookOpen className="size-4" />
              ) : message.role === "assistant" ? (
                <Bot className="size-4" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {message.role === "user"
                ? "作者"
                : message.role === "error"
                  ? "系统消息"
                  : "模型回答"}
              {message.status ? <span>{message.status}</span> : null}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6">{message.text}</p>
            {message.sourceRefs.length ? (
              <div className="mt-3 space-y-2 border-t border-[var(--tc-stone-mist)] pt-3">
                {message.sourceRefs.map((source, sourceIndex) => (
                  <div
                    key={`${source.source_id}-${sourceIndex}`}
                    className="rounded-[var(--tc-radius-control)] bg-[var(--tc-cream-paper)] px-3 py-2 text-xs"
                  >
                    <p className="font-medium">
                      来源 {sourceIndex + 1}：{source.display_name}
                    </p>
                    <p className="mt-1 text-[var(--tc-smoke)]">
                      {source.excerpt}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
            {message.role === "assistant" && index === latestAssistantIndex ? (
              <div className="mt-3 flex items-center justify-end gap-1 text-[var(--tc-smoke)]">
                <MessageActionButton
                  label="回放"
                  disabled={actionsDisabled}
                  onClick={onRegenerate}
                >
                  <RefreshCcw className="size-4" />
                </MessageActionButton>
                <MessageActionButton
                  label="复制"
                  disabled={actionsDisabled}
                  onClick={() => onCopy(message.text)}
                >
                  <Copy className="size-4" />
                </MessageActionButton>
                <MessageActionButton
                  label="清空面板"
                  disabled={actionsDisabled}
                  onClick={onDelete}
                >
                  <Trash2 className="size-4" />
                </MessageActionButton>
              </div>
            ) : null}
          </div>
        </article>
      ))}
    </section>
  );
}

function writingRunMessages(run: WritingAIRun | null): Array<{
  id: string;
  role: "user" | "assistant" | "error";
  text: string;
  sourceRefs: WritingAIRetrievalEvidenceItem[];
  snapshot: string | null;
  status: string | null;
}> {
  if (!run) {
    return [];
  }
  const promptSnapshot = run.prompt_snapshot
    ? [
        "【系统提示词】",
        run.prompt_snapshot.system_prompt,
        "",
        "【用户提示词】",
        run.prompt_snapshot.user_prompt,
      ].join("\n")
    : null;
  const assistantText =
    run.status === "failed"
      ? run.error || "模型调用失败"
      : writingAIResultText(run);
  return [
    {
      id: `${run.run_id}-user`,
      role: "user",
      text: run.input.user_input || "未填写额外要求",
      sourceRefs: [],
      snapshot: promptSnapshot,
      status: null,
    },
    {
      id: `${run.run_id}-assistant`,
      role: run.status === "failed" ? "error" : "assistant",
      text: assistantText,
      sourceRefs: run.retrieval_context?.items ?? [],
      snapshot: promptSnapshot,
      status: runStatusLabel(run.status),
    },
  ];
}

function MessageActionButton({
  label,
  disabled,
  children,
  onClick,
}: {
  label: string;
  disabled: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex size-8 items-center justify-center rounded-[var(--tc-radius-control)] text-[var(--tc-smoke)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-midnight-ink)] disabled:cursor-not-allowed disabled:opacity-45"
    >
      {children}
    </button>
  );
}

function EditorFloatingToast({ toast }: { toast: EditorToastState | null }) {
  if (!toast) {
    return null;
  }
  const isError = toast.tone === "error";
  return (
    <div
      key={toast.id}
      role={isError ? "alert" : "status"}
      className="pointer-events-none fixed left-1/2 top-20 z-[90] flex max-w-[min(420px,calc(100vw-32px))] -translate-x-1/2 items-center gap-3 rounded-[var(--tc-radius-pill)] border border-[var(--tc-workspace-border-weak)] bg-[color-mix(in_srgb,var(--tc-workspace-panel)_92%,transparent)] px-4 py-3 text-sm font-medium text-[var(--tc-midnight-ink)] shadow-[0_18px_54px_rgba(0,0,0,0.18)] backdrop-blur"
    >
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-full",
          isError
            ? "bg-[var(--tc-danger-soft)] text-[var(--tc-danger-text)]"
            : "bg-[var(--tc-success-soft)] text-[var(--tc-success-text)]",
        )}
      >
        {isError ? <X className="size-4" /> : <Check className="size-4" />}
      </span>
      <span className="truncate">{toast.message}</span>
    </div>
  );
}

function SelectionPreview({ selection }: { selection: TextSelection | null }) {
  const text = selection?.text.trim() ?? "";
  if (!text) {
    return null;
  }
  return (
    <div className="mb-3 border-l border-[var(--tc-stone-mist)] pl-3 text-xs leading-5 text-[var(--tc-smoke)]">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium text-[var(--tc-midnight-ink)]">当前选区</span>
        <span>共 {countReadableWords(text)} 字</span>
      </div>
      <p
        className="overflow-hidden whitespace-pre-wrap text-[var(--tc-smoke)]"
        style={
          {
            display: "-webkit-box",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 2,
          } as CSSProperties
        }
      >
        {middleEllipsis(text, 86)}
      </p>
    </div>
  );
}

function AIHistoryPicker({
  conversations,
  loading,
  error,
  activeConversationId,
  onSelect,
}: {
  conversations: WritingAIRun[];
  loading: boolean;
  error: string | null;
  activeConversationId: string | null;
  onSelect: (conversation: WritingAIRun) => void;
}) {
  return (
    <section className="mb-4 rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--tc-midnight-ink)]">
          历史对话
        </h3>
        <span className="text-xs text-[var(--tc-smoke)]">
          {loading ? "加载中" : `${conversations.length} 条`}
        </span>
      </div>
      {error ? (
        <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 text-sm text-[var(--tc-smoke)]">
          {error}
        </p>
      ) : null}
      {!loading && !error && !conversations.length ? (
        <p className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3 py-2 text-sm text-[var(--tc-smoke)]">
          本章暂无历史对话
        </p>
      ) : null}
      <div className="space-y-1">
        {conversations.map(conversation => (
          <button
            key={conversation.run_id}
            type="button"
            onClick={() => onSelect(conversation)}
            className={cn(
              "block w-full rounded-[var(--tc-radius-control)] border px-3 py-2 text-left text-sm transition-colors",
              conversation.run_id === activeConversationId
                ? "border-[var(--tc-midnight-ink)] bg-[var(--tc-workspace-panel-soft)] text-[var(--tc-midnight-ink)]"
                : "border-transparent text-[var(--tc-smoke)] hover:border-[var(--tc-stone-mist)] hover:text-[var(--tc-midnight-ink)]",
            )}
          >
            <span className="block truncate">
              {conversationTitle(conversation)}
            </span>
            <span className="mt-1 block text-xs text-[var(--tc-smoke)]">
              {shortDateLabel(conversation.updated_at)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function ChapterSummaryPanel({
  summary,
  loading,
  error,
}: {
  summary: ChapterSummaryInfo | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading && !summary) {
    return (
      <div className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 text-sm text-[var(--tc-smoke)]">
        摘要加载中
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4 text-sm text-[var(--tc-smoke)]">
        {error}
      </div>
    );
  }
  if (!summary) {
    return null;
  }
  return (
    <section className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-4">
      <h3 className="text-sm font-semibold text-[var(--tc-midnight-ink)]">
        本章摘要
      </h3>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--tc-midnight-ink)]">
        {summary.summary}
      </p>
      {summary.key_events.length ? (
        <div className="mt-4 border-t border-[var(--tc-stone-mist)] pt-3">
          <p className="text-xs text-[var(--tc-smoke)]">关键事件</p>
          <ul className="mt-2 space-y-1 text-sm leading-6">
            {summary.key_events.map(event => (
              <li key={event}>{event}</li>
            ))}
          </ul>
        </div>
      ) : null}
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
      className="inline-flex h-9 w-8 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] text-[var(--tc-smoke)] hover:text-[var(--tc-midnight-ink)]"
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

function countReadableWords(text: string): number {
  return text.replace(/\s/g, "").length;
}

function middleEllipsis(text: string, maxLength: number): string {
  const normalized = text.trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  const headLength = Math.ceil(maxLength * 0.58);
  const tailLength = Math.max(12, maxLength - headLength - 1);
  return `${normalized.slice(0, headLength)}……${normalized.slice(-tailLength)}`;
}

function lastAssistantMessageIndex(messages: Array<{ role: string }>): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      return index;
    }
  }
  return -1;
}

function conversationTitle(conversation: WritingAIRun): string {
  return middleEllipsis(conversation.input.user_input || conversation.button_label, 42);
}

function shortDateLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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

function readStoredEditorNumber(
  storageKey: string,
  fallback: number,
  min: number,
  max: number,
): number {
  if (typeof window === "undefined") {
    return fallback;
  }
  const storedValue = Number(window.localStorage.getItem(storageKey));
  if (!Number.isFinite(storedValue)) {
    return fallback;
  }
  return clampNumber(storedValue, min, max);
}

function writeStoredEditorNumber(storageKey: string, value: number) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(storageKey, String(value));
}

function readStoredEditorFontKey(): EditorFontKey {
  if (typeof window === "undefined") {
    return DEFAULT_EDITOR_FONT_KEY;
  }
  const storedFont = window.localStorage.getItem(EDITOR_FONT_STORAGE_KEY);
  if (editorFontOptions.some(option => option.key === storedFont)) {
    return storedFont as EditorFontKey;
  }
  return DEFAULT_EDITOR_FONT_KEY;
}

function writeStoredEditorFontKey(fontKey: EditorFontKey) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EDITOR_FONT_STORAGE_KEY, fontKey);
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
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
  taskType: WritingAIButtonType,
  range: ReferenceRangeChoice,
): WritingAIReferenceScope {
  const config = aiReferenceConfigs[taskType];
  if (!config) {
    return "none";
  }
  return config.options.includes(range) ? range : config.defaultScope;
}

function referenceScopeLabel(scope: WritingAIReferenceScope): string {
  return referenceOptions[scope] ?? "正文参考";
}

function defaultPromptFor(entryKey: AIEntryKey): string {
  if (entryKey === "chapter_summary") {
    return "生成本章摘要";
  }
  if (entryKey === "continue") {
    return "续写当前段落";
  }
  return "请根据当前正文参考给出结果";
}

function writingAIResultText(run: WritingAIRun): string {
  const output = run.structured_output;
  if (!output) {
    return run.error || "暂无模型结果";
  }
  const content = output.content;
  if (output.output_type === "chat_answer") {
    return [
      stringValue(content.answer),
      formatArray("推测", content.inference),
      formatArray("不确定点", content.uncertainties),
      formatArray("可执行建议", content.actionable_suggestions),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (typeof content.text === "string") {
    return content.text;
  }
  if (typeof content.polished_text === "string") {
    return [
      content.polished_text,
      formatArray("修改说明", content.change_summary),
      formatArray("风险提示", content.risk_notes),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (Array.isArray(content.setting_supplements)) {
    return [
      formatRecordList("设定补充", content.setting_supplements),
      formatArray("使用建议", content.usage_advice),
      formatArray("可能影响", content.possible_impacts),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (Array.isArray(content.diagnosis) || Array.isArray(content.suggestions)) {
    return [
      formatRecordList("问题诊断", content.diagnosis),
      formatRecordList("修改建议", content.suggestions),
      formatArray("建议保留", content.do_not_change),
      formatArray("待确认点", content.uncertainties),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (typeof content.conclusion === "string") {
    return [
      `结论：${content.conclusion}`,
      formatRecordList("依据", content.evidence),
      formatArray("推测", content.inference),
      formatArray("未确认点", content.unconfirmed_points),
      formatArray("冲突提醒", content.conflict_warnings),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (typeof content.summary === "string") {
    return [
      content.summary,
      formatArray("关键事件", content.key_events),
      formatRecordList("角色变化", content.character_changes),
      formatRecordList("设定候选", content.setting_candidates),
      formatArray("伏笔或衔接", content.foreshadow_or_hooks),
      formatArray("未确认点", content.unconfirmed_points),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (Array.isArray(content.ideas)) {
    return [
      formatRecordList("灵感", content.ideas),
      formatArray("下一步", content.recommended_next_action),
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (Array.isArray(content.candidates)) {
    return [
      formatRecordList("待确认事实候选", content.candidates),
      formatArray("未提取项", content.ignored_items),
    ]
      .filter(Boolean)
      .join("\n");
  }
  return humanReadableStructuredContent(content);
}

function runStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    retrieving: "检索中",
    calling_llm: "调用模型中",
    parsing: "解析中",
    completed: "完成",
    failed: "失败",
  };
  return labels[status] ?? "未知状态";
}

function formatArray(label: string, value: unknown): string {
  if (!Array.isArray(value) || !value.length) {
    return "";
  }
  const items = value
    .map(humanReadableListItem)
    .filter(Boolean);
  return items.length ? `${label}：${items.join("；")}` : "";
}

function formatRecordList(label: string, value: unknown): string {
  if (!Array.isArray(value) || !value.length) {
    return "";
  }
  const lines = value.map((item, index) => {
    if (!isPlainRecord(item)) {
      return `${index + 1}. ${String(item)}`;
    }
    return `${index + 1}. ${Object.values(item)
      .map(field => String(field))
      .filter(Boolean)
      .join("；")}`;
  });
  return `${label}：\n${lines.join("\n")}`;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "暂无";
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
