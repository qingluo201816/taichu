import assert from "node:assert/strict";

import {
  buildNovelStructureDisplay,
  buildStableMemoryProjection,
  buildRuntimeTrace,
  checkpointSourceLabel,
  contextPhaseLabel,
  generalSubagentResultViewKind,
  generalSubagentResultViewKinds,
  generalToolResultViewKind,
  generalToolResultViewKinds,
  modelCallLabel,
  readableEntries,
  splitReadableContent,
} from "../../src/lib/general-agent-memory-trace";
import type {
  GeneralAgentLLMReplay,
  GeneralAgentRun,
} from "../../src/lib/types/general-agent";

const call = {
  call_id: "llm-call",
  run_id: "run",
  task_type: "general_agent",
  task_name: "general_writing_orchestrator.verify",
  feature: "通用写作助手",
  model_id: "model",
  upstream_model: "model",
  wire_protocol: "openai_responses",
  status: "completed",
  response_mode: "json",
  messages: [{ role: "user", content: "请校验", tool_calls: [], is_error: false }],
  tools: [],
  tool_choice: "auto",
  response_tool_calls: [],
  response_text: "校验完成",
  request_sha256: "a".repeat(64),
  response_sha256: "b".repeat(64),
  redaction_count: 0,
  total_tokens: 20,
  started_at: "2026-07-22T00:00:03Z",
  finished_at: "2026-07-22T00:00:04Z",
  duration_ms: 1_000,
} satisfies GeneralAgentLLMReplay;

assert.equal(contextPhaseLabel("replan"), "重规划前");
assert.equal(modelCallLabel(call), "编排模型 · 校验并形成回答");
assert.equal(checkpointSourceLabel("loop"), "完成图步骤");
assert.deepEqual(Object.keys(generalToolResultViewKinds).sort(), [
  "apply_manuscript_patch",
  "create_confirmed_knowledge",
  "create_novel_structure_items",
  "delete_novel_structure_items",
  "get_novel_structure",
  "list_knowledge_catalog",
  "preview_manuscript_patch",
  "read_external_source",
  "read_knowledge_cards",
  "read_manuscript",
  "resolve_knowledge_identity",
  "retrieve_story_context",
  "search_external_sources",
  "update_confirmed_knowledge",
  "update_novel_structure",
]);
assert.equal(generalToolResultViewKind("read_manuscript"), "manuscript_content");
assert.equal(generalToolResultViewKind("retrieve_story_context"), "story_context");
assert.equal(generalToolResultViewKind("unknown_tool"), undefined);
assert.deepEqual(Object.keys(generalSubagentResultViewKinds).sort(), [
  "canon_evidence",
  "character",
  "consistency_reviewer",
  "drafting",
  "external_research",
  "narrative_reviewer",
  "narrative_summary",
  "revision",
  "scene_planning",
  "story_architecture",
  "style_reviewer",
  "worldbuilding",
]);
assert.equal(
  generalSubagentResultViewKind("consistency_reviewer"),
  "consistency_review",
);
assert.equal(generalSubagentResultViewKind("unknown_agent"), undefined);
assert.deepEqual(
  buildStableMemoryProjection(
    ["只能调用已注册能力。"],
    {
      ...call,
      messages: [
        {
          role: "system",
          content: JSON.stringify({
            "稳定记忆（System Prompt）": {
              "身份、基本行为与准则": ["你是高层编排智能体。"],
              "Static Capability Index（静态能力索引）": [
                { name: "retrieve_story_context", type: "tool" },
              ],
            },
          }),
          tool_calls: [],
          is_error: false,
        },
        {
          role: "developer",
          content: JSON.stringify({
            "阶段契约": {
              "相关能力字段摘要": [],
              "输出Schema": { type: "object" },
            },
          }),
          tool_calls: [],
          is_error: false,
        },
      ],
      tools: [
        {
          name: "retrieve_story_context",
          description: "搜索正文",
          parameters: { type: "object" },
          strict: true,
        },
      ],
    },
  ),
  {
    "系统要求": {
      "身份、基本行为与准则": ["你是高层编排智能体。"],
      "Static Capability Index（静态能力索引）": [
        { name: "retrieve_story_context", type: "tool" },
      ],
    },
    "稳定规则": ["只能调用已注册能力。"],
    "工具定义": [
      {
        name: "retrieve_story_context",
        description: "搜索正文",
        parameters: { type: "object" },
        strict: true,
      },
    ],
  },
);
assert.deepEqual(
  readableEntries({
    query: "秦浩轩",
    run_id: "隐藏",
    answer: "人物说明",
    knowledge_type: "character",
    resolution: "not_found",
  }),
  [
    { key: "query", label: "检索内容", value: "秦浩轩" },
    { key: "answer", label: "回答", value: "人物说明" },
    { key: "knowledge_type", label: "知识类型", value: "人物" },
    { key: "resolution", label: "解析结果", value: "未找到" },
  ],
);

const embeddedMemory = splitReadableContent(
  '资源摘要：已读取人物资料。结果摘要：{"lifecycle":"draft","artifact_type":"narrative_summary","summary":"秦浩轩完成引气。","source_refs":["internal-ref"]}',
);
assert.equal(embeddedMemory[0]?.kind, "text");
assert.equal(embeddedMemory[1]?.kind, "structured");
if (embeddedMemory[1]?.kind === "structured") {
  assert.deepEqual(readableEntries(embeddedMemory[1].value), [
    { key: "lifecycle", label: "记录状态", value: "待审核" },
    { key: "artifact_type", label: "产物类型", value: "叙事摘要" },
    { key: "summary", label: "内容摘要", value: "秦浩轩完成引气。" },
    { key: "source_refs", label: "来源证据", value: "已携带 1 处可追溯来源" },
  ]);
}
const truncatedMemory = splitReadableContent(
  '资料摘要：已完成检索。结果摘要：{"kind":"resource_summary","summary":"内容被截断…',
);
const truncatedTail = truncatedMemory.at(-1);
assert.equal(truncatedTail?.kind, "text");
assert.match(
  truncatedTail?.kind === "text" ? truncatedTail.text : "",
  /技术残片不在作者页面展示/,
);
assert.deepEqual(readableEntries({ kind: "resource_summary" }), [
  { key: "kind", label: "执行类型", value: "资料摘要" },
]);
assert.deepEqual(
  readableEntries({
    summary: "保留的业务内容",
    policy_name: "general_agent_runtime",
    unknown_internal_key: "不应展示",
  }),
  [{ key: "summary", label: "内容摘要", value: "保留的业务内容" }],
);
const localizedPrompt = splitReadableContent("结论应能回到 source_ref，并使用 [retrieve_story_context] 取证。");
assert.deepEqual(localizedPrompt, [
  { kind: "text", text: "结论应能回到 来源证据，并使用 【统一检索小说证据】 取证。" },
]);
assert.deepEqual(splitReadableContent("不要使用 Markdown 代码块。输出 Schema："), [
  { kind: "text", text: "不要使用 代码块。模型返回要求：" },
]);
assert.deepEqual(
  buildNovelStructureDisplay({
    total_chapters: 2,
    returned_chapters: 2,
    truncated: false,
    volumes: [
      {
        title: "第一卷",
        order: 1,
        chapters: [
          { title: "第1章 起点", order: 1, word_count: 3200, status: "active" },
          { title: "第2章 转折", order: 2, word_count: 2800, status: "active" },
        ],
      },
    ],
  }),
  {
    totalChapters: 2,
    returnedChapters: 2,
    truncated: false,
    volumes: [
      {
        title: "第一卷",
        order: 1,
        chapters: [
          { title: "第1章 起点", order: 1, wordCount: 3200, status: "active" },
          { title: "第2章 转折", order: 2, wordCount: 2800, status: "active" },
        ],
      },
    ],
  },
);

const run = {
  run_id: "run",
  task_id: "task",
  conversation_id: "conversation",
  request_index: 1,
  agent_name: "general_writing_assistant",
  user_goal: "秦浩轩是谁？",
  scope: { scope_type: "none", chapter_ids: [], selection_text: "", direct_context: "" },
  author_constraints: [],
  external_access_allowed: false,
  limits: {
    max_plan_nodes: 8,
    max_replans: 2,
    max_concurrency: 3,
    max_total_tool_calls: 20,
    max_runtime_seconds: 300,
  },
  status: "completed",
  messages: [],
  plan_revision: 1,
  replan_count: 0,
  node_runs: [],
  final_answer: "秦浩轩是故事中的人物。",
  verification_issues: [],
  memory_refs: [],
  compression_stats: {
    compressed: false,
    fallback_used: false,
    input_char_count: 10,
    output_char_count: 10,
    estimated_token_count: 3,
    omitted_message_count: 0,
    omitted_node_count: 0,
    selected_memory_count: 0,
  },
  context_resume_differences: [],
  lifecycle_events: [
    {
      status: "init",
      reason: "任务已创建。",
      created_at: "2026-07-22T00:00:00Z",
    },
    {
      status: "planning",
      reason: "开始高层规划。",
      created_at: "2026-07-22T00:00:01Z",
    },
    {
      status: "completed",
      reason: "回答已生成。",
      created_at: "2026-07-22T00:00:05Z",
    },
  ],
  checkpoint_revision: 2,
  resumable: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:05Z",
  started_at: "2026-07-22T00:00:00Z",
  finished_at: "2026-07-22T00:00:05Z",
  errors: [],
} satisfies GeneralAgentRun;

const capabilityContext = JSON.stringify({
  "稳定记忆（System Prompt）": {
    "Static Capability Index（静态能力索引）": Array.from(
      { length: 28 },
      (_, index) => ({ name: `capability_${index}`, type: "tool" }),
    ),
  },
});
const usageCall = {
  ...call,
  messages: [
    {
      role: "system" as const,
      content: capabilityContext,
      tool_calls: [],
      is_error: false,
    },
    ...call.messages,
  ],
  input_tokens: 176,
  cached_input_tokens: 21_632,
  output_tokens: 600,
};
const timeline = buildRuntimeTrace(run, [usageCall], []);
assert.deepEqual(timeline.map(item => item.kind), ["request", "model", "answer"]);
assert.equal(timeline[0].title, "Runtime · 接收请求");
assert.equal(timeline[1].status, "已返回");
assert.deepEqual(timeline[1].input, {
  caller: "编排 Agent",
  target: "model",
  message_count: 2,
  input_char_count: capabilityContext.length + "请校验".length,
  input_tokens: 176,
  cached_input_tokens: 21_632,
  capability_contract_count: 28,
  native_tool_definition_count: 0,
});
assert.deepEqual(timeline[1].output, {
  status: "completed",
  finish_reason: undefined,
  tool_call_names: [],
  output_tokens: 600,
});
assert.equal(timeline.at(-1)?.summary, "秦浩轩是故事中的人物。");

const coverageTimeline = buildRuntimeTrace(
  {
    ...run,
    node_runs: [
      {
        node_id: "get_coverage",
        plan_revision: 1,
        kind: "tool",
        capability_name: "get_knowledge_chapter_coverage",
        objective: "统计知识库覆盖章节。",
        dependencies: [],
        status: "success",
        resolved_input: {},
        output: {
          confirmed_card_count: 134,
          referenced_card_count: 83,
          latest_chapter: {
            order: 15,
            title: "第15章 是非黑白岂颠倒",
          },
        },
        source_refs: Array.from({ length: 84 }, (_, index) => `source-${index}`),
        artifact_refs: [],
        authorization_approved: false,
        authorization_second_confirmation: false,
        authorization_resource_scopes: [],
        duration_ms: 12,
      },
    ],
  },
  [],
  [],
);
const coverageNode = coverageTimeline.find(item => item.kind === "capability");
assert.equal(coverageNode?.title, "工具 · 统计知识库章节覆盖");
assert.deepEqual(coverageNode?.details, [
  "初始计划",
  "没有前置节点",
  "统计依据：83 张含章节引用的知识卡和 1 份章节目录",
  "12 毫秒",
]);
assert.deepEqual(coverageNode?.output, {
  latest_chapter: {
    order: 15,
    title: "第15章 是非黑白岂颠倒",
  },
  confirmed_card_count: 134,
  referenced_card_count: 83,
});
console.log("通用写作助手记忆追踪转换测试通过。");
