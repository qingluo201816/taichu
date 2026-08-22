export interface BenchmarkDisplayCopy {
  label: string;
  description: string;
}

export interface BenchmarkRunDisplay {
  name: string;
  timeLabel: string;
}

const benchmarkCaseCopies: Record<string, BenchmarkDisplayCopy> = {
  direct_answer_current_request: {
    label: "当前请求直接回答",
    description: "验证小型请求可以直接完成，不被强制送入冗长流程。",
  },
  single_manuscript_search: {
    label: "单次正文检索",
    description: "验证一次能力调用即可找到并引用相关正文。",
  },
  structure_coverage_read: {
    label: "结构与覆盖读取",
    description: "验证大纲结构与章节覆盖范围能够被准确读取。",
  },
  single_knowledge_retrieval: {
    label: "单次知识检索",
    description: "验证当前请求所需的知识卡能够被准确召回。",
  },
  knowledge_catalog_identity_read: {
    label: "知识目录身份读取",
    description: "验证知识目录与实际知识卡身份保持一致。",
  },
  external_research_grounded: {
    label: "外部资料有据研究",
    description: "验证获授权的外部研究保留可核对的来源依据。",
  },
  single_canon_evidence: {
    label: "单次设定证据",
    description: "验证小说设定结论只引用可核对的事实证据。",
  },
  summary_world_character: {
    label: "世界与人物并行分析",
    description: "验证世界观与人物信息可以并行分析并正确合并。",
  },
  architecture_scene_draft: {
    label: "场景规划与草稿生成",
    description: "验证场景规划结果能够继续驱动草稿生成。",
  },
  parallel_review_triad: {
    label: "三路并行审查",
    description: "验证多个审查能力能够并行执行且相互隔离。",
  },
  revision_from_reviews: {
    label: "依据审查定向修订",
    description: "验证审查意见能够被汇总并用于定向修订。",
  },
  manuscript_preview_only: {
    label: "正文补丁仅预览",
    description: "验证未获写入授权时只生成预览，不修改正文。",
  },
  manuscript_patch_authorized_resume: {
    label: "授权后应用正文补丁",
    description: "验证人工授权后可以从中断点恢复并执行写入。",
  },
  structure_create_update: {
    label: "结构创建与更新",
    description: "验证结构数据能够在授权范围内创建和更新。",
  },
  structure_delete_second_confirmation: {
    label: "结构删除二次确认",
    description: "验证高风险删除必须经过明确的二次确认。",
  },
  knowledge_create_update: {
    label: "知识创建与更新",
    description: "验证知识候选能够按既定规则创建和更新。",
  },
  write_authorization_denied: {
    label: "未授权写入阻断",
    description: "验证缺少写入授权时不会修改任何内容。",
  },
  memory_active_projection: {
    label: "有效记忆按需投影",
    description: "验证当前有效记忆只按本轮需要进入模型上下文。",
  },
  memory_stale_dependency: {
    label: "过期记忆依赖拒绝",
    description: "验证已经过期的记忆依赖不会进入当前执行。",
  },
  memory_rejected_parallel_isolation: {
    label: "拒绝记忆并行隔离",
    description: "验证被拒绝的记忆不会污染其他并行分支。",
  },
  memory_superseded_repair: {
    label: "被替代记忆状态修复",
    description: "验证新记忆替代旧记忆后运行状态保持正确。",
  },
};

const benchmarkFieldCopies: Record<string, BenchmarkDisplayCopy> = {
  "director and client request": {
    label: "编排与用户请求",
    description: "验证高层编排能够准确承接用户目标并保持全局控制。",
  },
};

const runTimestampPattern =
  /^benchmark_run_(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z(?:_|$)/;

export function benchmarkCaseDisplay(caseId: string): BenchmarkDisplayCopy {
  return (
    benchmarkCaseCopies[caseId] ??
    benchmarkFieldCopies[normalizeFieldKey(caseId)] ?? {
      label: "其他合同能力",
      description: "验证该项固定合同是否按要求完成；技术标识仅保留在调试记录中。",
    }
  );
}

export function benchmarkFieldDisplay(value: string): BenchmarkDisplayCopy {
  return (
    benchmarkFieldCopies[normalizeFieldKey(value)] ??
    benchmarkCaseCopies[value] ?? {
      label: "其他评测字段",
      description: "该字段尚未配置公开名称，原始技术值不会在普通界面显示。",
    }
  );
}

export function benchmarkRunDisplay(
  runId: string,
  ordinal: number,
): BenchmarkRunDisplay {
  const match = runTimestampPattern.exec(runId);
  const year = match ? Number(match[1]) : Number.NaN;
  return {
    name: `第 ${Math.max(1, ordinal)} 次评测`,
    timeLabel:
      match && year >= 2020
        ? formatRunTimestamp(match)
        : "固定基线记录",
  };
}

function normalizeFieldKey(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}

function formatRunTimestamp(match: RegExpExecArray): string {
  const [, year, month, day, hour, minute, second] = match;
  const timestamp = new Date(
    `${year}-${month}-${day}T${hour}:${minute}:${second}Z`,
  );
  if (Number.isNaN(timestamp.getTime())) return "运行时间待记录";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .formatToParts(timestamp)
    .reduce<Record<string, string>>((result, part) => {
      result[part.type] = part.value;
      return result;
    }, {});
  return `${parts.year}年${parts.month}月${parts.day}日 ${parts.hour}:${parts.minute}`;
}
