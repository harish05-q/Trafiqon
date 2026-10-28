"use client";

import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import type { ScenarioOut } from "@/lib/api/types";
import { useWorkspace } from "@/stores/workspace";
import { Legend } from "./Legend";
import { RoadEdgeView, RoadNodeView } from "./RoadElements";
import { toFlow, type RouteOverlay } from "./toFlow";

const nodeTypes: NodeTypes = { road: RoadNodeView };
const edgeTypes: EdgeTypes = { road: RoadEdgeView };
const NO_ROUTES: RouteOverlay[] = [];

function markerColor(traffic: string, onRoute: boolean, dimmed: boolean): string {
  if (onRoute) return dimmed ? "var(--tq-road)" : "var(--tq-route)";
  if (traffic === "closed") return "var(--tq-incident)";
  if (traffic === "congested") return "var(--tq-traffic-congested)";
  return "var(--tq-road)";
}

export function NetworkCanvas({
  scenario,
  routes = NO_ROUTES,
  altRoutes = NO_ROUTES,
}: {
  scenario: ScenarioOut;
  routes?: RouteOverlay[];
  altRoutes?: RouteOverlay[];
}) {
  const selection = useWorkspace((s) => s.selection);
  const select = useWorkspace((s) => s.select);

  const { nodes, edges } = useMemo(() => {
    const flow = toFlow(scenario, {
      routes,
      altRoutes,
      selectedNodeId: selection?.kind === "node" ? selection.id : null,
      selectedEdgeId: selection?.kind === "edge" ? selection.id : null,
      selectedVehicleId: selection?.kind === "route" ? selection.vehicleId : null,
    });
    return {
      nodes: flow.nodes,
      edges: flow.edges.map((e) => ({
        ...e,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 12,
          height: 12,
          color: markerColor(e.data!.traffic, e.data!.onRoute, e.data!.dimmed),
        },
      })),
    };
  }, [scenario, routes, altRoutes, selection]);

  return (
    <div
      className="relative h-full w-full"
      role="figure"
      aria-label={`Road network of ${scenario.name}: ${scenario.graph.nodes.length} nodes, ${scenario.graph.edges.length} directed roads`}
    >
      <ReactFlow
        key={scenario.id}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        onNodeClick={(_, n) => select({ kind: "node", id: n.id })}
        onEdgeClick={(_, e) => select({ kind: "edge", id: e.id })}
        onPaneClick={() => select(null)}
        fitView
        minZoom={0.2}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={24} size={1} color="var(--tq-border)" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
      <Legend synthetic={scenario.synthetic} />
    </div>
  );
}
