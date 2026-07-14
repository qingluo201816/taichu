"use client";

import { GitBranch } from "lucide-react";
import { useMemo } from "react";

import { generalCapabilityLabel, generalNodeStatusLabels } from "@/lib/general-agent-display";
import { buildGeneralAgentGraphLayout } from "@/lib/general-agent-monitor";
import type { GeneralAgentNodeRun } from "@/lib/types/general-agent";

export function GeneralAgentFlowGraph({
  nodes,
  selectedNodeId,
  onSelectNode,
}: {
  nodes: GeneralAgentNodeRun[];
  selectedNodeId: string;
  onSelectNode: (nodeId: string) => void;
}) {
  const layout = useMemo(() => buildGeneralAgentGraphLayout(nodes), [nodes]);
  const nodesById = new Map(layout.nodes.map(node => [node.node_id, node]));

  if (nodes.length === 0) {
    return (
      <div className="flex min-h-[220px] items-center justify-center rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[var(--tc-surface-muted)] text-sm text-[var(--tc-text-muted)]">
        该次计划直接回答，没有创建能力节点。
      </div>
    );
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-[var(--tc-text-primary)]">
          <GitBranch className="size-4" />
          动态执行图
        </h3>
        <span className="text-xs text-[var(--tc-text-muted)]">
          {nodes.length} 个节点 · 点击查看调用明细
        </span>
      </div>
      <div className="min-h-[260px] flex-1 overflow-auto rounded-[var(--tc-radius-card)] border border-[var(--tc-border-subtle)] bg-[linear-gradient(rgba(255,255,255,.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.025)_1px,transparent_1px),var(--tc-surface-muted)] bg-[size:32px_32px]">
        <svg
          role="img"
          aria-label="通用写作助手动态节点执行图"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          style={{ minWidth: layout.width, minHeight: layout.height }}
          className="block h-full w-full"
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
                const bend = Math.max(24, (x2 - x1) / 2);
                return (
                  <path
                    key={`${source.node_id}-${target.node_id}`}
                    d={`M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`}
                    stroke={edgeColor(source.status, target.status)}
                    strokeWidth={target.status === "running" ? 2 : 1.35}
                    markerEnd="url(#general-agent-arrow)"
                    className={target.status === "running" ? "motion-safe:animate-pulse" : ""}
                  />
                );
              }),
            )}
          </g>
          {layout.nodes.map((node, index) => {
            const selected = node.node_id === selectedNodeId;
            return (
              <g
                key={node.node_id}
                role="button"
                tabIndex={0}
                aria-label={`${generalCapabilityLabel(node.capability_name)}，${generalNodeStatusLabels[node.status]}`}
                onClick={() => onSelectNode(node.node_id)}
                onKeyDown={event => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectNode(node.node_id);
                  }
                }}
                className="cursor-pointer outline-none"
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx="10"
                  fill={selected ? "rgba(63,63,70,.96)" : "rgba(24,24,27,.96)"}
                  stroke={selected ? "rgba(255,255,255,.92)" : nodeStroke(node.status)}
                  strokeWidth={selected ? 1.8 : 1.2}
                />
                <circle
                  cx={node.x + 16}
                  cy={node.y + 17}
                  r="4"
                  fill={nodeStatusColor(node.status)}
                />
                <text
                  x={node.x + 27}
                  y={node.y + 21}
                  fill="rgba(244,244,245,.96)"
                  fontSize="12"
                  fontWeight="600"
                >
                  {truncate(generalCapabilityLabel(node.capability_name), 11)}
                </text>
                <text
                  x={node.x + 14}
                  y={node.y + 43}
                  fill="rgba(161,161,170,.92)"
                  fontSize="10"
                >
                  {node.kind === "tool" ? "工具" : "专业智能体"} · 第 {index + 1} 节点
                </text>
                <text
                  x={node.x + 14}
                  y={node.y + 59}
                  fill={nodeStatusColor(node.status)}
                  fontSize="10"
                >
                  {generalNodeStatusLabels[node.status]} · {durationLabel(node.duration_ms)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
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
