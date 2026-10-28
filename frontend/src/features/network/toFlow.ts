import type { Edge, Node } from "@xyflow/react";

import type { EdgeOut, ScenarioOut } from "@/lib/api/types";

export type NodeKind = "depot" | "customer" | "intersection";
export type TrafficState = "closed" | "congested" | "normal";

/** An open road is "congested" when its current time is at least this multiple of its
 * free-flow (base) time. Display rule only; costs always use current_time. */
export const CONGESTION_RATIO = 1.25;

export interface RoadNodeData extends Record<string, unknown> {
  label: string;
  kind: NodeKind;
  refId: string | null; // depot/customer id
  demand: number | null;
  onRoute: boolean;
  selected: boolean;
}

export interface RoadEdgeData extends Record<string, unknown> {
  edge: EdgeOut;
  traffic: TrafficState;
  onRoute: boolean;
  dimmed: boolean; // on another vehicle's route while one route is selected
  selected: boolean;
  hasReverse: boolean; // a parallel edge in the opposite direction exists: draw offset
  vehicles: string[]; // vehicles whose route uses this edge
}

export type RoadNode = Node<RoadNodeData, "road">;
export type RoadEdge = Edge<RoadEdgeData, "road">;

/** Pixels per scenario coordinate unit (km). Scenarios are synthetic: not geography. */
export const SCALE = 120;

export interface RouteOverlay {
  vehicleId: string;
  edgeIds: string[];
}

export interface FlowOptions {
  routes?: RouteOverlay[];
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  selectedVehicleId?: string | null;
}

export function trafficState(e: EdgeOut): TrafficState {
  if (e.closed) return "closed";
  if (e.base_time > 0 && e.current_time / e.base_time >= CONGESTION_RATIO) return "congested";
  return "normal";
}

/**
 * Convert a backend scenario (and optional backend routes) into React Flow elements.
 * Route membership comes only from the given edge ids: nothing is recomputed here.
 */
export function toFlow(
  scenario: ScenarioOut,
  opts: FlowOptions = {},
): { nodes: RoadNode[]; edges: RoadEdge[] } {
  const routes = opts.routes ?? [];
  const depotByNode = new Map(scenario.depots.map((d) => [d.node_id, d]));
  const customerByNode = new Map(scenario.customers.map((c) => [c.node_id, c]));
  const edgeById = new Map(scenario.graph.edges.map((e) => [e.id, e]));

  const vehiclesByEdge = new Map<string, string[]>();
  const routeNodes = new Set<string>();
  for (const r of routes) {
    for (const id of r.edgeIds) {
      const e = edgeById.get(id);
      if (!e) continue;
      const list = vehiclesByEdge.get(id) ?? [];
      if (!list.includes(r.vehicleId)) list.push(r.vehicleId);
      vehiclesByEdge.set(id, list);
      routeNodes.add(e.source).add(e.target);
    }
  }
  const pairs = new Set(scenario.graph.edges.map((e) => `${e.source}\u0000${e.target}`));

  const nodes: RoadNode[] = scenario.graph.nodes.map((n) => {
    const depot = depotByNode.get(n.id);
    const customer = customerByNode.get(n.id);
    return {
      id: n.id,
      type: "road",
      position: { x: (n.x ?? 0) * SCALE, y: (n.y ?? 0) * SCALE },
      draggable: false,
      data: {
        label: n.label ?? n.id,
        kind: depot ? "depot" : customer ? "customer" : "intersection",
        refId: depot?.id ?? customer?.id ?? null,
        demand: customer?.demand ?? null,
        onRoute: routeNodes.has(n.id),
        selected: opts.selectedNodeId === n.id,
      },
    };
  });

  const edges: RoadEdge[] = scenario.graph.edges
    .map((e): RoadEdge => {
      const vehicles = vehiclesByEdge.get(e.id) ?? [];
      const onRoute = vehicles.length > 0;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: "road",
        zIndex: onRoute ? 2 : e.closed ? 1 : 0,
        data: {
          edge: e,
          traffic: trafficState(e),
          onRoute,
          dimmed: !!opts.selectedVehicleId && onRoute && !vehicles.includes(opts.selectedVehicleId),
          selected: opts.selectedEdgeId === e.id,
          hasReverse: pairs.has(`${e.target}\u0000${e.source}`),
          vehicles,
        },
      };
    })
    // Route edges last so they paint above ordinary roads.
    .sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));

  return { nodes, edges };
}

/** Straight segment between two points, shifted perpendicular by `offset` pixels (to the
 * right of the direction of travel) so the two directions of a two-way road stay distinct. */
export function offsetSegment(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  offset: number,
): { x1: number; y1: number; x2: number; y2: number } {
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1;
  const ox = (-dy / len) * offset;
  const oy = (dx / len) * offset;
  return { x1: sx + ox, y1: sy + oy, x2: tx + ox, y2: ty + oy };
}
