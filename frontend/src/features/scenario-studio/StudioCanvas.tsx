"use client";

import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type EdgeTypes,
  type NodeChange,
  type NodeTypes,
  type XYPosition,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";

import { Legend } from "@/features/network/Legend";
import { RoadEdgeView, RoadNodeView } from "@/features/network/RoadElements";
import { SCALE, toFlow, type RoadNode } from "@/features/network/toFlow";
import type { ScenarioData } from "@/lib/api/types";

export type Tool = "select" | "add-node" | "add-road";

const nodeTypes: NodeTypes = { road: RoadNodeView };
const edgeTypes: EdgeTypes = { road: RoadEdgeView };

export interface StudioCanvasProps {
  data: ScenarioData;
  name: string;
  tool: Tool;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  pendingSource: string | null;
  onAddNode: (x: number, y: number) => void;
  onMoveNode: (id: string, x: number, y: number) => void;
  onNodeClick: (id: string) => void;
  onEdgeClick: (id: string) => void;
  onPaneClick: () => void;
}

function Inner(p: StudioCanvasProps) {
  const { screenToFlowPosition } = useReactFlow();
  const flow = useMemo(
    () =>
      toFlow(
        { ...p.data, id: "draft", name: p.name },
        {
          selectedNodeId: p.pendingSource ?? p.selectedNodeId,
          selectedEdgeId: p.selectedEdgeId,
        },
      ),
    [p.data, p.name, p.pendingSource, p.selectedNodeId, p.selectedEdgeId],
  );
  // Positions of nodes being dragged (smooth dragging); the draft is updated on drop.
  const [dragging, setDragging] = useState<Record<string, XYPosition>>({});
  const nodes = useMemo(
    () => flow.nodes.map((n) => (dragging[n.id] ? { ...n, position: dragging[n.id] } : n)),
    [flow.nodes, dragging],
  );
  const edges = useMemo(
    () =>
      flow.edges.map((e) => ({
        ...e,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 12,
          height: 12,
          color: e.data!.traffic === "closed" ? "var(--tq-incident)" : "var(--tq-road)",
        },
      })),
    [flow.edges],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      nodesDraggable={p.tool === "select"}
      nodesConnectable={false}
      elementsSelectable={false}
      onNodesChange={(changes: NodeChange<RoadNode>[]) => {
        const moved: Record<string, XYPosition> = {};
        for (const c of changes) if (c.type === "position" && c.position) moved[c.id] = c.position;
        if (Object.keys(moved).length) setDragging((d) => ({ ...d, ...moved }));
      }}
      onNodeDragStop={(_, n) => {
        p.onMoveNode(n.id, n.position.x / SCALE, n.position.y / SCALE);
        setDragging((d) => Object.fromEntries(Object.entries(d).filter(([id]) => id !== n.id)));
      }}
      onNodeClick={(_, n) => p.onNodeClick(n.id)}
      onEdgeClick={(_, e) => p.onEdgeClick(e.id)}
      onPaneClick={(event) => {
        if (p.tool === "add-node") {
          const pos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
          p.onAddNode(pos.x / SCALE, pos.y / SCALE);
        } else {
          p.onPaneClick();
        }
      }}
      fitView
      minZoom={0.2}
      className={p.tool === "add-node" ? "cursor-crosshair" : undefined}
    >
      <Background gap={SCALE / 2} size={1} color="var(--tq-border)" />
      <Controls showInteractive={false} position="bottom-left" />
    </ReactFlow>
  );
}

export function StudioCanvas(props: StudioCanvasProps) {
  return (
    <div
      className="relative h-full w-full"
      role="application"
      aria-label={`Network editor: ${props.data.graph.nodes.length} nodes, ${props.data.graph.edges.length} roads. Tool: ${props.tool}`}
    >
      <ReactFlowProvider>
        <Inner {...props} />
      </ReactFlowProvider>
      <Legend synthetic={props.data.synthetic} />
    </div>
  );
}
