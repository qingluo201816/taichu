import { generalCapabilityLabel, knownGeneralCapabilityLabel } from "./general-agent-display";
import type {
  GeneralAgentContextSnapshot,
  GeneralAgentInvocationTrace,
  GeneralAgentLLMReplay,
  GeneralAgentNodeRun,
  GeneralAgentRun,
} from "./types/general-agent";

export type MemoryTraceLayer = "model" | "runtime" | "recovery";

export type RuntimeTraceItem = {
  id: string;
  kind: "request" | "state" | "context" | "model" | "capability" | "human" | "answer";
  capabilityName?: string;
  title: string;
  summary: string;
  occurredAt: string;
  status: string;
  input?: unknown;
  output?: unknown;
  details: string[];
};

export type ReadableContentPart =
  | { kind: "text"; text: string }
  | { kind: "structured"; value: unknown };

export type NovelStructureDisplay = {
  totalChapters: number;
  returnedChapters: number;
  truncated: boolean;
  volumes: Array<{
    title: string;
    order: number;
    chapters: Array<{
      title: string;
      order: number;
      wordCount: number | null;
      status: string;
    }>;
  }>;
};

export type ToolResultViewKind =
  | "novel_structure"
  | "manuscript_content"
  | "story_context"
  | "knowledge_resolution"
  | "knowledge_catalog"
  | "knowledge_cards"
  | "external_search"
  | "external_content"
  | "manuscript_preview"
  | "manuscript_write"
  | "structure_write"
  | "knowledge_write";

export const generalToolResultViewKinds: Record<string, ToolResultViewKind> = {
  apply_manuscript_patch: "manuscript_write",
  create_confirmed_knowledge: "knowledge_write",
  create_novel_structure_items: "structure_write",
  delete_novel_structure_items: "structure_write",
  get_novel_structure: "novel_structure",
  list_knowledge_catalog: "knowledge_catalog",
  preview_manuscript_patch: "manuscript_preview",
  read_external_source: "external_content",
  read_knowledge_cards: "knowledge_cards",
  read_manuscript: "manuscript_content",
  resolve_knowledge_identity: "knowledge_resolution",
  retrieve_story_context: "story_context",
  search_external_sources: "external_search",
  update_confirmed_knowledge: "knowledge_write",
  update_novel_structure: "structure_write",
};

export function generalToolResultViewKind(
  capabilityName: string,
): ToolResultViewKind | undefined {
  return generalToolResultViewKinds[capabilityName];
}

export type SubagentResultViewKind =
  | "canon_evidence"
  | "external_research"
  | "narrative_summary"
  | "worldbuilding"
  | "character"
  | "story_architecture"
  | "scene_planning"
  | "drafting"
  | "revision"
  | "consistency_review"
  | "narrative_review"
  | "style_review";

export const generalSubagentResultViewKinds: Record<
  string,
  SubagentResultViewKind
> = {
  canon_evidence: "canon_evidence",
  character: "character",
  consistency_reviewer: "consistency_review",
  drafting: "drafting",
  external_research: "external_research",
  narrative_reviewer: "narrative_review",
  narrative_summary: "narrative_summary",
  revision: "revision",
  scene_planning: "scene_planning",
  story_architecture: "story_architecture",
  style_reviewer: "style_review",
  worldbuilding: "worldbuilding",
};

export function generalSubagentResultViewKind(
  capabilityName: string,
): SubagentResultViewKind | undefined {
  return generalSubagentResultViewKinds[capabilityName];
}

const readableFieldLabels: Record<string, string> = {
  "稳定记忆": "稳定记忆",
  "阶段稳定契约": "阶段稳定契约",
  "工作记忆": "工作记忆",
  "本阶段运行参数": "本阶段运行参数",
  "长期记忆": "长期记忆",
  "完整轻量能力目录": "本轮可用能力",
  "已选能力完整契约": "已选能力的输入输出要求",
  "已选能力精确契约": "已选能力的输入输出要求",
  "输出Schema": "模型返回要求",
  answer: "回答",
  accepted_artifact_types: "可接收的上游产物",
  allowed_tools: "可调用的工具",
  aliases: "别名",
  artifact_type: "产物类型",
  auto_collect: "是否自动收集资料",
  authorization_policy: "授权方式",
  chapter_ids: "章节范围",
  capability_name: "使用能力",
  caller: "调用方",
  cached_input_tokens: "缓存命中 Token",
  character_changes: "人物变化",
  clarification_question: "需要向作者确认的问题",
  confidence: "可信程度",
  conflicting_evidence: "冲突证据",
  content: "内容",
  created_at: "记录时间",
  created_request_index: "产生请求",
  current_chapter_id: "当前章节",
  current_request: "当前请求",
  description: "说明",
  direct_context: "直接补充的上下文",
  direct_response: "直接回答",
  display_name: "名称",
  evidence: "证据",
  estimated_input_tokens: "估算输入 Token",
  excerpt: "原文摘录",
  expires_after_request_index: "自动退出上下文",
  final_answer: "最终回答",
  final_response_guidance: "回答要求",
  finish_reason: "结束原因",
  hits: "命中内容",
  include_structure: "是否读取小说结构",
  issues: "发现的问题",
  key_events: "关键事件",
  kind: "执行类型",
  knowledge_type: "知识类型",
  lifecycle: "记录状态",
  matches: "匹配结果",
  memories: "运行记忆",
  name: "名称",
  non_responsibilities: "不负责的事项",
  node_summaries: "节点结果摘要",
  nodes: "执行节点",
  objective: "节点目标",
  dependencies: "前置节点",
  outcome: "校验结论",
  phase: "运行阶段",
  query: "检索内容",
  rank: "相关顺序",
  question: "问题",
  rationale: "判断依据",
  reason: "原因",
  long_term_memory: "长期记忆",
  replan_guidance: "重规划要求",
  resolution: "解析结果",
  role: "消息角色",
  scanned_chapters: "已检查章节",
  score: "相关程度",
  selection_text: "选中的正文",
  should_replan: "是否需要重规划",
  requires_clarification: "是否需要作者澄清",
  source_request: "来源要求",
  source_note: "来源说明",
  source_origin: "来源方式",
  source_ref: "证据来源",
  source_refs: "来源证据",
  target: "调用目标",
  tool_call_names: "模型请求的工具",
  artifact_refs: "关联产物",
  side_effect: "读写属性",
  stable_memory: "稳定记忆",
  summary: "内容摘要",
  summary_goal: "归纳目标",
  target_chars: "目标篇幅",
  tool_name: "工具",
  truncated: "是否截断",
  type: "类型",
  plan_summary: "当前计划摘要",
  history_memory: "历史记忆",
  confirmed_card_count: "已确认知识卡",
  referenced_card_count: "含章节引用的知识卡",
  latest_chapter: "最晚覆盖章节",
  scope: "作用范围",
  scope_type: "范围类型",
  status: "执行状态",
  unknowns: "尚不确定的内容",
  unresolved_issues: "未解决事项",
  unresolved_items: "未解决事项",
  user_constraints: "作者约束",
  warnings: "注意事项",
  working_memory: "当前工作",
  produced_artifact_types: "可产出的结果",
  requires_external_access: "是否需要外部访问",
  input_schema: "输入要求",
  input_char_count: "输入字符数",
  input_tokens: "输入 Token",
  message_count: "消息数量",
  native_tool_definition_count: "API 原生工具定义数量",
  capability_contract_count: "上下文能力契约数量",
  output_schema: "返回要求",
  output_tokens: "输出 Token",
  max_content_chars: "最多读取字符",
  max_hits: "最多命中数量",
  excerpt_chars: "每段摘录长度",
  manuscript_query: "正文检索内容",
  knowledge_query: "知识检索内容",
  knowledge_identities: "指定知识对象",
  knowledge_card_ids: "指定知识卡",
  catalog_types: "知识目录类型",
  upstream_artifact_refs: "上游产物",
  volume_ids: "卷范围",
  match_reasons: "命中原因",
  items: "召回内容",
  mode: "召回模式",
  strategy: "召回策略",
  source: "资料来源",
  source_type: "资料类型",
};

const readableEnumValues: Record<string, Record<string, string>> = {
  artifact_type: {
    canon_evidence_report: "小说事实证据报告",
    character_proposal: "人物设定方案",
    consistency_review: "一致性审查报告",
    external_research_report: "外部资料研究报告",
    knowledge_proposal: "知识候选方案",
    manuscript_candidate: "正文草稿",
    narrative_review: "叙事审查报告",
    narrative_summary: "叙事摘要",
    revision_candidate: "正文修改稿",
    scene_plan: "场景规划",
    story_architecture: "剧情架构",
    style_review: "文风审查报告",
    worldbuilding_proposal: "世界观设定方案",
  },
  authorization_policy: {
    none: "无需授权",
    author_grant: "需要作者授权",
    second_confirmation: "需要作者二次确认",
  },
  confidence: { high: "高", medium: "中", low: "低", unknown: "未知" },
  knowledge_type: {
    character: "人物",
    event: "事件",
    faction: "势力",
    item: "物品",
    location: "地点",
    rule: "规则",
  },
  lifecycle: { draft: "待审核", confirmed: "已确认", rejected: "已拒绝" },
  outcome: { satisfied: "已满足请求", partial: "部分满足", failed: "未满足" },
  phase: { plan: "规划", replan: "重规划", verify: "结果校验" },
  resolution: { unique: "唯一匹配", ambiguous: "存在歧义", not_found: "未找到" },
  side_effect: {
    read_only: "只读",
    preview: "仅生成预览",
    write: "会写入数据",
    high_risk_write: "高风险写入",
    none: "无写入",
  },
  status: {
    completed: "已完成",
    failed: "失败",
    timed_out: "超时",
    pending: "未开始",
    running: "运行中",
    success: "已完成",
    skipped: "已跳过",
    waiting_human: "等待作者",
  },
  kind: {
    tool: "工具",
    subagent: "专业智能体",
    user_instruction: "作者约束",
    task_summary: "任务摘要",
    resource_summary: "资料摘要",
    work_note: "过程记录",
    unresolved_issue: "未解决事项",
    fact_reference: "事实来源提示",
  },
  source_origin: {
    agent_extract: "智能体从原文提取",
    manual: "作者录入",
    migration: "历史资料迁移",
  },
  type: {
    tool: "工具",
    subagent: "专业智能体",
    character: "人物",
    event: "事件",
    faction: "势力",
    item: "物品",
    location: "地点",
    rule: "规则",
  },
  mode: { relevance: "按相关性召回", identity: "按身份解析" },
  scope: { fact_scope: "小说事实范围", writing_scope: "创作资料范围" },
  source: { confirmed_knowledge: "已确认知识", manuscript: "小说正文" },
  source_type: { confirmed_knowledge: "已确认知识", manuscript: "小说正文" },
  strategy: {
    milvus_hybrid_vector_graph: "Milvus 混合向量图谱召回",
    manuscript_lexical: "正文词法搜索",
    milvus_vector_graph: "向量图谱多跳召回",
  },
};

const hiddenTechnicalFields = new Set([
  "id",
  "artifact_id",
  "backend_duration_ms",
  "backend_metrics",
  "budget_limited",
  "call_id",
  "candidate_count",
  "content_sha256",
  "content_chars_used",
  "duration_ms",
  "effect_id",
  "effective_strategy",
  "embedding_call_id",
  "embedding_cost_amount",
  "embedding_duration_ms",
  "embedding_input_tokens",
  "empty_reason",
  "fallback_reason_code",
  "fallback_used",
  "finished_at",
  "hit_count",
  "index_search_duration_ms",
  "index_snapshot_id",
  "input_sha256",
  "memory_id",
  "node_id",
  "parent_call_id",
  "policy_name",
  "post_filter_duration_ms",
  "requested_strategy",
  "retrieval_id",
  "run_id",
  "source_id",
  "started_at",
  "strategy_snapshot",
  "task_id",
  "trace_id",
  "updated_at",
]);

export function contextPhaseLabel(phase: GeneralAgentContextSnapshot["phase"]): string {
  return { plan: "规划前", replan: "重规划前", verify: "结果校验前" }[phase];
}

export function contextPhasePurpose(phase: GeneralAgentContextSnapshot["phase"]): string {
  return {
    plan: "让编排模型理解本轮目标并决定最小执行路径。",
    replan: "带着上一轮校验问题重新调整执行计划。",
    verify: "结合执行结果判断任务是否完成以及如何回答。",
  }[phase];
}

export function modelCallLabel(call: GeneralAgentLLMReplay): string {
  const task = call.task_name;
  if (task === "general_writing_orchestrator.plan") return "编排模型 · 制定执行路径";
  if (task === "general_writing_orchestrator.plan.materialize") {
    return "编排模型 · 补齐节点参数";
  }
  if (task === "general_writing_orchestrator.replan") return "编排模型 · 调整执行路径";
  if (task === "general_writing_orchestrator.verify") return "编排模型 · 校验并形成回答";
  return `专业智能体 · ${generalCapabilityLabel(task)}`;
}

export function modelCallPurpose(call: GeneralAgentLLMReplay): string {
  if (call.task_name.endsWith(".plan")) return "根据已组装上下文判断本轮需要哪些能力。";
  if (call.task_name.endsWith(".plan.materialize")) return "根据能力契约生成节点可校验的具体输入。";
  if (call.task_name.endsWith(".replan")) return "根据执行或校验问题修订后续路径。";
  if (call.task_name.endsWith(".verify")) return "检查执行证据是否满足请求，并生成最终回答。";
  return "在明确职责边界内处理编排器交付的结构化任务。";
}

export function buildStableMemoryProjection(
  stableRules: string[],
  call?: GeneralAgentLLMReplay,
): Record<string, unknown> {
  const systemRequirements =
    call?.messages
      .filter(message => message.role === "system" && message.content.trim())
      .map(message => message.content) ?? [];
  const phaseContracts =
    call?.messages
      .filter(message => message.role === "developer")
      .map(message => parseStructuredContent(message.content))
      .filter(isRecord)
      .map(value => value["阶段稳定契约"])
      .filter(value => value !== undefined && value !== null) ?? [];

  return {
    ...(systemRequirements.length
      ? {
          "系统要求":
            systemRequirements.length === 1
              ? systemRequirements[0]
              : systemRequirements,
        }
      : {}),
    "稳定规则": stableRules,
    ...(phaseContracts.length
      ? {
          "阶段稳定契约":
            phaseContracts.length === 1 ? phaseContracts[0] : phaseContracts,
        }
      : {}),
    ...(call?.tools.length ? { "工具定义": call.tools } : {}),
  };
}

export function checkpointEventLabel(eventType: string): string {
  if (eventType === "checkpoint_put") return "保存可恢复状态";
  if (eventType === "checkpoint_writes") return "记录节点中间写入";
  if (eventType === "legacy_migrated") return "迁移旧检查点";
  if (eventType.startsWith("repaired_from_revision_")) return "从有效记录修复恢复点";
  return "更新恢复记录";
}

export function readableFieldLabel(key: string): string {
  if (readableFieldLabels[key]) return readableFieldLabels[key];
  return /[\u3400-\u9fff]/.test(key) ? key : "";
}

export function readableEntries(value: unknown): Array<{ key: string; label: string; value: unknown }> {
  if (!isRecord(value)) return [];
  return Object.entries(value)
    .filter(([key, item]) => !hiddenTechnicalFields.has(key) && item !== null && item !== "")
    .map(([key, item]) => ({ key, label: readableFieldLabel(key), value: readableFieldValue(key, item) }))
    .filter(entry => Boolean(entry.label));
}

export function sanitizeReadableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeReadableValue);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !hiddenTechnicalFields.has(key))
      .map(([key, item]) => [key, sanitizeReadableValue(item)]),
  );
}

export function splitReadableContent(content: string): ReadableContentPart[] {
  const parts: ReadableContentPart[] = [];
  let cursor = 0;

  while (cursor < content.length) {
    const opening = findNextJsonOpening(content, cursor);
    if (opening < 0) {
      appendReadableText(parts, content.slice(cursor));
      break;
    }
    appendReadableText(parts, content.slice(cursor, opening));
    const end = findJsonEnd(content, opening);
    if (end < 0) {
      parts.push({ kind: "text", text: "结构化结果已被运行时压缩，技术残片不在作者页面展示。" });
      break;
    }
    const candidate = content.slice(opening, end + 1);
    try {
      parts.push({ kind: "structured", value: JSON.parse(candidate) as unknown });
      cursor = end + 1;
    } catch {
      appendReadableText(parts, content.slice(opening, end + 1));
      cursor = end + 1;
    }
  }

  return parts.length ? parts : [{ kind: "text", text: "没有可读内容。" }];
}

export function parseStructuredContent(content: string): unknown | null {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return null;
  }
}

export function buildNovelStructureDisplay(
  value: unknown,
): NovelStructureDisplay | null {
  if (!isRecord(value) || !Array.isArray(value.volumes)) return null;
  const volumes = value.volumes
    .filter(isRecord)
    .map((volume, volumeIndex) => {
      const chapters = Array.isArray(volume.chapters)
        ? volume.chapters
            .filter(isRecord)
            .map((chapter, chapterIndex) => ({
              title:
                typeof chapter.title === "string"
                  ? chapter.title
                  : `第 ${chapterIndex + 1} 章`,
              order:
                typeof chapter.order === "number"
                  ? chapter.order
                  : chapterIndex + 1,
              wordCount:
                typeof chapter.word_count === "number"
                  ? chapter.word_count
                  : null,
              status:
                typeof chapter.status === "string"
                  ? chapter.status
                  : "",
            }))
        : [];
      return {
        title:
          typeof volume.title === "string"
            ? volume.title
            : `第 ${volumeIndex + 1} 卷`,
        order:
          typeof volume.order === "number"
            ? volume.order
            : volumeIndex + 1,
        chapters,
      };
    });
  const returnedChapters =
    typeof value.returned_chapters === "number"
      ? value.returned_chapters
      : volumes.reduce((total, volume) => total + volume.chapters.length, 0);
  return {
    totalChapters:
      typeof value.total_chapters === "number"
        ? value.total_chapters
        : returnedChapters,
    returnedChapters,
    truncated: value.truncated === true,
    volumes,
  };
}

function readableFieldValue(key: string, value: unknown): unknown {
  if (typeof value === "string" && readableEnumValues[key]?.[value]) {
    return readableEnumValues[key][value];
  }
  if (key === "capability_name" && typeof value === "string") {
    return generalCapabilityLabel(value);
  }
  if (key === "created_at" && typeof value === "string") {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(date);
  }
  if (key === "dependencies" && Array.isArray(value)) {
    return value.length ? `${value.length} 个前置节点` : "没有前置节点";
  }
  if ((key === "source_refs" || key === "artifact_refs") && Array.isArray(value)) {
    if (!value.length) return "无";
    return key === "source_refs"
      ? `已携带 ${value.length} 处可追溯来源`
      : `已关联 ${value.length} 份运行产物`;
  }
  if (key === "allowed_tools" && Array.isArray(value)) {
    return value.map(item => typeof item === "string" ? generalCapabilityLabel(item) : item);
  }
  if ((key === "accepted_artifact_types" || key === "produced_artifact_types") && Array.isArray(value)) {
    return value.map(item => typeof item === "string"
      ? readableEnumValues.artifact_type[item] ?? "其他结构化结果"
      : item);
  }
  if (key === "source_ref" && typeof value === "string") {
    return "已保留可追溯来源";
  }
  if (key === "created_request_index" && typeof value === "number") {
    return `运行时在第 ${value} 次请求后生成`;
  }
  if (key === "expires_after_request_index" && typeof value === "number") {
    return `第 ${value} 次请求后由运行时自动退出`;
  }
  if (key === "role" && typeof value === "string") {
    return { system: "系统要求", user: "任务消息", assistant: "模型历史回答" }[value] ?? value;
  }
  if (key === "scope_type" && typeof value === "string") {
    return {
      none: "未限定范围",
      selection: "当前选区",
      chapter: "当前章节",
      range: "章节范围",
      novel: "整本小说",
    }[value] ?? value;
  }
  return sanitizeReadableValue(value);
}

function appendReadableText(parts: ReadableContentPart[], value: string): void {
  const text = humanizeVisibleText(value).trim();
  if (text) parts.push({ kind: "text", text });
}

export function humanizeVisibleText(value: string): string {
  const localized = value
    .replace(/\[([a-z][a-z0-9_]*)\]/gi, (_, name: string) => `【${knownGeneralCapabilityLabel(name) ?? "运行资料"}】`)
    .replaceAll("输出 Schema", "模型返回要求")
    .replaceAll("Markdown 代码块", "代码块")
    .replaceAll("Schema", "返回格式")
    .replaceAll("JSON 对象", "结构化对象")
    .replaceAll("JSON", "结构化数据")
    .replaceAll("Runtime", "运行时")
    .replaceAll("Tool", "工具")
    .replaceAll("Prompt", "模型输入");
  const technicalTerms: Record<string, string> = {
    agent: "智能体",
    markdown: "正文文件",
    mongodb: "知识库",
    input_data: "能力输入",
    input_bindings: "上游结果绑定",
    fact_reference: "事实来源提示",
    source_ref: "来源证据",
    llm: "模型",
    schema: "返回格式",
  };
  return localized.replace(/\b[a-z][a-z0-9_]*\b/gi, token => {
    const capabilityLabel = knownGeneralCapabilityLabel(token);
    if (capabilityLabel) return capabilityLabel;
    return technicalTerms[token.toLowerCase()] ?? token;
  });
}

function findNextJsonOpening(content: string, start: number): number {
  for (let index = start; index < content.length; index += 1) {
    const character = content[index];
    if (character === "{" || character === "[") {
      if (character === "[") {
        const closing = content.indexOf("]", index);
        const label = closing < 0 ? "" : content.slice(index + 1, closing);
        if (/^[a-z][a-z0-9_]*$/i.test(label)) {
          index = closing;
          continue;
        }
      }
      return index;
    }
  }
  return -1;
}

function findJsonEnd(content: string, start: number): number {
  const stack: string[] = [];
  let inString = false;
  let escaped = false;
  for (let index = start; index < content.length; index += 1) {
    const character = content[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') {
      inString = true;
      continue;
    }
    if (character === "{" || character === "[") stack.push(character);
    if (character === "}" || character === "]") {
      const expected = character === "}" ? "{" : "[";
      if (stack.pop() !== expected) return -1;
      if (!stack.length) return index;
    }
  }
  return -1;
}

export function buildRuntimeTrace(
  run: GeneralAgentRun,
  calls: GeneralAgentLLMReplay[],
  traces: GeneralAgentInvocationTrace[],
): RuntimeTraceItem[] {
  const items: RuntimeTraceItem[] = [
    {
      id: `request-${run.run_id}`,
      kind: "request",
      title: "Runtime · 接收请求",
      summary: run.user_goal,
      occurredAt: run.created_at,
      status: "已接收",
      input: {
        content: run.user_goal,
        ...run.scope,
      },
      details: [
        run.author_constraints.length
          ? `同时携带 ${run.author_constraints.length} 条作者约束。`
          : "本轮没有额外作者约束。",
        run.external_access_allowed ? "允许使用外部访问能力。" : "本轮未授权外部访问。",
      ],
    },
  ];

  run.lifecycle_events
    .filter(event =>
      event.status === "failed" ||
      event.status === "cancelled" ||
      event.status === "timeout"
    )
    .forEach((event, index) => {
    items.push({
      id: `state-${index}-${event.created_at}`,
      kind: "state",
      title: `Runtime · ${runStatusLabel(event.status)}`,
      summary: event.reason || "运行状态已更新。",
      occurredAt: event.created_at,
      status: runStatusLabel(event.status),
      details: [],
    });
    });

  calls.forEach(call => {
    const inputCharCount = call.messages.reduce(
      (total, message) => total + message.content.length,
      0,
    );
    const capabilityContractCount = modelCallCapabilityContractCount(call);
    items.push({
      id: call.call_id,
      kind: "model",
      title: modelCallLabel(call),
      summary: modelCallPurpose(call),
      occurredAt: call.started_at,
      status: call.status === "completed" ? "已返回" : "调用失败",
      input: {
        caller: call.task_name.startsWith("general_writing_orchestrator.")
          ? "编排 Agent"
          : "专业子 Agent",
        target: call.model_id,
        message_count: call.messages.length,
        input_char_count: inputCharCount,
        ...(call.input_tokens !== null && call.input_tokens !== undefined
          ? { input_tokens: call.input_tokens }
          : { estimated_input_tokens: Math.ceil(inputCharCount / 4) }),
        ...(call.cached_input_tokens !== null && call.cached_input_tokens !== undefined
          ? { cached_input_tokens: call.cached_input_tokens }
          : {}),
        ...(capabilityContractCount !== undefined
          ? { capability_contract_count: capabilityContractCount }
          : {}),
        native_tool_definition_count: call.tools.length,
      },
      output: {
        status: call.status,
        finish_reason: call.finish_reason,
        tool_call_names: call.response_tool_calls.map(item => item.name),
        ...(call.output_tokens !== null && call.output_tokens !== undefined
          ? { output_tokens: call.output_tokens }
          : {}),
      },
      details: [
        `${call.messages.length} 条角色消息`,
        `${call.total_tokens?.toLocaleString("zh-CN") ?? "未统计"} Token`,
        formatDuration(call.duration_ms),
      ],
    });
  });

  run.node_runs.forEach(node => items.push(nodeTraceItem(node, traces)));

  if (run.pending_human_request) {
    items.push({
      id: run.pending_human_request.request_id,
      kind: "human",
      title: "运行时等待作者决定",
      summary: run.pending_human_request.prompt,
      occurredAt: run.pending_human_request.created_at,
      status: "等待作者",
      input: run.pending_human_request.input_summary,
      details: [
        run.pending_human_request.second_confirmation_required
          ? "该操作还需要二次确认。"
          : "作者答复后可继续执行。",
      ],
    });
  }

  if (run.final_answer) {
    items.push({
      id: `answer-${run.run_id}`,
      kind: "answer",
      title: "运行时输出本轮回答",
      summary: run.final_answer,
      occurredAt: run.finished_at ?? run.updated_at,
      status: "已输出",
      output: run.final_answer,
      details: [
        run.verification_issues.length
          ? `仍记录 ${run.verification_issues.length} 个校验问题。`
          : "结果校验未留下待处理问题。",
      ],
    });
  }

  return items.sort((left, right) => {
    const timeDifference = Date.parse(left.occurredAt) - Date.parse(right.occurredAt);
    return timeDifference || traceOrder(left.kind) - traceOrder(right.kind);
  });
}

function modelCallCapabilityContractCount(
  call: GeneralAgentLLMReplay,
): number | undefined {
  for (const message of call.messages) {
    if (message.role !== "developer") continue;
    const content = parseStructuredContent(message.content);
    if (!isRecord(content)) continue;
    const phaseContract = content["阶段稳定契约"];
    if (!isRecord(phaseContract)) continue;
    for (const catalogName of ["完整能力契约目录", "完整轻量能力目录"]) {
      const catalog = phaseContract[catalogName];
      if (!isRecord(catalog)) continue;
      const count = catalog["能力总数"];
      if (typeof count === "number" && Number.isFinite(count)) return count;
    }
  }
  return undefined;
}

function nodeTraceItem(
  node: GeneralAgentNodeRun,
  traces: GeneralAgentInvocationTrace[],
): RuntimeTraceItem {
  const trace = node.trace_id ? traces.find(item => item.trace_id === node.trace_id) : undefined;
  return {
    id: `node-${node.plan_revision}-${node.node_id}`,
    kind: "capability",
    capabilityName: node.capability_name,
    title: `${node.kind === "tool" ? "工具" : "专业智能体"} · ${generalCapabilityLabel(node.capability_name)}`,
    summary: node.objective ? humanizeVisibleText(node.objective) : "执行计划中的专业能力节点。",
    occurredAt: node.started_at ?? node.finished_at ?? "9999-12-31T23:59:59Z",
    status: nodeStatusLabel(node.status),
    input: node.resolved_input,
    output: nodeDisplayOutput(node),
    details: [
      node.plan_revision === 1
        ? "初始计划"
        : `第 ${node.plan_revision - 1} 次调整后的计划`,
      node.dependencies.length ? `等待 ${node.dependencies.length} 个前置节点` : "没有前置节点",
      nodeSourceSummary(node, trace?.source_count),
      formatDuration(node.duration_ms),
    ],
  };
}

function nodeDisplayOutput(node: GeneralAgentNodeRun): unknown {
  if (
    node.capability_name !== "get_knowledge_chapter_coverage"
    || !isRecord(node.output)
  ) {
    return node.output;
  }
  return {
    latest_chapter: node.output["latest_chapter"],
    confirmed_card_count: node.output["confirmed_card_count"],
    referenced_card_count: node.output["referenced_card_count"],
  };
}

function nodeSourceSummary(
  node: GeneralAgentNodeRun,
  traceSourceCount: number | undefined,
): string {
  if (
    node.capability_name === "get_knowledge_chapter_coverage"
    && isRecord(node.output)
  ) {
    const referencedCardCount = node.output["referenced_card_count"];
    if (typeof referencedCardCount === "number" && Number.isFinite(referencedCardCount)) {
      return `统计依据：${referencedCardCount} 张含章节引用的知识卡和 1 份章节目录`;
    }
  }
  const sourceCount = node.source_refs.length || traceSourceCount || 0;
  return sourceCount ? `${sourceCount} 个来源引用` : "没有来源引用";
}

function runStatusLabel(status: GeneralAgentRun["status"]): string {
  return {
    init: "初始化",
    clarifying: "澄清需求",
    planning: "制定计划",
    executing: "执行能力",
    waiting_human: "等待作者",
    verifying: "校验结果",
    replanning: "调整计划",
    completed: "完成",
    failed: "失败",
    cancelled: "已取消",
    timeout: "已超时",
  }[status];
}

function nodeStatusLabel(status: GeneralAgentNodeRun["status"]): string {
  return {
    pending: "未开始",
    running: "运行中",
    success: "已完成",
    failed: "失败",
    skipped: "已跳过",
    waiting_human: "等待作者",
  }[status];
}

function traceOrder(kind: RuntimeTraceItem["kind"]): number {
  return { request: 0, state: 1, context: 2, model: 3, capability: 4, human: 5, answer: 6 }[kind];
}

function formatDuration(durationMs: number): string {
  return durationMs < 1_000 ? `${durationMs} 毫秒` : `${(durationMs / 1_000).toFixed(1)} 秒`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
