"use client";

import { GitBranch } from "lucide-react";
import { useMemo } from "react";

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
  const flowNodes = useMemo(
    () => buildGeneralAgentExecutionFlow(nodes, runStatus),
    [nodes, runStatus],
  );
  const layout = useMemo(
    () => buildGeneralAgentGraphLayout(flowNodes),
    [flowNodes],
  );
  const nodesById = new Map(layout.nodes.map(node => [node.node_id, node]));

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--tc-text-primary)]">
          <GitBranch className="size-4" />
          本次请求执行流
        </h3>
        <span className="text-xs text-[var(--tc-text-muted)]">
          规划编排 → {nodes.length > 0 ? `${nodes.length} 个能力节点 → ` : ""}最终回答
        </span>
      </div>
      <div className="min-h-[260px] flex-1 overflow-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[linear-gradient(rgba(255,255,255,.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.025)_1px,transparent_1px),var(--tc-surface-muted)] bg-[size:32px_32px]">
        <div
          className="flex h-full min-h-[260px] items-center justify-center"
          style={{ minWidth: layout.width, minHeight: layout.height }}
        >
          <svg
            role="img"
            aria-label="通用写作助手本次请求执行流"
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            width={layout.width}
            height={layout.height}
            className="block max-w-none shrink-0"
          >
            <defs>
              <marker
                id="general-agent-arrow"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill="rgba(161,161,170,.75)" />
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
                  const sourceStatus = generalNodeVisualStatus(
                    source.status,
                    runStatus,
                  );
                  const targetStatus = generalNodeVisualStatus(
                    target.status,
                    runStatus,
                  );
                  return (
                    <path
                      key={`${source.node_id}-${target.node_id}`}
                      d={`M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`}
                      stroke={edgeColor(sourceStatus, targetStatus)}
                      strokeWidth={targetStatus === "running" ? 2 : 1.35}
                      markerEnd="url(#general-agent-arrow)"
                      className={targetStatus === "running" ? "motion-safe:animate-pulse" : ""}
                    />
                  );
                }),
              )}
            </g>
            {layout.nodes.map(node => {
              const selected =
                node.flow_role === "capability" && node.node_id === selectedNodeId;
              const displayStatus = generalNodeVisualStatus(node.status, runStatus);
              const title = flowNodeTitle(node.flow_role, node.capability_name);
              const meta = flowNodeMeta(
                node.flow_role,
                node.kind,
                node.status,
                node.duration_ms,
                runStatus,
              );
              const activate = () => onSelectNode(node.node_id, node.flow_role);
              return (
                <g
                  key={node.node_id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${title}，${generalNodeStatusLabel(node.status, runStatus)}`}
                  onClick={activate}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      activate();
                    }
                  }}
                  className="cursor-pointer outline-none"
                >
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.width}
                    height={node.height}
                    rx="9"
                    fill={nodeFill(node.flow_role, selected)}
                    stroke={selected ? "rgba(255,255,255,.92)" : nodeStroke(displayStatus)}
                    strokeWidth={selected ? 1.8 : 1.2}
                  />
                  <circle
                    cx={node.x + 15}
                    cy={node.y + 18}
                    r="3.5"
                    fill={nodeStatusColor(displayStatus)}
                  />
                  <text
                    x={node.x + 25}
                    y={node.y + 21}
                    fill="rgba(244,244,245,.96)"
                    fontSize="11"
                    fontWeight="600"
                  >
                    {truncate(title, 10)}
                  </text>
                  <text
                    x={node.x + 14}
                    y={node.y + 42}
                    fill={nodeStatusColor(displayStatus)}
                    fontSize="9.5"
                  >
                    {truncate(meta, 18)}
                  </text>
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
    return "规划编排 Agent";
  }
  if (role === "answer") {
    return "最终回答";
  }
  return generalCapabilityLabel(capabilityName);
}

function flowNodeMeta(
  role: GeneralAgentFlowRole,
  kind: GeneralAgentNodeRun["kind"],
  status: GeneralAgentNodeRun["status"],
  durationMs: number,
  runStatus: GeneralAgentRunStatus,
): string {
  const statusLabel = generalNodeStatusLabel(status, runStatus);
  if (role === "orchestrator") {
    return `高层编排 · ${statusLabel}`;
  }
  if (role === "answer") {
    return `回答 · ${statusLabel}`;
  }
  return `${kind === "tool" ? "工具" : "专业智能体"} · ${statusLabel} · ${durationLabel(durationMs)}`;
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function durationLabel(durationMs: number): string {
  return durationMs < 1_000 ? `${durationMs} 毫秒` : `${(durationMs / 1_000).toFixed(1)} 秒`;
}

function nodeFill(role: GeneralAgentFlowRole, selected: boolean): string {
  if (selected) {
    return "rgba(63,63,70,.96)";
  }
  if (role === "orchestrator") {
    return "rgba(30,41,59,.96)";
  }
  if (role === "answer") {
    return "rgba(20,48,42,.96)";
  }
  return "rgba(24,24,27,.96)";
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

function nodeStroke(status: GeneralAgentNodeRun["status"]): string {
  return status === "pending" ? "rgba(82,82,91,.9)" : nodeStatusColor(status);
}

function edgeColor(
  source: GeneralAgentNodeRun["status"],
  target: GeneralAgentNodeRun["status"],
): string {
  if (source === "failed" || target === "failed") {
    return "rgba(248,113,113,.85)";
  }
  if (target === "running") {
    return "rgba(96,165,250,.95)";
  }
  if (source === "success") {
    return "rgba(74,222,128,.75)";
  }
  return "rgba(113,113,122,.65)";
}
