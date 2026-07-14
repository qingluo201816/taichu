import type {
  GeneralAgentInvocationTrace,
  GeneralAgentNodeRun,
} from "@/lib/types/general-agent";

export type GeneralAgentGraphNode = GeneralAgentNodeRun & {
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

const NODE_WIDTH = 172;
const NODE_HEIGHT = 72;
const COLUMN_GAP = 70;
const ROW_GAP = 34;
const PADDING = 28;

export function generalAgentPlanRevisions(nodes: GeneralAgentNodeRun[]): number[] {
  return [...new Set(nodes.map(node => node.plan_revision))].sort((a, b) => b - a);
}

export function buildGeneralAgentGraphLayout(
  nodes: GeneralAgentNodeRun[],
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
  const columns = new Map<number, GeneralAgentNodeRun[]>();
  for (const node of nodes) {
    const level = levels.get(node.node_id) ?? 0;
    columns.set(level, [...(columns.get(level) ?? []), node]);
  }
  const maxRows = Math.max(...[...columns.values()].map(column => column.length));
  const maxLevel = Math.max(...levels.values());
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
        x: PADDING + level * (NODE_WIDTH + COLUMN_GAP),
        y: startY + index * (NODE_HEIGHT + ROW_GAP),
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });
  }
  return {
    nodes: layoutNodes,
    width: Math.max(
      520,
      PADDING * 2 + (maxLevel + 1) * NODE_WIDTH + maxLevel * COLUMN_GAP,
    ),
    height,
  };
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
