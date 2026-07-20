import type {
  GeneralAgentInvocationTrace,
  GeneralAgentNodeRun,
  GeneralAgentNodeStatus,
  GeneralAgentRunStatus,
} from "@/lib/types/general-agent";

export const GENERAL_AGENT_FLOW_ORCHESTRATOR_ID = "flow_orchestrator";
export const GENERAL_AGENT_FLOW_ANSWER_ID = "flow_answer";

export type GeneralAgentFlowRole = "orchestrator" | "capability" | "answer";

export type GeneralAgentFlowNode = Pick<
  GeneralAgentNodeRun,
  "node_id" | "kind" | "capability_name" | "dependencies" | "status" | "duration_ms"
> & {
  flow_role: GeneralAgentFlowRole;
};

export type GeneralAgentGraphNode = GeneralAgentFlowNode & {
  x: number;
  y: number;
  width: number;
  height: number;
  level: number;
};

export interface GeneralAgentGraphLayout {
  nodes: GeneralAgentGraphNode[];
  width: number;
  height: number;
}

const NODE_WIDTH = 148;
const NODE_HEIGHT = 56;
const COLUMN_GAP = 52;
const ROW_GAP = 24;
const PADDING = 22;

export function generalAgentPlanRevisions(nodes: GeneralAgentNodeRun[]): number[] {
  return [...new Set(nodes.map(node => node.plan_revision))].sort((a, b) => b - a);
}

export function buildGeneralAgentExecutionFlow(
  nodes: GeneralAgentNodeRun[],
  runStatus: GeneralAgentRunStatus,
): GeneralAgentFlowNode[] {
  const knownNodeIds = new Set(nodes.map(node => node.node_id));
  const capabilityNodes: GeneralAgentFlowNode[] = nodes.map(node => {
    const knownDependencies = node.dependencies.filter(dependency =>
      knownNodeIds.has(dependency),
    );
    return {
      node_id: node.node_id,
      kind: node.kind,
      capability_name: node.capability_name,
      dependencies:
        knownDependencies.length > 0
          ? knownDependencies
          : [GENERAL_AGENT_FLOW_ORCHESTRATOR_ID],
      status: node.status,
      duration_ms: node.duration_ms,
      flow_role: "capability",
    };
  });
  const dependedOnNodeIds = new Set(
    capabilityNodes.flatMap(node => node.dependencies),
  );
  const leafNodeIds = capabilityNodes
    .filter(node => !dependedOnNodeIds.has(node.node_id))
    .map(node => node.node_id);

  return [
    {
      node_id: GENERAL_AGENT_FLOW_ORCHESTRATOR_ID,
      kind: "subagent",
      capability_name: "general_writing_orchestrator",
      dependencies: [],
      status: orchestratorFlowStatus(runStatus, nodes.length > 0),
      duration_ms: 0,
      flow_role: "orchestrator",
    },
    ...capabilityNodes,
    {
      node_id: GENERAL_AGENT_FLOW_ANSWER_ID,
      kind: "subagent",
      capability_name: "general_agent_final_answer",
      dependencies:
        leafNodeIds.length > 0
          ? leafNodeIds
          : [GENERAL_AGENT_FLOW_ORCHESTRATOR_ID],
      status: answerFlowStatus(runStatus),
      duration_ms: 0,
      flow_role: "answer",
    },
  ];
}

export function buildGeneralAgentGraphLayout(
  nodes: GeneralAgentFlowNode[],
): GeneralAgentGraphLayout {
  if (nodes.length === 0) {
    return { nodes: [], width: 520, height: 220 };
  }
  const known = new Set(nodes.map(node => node.node_id));
  const levels = new Map<string, number>();
  const remaining = new Map(nodes.map(node => [node.node_id, node]));
  while (remaining.size > 0) {
    let progressed = false;
    for (const [nodeId, node] of remaining) {
      const dependencies = node.dependencies.filter(item => known.has(item));
      if (!dependencies.every(item => levels.has(item))) {
        continue;
      }
      levels.set(
        nodeId,
        dependencies.length === 0
          ? 0
          : Math.max(...dependencies.map(item => levels.get(item) ?? 0)) + 1,
      );
      remaining.delete(nodeId);
      progressed = true;
    }
    if (!progressed) {
      for (const nodeId of remaining.keys()) {
        levels.set(nodeId, 0);
      }
      remaining.clear();
    }
  }
  const columns = new Map<number, GeneralAgentFlowNode[]>();
  for (const node of nodes) {
    const level = levels.get(node.node_id) ?? 0;
    columns.set(level, [...(columns.get(level) ?? []), node]);
  }
  const maxRows = Math.max(...[...columns.values()].map(column => column.length));
  const maxLevel = Math.max(...levels.values());
  const naturalWidth =
    PADDING * 2 + (maxLevel + 1) * NODE_WIDTH + maxLevel * COLUMN_GAP;
  const width = Math.max(520, naturalWidth);
  const horizontalOffset = (width - naturalWidth) / 2;
  const height = Math.max(
    220,
    PADDING * 2 + maxRows * NODE_HEIGHT + Math.max(0, maxRows - 1) * ROW_GAP,
  );
  const layoutNodes: GeneralAgentGraphNode[] = [];
  for (const [level, column] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
    const columnHeight =
      column.length * NODE_HEIGHT + Math.max(0, column.length - 1) * ROW_GAP;
    const startY = (height - columnHeight) / 2;
    column.forEach((node, index) => {
      layoutNodes.push({
        ...node,
        level,
        x: horizontalOffset + PADDING + level * (NODE_WIDTH + COLUMN_GAP),
        y: startY + index * (NODE_HEIGHT + ROW_GAP),
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });
  }
  return {
    nodes: layoutNodes,
    width,
    height,
  };
}

function orchestratorFlowStatus(
  runStatus: GeneralAgentRunStatus,
  hasCapabilityNodes: boolean,
): GeneralAgentNodeStatus {
  if (hasCapabilityNodes) {
    return "success";
  }
  if (["failed", "timeout"].includes(runStatus)) {
    return "failed";
  }
  if (runStatus === "cancelled") {
    return "skipped";
  }
  if (["init", "clarifying", "planning", "replanning"].includes(runStatus)) {
    return "running";
  }
  return "success";
}

function answerFlowStatus(runStatus: GeneralAgentRunStatus): GeneralAgentNodeStatus {
  if (runStatus === "completed") {
    return "success";
  }
  if (["failed", "timeout"].includes(runStatus)) {
    return "failed";
  }
  if (runStatus === "cancelled") {
    return "skipped";
  }
  return "pending";
}

export function tracesForGeneralAgentNode(
  node: GeneralAgentNodeRun,
  traces: GeneralAgentInvocationTrace[],
): GeneralAgentInvocationTrace[] {
  const root = traces.find(trace => trace.trace_id === node.trace_id);
  if (!root) {
    return [];
  }
  const callIds = new Set([root.call_id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const trace of traces) {
      if (
        trace.parent_call_id &&
        callIds.has(trace.parent_call_id) &&
        !callIds.has(trace.call_id)
      ) {
        callIds.add(trace.call_id);
        changed = true;
      }
    }
  }
  return traces.filter(trace => trace === root || callIds.has(trace.call_id));
}

export function orchestratorTraces(
  traces: GeneralAgentInvocationTrace[],
): GeneralAgentInvocationTrace[] {
  return traces.filter(
    trace =>
      trace.capability_type === "llm" &&
      trace.caller_name === "general_writing_orchestrator",
  );
}
