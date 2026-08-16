"use client";

import { useEffect, useMemo, useState } from "react";
import { GitBranch } from "lucide-react";

import type {
  AgentBatchChapterProgress,
  AgentNodeStatus,
  AgentRun,
  AgentRunGraphEdge,
  AgentRunGraphNode,
  AgentRunNode,
} from "@/lib/types/agent-workbench";

const nodeStatusLabel: Record<AgentNodeStatus, string> = {
  pending: "等待",
  running: "运行中",
  success: "成功",
  failed: "失败",
  skipped: "跳过",
};

const defaultSingleGraphNodes: AgentRunGraphNode[] = [
  { node_name: "LoadChapterNode", label: "读取章节", lane: "预处理" },
  { node_name: "SegmentChapterNode", label: "切分正文", lane: "预处理" },
  { node_name: "GeneralExtractionNode", label: "通用抽取", lane: "抽取" },
  { node_name: "MentionNormalizeNode", label: "提及清洗", lane: "抽取" },
  { node_name: "EntityAggregationNode", label: "实体聚合", lane: "抽取" },
  { node_name: "CandidateQualityGateNode", label: "质量闸门", lane: "抽取" },
  { node_name: "TypeDispatchNode", label: "类型分发", lane: "分发" },
  { node_name: "CharacterExpertNode", label: "角色专家", lane: "并行专家" },
  { node_name: "EntityExpertNode", label: "实体专家", lane: "并行专家" },
  { node_name: "EventRuleExpertNode", label: "事件规则专家", lane: "并行专家" },
  { node_name: "MergeExpertCandidatesNode", label: "分支汇合", lane: "汇合" },
  { node_name: "NormalizeAndValidateNode", label: "规范校验", lane: "后处理" },
  {
    node_name: "RunInternalConflictCheckNode",
    label: "本次冲突检查",
    lane: "后处理",
  },
  { node_name: "MatchExistingKnowledgeNode", label: "匹配有效知识", lane: "后处理" },
  {
    node_name: "SynthesizeCandidateSummariesNode",
    label: "综合候选摘要",
    lane: "后处理",
  },
  { node_name: "BuildReviewItemsNode", label: "生成审核项", lane: "后处理" },
  { node_name: "WriteIntermediateJsonNode", label: "写入中间态", lane: "写入" },
];

const defaultSingleGraphEdges: AgentRunGraphEdge[] = [
  { source: "LoadChapterNode", target: "SegmentChapterNode" },
  { source: "SegmentChapterNode", target: "GeneralExtractionNode" },
  { source: "GeneralExtractionNode", target: "MentionNormalizeNode" },
  { source: "MentionNormalizeNode", target: "EntityAggregationNode" },
  { source: "EntityAggregationNode", target: "CandidateQualityGateNode" },
  { source: "CandidateQualityGateNode", target: "TypeDispatchNode" },
  { source: "TypeDispatchNode", target: "CharacterExpertNode" },
  { source: "TypeDispatchNode", target: "EntityExpertNode" },
  { source: "TypeDispatchNode", target: "EventRuleExpertNode" },
  { source: "CharacterExpertNode", target: "MergeExpertCandidatesNode" },
  { source: "EntityExpertNode", target: "MergeExpertCandidatesNode" },
  { source: "EventRuleExpertNode", target: "MergeExpertCandidatesNode" },
  { source: "MergeExpertCandidatesNode", target: "NormalizeAndValidateNode" },
  { source: "NormalizeAndValidateNode", target: "RunInternalConflictCheckNode" },
  { source: "RunInternalConflictCheckNode", target: "MatchExistingKnowledgeNode" },
  {
    source: "MatchExistingKnowledgeNode",
    target: "SynthesizeCandidateSummariesNode",
  },
  {
    source: "SynthesizeCandidateSummariesNode",
    target: "BuildReviewItemsNode",
  },
  { source: "BuildReviewItemsNode", target: "WriteIntermediateJsonNode" },
];

const batchPreNodes = defaultSingleGraphNodes.slice(0, 7);
const batchExpertNodes = defaultSingleGraphNodes.slice(7, 10);
const batchPostNodes: AgentRunGraphNode[] = [
  { node_name: "BatchCardAggregationNode", label: "多章聚合", lane: "统一后处理" },
  { node_name: "BatchConflictCheckNode", label: "批量冲突", lane: "统一后处理" },
  {
    node_name: "BatchMatchExistingKnowledgeNode",
    label: "匹配知识",
    lane: "统一后处理",
  },
  {
    node_name: "BatchSynthesizeCandidateSummariesNode",
    label: "综合候选摘要",
    lane: "统一后处理",
  },
  { node_name: "BatchBuildReviewItemsNode", label: "生成审核", lane: "统一后处理" },
  { node_name: "BatchWriteRunNode", label: "写入运行", lane: "写入" },
];

type VisualGraphNode = AgentRunGraphNode & {
  source_node_name?: string;
};

type FlowNode = VisualGraphNode & {
  x: number;
  y: number;
  width: number;
  height: number;
};

type FlowBounds = {
  width: number;
  height: number;
};

type FlowLayout = {
  nodes: FlowNode[];
  bounds: FlowBounds;
};

type NodeViewState = {
  status: AgentNodeStatus;
  durationLabel: string;
  node?: AgentRunNode;
};

const singlePositions: Record<
  string,
  { x: number; y: number; width?: number; height?: number }
> = {
  LoadChapterNode: { x: 24, y: 24 },
  SegmentChapterNode: { x: 134, y: 24 },
  GeneralExtractionNode: { x: 244, y: 24 },
  MentionNormalizeNode: { x: 354, y: 24 },
  EntityAggregationNode: { x: 464, y: 24 },
  CandidateQualityGateNode: { x: 574, y: 24 },
  TypeDispatchNode: { x: 684, y: 24 },
  CharacterExpertNode: { x: 244, y: 124 },
  EntityExpertNode: { x: 404, y: 124 },
  EventRuleExpertNode: { x: 564, y: 124 },
  MergeExpertCandidatesNode: { x: 404, y: 220 },
  NormalizeAndValidateNode: { x: 684, y: 316 },
  RunInternalConflictCheckNode: { x: 574, y: 316 },
  MatchExistingKnowledgeNode: { x: 464, y: 316 },
  SynthesizeCandidateSummariesNode: { x: 354, y: 316 },
  BuildReviewItemsNode: { x: 244, y: 316 },
  WriteIntermediateJsonNode: { x: 134, y: 316 },
};

const SINGLE_NODE_WIDTH = 96;
const SINGLE_NODE_HEIGHT = 48;

export function TaskFlowGraph({ run }: { run: AgentRun }) {
  const [now, setNow] = useState(() => Date.now());
  const hasRunning = runHasRunningNode(run);

  useEffect(() => {
    if (!hasRunning) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasRunning, run.run_id]);

  if (run.scope.scope_type === "chapter_batch") {
    return <BatchFlowGraph run={run} now={now} />;
  }

  return <SingleFlowGraph run={run} now={now} />;
}

function SingleFlowGraph({ run, now }: { run: AgentRun; now: number }) {
  const graphNodes = run.graph_nodes.length > 0 ? run.graph_nodes : defaultSingleGraphNodes;
  const graphEdges = run.graph_edges.length > 0 ? run.graph_edges : defaultSingleGraphEdges;
  const layout = buildFlowLayout(graphNodes);
  const nodesByName = new Map(layout.nodes.map(node => [node.node_name, node]));
  const statusByName = new Map(run.nodes.map(node => [node.node_name, node]));
  const nodeFor = (graphNode: FlowNode | undefined): AgentRunNode | undefined => {
    if (!graphNode) {
      return undefined;
    }
    return statusByName.get(graphNode.source_node_name ?? graphNode.node_name);
  };
  const statusFor = (graphNode: FlowNode | undefined): AgentNodeStatus =>
    nodeFor(graphNode)?.status ?? "pending";

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <GraphHeader
        title="节点架构状态流转图"
        meta={`${layout.nodes.length} 节点 · ${graphEdges.length} 连线`}
      />

      <div className="mt-2 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[linear-gradient(180deg,rgba(250,250,250,0.025),rgba(0,0,0,0)),var(--tc-surface-muted)]">
        <svg
          role="img"
          aria-label="智能体任务状态流程图"
          className="mx-auto block h-full min-h-0 w-full max-w-[980px]"
          viewBox={`0 0 ${layout.bounds.width} ${layout.bounds.height}`}
        >
          <defs>
            <TaskFlowGrid />
            <marker
              id="single-task-flow-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6.5"
              refY="4"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M 0 0 L 8 4 L 0 8 z" fill="rgba(161,161,170,0.9)" />
            </marker>
          </defs>

          <rect width="100%" height="100%" fill="url(#task-flow-grid)" />
          <SingleBranchBands />

          <g fill="none">
            {graphEdges.map(edge => {
              const source = nodesByName.get(edge.source);
              const target = nodesByName.get(edge.target);
              if (!source || !target) {
                return null;
              }
              const status = edgeStatus(statusFor(source), statusFor(target));
              return (
                <path
                  key={`${edge.source}-${edge.target}`}
                  d={singleEdgePath(source, target, edge.source, edge.target)}
                  stroke={edgeStroke(status)}
                  strokeWidth={status === "running" ? 1.7 : 1.25}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  markerEnd="url(#single-task-flow-arrow)"
                  opacity={status === "pending" ? 0.46 : 0.92}
                  className={status === "running" ? "motion-safe:animate-pulse" : ""}
                />
              );
            })}
          </g>

          <g>
            {layout.nodes.map((graphNode, index) => {
              const node = nodeFor(graphNode);
              const status = node?.status ?? "pending";
              return (
                <FlowNodeItem
                  key={graphNode.node_name}
                  graphNode={graphNode}
                  node={node}
                  index={index}
                  status={status}
                  now={now}
                />
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}

function BatchFlowGraph({ run, now }: { run: AgentRun; now: number }) {
  const lanes = useMemo(() => normalizeBatchProgress(run), [run]);
  const branchStages = layeredBranchStages();
  const postStages = layeredPostStages();
  const branchEdges = layeredBranchEdges(branchStages);
  const dispatchStage = branchStages.find(stage => stage.key === "dispatch");
  const expertStages = branchStages.filter(stage =>
    ["character", "entityExpert", "eventRule"].includes(stage.key),
  );
  const mergeStage = branchStages.find(stage => stage.key === "merge");
  const mergeStatus = mergeStage
    ? combinedStatus(
        lanes.map(lane => stageStateForLane(mergeStage, lane, run.status, now).status),
      )
    : "pending";
  const postStates = postStages.map(stage =>
    stateFromNodes(run.nodes, stage.nodeName ?? stage.key, now),
  );
  const branchNodeCount = batchPreNodes.length + batchExpertNodes.length + 1;
  const concurrentText = `并发 ${run.current_concurrency}/${run.max_concurrency || 5}`;
  const width = 1160;
  const height = 560;

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <GraphHeader
        title="节点架构状态流转图"
        meta={`${lanes.length} 条并行线 · ${branchNodeCount} 分支节点 · ${batchPostNodes.length} 后处理节点 · ${concurrentText}`}
      />

      <div className="mt-2 flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[linear-gradient(180deg,rgba(250,250,250,0.025),rgba(0,0,0,0)),var(--tc-surface-muted)]">
        <svg
          role="img"
          aria-label="批量知识沉淀并行任务状态流程图"
          className="mx-auto block h-full min-h-0 w-full max-w-[1160px]"
          viewBox={`0 0 ${width} ${height}`}
        >
          <defs>
            <TaskFlowGrid />
            <marker
              id="batch-task-flow-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6.5"
              refY="4"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M 0 0 L 8 4 L 0 8 z" fill="rgba(161,161,170,0.88)" />
            </marker>
          </defs>
          <rect width="100%" height="100%" fill="url(#task-flow-grid)" />

          {branchEdges.map(([source, target]) => (
            <LayeredAggregateEdge
              key={`${source.key}-${target.key}`}
              source={source}
              target={target}
              lanes={lanes}
              runStatus={run.status}
              now={now}
            />
          ))}

          {dispatchStage && expertStages.length > 0 ? (
            <LayeredForkConnector
              source={dispatchStage}
              targets={expertStages}
              lanes={lanes}
              runStatus={run.status}
              now={now}
            />
          ) : null}

          {mergeStage && expertStages.length > 0 ? (
            <LayeredJoinConnector
              sources={expertStages}
              target={mergeStage}
              lanes={lanes}
              runStatus={run.status}
              now={now}
            />
          ) : null}

          {mergeStage ? (
            <LayeredSingleEdge
              source={mergeStage}
              target={postStages[0]}
              status={downstreamEdgeStatus(mergeStatus, postStates[0].status)}
            />
          ) : null}

          {postStages.slice(0, -1).map((stage, index) => (
            <LayeredSingleEdge
              key={`${stage.key}-${postStages[index + 1].key}`}
              source={stage}
              target={postStages[index + 1]}
              status={edgeStatus(postStates[index].status, postStates[index + 1].status)}
            />
          ))}

          {branchStages.map(stage => (
            <LayeredStageNode
              key={stage.key}
              stage={stage}
              lanes={lanes}
              runStatus={run.status}
              now={now}
            />
          ))}

          {postStages.map((stage, index) => (
            <PostStageNode
              key={stage.key}
              stage={stage}
              state={postStates[index]}
            />
          ))}
        </svg>
      </div>
    </section>
  );
}

type LayeredStage = {
  key: string;
  index: number;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  nodeName?: string;
  llmHeavy?: boolean;
};

const BATCH_FORK_BUS_Y = 194;
const BATCH_JOIN_BUS_Y = 330;
const BATCH_POST_BUS_Y = 448;

function layeredBranchStages(): LayeredStage[] {
  return [
    {
      key: "load",
      index: 1,
      label: "读取章节",
      nodeName: "LoadChapterNode",
      x: 50,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "segment",
      index: 2,
      label: "切分正文",
      nodeName: "SegmentChapterNode",
      x: 205,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "general",
      index: 3,
      label: "通用抽取",
      nodeName: "GeneralExtractionNode",
      x: 360,
      y: 84,
      width: 128,
      height: 68,
      llmHeavy: true,
    },
    {
      key: "mention",
      index: 4,
      label: "提及清洗",
      nodeName: "MentionNormalizeNode",
      x: 530,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "entity",
      index: 5,
      label: "实体聚合",
      nodeName: "EntityAggregationNode",
      x: 685,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "quality",
      index: 6,
      label: "质量闸门",
      nodeName: "CandidateQualityGateNode",
      x: 840,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "dispatch",
      index: 7,
      label: "类型分发",
      nodeName: "TypeDispatchNode",
      x: 995,
      y: 86,
      width: 116,
      height: 66,
    },
    {
      key: "character",
      index: 8,
      label: "角色专家",
      nodeName: "CharacterExpertNode",
      x: 360,
      y: 234,
      width: 138,
      height: 70,
      llmHeavy: true,
    },
    {
      key: "entityExpert",
      index: 9,
      label: "实体专家",
      nodeName: "EntityExpertNode",
      x: 565,
      y: 234,
      width: 138,
      height: 70,
      llmHeavy: true,
    },
    {
      key: "eventRule",
      index: 10,
      label: "事件规则专家",
      nodeName: "EventRuleExpertNode",
      x: 770,
      y: 234,
      width: 148,
      height: 70,
      llmHeavy: true,
    },
    {
      key: "merge",
      index: 11,
      label: "分支汇合",
      nodeName: "MergeExpertCandidatesNode",
      x: 565,
      y: 358,
      width: 148,
      height: 68,
    },
  ];
}

function layeredPostStages(): LayeredStage[] {
  return batchPostNodes.map((node, index) => ({
    key: node.node_name,
    index: 12 + index,
    label: node.label,
    nodeName: node.node_name,
    x: 972 - index * 180,
    y: 470,
    width: 156,
    height: 64,
    llmHeavy: node.node_name === "BatchSynthesizeCandidateSummariesNode",
  }));
}

function layeredBranchEdges(stages: LayeredStage[]): Array<[LayeredStage, LayeredStage]> {
  const byKey = new Map(stages.map(stage => [stage.key, stage]));
  const edgeKeys: Array<[string, string]> = [
    ["load", "segment"],
    ["segment", "general"],
    ["general", "mention"],
    ["mention", "entity"],
    ["entity", "quality"],
    ["quality", "dispatch"],
  ];
  return edgeKeys.flatMap(([sourceKey, targetKey]) => {
    const source = byKey.get(sourceKey);
    const target = byKey.get(targetKey);
    return source && target ? [[source, target] as [LayeredStage, LayeredStage]] : [];
  });
}

function LayeredStageNode({
  stage,
  lanes,
  runStatus,
  now,
}: {
  stage: LayeredStage;
  lanes: AgentBatchChapterProgress[];
  runStatus: AgentRun["status"];
  now: number;
}) {
  const states = lanes.map(lane => stageStateForLane(stage, lane, runStatus, now));
  const aggregateStatus = combinedStatus(states.map(item => item.status));
  const style = statusStyle(aggregateStatus);
  const durationLabel = stagePrimaryDurationLabel(states, now);
  const successCount = states.filter(item => item.status === "success").length;
  const runningCount = states.filter(item => item.status === "running").length;
  const failedCount = states.filter(item => item.status === "failed").length;
  const statusSummary =
    failedCount > 0
      ? `失败 ${failedCount}/${states.length}`
      : runningCount > 0
        ? `运行 ${runningCount}/${states.length}`
        : successCount > 0
          ? `完成 ${successCount}/${states.length}`
          : `等待 0/${states.length}`;
  const durationSummary =
    runningCount > 1 ? `最长 ${durationLabel}` : durationLabel;

  return (
    <g transform={`translate(${stage.x} ${stage.y})`}>
      <title>
        {stage.label} · {statusSummary} · {durationSummary}
      </title>
          {states
            .slice(1)
            .reverse()
            .map((state, reverseIndex) => {
              const layerIndex = states.length - reverseIndex - 1;
              const layerStyle = statusStyle(state.status);
              const offset = layerOffset(layerIndex);
              const layerOpacity = Math.max(0.36, 0.74 - layerIndex * 0.06);
              return (
                <g
                  key={`${stage.key}-${layerIndex}`}
                  transform={`translate(${offset.x} ${offset.y})`}
                  opacity={layerOpacity}
                >
                  <rect
                    width={stage.width}
                    height={stage.height}
                    rx="8"
                    fill="rgba(24,24,24,0.55)"
                    stroke={layerStyle.stroke}
                    strokeWidth="0.95"
                  />
                  <path
                    d={`M 9 1 H ${stage.width - 18}`}
                    stroke={layerStyle.accent}
                    strokeWidth="1.15"
                    opacity={state.status === "pending" ? 0.2 : 0.64}
                  />
                  <circle
                    cx={stage.width - 12}
                    cy="12"
                    r={state.status === "running" ? 3.7 : 2.9}
                    fill={layerStyle.accent}
                    opacity={state.status === "pending" ? 0.42 : 0.95}
                    className={state.status === "running" ? "motion-safe:animate-pulse" : ""}
                  />
                </g>
              );
            })}
      <rect
        width={stage.width}
        height={stage.height}
        rx="8"
        fill={style.fill}
        stroke={style.stroke}
        strokeWidth={aggregateStatus === "running" ? 1.55 : 1.05}
      />
      <path
        d={`M 9 1 H ${stage.width - 18}`}
        stroke={style.accent}
        strokeWidth="1.45"
        opacity={aggregateStatus === "pending" ? 0.28 : 0.82}
      />
      <circle
        cx={stage.width - 12}
        cy="12"
        r={aggregateStatus === "running" ? 3.9 : 3}
        fill={style.accent}
        opacity={aggregateStatus === "pending" ? 0.46 : 0.96}
        className={aggregateStatus === "running" ? "motion-safe:animate-pulse" : ""}
      />
      <text
        x="12"
        y="18"
        fill="rgba(161,161,170,0.96)"
        fontFamily="var(--tc-font-mono)"
        fontSize="10"
      >
        {String(stage.index).padStart(2, "0")}
      </text>
      {stage.llmHeavy ? (
        <text
          x={stage.width - 30}
          y="16"
          fill="rgba(251,191,36,0.84)"
          fontFamily="var(--tc-font-mono)"
          fontSize="7.5"
        >
          LLM
        </text>
      ) : null}
      <text
        x="12"
        y="37"
        fill="var(--tc-text-primary)"
        fontFamily="var(--tc-font-ui)"
        fontSize="14"
        fontWeight="700"
      >
        {stage.label}
      </text>
      <text
        x="12"
        y={stage.height - 13}
        fill="rgba(161,161,170,0.95)"
        fontFamily="var(--tc-font-mono)"
        fontSize="8.2"
      >
        {statusSummary} · {durationSummary}
      </text>
    </g>
  );
}

function PostStageNode({
  stage,
  state,
}: {
  stage: LayeredStage;
  state: NodeViewState;
}) {
  const style = statusStyle(state.status);
  return (
    <g transform={`translate(${stage.x} ${stage.y})`}>
      <title>
        {stage.label} · {nodeStatusLabel[state.status]} · {state.durationLabel}
      </title>
      <rect
        width={stage.width}
        height={stage.height}
        rx="8"
        fill={style.fill}
        stroke={style.stroke}
        strokeWidth={state.status === "running" ? 1.45 : 0.95}
      />
      <path
        d={`M 8 1 H ${stage.width - 16}`}
        stroke={style.accent}
        strokeWidth="1.25"
        opacity={state.status === "pending" ? 0.28 : 0.8}
      />
      <circle
        cx={stage.width - 11}
        cy="11"
        r={state.status === "running" ? 3.5 : 2.8}
        fill={style.accent}
        opacity={state.status === "pending" ? 0.45 : 0.95}
      />
      <text
        x="12"
        y="19"
        fill="rgba(161,161,170,0.95)"
        fontFamily="var(--tc-font-mono)"
        fontSize="9.2"
      >
        {String(stage.index).padStart(2, "0")}
      </text>
      <text
        x="12"
        y="39"
        fill="var(--tc-text-primary)"
        fontFamily="var(--tc-font-ui)"
        fontSize="14"
        fontWeight="700"
      >
        {stage.label}
      </text>
      {stage.llmHeavy ? (
        <text
          x={stage.width - 30}
          y="16"
          fill="rgba(251,191,36,0.84)"
          fontFamily="var(--tc-font-mono)"
          fontSize="7.5"
        >
          LLM
        </text>
      ) : null}
      <text
        x="12"
        y="54"
        fill="rgba(161,161,170,0.95)"
        fontFamily="var(--tc-font-mono)"
        fontSize="8.8"
      >
        {state.durationLabel}
      </text>
    </g>
  );
}

function layeredStageStatus(
  stage: LayeredStage,
  lanes: AgentBatchChapterProgress[],
  runStatus: AgentRun["status"],
  now: number,
): AgentNodeStatus {
  return combinedStatus(
    lanes.map(lane => stageStateForLane(stage, lane, runStatus, now).status),
  );
}

function LayeredForkConnector({
  source,
  targets,
  lanes,
  runStatus,
  now,
}: {
  source: LayeredStage;
  targets: LayeredStage[];
  lanes: AgentBatchChapterProgress[];
  runStatus: AgentRun["status"];
  now: number;
}) {
  if (targets.length === 0) {
    return null;
  }
  const sourceStatus = layeredStageStatus(source, lanes, runStatus, now);
  const targetStates = targets.map(target => ({
    target,
    status: layeredStageStatus(target, lanes, runStatus, now),
  }));
  const busStatus = edgeStatus(
    sourceStatus,
    combinedStatus(targetStates.map(item => item.status)),
  );
  const sourceX = source.x + source.width / 2;
  const targetCenters = targets.map(target => target.x + target.width / 2);
  const busStartX = Math.min(...targetCenters);

  return (
    <g fill="none">
      <LayeredConnectorPath
        d={`M ${sourceX} ${source.y + source.height} V ${BATCH_FORK_BUS_Y} H ${busStartX}`}
        status={busStatus}
      />
      {targetStates.map(({ target, status }) => {
        const targetX = target.x + target.width / 2;
        return (
          <LayeredConnectorPath
            key={target.key}
            d={`M ${targetX} ${BATCH_FORK_BUS_Y} V ${target.y}`}
            status={edgeStatus(sourceStatus, status)}
            withArrow
          />
        );
      })}
    </g>
  );
}

function LayeredJoinConnector({
  sources,
  target,
  lanes,
  runStatus,
  now,
}: {
  sources: LayeredStage[];
  target: LayeredStage;
  lanes: AgentBatchChapterProgress[];
  runStatus: AgentRun["status"];
  now: number;
}) {
  if (sources.length === 0) {
    return null;
  }
  const sourceStates = sources.map(source => ({
    source,
    status: layeredStageStatus(source, lanes, runStatus, now),
  }));
  const targetStatus = layeredStageStatus(target, lanes, runStatus, now);
  const combinedSourceStatus = combinedStatus(sourceStates.map(item => item.status));
  const busStatus = downstreamEdgeStatus(combinedSourceStatus, targetStatus);
  const sourceCenters = sources.map(source => source.x + source.width / 2);
  const busStartX = Math.min(...sourceCenters);
  const busEndX = Math.max(...sourceCenters);
  const targetX = target.x + target.width / 2;

  return (
    <g fill="none">
      {sourceStates.map(({ source, status }) => {
        const sourceX = source.x + source.width / 2;
        return (
          <LayeredConnectorPath
            key={source.key}
            d={`M ${sourceX} ${source.y + source.height} V ${BATCH_JOIN_BUS_Y}`}
            status={edgeStatus(status, targetStatus)}
          />
        );
      })}
      <LayeredConnectorPath
        d={`M ${busStartX} ${BATCH_JOIN_BUS_Y} H ${busEndX}`}
        status={busStatus}
      />
      <LayeredConnectorPath
        d={`M ${targetX} ${BATCH_JOIN_BUS_Y} V ${target.y}`}
        status={busStatus}
        withArrow
      />
    </g>
  );
}

function LayeredAggregateEdge({
  source,
  target,
  lanes,
  runStatus,
  now,
  sourceOverride,
  targetOverride,
}: {
  source: LayeredStage;
  target: LayeredStage;
  lanes: AgentBatchChapterProgress[];
  runStatus: AgentRun["status"];
  now: number;
  sourceOverride?: AgentNodeStatus;
  targetOverride?: AgentNodeStatus;
}) {
  const sourceStatus =
    sourceOverride ??
    layeredStageStatus(source, lanes, runStatus, now);
  const targetStatus =
    targetOverride ??
    layeredStageStatus(target, lanes, runStatus, now);
  const status = edgeStatus(sourceStatus, targetStatus);
  return <LayeredSingleEdge source={source} target={target} status={status} />;
}

function LayeredConnectorPath({
  d,
  status,
  withArrow = false,
}: {
  d: string;
  status: AgentNodeStatus;
  withArrow?: boolean;
}) {
  return (
    <path
      d={d}
      fill="none"
      stroke={edgeStroke(status)}
      strokeWidth={status === "running" ? 1.7 : 1.15}
      strokeLinecap="round"
      strokeLinejoin="round"
      markerEnd={withArrow ? "url(#batch-task-flow-arrow)" : undefined}
      opacity={edgeOpacity(status)}
      className={status === "running" ? "motion-safe:animate-pulse" : ""}
    />
  );
}

function LayeredSingleEdge({
  source,
  target,
  status,
}: {
  source: LayeredStage;
  target: LayeredStage;
  status: AgentNodeStatus;
}) {
  return (
    <LayeredConnectorPath
      d={layeredEdgePath(source, target, { x: 0, y: 0 })}
      status={status}
      withArrow
    />
  );
}

function layeredEdgePath(
  source: LayeredStage,
  target: LayeredStage,
  offset: { x: number; y: number },
): string {
  if (source.key === "merge" && target.key === "BatchCardAggregationNode") {
    const startX = source.x + source.width / 2 + offset.x;
    const startY = source.y + source.height + offset.y;
    const targetX = target.x + target.width / 2 + offset.x;
    const targetY = target.y + offset.y;
    const busY = BATCH_POST_BUS_Y + offset.y;
    return `M ${startX} ${startY} V ${busY} H ${targetX} V ${targetY}`;
  }
  const sourceCenterX = source.x + source.width / 2 + offset.x;
  const sourceCenterY = source.y + source.height / 2 + offset.y;
  const targetCenterX = target.x + target.width / 2 + offset.x;
  const targetCenterY = target.y + target.height / 2 + offset.y;
  const dx = targetCenterX - sourceCenterX;
  const dy = targetCenterY - sourceCenterY;
  if (Math.abs(dx) >= Math.abs(dy)) {
    const startX = dx >= 0 ? source.x + source.width + offset.x : source.x + offset.x;
    const endX = dx >= 0 ? target.x + offset.x : target.x + target.width + offset.x;
    const midX = startX + (endX - startX) / 2;
    return `M ${startX} ${sourceCenterY} H ${midX} V ${targetCenterY} H ${endX}`;
  }
  const startY = dy >= 0 ? source.y + source.height + offset.y : source.y + offset.y;
  const endY = dy >= 0 ? target.y + offset.y : target.y + target.height + offset.y;
  const midY = startY + (endY - startY) / 2;
  return `M ${sourceCenterX} ${startY} V ${midY} H ${targetCenterX} V ${endY}`;
}

function stageStateForLane(
  stage: LayeredStage,
  lane: AgentBatchChapterProgress,
  runStatus: AgentRun["status"],
  now: number,
): NodeViewState {
  if (!stage.nodeName) {
    return { status: "pending", durationLabel: "未开始" };
  }
  return branchState(lane, stage.nodeName, now, runStatus);
}

function layerOffset(index: number): { x: number; y: number } {
  return { x: index * 7, y: -index * 7 };
}

function stagePrimaryDurationLabel(states: NodeViewState[], now: number): string {
  const failed = states.find(item => item.status === "failed");
  if (failed) {
    return failed.durationLabel;
  }
  const running = states
    .filter(item => item.status === "running")
    .map(item => ({
      durationMs: durationMsFromState(item, now),
      label: item.durationLabel,
    }))
    .sort((left, right) => (right.durationMs ?? 0) - (left.durationMs ?? 0));
  if (running.length > 0) {
    return running[0].label;
  }
  return stageDurationSummary(states, now);
}

function stageDurationSummary(states: NodeViewState[], now: number): string {
  const running = states.find(item => item.status === "running");
  if (running) {
    return running.durationLabel;
  }
  const recorded = states
    .map(item => ({
      durationMs: durationMsFromState(item, now),
      label: item.durationLabel,
    }))
    .filter(
      item =>
        item.durationMs !== null &&
        item.label !== "未开始" &&
        item.label !== "未记录" &&
        item.label !== "等待事件",
    )
    .sort((left, right) => (right.durationMs ?? 0) - (left.durationMs ?? 0));
  return recorded[0]?.label ?? "未开始";
}

function GraphHeader({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--tc-text-primary)]">
        <GitBranch className="size-3.5 text-[var(--tc-text-muted)]" />
        {title}
      </h2>
      <span className="font-mono text-xs text-[var(--tc-text-muted)]">{meta}</span>
    </div>
  );
}

function buildFlowLayout(graphNodes: VisualGraphNode[]): FlowLayout {
  const nodes = graphNodes.map((node, index) => {
    const fallbackColumn = index % 6;
    const fallbackRow = Math.floor(index / 6);
    const position = singlePositions[node.node_name] ?? {
      x: 28 + fallbackColumn * 138,
      y: 28 + fallbackRow * 84,
    };
    return {
      ...node,
      x: position.x,
      y: position.y,
      width: position.width ?? SINGLE_NODE_WIDTH,
      height: position.height ?? SINGLE_NODE_HEIGHT,
    };
  });
  const width = Math.max(
    820,
    Math.max(...nodes.map(node => node.x + node.width), 0) + 28,
  );
  const height = Math.max(
    392,
    Math.max(...nodes.map(node => node.y + node.height), 0) + 28,
  );
  return { nodes, bounds: { width, height } };
}

function FlowNodeItem({
  graphNode,
  node,
  index,
  status,
  now,
}: {
  graphNode: FlowNode;
  node: AgentRunNode | undefined;
  index: number;
  status: AgentNodeStatus;
  now: number;
}) {
  const style = statusStyle(status);
  const durationLabel = nodeDurationLabel(node, status, now);
  return (
    <g transform={`translate(${graphNode.x} ${graphNode.y})`}>
      <title>
        {graphNode.label} · {nodeStatusLabel[status]}
        {node?.error ? ` · ${node.error}` : node?.output_summary ? ` · ${node.output_summary}` : ""}
      </title>
      <rect
        width={graphNode.width}
        height={graphNode.height}
        rx="8"
        fill={style.fill}
        stroke={style.stroke}
        strokeWidth={status === "running" ? 1.6 : 1}
      />
      <path
        d={`M 8 1 H ${graphNode.width - 8}`}
        stroke={style.accent}
        strokeWidth="1.5"
        opacity={status === "pending" ? 0.3 : 0.76}
      />
      <circle
        cx={graphNode.width - 12}
        cy="12"
        r={status === "running" ? 4 : 3.3}
        fill={style.accent}
        opacity={status === "pending" ? 0.42 : 0.95}
        className={status === "running" ? "motion-safe:animate-pulse" : ""}
      />
      <text
        x="10"
        y="17"
        fill="rgba(161,161,170,0.95)"
        fontFamily="var(--tc-font-mono)"
        fontSize="10"
      >
        {String(index + 1).padStart(2, "0")}
      </text>
      <text
        x="10"
        y="31"
        fill="var(--tc-text-primary)"
        fontFamily="var(--tc-font-ui)"
        fontSize="11.5"
        fontWeight="600"
      >
        {graphNode.label}
      </text>
      <text
        x="10"
        y="44"
        fill="rgba(161,161,170,0.95)"
        fontFamily="var(--tc-font-ui)"
        fontSize="9.2"
      >
        {nodeStatusLabel[status]} · {durationLabel}
      </text>
    </g>
  );
}

function TaskFlowGrid() {
  return (
    <pattern id="task-flow-grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path
        d="M 32 0 L 0 0 0 32"
        fill="none"
        stroke="rgba(250,250,250,0.045)"
        strokeWidth="1"
      />
    </pattern>
  );
}

function SingleBranchBands() {
  return (
    <g>
      <text
        x="634"
        y="96"
        fill="rgba(161,161,170,0.72)"
        fontFamily="var(--tc-font-mono)"
        fontSize="10"
      >
        分发总线
      </text>
      <text
        x="462"
        y="192"
        fill="rgba(161,161,170,0.72)"
        fontFamily="var(--tc-font-mono)"
        fontSize="10"
      >
        汇合总线
      </text>
      <path
        d="M 292 100 H 732"
        stroke="rgba(167,234,220,0.26)"
        strokeDasharray="4 8"
        strokeWidth="1"
      />
      <path
        d="M 292 196 H 612"
        stroke="rgba(167,234,220,0.22)"
        strokeDasharray="4 8"
        strokeWidth="1"
      />
      <path
        d="M 452 292 H 732"
        stroke="rgba(167,234,220,0.18)"
        strokeDasharray="4 8"
        strokeWidth="1"
      />
    </g>
  );
}

function singleEdgePath(
  source: FlowNode,
  target: FlowNode,
  sourceName: string,
  targetName: string,
): string {
  const expertTargets = new Set([
    "CharacterExpertNode",
    "EntityExpertNode",
    "EventRuleExpertNode",
  ]);
  if (sourceName === "TypeDispatchNode" && expertTargets.has(targetName)) {
    const startX = source.x + source.width / 2;
    const startY = source.y + source.height;
    const targetX = target.x + target.width / 2;
    const targetY = target.y;
    return `M ${startX} ${startY} V 100 H ${targetX} V ${targetY}`;
  }
  if (targetName === "MergeExpertCandidatesNode" && expertTargets.has(sourceName)) {
    const startX = source.x + source.width / 2;
    const startY = source.y + source.height;
    const endX = target.x + target.width / 2;
    const endY = target.y;
    return `M ${startX} ${startY} V 196 H ${endX} V ${endY}`;
  }
  if (
    sourceName === "MergeExpertCandidatesNode" &&
    targetName === "NormalizeAndValidateNode"
  ) {
    const startX = source.x + source.width / 2;
    const startY = source.y + source.height;
    const endX = target.x + target.width / 2;
    const endY = target.y;
    return `M ${startX} ${startY} V 292 H ${endX} V ${endY}`;
  }

  const sourceCenterX = source.x + source.width / 2;
  const sourceCenterY = source.y + source.height / 2;
  const targetCenterX = target.x + target.width / 2;
  const targetCenterY = target.y + target.height / 2;
  const dx = targetCenterX - sourceCenterX;
  const dy = targetCenterY - sourceCenterY;

  if (Math.abs(dx) >= Math.abs(dy)) {
    const startX = dx >= 0 ? source.x + source.width : source.x;
    const endX = dx >= 0 ? target.x : target.x + target.width;
    const midX = startX + (endX - startX) / 2;
    return `M ${startX} ${sourceCenterY} H ${midX} V ${targetCenterY} H ${endX}`;
  }

  const startY = dy >= 0 ? source.y + source.height : source.y;
  const endY = dy >= 0 ? target.y : target.y + target.height;
  const midY = startY + (endY - startY) / 2;
  return `M ${sourceCenterX} ${startY} V ${midY} H ${targetCenterX} V ${endY}`;
}

function normalizeBatchProgress(run: AgentRun): AgentBatchChapterProgress[] {
  const progressByChapter = new Map(
    run.batch_chapter_progress.map(item => [item.chapter_id, item]),
  );
  const chapterIds =
    run.scope.chapter_ids.length > 0
      ? run.scope.chapter_ids
      : run.batch_chapter_progress.map(item => item.chapter_id);
  if (chapterIds.length === 0) {
    return run.batch_chapter_progress;
  }
  return chapterIds.map((chapterId, index) => {
    const progress = progressByChapter.get(chapterId);
    if (progress) {
      return progress;
    }
    return {
      chapter_id: chapterId,
      chapter_title: run.scope.chapter_titles[index] ?? chapterId,
      status: "pending",
      candidate_count: 0,
      nodes: [],
    };
  });
}

function branchState(
  progress: AgentBatchChapterProgress,
  nodeName: string,
  now: number,
  runStatus: AgentRun["status"] = "running",
): NodeViewState {
  const nodes = progress.nodes ?? [];
  const node = nodes.find(item => item.node_name === nodeName);
  if (node) {
    return {
      status: node.status,
      durationLabel: nodeDurationLabel(node, node.status, now),
      node,
    };
  }
  if (nodes.length === 0) {
    if (progress.status === "success" && runStatus === "completed") {
      return { status: "success", durationLabel: "未记录" };
    }
    if (progress.status === "failed") {
      return { status: "failed", durationLabel: "未记录" };
    }
    if (progress.status === "running" && nodeName === batchPreNodes[0].node_name) {
      return {
        status: "running",
        durationLabel: durationFromTimestamps(progress.started_at, undefined, now),
      };
    }
    return {
      status: "pending",
      durationLabel: "未开始",
    };
  }
  return { status: "pending", durationLabel: "未开始" };
}

function stateFromNodes(
  nodes: AgentRunNode[],
  nodeName: string,
  now: number,
): NodeViewState {
  const node = nodes.find(item => item.node_name === nodeName);
  if (!node) {
    return { status: "pending", durationLabel: "未开始" };
  }
  return {
    status: node.status,
    durationLabel: nodeDurationLabel(node, node.status, now),
    node,
  };
}

function nodeDurationLabel(
  node: AgentRunNode | undefined,
  status: AgentNodeStatus,
  now: number,
): string {
  if (!node) {
    return status === "running" ? "0秒" : "未开始";
  }
  if (status === "running") {
    return durationFromTimestamps(node.started_at, undefined, now);
  }
  if (node.duration_ms > 0) {
    return formatDurationMs(node.duration_ms);
  }
  return durationFromTimestamps(node.started_at, node.finished_at, now, status);
}

function durationMsFromState(state: NodeViewState, now: number): number | null {
  const node = state.node;
  if (!node) {
    return null;
  }
  if (node.duration_ms > 0) {
    return node.duration_ms;
  }
  if (!node.started_at) {
    return null;
  }
  const started = Date.parse(node.started_at);
  if (Number.isNaN(started)) {
    return null;
  }
  const finished = node.finished_at ? Date.parse(node.finished_at) : now;
  if (Number.isNaN(finished) || finished < started) {
    return null;
  }
  return finished - started;
}

function durationFromTimestamps(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
  now: number,
  status: AgentNodeStatus = "running",
): string {
  if (!startedAt) {
    return status === "running" ? "0秒" : "未开始";
  }
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) {
    return status === "running" ? "0秒" : "未记录";
  }
  const finished = finishedAt ? Date.parse(finishedAt) : now;
  if (Number.isNaN(finished) || finished < started) {
    return status === "running" ? "0秒" : "未记录";
  }
  return formatDurationMs(finished - started);
}

function formatDurationMs(durationMs: number): string {
  if (durationMs <= 0) {
    return "0秒";
  }
  if (durationMs < 1000) {
    return `${durationMs}毫秒`;
  }
  if (durationMs < 10000) {
    return `${(durationMs / 1000).toFixed(1)}秒`;
  }
  return `${Math.round(durationMs / 1000)}秒`;
}

function runHasRunningNode(run: AgentRun): boolean {
  return (
    run.nodes.some(node => node.status === "running") ||
    run.batch_chapter_progress.some(
      progress =>
        progress.status === "running" ||
        (progress.nodes ?? []).some(node => node.status === "running"),
    )
  );
}

function combinedStatus(statuses: AgentNodeStatus[]): AgentNodeStatus {
  if (statuses.some(status => status === "failed")) {
    return "failed";
  }
  if (statuses.some(status => status === "running")) {
    return "running";
  }
  if (statuses.length > 0 && statuses.every(status => status === "success")) {
    return "success";
  }
  if (statuses.some(status => status === "success")) {
    return "running";
  }
  if (statuses.some(status => status === "skipped")) {
    return "skipped";
  }
  return "pending";
}

function edgeStatus(
  sourceStatus: AgentNodeStatus,
  targetStatus: AgentNodeStatus,
): AgentNodeStatus {
  if (sourceStatus === "failed" || targetStatus === "failed") {
    return "failed";
  }
  if (sourceStatus === "running" || targetStatus === "running") {
    return "running";
  }
  if (sourceStatus === "success") {
    return "success";
  }
  return "pending";
}

function downstreamEdgeStatus(
  sourceStatus: AgentNodeStatus,
  targetStatus: AgentNodeStatus,
): AgentNodeStatus {
  if (sourceStatus === "failed" || targetStatus === "failed") {
    return "failed";
  }
  if (targetStatus === "running") {
    return "running";
  }
  if (targetStatus === "success" || sourceStatus === "success") {
    return "success";
  }
  return "pending";
}

function statusStyle(status: AgentNodeStatus): {
  fill: string;
  stroke: string;
  accent: string;
} {
  if (status === "success") {
    return {
      fill: "rgba(35,118,92,0.14)",
      stroke: "rgba(52,168,126,0.72)",
      accent: "rgb(52,211,153)",
    };
  }
  if (status === "failed") {
    return {
      fill: "rgba(180,90,90,0.18)",
      stroke: "rgba(180,90,90,0.92)",
      accent: "rgb(248,113,113)",
    };
  }
  if (status === "running") {
    return {
      fill: "rgba(198,155,77,0.2)",
      stroke: "rgba(198,155,77,0.92)",
      accent: "rgb(251,191,36)",
    };
  }
  if (status === "skipped") {
    return {
      fill: "rgba(24,24,24,0.42)",
      stroke: "rgba(92,92,97,0.42)",
      accent: "rgba(161,161,170,0.5)",
    };
  }
  return {
    fill: "rgba(24,24,24,0.68)",
    stroke: "rgba(92,92,97,0.58)",
    accent: "rgba(161,161,170,0.72)",
  };
}

function edgeStroke(status: AgentNodeStatus): string {
  if (status === "success") {
    return "rgba(52,211,153,0.52)";
  }
  if (status === "failed") {
    return "rgba(248,113,113,0.72)";
  }
  if (status === "running") {
    return "rgba(251,191,36,0.76)";
  }
  return "rgba(161,161,170,0.48)";
}

function edgeOpacity(status: AgentNodeStatus): number {
  if (status === "pending") {
    return 0.26;
  }
  if (status === "success") {
    return 0.58;
  }
  return 0.82;
}
