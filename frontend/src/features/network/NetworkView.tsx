"use client";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { memo, useMemo } from "react";

import type { ScenarioOut } from "@/lib/api/types";
import { toFlow, type RoadNode } from "./toFlow";

const centered = { left: "50%", top: "50%", opacity: 0, pointerEvents: "none" } as const;

const RoadNodeView = memo(function RoadNodeView({ id, data }: NodeProps<RoadNode>) {
  const classes = ["road-node", data.kind, data.onPath && "on-path", data.isEndpoint && "endpoint"]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes} title={`${data.kind} ${id}`} data-node-id={id}>
      <Handle type="target" position={Position.Top} style={centered} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={centered} isConnectable={false} />
      {data.kind !== "intersection" && <span className="road-node-label">{id}</span>}
    </div>
  );
});

const nodeTypes: NodeTypes = { road: RoadNodeView };

export interface NetworkViewProps {
  scenario: ScenarioOut;
  pathEdgeIds: readonly string[];
  endpoints: readonly string[];
  onNodeClick?: (nodeId: string) => void;
}

export function NetworkView({ scenario, pathEdgeIds, endpoints, onNodeClick }: NetworkViewProps) {
  const { nodes, edges } = useMemo(() => {
    const flow = toFlow(scenario, pathEdgeIds, endpoints);
    return {
      nodes: flow.nodes,
      edges: flow.edges.map((e) => ({
        ...e,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: e.data?.onPath
            ? "var(--route)"
            : e.data?.closed
              ? "var(--incident)"
              : "var(--road)",
        },
      })),
    };
  }, [scenario, pathEdgeIds, endpoints]);

  return (
    <div className="h-full w-full" aria-label={`Road network for ${scenario.name}`} role="figure">
      <ReactFlow
        key={scenario.id}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        fitView
        colorMode="dark"
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={24} size={1} color="var(--border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
