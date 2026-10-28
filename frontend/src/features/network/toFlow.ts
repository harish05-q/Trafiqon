import type { Edge, Node } from "@xyflow/react";

import type { ScenarioOut } from "@/lib/api/types";

export type NodeKind = "depot" | "customer" | "intersection";

export interface RoadNodeData extends Record<string, unknown> {
  label: string;
  kind: NodeKind;
  onPath: boolean;
  isEndpoint: boolean;
}

export interface RoadEdgeData extends Record<string, unknown> {
  onPath: boolean;
  closed: boolean;
  currentTime: number;
  distance: number;
}

export type RoadNode = Node<RoadNodeData, "road">;
export type RoadEdge = Edge<RoadEdgeData>;

/** Pixels per scenario coordinate unit (km). Scenarios are synthetic grids, not geography. */
export const SCALE = 120;

/**
 * Convert a backend scenario and an (optional) backend path into React Flow elements.
 * Only edges whose ids are in `pathEdgeIds` are marked on-path: the drawn route is exactly
 * the API's route, never recomputed in the browser.
 */
export function toFlow(
  scenario: ScenarioOut,
  pathEdgeIds: readonly string[] = [],
  endpoints: readonly string[] = [],
): { nodes: RoadNode[]; edges: RoadEdge[] } {
  const depotNodes = new Set(scenario.depots.map((d) => d.node_id));
  const customerNodes = new Set(scenario.customers.map((c) => c.node_id));
  const onPathEdges = new Set(pathEdgeIds);
  const edgeById = new Map(scenario.graph.edges.map((e) => [e.id, e]));
  const onPathNodes = new Set<string>();
  for (const id of pathEdgeIds) {
    const e = edgeById.get(id);
    if (e) {
      onPathNodes.add(e.source);
      onPathNodes.add(e.target);
    }
  }

  const nodes: RoadNode[] = scenario.graph.nodes.map((n) => ({
    id: n.id,
    type: "road",
    position: { x: (n.x ?? 0) * SCALE, y: (n.y ?? 0) * SCALE },
    data: {
      label: n.label ?? n.id,
      kind: depotNodes.has(n.id) ? "depot" : customerNodes.has(n.id) ? "customer" : "intersection",
      onPath: onPathNodes.has(n.id),
      isEndpoint: endpoints.includes(n.id),
    },
    draggable: false,
  }));

  // On-path edges last so they render above the parallel reverse-direction edge.
  const edges: RoadEdge[] = scenario.graph.edges
    .map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "straight",
      className: onPathEdges.has(e.id)
        ? "road-edge on-path"
        : e.closed
          ? "road-edge closed"
          : "road-edge",
      zIndex: onPathEdges.has(e.id) ? 10 : 0,
      data: {
        onPath: onPathEdges.has(e.id),
        closed: e.closed,
        currentTime: e.current_time,
        distance: e.distance,
      },
    }))
    .sort((a, b) => Number(a.data.onPath) - Number(b.data.onPath));

  return { nodes, edges };
}
