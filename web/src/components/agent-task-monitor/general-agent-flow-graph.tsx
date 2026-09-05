"use client";

import { GitBranch } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

import {
  generalCapabilityLabel,
  generalNodeStatusLabel,
  generalNodeVisualStatus,
} from "@/lib/general-agent-display";
import {
  buildGeneralAgentExecutionFlow,
  buildGeneralAgentGraphLayout,
  type GeneralAgentFlowRole,
} from "@/lib/general-agent-monitor";
import type {
  GeneralAgentNodeRun,
  GeneralAgentRunStatus,
} from "@/lib/types/general-agent";

export function GeneralAgentFlowGraph({
  nodes,
  runStatus,
  selectedNodeId,
  onSelectNode,
}: {
  nodes: GeneralAgentNodeRun[];
  runStatus: GeneralAgentRunStatus;
  selectedNodeId: string;
  onSelectNode: (nodeId: string, role: GeneralAgentFlowRole) => void;
}) {
  const arrowId = useId();
  const [expanded, setExpanded] = useState(false);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const flowNodes = useMemo(
    () => buildGeneralAgentExecutionFlow(nodes, runStatus),
    [nodes, runStatus],
  );
  const layout = useMemo(
    () => buildGeneralAgentGraphLayout(flowNodes),
    [flowNodes],
  );
  const nodesById = new Map(layout.nodes.map(node => [node.node_id, node]));

  const activeId = focusedId;
  const relatedIds = new Set<string>(activeId ? [activeId] : []);
  for (const node of layout.nodes) {
    if (node.node_id === activeId) node.dependencies.forEach(id => relatedIds.add(id));
    if (activeId && node.dependencies.includes(activeId)) relatedIds.add(node.node_id);
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--tc-text-primary)]">
          <GitBranch className="size-4" />
          本次请求执行流
        </h3>
        <div className="flex items-center gap-3"><span className="text-xs text-[var(--tc-text-muted)]">
          规划编排 → {nodes.length > 0 ? `${nodes.length} 个能力节点 → ` : ""}最终回答
        </span>
        <Button variant="ghost" size="sm" onClick={() => setExpanded(value => !value)}>
          {expanded ? "适应画布" : "放大查看"}
        </Button></div>
      </div>
      <div className="min-h-[300px] flex-1 overflow-auto rounded-[var(--tc-radius-card)] bg-[var(--tc-surface-muted)]">
        <div
          className="flex h-full min-h-[300px] items-center justify-center"
          style={expanded ? { minWidth: layout.width, minHeight: layout.height } : undefined}
        >
          <svg
            role="group"
            aria-label="通用写作助手本次请求执行流"
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            width={expanded ? layout.width : "100%"}
            height={expanded ? layout.height : "100%"}
            preserveAspectRatio="xMidYMid meet"
            className="block"
          >
            <defs>
              <marker
                id={arrowId}
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill="context-stroke" />
              </marker>
            </defs>
            <g fill="none">
              {layout.nodes.flatMap(target =>
                target.dependencies.map(dependency => {
                  const source = nodesById.get(dependency);
                  if (!source) {
                    return null;
                  }
                  const x1 = source.x + source.width;
                  const y1 = source.y + source.height / 2;
                  const x2 = target.x;
                  const y2 = target.y + target.height / 2;
                  const bend = Math.max(20, (x2 - x1) / 2);
                  const highlighted = source.node_id === activeId || target.node_id === activeId;
                  const between = layout.nodes.filter(node => node.level > source.level && node.level < target.level);
                  const bypassY = Math.min(source.y, target.y, ...between.map(node => node.y)) - 20 - (target.level % 3) * 8;
                  const path = between.length
                    ? `M${x1},${y1} C${x1 + 18},${y1} ${x1 + 18},${bypassY} ${x1 + 32},${bypassY} L${x2 - 32},${bypassY} C${x2 - 18},${bypassY} ${x2 - 18},${y2} ${x2},${y2}`
                    : `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`;
                  const targetStatus = generalNodeVisualStatus(
                    target.status,
                    runStatus,
                  );
                  return (
                    <path
                      key={`${source.node_id}-${target.node_id}`}
                      d={path}
                      stroke={highlighted ? "var(--tc-text-primary)" : "var(--tc-text-muted)"}
                      opacity={activeId && !highlighted ? 0.25 : 0.65}
                      strokeWidth={targetStatus === "running" ? 2 : 1.35}
                      markerEnd={`url(#${arrowId})`}
                      className={targetStatus === "running" ? "motion-safe:animate-pulse" : ""}
                    />
                  );
                }),
              )}
            </g>
            {layout.nodes.map(node => {
              const selected =
                node.node_id === selectedNodeId;
              const displayStatus = generalNodeVisualStatus(node.status, runStatus);
              const title = flowNodeTitle(node.flow_role, node.capability_name);
              const kind = node.flow_role === "orchestrator" ? "高层编排" : node.flow_role === "answer" ? "回答" : node.kind === "tool" ? "工具" : "专业智能体";
              const activate = () => onSelectNode(node.node_id, node.flow_role);
              return (
                <g
                  key={node.node_id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${title}，${generalNodeStatusLabel(node.status, runStatus)}`}
                  onClick={activate}
                  onMouseEnter={() => setFocusedId(node.node_id)}
                  onMouseLeave={() => setFocusedId(null)}
                  onFocus={() => setFocusedId(node.node_id)}
                  onBlur={() => setFocusedId(null)}
                  opacity={activeId && !relatedIds.has(node.node_id) ? 0.5 : 1}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      activate();
                    }
                  }}
                  className="group cursor-pointer outline-none"
                >
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.width}
                    height={node.height}
                    rx="12"
                    fill={selected ? "var(--tc-surface-card)" : "var(--tc-surface-muted)"}
                    stroke={selected ? "var(--tc-text-primary)" : "var(--tc-border-subtle)"}
                    className="group-focus-visible:stroke-[var(--tc-text-primary)] group-hover:stroke-[var(--tc-text-secondary)]"
                    strokeWidth={selected ? 1.8 : 1.2}
                  />
                  <circle
                    cx={node.x + 15}
                    cy={node.y + 23}
                    r="3.5"
                    fill={nodeStatusColor(displayStatus)}
                  />
                  <text
                    x={node.x + 25}
                    y={node.y + 27}
                    fill="var(--tc-text-primary)"
                    fontSize="15"
                    fontWeight="600"
                  >
                    {title}
                  </text>
                  <text
                    x={node.x + 14}
                    y={node.y + 52}
                    fill="var(--tc-text-muted)"
                    fontSize="12"
                  >
                    {kind}
                  </text>
                  <text x={node.x + node.width - 14} y={node.y + 52} textAnchor="end" fill="var(--tc-text-muted)" fontSize="12">
                    {node.flow_role === "capability" ? durationLabel(node.duration_ms) : ""}
                  </text>
                  <text x={node.x + 14} y={node.y + 73} fill="var(--tc-text-secondary)" fontSize="12">
                    {generalNodeStatusLabel(node.status, runStatus)}
                  </text>
                  <title>{`${title} · ${generalNodeStatusLabel(node.status, runStatus)}`}</title>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    </section>
  );
}

function flowNodeTitle(role: GeneralAgentFlowRole, capabilityName: string): string {
  if (role === "orchestrator") {
    return "规划编排";
  }
  if (role === "answer") {
    return "最终回答";
  }
  return generalCapabilityLabel(capabilityName);
}

function durationLabel(durationMs: number): string {
  return durationMs < 1_000 ? `${durationMs} 毫秒` : `${(durationMs / 1_000).toFixed(1)} 秒`;
}

function nodeStatusColor(status: GeneralAgentNodeRun["status"]): string {
  return {
    pending: "rgba(161,161,170,.9)",
    running: "rgb(96,165,250)",
    success: "rgb(74,222,128)",
    failed: "rgb(248,113,113)",
    skipped: "rgb(250,204,21)",
    waiting_human: "rgb(251,146,60)",
  }[status];
}
